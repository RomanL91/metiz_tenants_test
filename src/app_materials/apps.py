from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AppMaterialsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "app_materials"
    verbose_name = _("Справочник материалов")
