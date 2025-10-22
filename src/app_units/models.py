from django.db import models
from django.utils.translation import gettext_lazy as _


class Unit(models.Model):
    # Держим максимально просто: символ уникален («м», «м²», «кг», «ч», «шт», «%»)
    symbol = models.CharField(
        _("Символ"),
        max_length=32,
        unique=True,
        db_index=True,
    )
    # Человеко-читаемое название (опционально)
    name = models.CharField(
        _("Название"),
        max_length=100,
        blank=True,
        default="",
    )
    is_active = models.BooleanField(
        _("Активна"),
        default=True,
    )

    class Meta:
        verbose_name = _("Единица измерения")
        verbose_name_plural = _("Единицы измерения")
        ordering = ["symbol", "id"]

    def __str__(self) -> str:
        return self.symbol
