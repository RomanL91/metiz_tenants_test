from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AppOverheadCostsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "app_overhead_costs"
    verbose_name = _("Накладные расходы")
