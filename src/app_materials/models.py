from decimal import Decimal, ROUND_HALF_UP

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator  # ← NEW
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
        verbose_name=_("Цена за единицу (без НДС)"),
        help_text=_("Текущая цена за 1 единицу измерения (живой справочник)."),
    )

    supplier_ref = models.ForeignKey(
        "app_suppliers.Supplier",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="materials",
        verbose_name=_("Поставщик"),
        help_text=_("Справочник поставщиков."),
    )
    vat_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("НДС, %"),
        help_text=_(
            "Ставка НДС в процентах, например 12.00; оставьте пустым, если не задано."
        ),
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

    def get_effective_vat_percent(self) -> Decimal:
        """
        Возвращает эффективную ставку НДС в %, если задана, иначе 0.
        (Легко расширить: можно учитывать дефолтную ставку от поставщика,
        если появится в модели поставщика.)
        """
        return (
            Decimal(self.vat_percent) if self.vat_percent is not None else Decimal("0")
        )

    def price_with_vat(self) -> Decimal:
        """
        Цена за единицу С НДС, округление до копеек (0.01, банковское округление).
        """
        price = Decimal(self.price_per_unit or 0)
        vat = self.get_effective_vat_percent()
        total = price * (Decimal("1") + vat / Decimal("100"))
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def vat_amount(self) -> Decimal:
        """
        Сумма НДС на единицу (удобно для вывода/аналитики).
        """
        return (self.price_with_vat() - Decimal(self.price_per_unit or 0)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
