from datetime import timedelta

from django.db import models
from django.utils import timezone
from django.utils.crypto import get_random_string
from django_tenants.models import DomainMixin, TenantMixin


class Tenant(TenantMixin):
    name = models.CharField(max_length=100)


class Domain(DomainMixin):
    pass


class TenantLogin(models.Model):
    """Login that is shared across tenants for the public /into/ page."""

    login = models.CharField(
        max_length=150,
        unique=True,
        help_text="Логин, который вводит пользователь на общей странице входа",
    )
    tenant_username = models.CharField(
        max_length=150,
        help_text="Имя пользователя внутри tenant-схемы",
    )
    domain = models.ForeignKey(
        Domain,
        on_delete=models.CASCADE,
        related_name="login_accounts",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Кросс-tenant аккаунт"
        verbose_name_plural = "Кросс-tenant аккаунты"

    def __str__(self) -> str:  # pragma: no cover - string repr only
        return f"{self.login} → {self.domain}"


class TenantLoginTicketManager(models.Manager):
    def issue(
        self,
        *,
        schema_name: str,
        tenant_username: str,
        backend_path: str,
        redirect_to: str = "/ru/admin/",
        ttl: timedelta = timedelta(minutes=2),
    ) -> "TenantLoginTicket":
        token = get_random_string(48)
        expires_at = timezone.now() + ttl
        return self.create(
            token=token,
            schema_name=schema_name,
            tenant_username=tenant_username,
            backend_path=backend_path,
            redirect_to=redirect_to,
            expires_at=expires_at,
        )


class TenantLoginTicket(models.Model):
    token = models.CharField(max_length=96, unique=True)
    schema_name = models.CharField(max_length=63)
    tenant_username = models.CharField(max_length=150)
    backend_path = models.CharField(max_length=255)
    redirect_to = models.CharField(max_length=255, default="/ru/admin/")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    objects = TenantLoginTicketManager()

    class Meta:
        verbose_name = "SSO-токен входа"
        verbose_name_plural = "SSO-токены входа"

    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at