from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.db import connection, transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET
from django_tenants.utils import schema_context

from app_tenants.models import TenantLoginTicket


@require_GET
def tenant_sso_login_view(request: HttpRequest) -> HttpResponse:
    token = request.GET.get("token")
    default_redirect = "/ru/admin/login/"
    if not token:
        messages.error(request, _("Отсутствует токен SSO"))
        return redirect(default_redirect)

    ticket_payload: dict | None = None
    error_message: str | None = None

    current_schema = connection.schema_name

    with schema_context("public"):
        with transaction.atomic():
            ticket = (
                TenantLoginTicket.objects.select_for_update()
                .filter(token=token)
                .first()
            )
            if ticket is None:
                error_message = _("Ссылка для входа больше не действительна")
            elif ticket.schema_name != current_schema:
                error_message = _("Токен предназначен для другого арендатора")
            elif ticket.is_expired():
                error_message = _("Срок действия токена истёк")
                ticket.delete()
            else:
                ticket_payload = {
                    "tenant_username": ticket.tenant_username,
                    "backend_path": ticket.backend_path,
                    "redirect_to": ticket.redirect_to,
                }
                ticket.delete()

    if error_message:
        messages.error(request, error_message)
        return redirect(default_redirect)

    assert ticket_payload is not None
    redirect_to = ticket_payload["redirect_to"] or "/"
    backend_path = ticket_payload["backend_path"]

    UserModel = get_user_model()
    try:
        user = UserModel.objects.get(username=ticket_payload["tenant_username"])
    except UserModel.DoesNotExist:
        messages.error(request, _("Пользователь не найден"))
        return redirect(default_redirect)

    login(request, user, backend=backend_path)
    messages.success(request, _("Добро пожаловать!"))
    return redirect(redirect_to)
