from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AppTechnicalCardsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "app_technical_cards"
    verbose_name = _("Справочник Технических карт")
