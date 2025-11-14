import json
import secrets
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django_tenants.utils import (get_public_schema_name, get_tenant_model,
                                  schema_context)

# Опциональный proxy Role (если есть, можно назначать роли владельцу/тест-пользователям)
try:
    from app_users.models import Role
except Exception:  # pragma: no cover
    Role = None  # type: ignore


class Command(BaseCommand):
    help = (
        "Seed tenants from a JSON file located next to this command by default. "
        "Ensures Tenant, Domain and schema exist; creates owner user per tenant (except public). "
        "Optionally creates two extra test users."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default=None,
            help="Path to JSON. Default: tenants_seed.json next to this command file.",
        )
        parser.add_argument(
            "--base-domain",
            default=None,
            help="Override BASE_DOMAIN (otherwise uses settings.BASE_DOMAIN or 'localhost').",
        )
        parser.add_argument(
            "--reset-owner-password",
            action="store_true",
            help="If owner users already exist, reset their password to the JSON value.",
        )
        parser.add_argument(
            "--create-test-users",
            action="store_true",
            help="Also create two test users per tenant (not in public).",
        )
        parser.add_argument(
            "--test-password",
            default=None,
            help="Password for both test users; if omitted, generates random.",
        )
        parser.add_argument(
            "--role-owner",
            default=None,
            help="Optional role name to assign to the owner (proxy to Group).",
        )
        parser.add_argument(
            "--role-test1",
            default=None,
            help="Optional role for first test user (test_admin).",
        )
        parser.add_argument(
            "--role-test2",
            default=None,
            help="Optional role for second test user (test_user).",
        )

    # -------- main --------
    def handle(self, *args, **opts):
        json_path = opts["file"] or Path(__file__).with_name("tenants_seed.json")
        json_path = Path(json_path)

        if not json_path.exists():
            raise CommandError(f"JSON not found: {json_path}")

        base_domain = (
            opts["base_domain"] or getattr(settings, "BASE_DOMAIN", None) or "localhost"
        )

        with open(json_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                raise CommandError(f"Invalid JSON: {e}") from e

        if not isinstance(data, list):
            raise CommandError("Root of JSON must be a list of tenants")

        for item in data:
            self._process_tenant_item(item, base_domain, opts)

        self.stdout.write(self.style.SUCCESS("✅ Seeding finished"))

    # -------- per-tenant processing --------
    def _process_tenant_item(self, item: dict, base_domain: str, opts: dict):
        schema_name = item.get("schema_name")
        name = item.get("name") or schema_name
        subdomain = item.get("subdomain", "")
        owner = item.get("owner", None)

        if not schema_name:
            self.stderr.write(self.style.ERROR("Skipping item without 'schema_name'"))
            return

        domain_str = f"{subdomain}.{base_domain}" if subdomain else base_domain

        tenant = self._ensure_tenant_and_schema(schema_name, name, domain_str)

        # Создание владельца: пропускаем public, т.к. в public нет auth-таблиц
        if schema_name == get_public_schema_name():
            self.stdout.write(f"public: ensured (domain={domain_str}); owner skipped")
        else:
            if owner:
                self._ensure_owner(schema_name, owner, opts)
            if opts.get("create_test_users"):
                self._create_test_users(schema_name, opts)

        self.stdout.write(self.style.SUCCESS(f"✓ {schema_name}: ok ({domain_str})"))

    # -------- ensure tenant/domain/schema in public --------
    def _ensure_tenant_and_schema(self, schema: str, tenant_name: str, domain_str: str):
        TenantModel = get_tenant_model()
        DomainModel = apps.get_model("app_tenants", "Domain")

        with schema_context(get_public_schema_name()):
            tenant, created = TenantModel.objects.get_or_create(
                schema_name=schema,
                defaults={"name": tenant_name},
            )
            if created:
                tenant.save()
                tenant.create_schema(check_if_exists=True)
            else:
                tenant.create_schema(check_if_exists=True)

            dom, d_created = DomainModel.objects.get_or_create(
                domain=domain_str,
                defaults={"tenant": tenant, "is_primary": True},
            )
            if not d_created and dom.tenant_id != tenant.id:
                raise CommandError(
                    f"Domain '{domain_str}' is already attached to another tenant."
                )
        return tenant

    # -------- ensure owner in tenant schema --------
    def _ensure_owner(self, schema: str, owner: dict, opts: dict):
        username = owner.get("username")
        email = owner.get("email") or username
        password = owner.get("password") or self._gen_password()
        reset = bool(opts.get("reset_owner_password"))
        role_owner = opts.get("role_owner")

        if not username:
            self.stderr.write(
                self.style.WARNING(f"[{schema}] owner without username — skipped")
            )
            return

        with schema_context(schema):
            User = get_user_model()
            with transaction.atomic():
                u, created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        "email": email,
                        "is_active": True,
                        "is_staff": True,
                        "is_superuser": True,
                    },
                )
                if created or reset:
                    u.set_password(password)
                    u.save(update_fields=["password"])
                if role_owner and Role is not None:
                    r, _ = Role.objects.get_or_create(name=role_owner)
                    u.groups.add(r)

        if owner.get("password") is None:
            self.stdout.write(
                self.style.WARNING(f"[{schema}] Generated owner password: {password}")
            )

    # -------- create two test users in tenant schema --------
    def _create_test_users(self, schema: str, opts: dict):
        pwd = opts.get("test_password") or self._gen_password()
        role1 = opts.get("role_test1")
        role2 = opts.get("role_test2")

        with schema_context(schema):
            User = get_user_model()
            with transaction.atomic():
                # test_admin
                u1, c1 = User.objects.get_or_create(
                    username="test_admin",
                    defaults={
                        "email": f"test_admin@{schema}.local",
                        "is_active": True,
                        "is_staff": True,
                        "is_superuser": True,
                    },
                )
                if c1 or opts.get("test_password"):
                    u1.set_password(pwd)
                    u1.save(update_fields=["password"])
                if role1 and Role is not None:
                    r1, _ = Role.objects.get_or_create(name=role1)
                    u1.groups.add(r1)

                # test_user
                u2, c2 = User.objects.get_or_create(
                    username="test_user",
                    defaults={
                        "email": f"test_user@{schema}.local",
                        "is_active": True,
                        "is_staff": False,
                        "is_superuser": False,
                    },
                )
                if c2 or opts.get("test_password"):
                    u2.set_password(pwd)
                    u2.save(update_fields=["password"])
                if role2 and Role is not None:
                    r2, _ = Role.objects.get_or_create(name=role2)
                    u2.groups.add(r2)

        if not opts.get("test_password"):
            self.stdout.write(
                self.style.WARNING(f"[{schema}] Generated test users password: {pwd}")
            )

    @staticmethod
    def _gen_password(length: int = 14) -> str:
        return secrets.token_urlsafe(length)
