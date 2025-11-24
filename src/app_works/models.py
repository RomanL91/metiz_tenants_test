"""
Справочник работ.

Назначение
---------
«Живой» каталог видов работ с базовыми полями: название, единица измерения,
расценка за единицу и признак активности. Историчность смет обеспечивается
снапшотами в версиях техкарт; значения в справочнике могут обновляться со временем.
"""

from decimal import Decimal

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
        default=0,
        blank=True,
        verbose_name=_("Расценка за единицу"),
        help_text=_("Текущая стоимость за 1 единицу измерения (живой справочник)."),
    )
    price_per_labor_hour = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        null=True,
        blank=True,
        verbose_name=_("Предварительная расценка за человеко-час"),
        help_text=_("Стоимость работы за один человеко-час."),
    )
    labor_hours = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        blank=True,
        verbose_name=_("Кол-во человеко-часов"),
        help_text=_("Нормативное количество человеко-часов на единицу работы."),
    )
    calculate_only_by_labor = models.BooleanField(
        default=False,
        verbose_name=_("Считать только по ЧЧ"),
        help_text=_(
            "Если включено, работа всегда рассчитывается по тарифу за человеко-час."
        ),
    )
    supplier_ref = models.ForeignKey(
        "app_suppliers.Supplier",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="works",
        verbose_name=_("Поставщик"),
        help_text=_("Справочник поставщиков."),
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
        def _gt_zero(value: Decimal | None) -> bool:
            return value is not None and Decimal(value) > 0
       
        if method == self.CostingMethod.LABOR:
            return self.unit_ref_id is not None and _gt_zero(self.price_per_unit)
        if self.calculate_only_by_labor:
            return False
        # По умолчанию считаем, что услуга доступна, если есть базовые поля
        return self.unit_ref_id is not None and _gt_zero(self.price_per_unit)

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
            price = self.price_per_labor_hour
        else:
            price = self.price_per_unit

        if price is None:
            return None

        price_dec = Decimal(price)
        return price_dec if price_dec > 0 else None

    def available_costing_methods(self) -> list[str]:
        methods: list[str] = []
        if self.supports_calculation_method(self.CostingMethod.SERVICE):
            methods.append(self.CostingMethod.SERVICE)
        if self.supports_calculation_method(self.CostingMethod.LABOR):
            methods.append(self.CostingMethod.LABOR)
        return methods
    
    def clean(self):
        super().clean()

        errors: dict[str, str] = {}

        price_unit = Decimal(self.price_per_unit or 0)
        price_labor = Decimal(self.price_per_labor_hour or 0)
        labor_hours = Decimal(self.labor_hours or 0)

        self.price_per_unit = price_unit
        self.price_per_labor_hour = price_labor
        self.labor_hours = labor_hours

        if price_unit <= 0 and price_labor <= 0:
            msg = _("Заполните хотя бы одну расценку: за единицу или за человеко-час.")
            errors["price_per_unit"] = msg
            errors["price_per_labor_hour"] = msg

        if self.calculate_only_by_labor and price_labor <= 0:
            errors["price_per_labor_hour"] = _(
                "Для расчёта только по человеко-часам нужна расценка за человеко-час."
            )

        if price_labor > 0 and labor_hours <= 0:
            errors["labor_hours"] = _(
                "Укажите количество человеко-часов для предварительной расценки."
            )

        if errors:
            raise ValidationError(errors)

