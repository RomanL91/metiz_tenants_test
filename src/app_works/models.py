"""
Справочник работ.

Назначение
---------
«Живой» каталог видов работ с базовыми полями: название, единица измерения,
расценка за единицу и признак активности. Историчность смет обеспечивается
снапшотами в версиях техкарт; значения в справочнике могут обновляться со временем.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from app_units.models import Unit


class Work(models.Model):
    """
    РАБОТА — базовая сущность с одним главным полем name.
    Детали (категория, трудозатраты, разряды) можно добавить по мере проектирования.
    """

    class CostingMethod(models.TextChoices):
        SERVICE = "service", _("Услуга")
        LABOR = "labor", _("Человеко-часы")

    name = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name=_("Наименование работы"),
        help_text=_("Короткое понятное название работы."),
    )
    unit_ref = models.ForeignKey(
        Unit,
        verbose_name=_("Единица измерения"),
        help_text=_("Выберите из справочника"),
        on_delete=models.PROTECT,
        related_name="works",
    )
    price_per_unit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_("Расценка за единицу"),
        help_text=_("Текущая стоимость за 1 единицу измерения (живой справочник)."),
    )
    price_per_labor_hour = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Расценка за человеко-час"),
        help_text=_("Стоимость работы за один человеко-час."),
    )
    calculate_only_by_labor = models.BooleanField(
        default=False,
        verbose_name=_("Считать только по ЧЧ"),
        help_text=_(
            "Если включено, работа всегда рассчитывается по тарифу за человеко-час."
        ),
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

    # ====== Утилиты расчёта ======
    def supports_calculation_method(self, method: str) -> bool:
        if method == self.CostingMethod.LABOR:
            return self.price_per_labor_hour is not None
        if self.calculate_only_by_labor:
            return False
        # По умолчанию считаем, что услуга доступна, если есть базовые поля
        return self.unit_ref_id is not None and self.price_per_unit is not None

    def resolve_calculation_method(self, requested: str | None = None) -> str:
        """Подбирает корректный метод расчёта для работы."""

        requested_code = (requested or "").strip()
        if requested_code and requested_code not in self.CostingMethod.values:
            requested_code = ""

        if self.calculate_only_by_labor:
            requested_code = self.CostingMethod.LABOR

        if requested_code:
            if self.supports_calculation_method(requested_code):
                return requested_code
            method_label = dict(self.CostingMethod.choices).get(
                requested_code, requested_code
            )
            raise ValidationError(
                _('Работа "{name}" не поддерживает метод расчёта "{method}".').format(
                    name=self.name, method=method_label
                )
            )

        for fallback in (self.CostingMethod.SERVICE, self.CostingMethod.LABOR):
            if self.supports_calculation_method(fallback):
                return fallback

        raise ValidationError(
            _('Работа "{name}" не имеет доступных методик расчёта.').format(
                name=self.name
            )
        )

    def get_unit_for_method(self, method: str) -> Unit | None:
        return self.unit_ref

    def get_price_for_method(self, method: str):
        if method == self.CostingMethod.LABOR:
            return self.price_per_labor_hour
        return self.price_per_unit

    def available_costing_methods(self) -> list[str]:
        methods: list[str] = []
        if self.supports_calculation_method(self.CostingMethod.SERVICE):
            methods.append(self.CostingMethod.SERVICE)
        if self.supports_calculation_method(self.CostingMethod.LABOR):
            methods.append(self.CostingMethod.LABOR)
        return methods
