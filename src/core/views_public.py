from dataclasses import dataclass

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods
from django_tenants.utils import schema_context

from app_tenants.models import Domain, TenantLogin, TenantLoginTicket


class IntoLoginForm(forms.Form):
    login = forms.CharField(label=_("Логин"), max_length=150)
    password = forms.CharField(
        label=_("Пароль"), max_length=128, widget=forms.PasswordInput
    )


@dataclass
class TenantTarget:
    schema_name: str
    domain: str
    tenant_username: str


def _lookup_tenant(login: str) -> TenantTarget | None:
    try:
        record = TenantLogin.objects.select_related("domain__tenant").get(
            login__iexact=login, is_active=True
        )
    except TenantLogin.DoesNotExist:
        return _lookup_tenant_by_scanning(login)
    tenant = record.domain.tenant
    return TenantTarget(
        schema_name=tenant.schema_name,
        domain=record.domain.domain,
        tenant_username=record.tenant_username,
    )


def _authenticate_in_schema(target: TenantTarget, password: str, request: HttpRequest):
    with schema_context(target.schema_name):
        return authenticate(request, username=target.tenant_username, password=password)


def _lookup_tenant_by_scanning(login: str) -> TenantTarget | None:
    """Fallback: iterate over tenant schemas and look for the login."""

    UserModel = get_user_model()
    normalized_login = login.strip()

    domains = (
        Domain.objects.select_related("tenant")
        .filter(is_primary=True)
        .exclude(tenant__schema_name="public")
    )

    for domain in domains:
        tenant = domain.tenant
        with schema_context(tenant.schema_name):
            try:
                user = UserModel.objects.get(
                    Q(username__iexact=normalized_login)
                    | Q(email__iexact=normalized_login)
                )
            except UserModel.DoesNotExist:
                continue
            except UserModel.MultipleObjectsReturned:
                continue
            else:
                return TenantTarget(
                    schema_name=tenant.schema_name,
                    domain=domain.domain,
                    tenant_username=user.get_username(),
                )
    return None


def _build_redirect_url(domain: str, request: HttpRequest, path: str) -> str:
    # пока у тебя тенанты работают по http (без https), можно оставить так:
    scheme = "http"

    # если потом сделаешь HTTPS для demo2.metisone.com — поменяешь на "https"
    # или вернёшь логику с is_secure(), но БЕЗ портов

    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{scheme}://{domain}{normalized_path}"


@require_http_methods(["GET", "POST"])
def into_login_view(request: HttpRequest) -> HttpResponse:
    form = IntoLoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        login = form.cleaned_data["login"]
        password = form.cleaned_data["password"]
        target = _lookup_tenant(login)
        if not target:
            form.add_error("login", _("Пользователь не найден"))
        else:
            user = _authenticate_in_schema(target, password, request)
            if user is None:
                form.add_error("password", _("Неверный пароль"))
            elif not user.is_active:
                form.add_error(None, _("Пользователь деактивирован"))
            else:
                backend_path = getattr(
                    user,
                    "backend",
                    settings.AUTHENTICATION_BACKENDS[0],
                )
                ticket = TenantLoginTicket.objects.issue(
                    schema_name=target.schema_name,
                    tenant_username=user.get_username(),
                    backend_path=backend_path,
                )
                messages.success(request, _("Успешный вход. Перенаправляем…"))
                sso_path = f"/sso/login/?token={ticket.token}"
                return redirect(
                    _build_redirect_url(target.domain, request, sso_path)
                )
    return render(request, "public/into_login.html", {"form": form})
