"""
Справочник работ.

Назначение
---------
«Живой» каталог видов работ с базовыми полями: название, единица измерения,
расценка за единицу и признак активности. Историчность смет обеспечивается
снапшотами в версиях техкарт; значения в справочнике могут обновляться со временем.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class Work(models.Model):
    """
    РАБОТА — базовая сущность с одним главным полем name.
    Детали (категория, трудозатраты, разряды) можно добавить по мере проектирования.
    """

    name = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name=_("Наименование работы"),
        help_text=_("Короткое понятное название работы."),
    )
    unit = models.CharField(
        max_length=32,
        verbose_name=_("Единица измерения"),
        help_text=_("Например: «чел·ч», «м²», «п.м.»."),
    )
    price_per_unit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_("Расценка за единицу"),
        help_text=_("Текущая стоимость за 1 единицу измерения (живой справочник)."),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Активна"),
        help_text=_("Снимите отметку, чтобы скрыть работу из выбора без удаления."),
    )

    class Meta:
        verbose_name = _("Работа")
        verbose_name_plural = _("Работы")
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return self.name
