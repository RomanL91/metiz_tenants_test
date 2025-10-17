"""
Справочник материалов.

Назначение
---------
Держим «живой» каталог материалов (одно ключевое поле — name) для использования
в технических картах. Историчность смет обеспечивается за счёт снапшотов
в версиях техкарт; значения в этом справочнике могут обновляться со временем.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class Material(models.Model):
    """
    МАТЕРИАЛ — базовая сущность с одним главным полем name.
    Историчность смет обеспечивается на уровне версий техкарт (снапшоты),
    а здесь держим живой справочник материалов.
    """

    name = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name=_("Наименование"),
        help_text=_("Короткое понятное название материала."),
    )
    unit = models.CharField(
        max_length=32,
        verbose_name=_("Единица измерения"),
        help_text=_("Например: «м³», «м²», «шт», «кг»."),
    )
    price_per_unit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_("Цена за единицу"),
        help_text=_("Текущая цена за 1 единицу измерения (живой справочник)."),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Активен"),
        help_text=_("Снимите отметку, чтобы скрыть материал из выбора без удаления."),
    )

    class Meta:
        verbose_name = _("Материал")
        verbose_name_plural = _("Материалы")
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return self.name
