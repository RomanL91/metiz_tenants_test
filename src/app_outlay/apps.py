from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AppOutlayConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "app_outlay"
    verbose_name = _("Справочник Смет")

    def ready(self):
        import app_outlay.signals
