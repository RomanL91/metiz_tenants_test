from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AppUnitsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "app_units"
    verbose_name = _("Справочник единиц измерения")
