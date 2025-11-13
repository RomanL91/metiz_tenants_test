"""Модели для управления накладными расходами.

Основные сущности:
- OverheadCostContainer — контейнер накладных расходов с настройкой распределения
- OverheadCostItem — статья расходов (налоги, зарплата, аренда и т.д.)
"""

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Sum
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _

from app_units.models import Unit


class OverheadCostContainer(models.Model):
    """
    Контейнер накладных расходов.
    Хранит общую сумму статей и настройки распределения на материалы/работы.
    """

    name = models.CharField(
        _("Название"),
        max_length=255,
        db_index=True,
        help_text=_("Например: 'Накладные расходы Q1 2025' или 'Стандартные НР'"),
    )

    description = models.TextField(
        _("Описание"),
        blank=True,
        default="",
        help_text=_("Дополнительная информация о составе накладных расходов"),
    )

    # Настройка распределения (в процентах)
    materials_percentage = models.DecimalField(
        _("% на материалы"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("30.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00")),
        ],
        help_text=_("Процент накладных расходов, распределяемый на материалы (0-100)"),
    )

    works_percentage = models.DecimalField(
        _("% на работы"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("70.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00")),
        ],
        help_text=_("Процент накладных расходов, распределяемый на работы (0-100)"),
    )

    is_active = models.BooleanField(
        _("Активен"),
        default=True,
        help_text=_("Неактивные контейнеры не доступны для применения к сметам"),
    )

    created_at = models.DateTimeField(
        _("Дата создания"),
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        _("Дата изменения"),
        auto_now=True,
    )

    class Meta:
        verbose_name = _("Контейнер накладных расходов")
        verbose_name_plural = _("Контейнеры накладных расходов")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        """Валидация: сумма процентов должна быть 100%"""
        from django.core.exceptions import ValidationError

        total = (self.materials_percentage or 0) + (self.works_percentage or 0)
        if total != 100:
            raise ValidationError(
                {
                    "materials_percentage": _(
                        "Сумма процентов материалов и работ должна равняться 100%"
                    ),
                    "works_percentage": _(
                        "Сумма процентов материалов и работ должна равняться 100%"
                    ),
                }
            )

    @property
    def total_amount(self) -> Decimal:
        """Общая сумма всех статей расходов"""

        total = self.items.aggregate(
            total=Coalesce(Sum(F("quantity") * F("price_per_unit")), Decimal("0.00"))
        )["total"]
        return total or Decimal("0.00")

    @property
    def items_count(self) -> int:
        """Количество статей расходов"""
        return self.items.count()


class OverheadCostItem(models.Model):
    """
    Статья накладных расходов.
    Может быть: налог, зарплата, аренда, транспорт, страхование и т.д.
    """

    container = models.ForeignKey(
        OverheadCostContainer,
        verbose_name=_("Контейнер"),
        on_delete=models.CASCADE,
        related_name="items",
    )

    name = models.CharField(
        _("Наименование статьи"),
        max_length=255,
        help_text=_("Например: 'НДС 20%', 'Зарплата администрации', 'Аренда офиса'"),
    )

    quantity = models.DecimalField(
        _("Количество"),
        max_digits=16,
        decimal_places=3,
        default=Decimal("1.000"),
        validators=[MinValueValidator(Decimal("0.001"))],
    )

    unit_ref = models.ForeignKey(
        Unit,
        verbose_name=_("Единица измерения"),
        help_text=_("Выберите из справочника"),
        on_delete=models.PROTECT,
        related_name="overheadcostitems",
    )

    price_per_unit = models.DecimalField(
        _("Цена за единицу"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    comment = models.TextField(
        _("Комментарий"),
        blank=True,
        default="",
        help_text=_("Дополнительная информация о статье расходов"),
    )

    order = models.PositiveIntegerField(
        _("Порядок"),
        default=0,
        db_index=True,
        help_text=_("Порядок отображения статей в контейнере"),
    )

    class Meta:
        verbose_name = _("Статья накладных расходов")
        verbose_name_plural = _("Статьи накладных расходов")
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return f"{self.name} ({self.total_cost})"

    @property
    def total_cost(self) -> Decimal:
        """Итоговая стоимость: количество × цена за единицу"""
        return (self.quantity or Decimal("0")) * (self.price_per_unit or Decimal("0"))
