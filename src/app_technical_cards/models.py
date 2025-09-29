from django.db import models
from django.db.models import Sum, F, DecimalField
from django.db.models.functions import Coalesce


class TechnicalCard(models.Model):
    """
    Живая «голова» ТК (редактируемый черновик/эталон).
    Версии создаются снимками, и именно к версиям будут привязываться сметы.
    """

    name = models.CharField(
        max_length=255,
        db_index=True,
    )
    output_unit = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="ед. выпуска ТК (напр. 'м', 'м2')",
    )
    code = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
    )

    def __str__(self) -> str:
        return self.name

    @property
    def latest_version(self):
        return self.versions.order_by("-version").first()


class TechnicalCardVersion(models.Model):
    """
    НЕИЗМЕНЯЕМАЯ версия ТК (снапшот на момент фиксации).
    Сметы/группы используют только этот объект.
    """

    card = models.ForeignKey(
        TechnicalCard,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    version = models.PositiveIntegerField()  # 1,2,3,...
    name = models.CharField(
        max_length=255,
    )
    output_unit = models.CharField(
        max_length=32,
        blank=True,
        default="",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    is_published = models.BooleanField(
        default=True,
    )

    # Денормализованные агрегаты (на 1 ед. выпуска ТК):
    materials_cost_per_unit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )
    works_cost_per_unit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )
    total_cost_per_unit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )

    class Meta:
        unique_together = [("card", "version")]
        ordering = ["card_id", "-version"]
        verbose_name = "Версия техкарты"
        verbose_name_plural = "Версии техкарт"

    def __str__(self) -> str:
        return f"{self.card.name} v{self.version}"

    def recalc_totals(self, save=True):
        """Пересчитать агрегаты на 1 ед. выпуска ТК из строк состава."""
        m_sum = (
            self.material_items.annotate(
                line=Coalesce(F("qty_per_unit") * F("price_per_unit"), 0.0)
            ).aggregate(
                s=Coalesce(
                    Sum("line"),
                    0.0,
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            )[
                "s"
            ]
            or 0
        )
        w_sum = (
            self.work_items.annotate(
                line=Coalesce(F("qty_per_unit") * F("price_per_unit"), 0.0)
            ).aggregate(
                s=Coalesce(
                    Sum("line"),
                    0.0,
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            )[
                "s"
            ]
            or 0
        )
        self.materials_cost_per_unit = m_sum
        self.works_cost_per_unit = w_sum
        self.total_cost_per_unit = (m_sum or 0) + (w_sum or 0)
        if save:
            self.save(
                update_fields=[
                    "materials_cost_per_unit",
                    "works_cost_per_unit",
                    "total_cost_per_unit",
                ]
            )


# Пока ТК = перечень материалов и работ.
# Фиксируем состав в версиях ТК отдельными строками (снимок названия; позже добавим qty/unit/цены).
class TechnicalCardVersionMaterial(models.Model):
    technical_card_version = models.ForeignKey(
        TechnicalCardVersion, on_delete=models.CASCADE, related_name="material_items"
    )

    # связь на живой справочник + снапшоты атрибутов
    material = models.ForeignKey(
        "app_materials.Material",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="version_links",
    )
    material_name = models.CharField(max_length=255)  # снапшот названия
    unit = models.CharField(max_length=32, blank=True, default="")  # снапшот ед. изм.
    price_per_unit = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )  # снапшот цены/ед.

    # норма на 1 ед. выпуска ТК
    qty_per_unit = models.DecimalField(max_digits=16, decimal_places=6, default=0)

    order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Материал версии ТК"
        verbose_name_plural = "Материалы версии ТК"

    @property
    def line_cost_per_unit(self):
        if self.price_per_unit is None:
            return None
        return (self.price_per_unit or 0) * (self.qty_per_unit or 0)


class TechnicalCardVersionWork(models.Model):
    """Строка состава ТК (снапшот работы и цены на дату версии). Нормы на 1 ед. выпуска ТК."""

    technical_card_version = models.ForeignKey(
        TechnicalCardVersion,
        on_delete=models.CASCADE,
        related_name="work_items",
    )

    work = models.ForeignKey(
        "app_works.Work",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="version_links",
    )
    work_name = models.CharField(
        max_length=255,
    )
    unit = models.CharField(
        max_length=32,
        blank=True,
        default="",
    )
    price_per_unit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    qty_per_unit = models.DecimalField(
        max_digits=16,
        decimal_places=6,
        default=0,
    )

    order = models.PositiveIntegerField(
        default=0,
        db_index=True,
    )

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Работа версии ТК"
        verbose_name_plural = "Работы версии ТК"

    @property
    def line_cost_per_unit(self):
        if self.price_per_unit is None:
            return None
        return (self.price_per_unit or 0) * (self.qty_per_unit or 0)


# СИГНАЛЫ TODO
# Автоматический пересчёт агрегатов версии ТК при изменении состава
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


@receiver([post_save, post_delete], sender=TechnicalCardVersionMaterial)
@receiver([post_save, post_delete], sender=TechnicalCardVersionWork)
def _recalc_tc_totals(sender, instance, **kwargs):
    instance.technical_card_version.recalc_totals(save=True)
