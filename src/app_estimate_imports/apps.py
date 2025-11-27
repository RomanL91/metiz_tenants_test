from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AppEstimateImportsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "app_estimate_imports"
    verbose_name = _("Импорт EXCEL | Разметка")
