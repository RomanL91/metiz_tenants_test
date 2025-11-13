from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from app_units.models import Unit
from app_works.models import Work


class TechnicalCard(models.Model):
    """
    Живая «голова» ТК (редактируемый черновик/эталон).
    Версии создаются снимками, и именно к версиям будут привязываться сметы.
    """

    name = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name=_("Название"),
    )
    unit_ref = models.ForeignKey(
        Unit,
        verbose_name=_("Единица измерения"),
        help_text=_("Выберите из справочника"),
        on_delete=models.PROTECT,
        related_name="technicalcards",
    )

    # ========== НАДБАВКИ И РАСХОДЫ (в процентах) ==========
    materials_markup_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name=_("Надбавка на материалы (%)"),
        help_text=_("Например, 15.50 для 15.5%"),
    )
    works_markup_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name=_("Надбавка на работы (%)"),
        help_text=_("Например, 20.00 для 20%"),
    )
    transport_costs_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name=_("Транспортные расходы (%)"),
        help_text=_(
            "Применяется к чистой себестоимости материалов и работ (до надбавок)"
        ),
    )

    # ========== МАРЖИНАЛЬНОСТЬ (в процентах) ==========
    materials_margin_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name=_("Маржинальность материалов (%)"),
        help_text=_("Применяется к общей стоимости материалов"),
    )
    works_margin_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name=_("Маржинальность работ (%)"),
        help_text=_("Применяется к общей стоимости работ"),
    )

    class Meta:
        verbose_name = _("Техкарта")
        verbose_name_plural = _("Техкарты")

    def __str__(self) -> str:
        return f"{self.name} [{self.unit_ref}]"

    @property
    def latest_version(self):
        return self.versions.order_by("-created_at").first()

    def create_version(self, user=None):
        """
        Создать новую версию ТК.
        Версия автоматически генерируется на основе даты/времени.
        Все проценты копируются в версию как снапшот.
        """
        version_string = timezone.now().strftime("%Y%m%d-%H%M%S")

        new_version = TechnicalCardVersion.objects.create(
            card=self,
            version=version_string,
            # Копируем проценты как снапшот
            materials_markup_percent=self.materials_markup_percent,
            works_markup_percent=self.works_markup_percent,
            transport_costs_percent=self.transport_costs_percent,
            materials_margin_percent=self.materials_margin_percent,
            works_margin_percent=self.works_margin_percent,
        )

        return new_version


class TechnicalCardVersion(models.Model):
    """
    НЕИЗМЕНЯЕМАЯ версия ТК (снапшот на момент фиксации).
    Сметы/группы используют только этот объект.

    ВАЖНО: Версия НЕ хранит name и output_unit - они берутся из card.
    Версия идентифицируется по дате/времени создания.
    """

    card = models.ForeignKey(
        TechnicalCard,
        on_delete=models.CASCADE,
        related_name="versions",
        verbose_name=_("Техкарта"),
    )

    version = models.CharField(
        max_length=64,
        verbose_name=_("Версия"),
        help_text=_("Генерируется автоматически при создании"),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Дата создания"),
    )
    is_published = models.BooleanField(
        default=True,
        verbose_name=_("Опубликована"),
    )

    # ========== СНАПШОТЫ ПРОЦЕНТОВ из TechnicalCard ==========
    materials_markup_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name=_("Надбавка на материалы (%)"),
    )
    works_markup_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name=_("Надбавка на работы (%)"),
    )
    transport_costs_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name=_("Транспортные расходы (%)"),
    )
    materials_margin_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name=_("Маржинальность материалов (%)"),
    )
    works_margin_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name=_("Маржинальность работ (%)"),
    )

    # ========== СЕБЕСТОИМОСТЬ (базовая) ==========
    materials_cost_per_unit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Себестоимость материалов за ед."),
    )
    works_cost_per_unit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Себестоимость работ за ед."),
    )
    total_cost_per_unit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Общая себестоимость за ед."),
    )

    # ========== ОБЩАЯ СТОИМОСТЬ (с надбавками + транспорт) ==========
    materials_total_cost_per_unit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Общая стоимость материалов за ед."),
        help_text=_("С учетом надбавок и транспорта"),
    )
    works_total_cost_per_unit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Общая стоимость работ за ед."),
        help_text=_("С учетом надбавок и транспорта"),
    )
    total_cost_with_markups_per_unit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Общая стоимость техкарты за ед."),
        help_text=_("Материалы + работы с надбавками и транспортом"),
    )

    # ========== ЦЕНА ПРОДАЖИ (с маржинальностью) ==========
    materials_sale_price_per_unit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Цена продажи материалов за ед."),
        help_text=_("С учетом маржинальности"),
    )
    works_sale_price_per_unit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Цена продажи работ за ед."),
        help_text=_("С учетом маржинальности"),
    )
    total_sale_price_per_unit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Цена продажи техкарты за ед."),
        help_text=_("Итоговая цена продажи"),
    )

    class Meta:
        unique_together = [("card", "version")]
        ordering = ["card_id", "-created_at"]
        verbose_name = _("Версия техкарты")
        verbose_name_plural = _("Версии техкарт")

    def __str__(self) -> str:
        return f"{self.card.name} [{self.version}]"

    def save(self, *args, **kwargs):
        """Автоматически генерируем версию и копируем проценты если это новая версия."""
        is_new = not self.pk

        if not self.version:
            self.version = timezone.now().strftime("%Y%m%d-%H%M%S")

        # Если это новая версия И проценты не установлены, копируем из техкарты
        if is_new and self.card_id:
            if self.materials_markup_percent == 0 and self.works_markup_percent == 0:
                self.materials_markup_percent = self.card.materials_markup_percent
                self.works_markup_percent = self.card.works_markup_percent
                self.transport_costs_percent = self.card.transport_costs_percent
                self.materials_margin_percent = self.card.materials_margin_percent
                self.works_margin_percent = self.card.works_margin_percent

        super().save(*args, **kwargs)

    @property
    def name(self):
        """Название берётся из родительской карточки."""
        return self.card.name

    @property
    def output_unit(self):
        """Единица выпуска берётся из родительской карточки."""
        return str(self.card.unit_ref)

    def recalc_totals(self, save: bool = True) -> dict:
        """
        Пересчитывает и (опционально) сохраняет все агрегаты версии:
        - себестоимость (materials/works/total)
        - общая стоимость с надбавками и транспортом
        - цена продажи с маржинальностью
        Возвращает словарь с подсчитанными суммами.
        """
        TWO = Decimal("0.01")
        ONE = Decimal("1")

        # 1) СЕБЕСТОИМОСТЬ (по снапшот-ценам версии)
        mats_sum = sum(
            (
                (
                    Decimal(row.qty_per_unit or 0) * Decimal(row.price_per_unit or 0)
                ).quantize(TWO, ROUND_HALF_UP)
                for row in self.material_items.all()
            ),
            Decimal("0"),
        )
        works_sum = sum(
            (
                (
                    Decimal(row.qty_per_unit or 0) * Decimal(row.price_per_unit or 0)
                ).quantize(TWO, ROUND_HALF_UP)
                for row in self.work_items.all()
            ),
            Decimal("0"),
        )

        total_cost = (mats_sum + works_sum).quantize(TWO, ROUND_HALF_UP)

        # 2) ПРОЦЕНТЫ (в доли)
        m_markup = Decimal(self.materials_markup_percent or 0) / Decimal("100")
        w_markup = Decimal(self.works_markup_percent or 0) / Decimal("100")
        transport = Decimal(self.transport_costs_percent or 0) / Decimal("100")
        m_margin = Decimal(self.materials_margin_percent or 0) / Decimal("100")
        w_margin = Decimal(self.works_margin_percent or 0) / Decimal("100")

        # 3) ОБЩАЯ СТОИМОСТЬ (с надбавками + транспорт)
        mats_marked = (mats_sum * (ONE + m_markup + transport)).quantize(
            TWO, ROUND_HALF_UP
        )
        works_marked = (works_sum * (ONE + w_markup + transport)).quantize(
            TWO, ROUND_HALF_UP
        )
        total_marked = (mats_marked + works_marked).quantize(TWO, ROUND_HALF_UP)

        # 4) ЦЕНА ПРОДАЖИ (с маржей)
        mats_sale = (mats_marked * (ONE + m_margin)).quantize(TWO, ROUND_HALF_UP)
        works_sale = (works_marked * (ONE + w_margin)).quantize(TWO, ROUND_HALF_UP)
        total_sale = (mats_sale + works_sale).quantize(TWO, ROUND_HALF_UP)

        # 5) Записываем ровно в ВАШИ поля (они уже есть в модели)
        self.materials_cost_per_unit = mats_sum
        self.works_cost_per_unit = works_sum
        self.total_cost_per_unit = total_cost

        self.materials_total_cost_per_unit = mats_marked
        self.works_total_cost_per_unit = works_marked
        self.total_cost_with_markups_per_unit = total_marked

        self.materials_sale_price_per_unit = mats_sale
        self.works_sale_price_per_unit = works_sale
        self.total_sale_price_per_unit = total_sale

        if save:
            self.save(
                update_fields=[
                    "materials_cost_per_unit",
                    "works_cost_per_unit",
                    "total_cost_per_unit",
                    "materials_total_cost_per_unit",
                    "works_total_cost_per_unit",
                    "total_cost_with_markups_per_unit",
                    "materials_sale_price_per_unit",
                    "works_sale_price_per_unit",
                    "total_sale_price_per_unit",
                ]
            )

        return {
            "cost": {"materials": mats_sum, "works": works_sum, "total": total_cost},
            "marked": {
                "materials": mats_marked,
                "works": works_marked,
                "total": total_marked,
            },
            "sale": {"materials": mats_sale, "works": works_sale, "total": total_sale},
        }


class TechnicalCardVersionMaterial(models.Model):
    """
    Строка материала в версии ТК (снапшот материала на момент создания версии).

    АВТОМАТИЗАЦИЯ: material_name, unit, price_per_unit автоматически
    копируются из справочника Material при сохранении.
    """

    technical_card_version = models.ForeignKey(
        TechnicalCardVersion,
        on_delete=models.CASCADE,
        related_name="material_items",
        verbose_name=_("Версия ТК"),
    )

    material = models.ForeignKey(
        "app_materials.Material",
        on_delete=models.PROTECT,
        verbose_name=_("Материал"),
        help_text=_("Выберите материал из справочника"),
    )

    # СНАПШОТЫ
    material_name = models.CharField(
        max_length=255,
        verbose_name=_("Название (снапшот)"),
        editable=False,
        help_text=_("Заполняется автоматически"),
    )
    unit_ref = models.ForeignKey(
        Unit,
        verbose_name=_("Единица измерения"),
        help_text=_("Выберите из справочника"),
        on_delete=models.PROTECT,
        related_name="tecnicalcardversmaterials",
    )
    price_per_unit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Цена за ед. (снапшот)"),
        editable=False,
    )

    qty_per_unit = models.DecimalField(
        max_digits=16,
        decimal_places=6,
        default=0,
        verbose_name=_("Количество на 1 ед. выпуска"),
    )

    order = models.PositiveIntegerField(
        default=0,
        db_index=True,
        verbose_name=_("Порядок"),
    )

    class Meta:
        ordering = ["order", "id"]
        verbose_name = _("Материал версии ТК")
        verbose_name_plural = _("Материалы версии ТК")

    def __str__(self):
        return f"{self.material_name} ({self.qty_per_unit} {self.unit_ref})"

    def save(self, *args, **kwargs):
        """Автоматически копируем данные из справочника Material."""
        if self.material:
            self.material_name = self.material.name
            self.unit_ref = self.material.unit_ref
            self.price_per_unit = self.material.price_per_unit
        super().save(*args, **kwargs)

    @property
    def line_cost_per_unit(self):
        """Стоимость строки на 1 ед. выпуска ТК."""
        if self.price_per_unit is None:
            return None
        return (self.price_per_unit or 0) * (self.qty_per_unit or 0)


class TechnicalCardVersionWork(models.Model):
    """
    Строка работы в версии ТК (снапшот работы на момент создания версии).

    АВТОМАТИЗАЦИЯ: work_name, unit, price_per_unit автоматически
    копируются из справочника Work при сохранении.
    """

    technical_card_version = models.ForeignKey(
        TechnicalCardVersion,
        on_delete=models.CASCADE,
        related_name="work_items",
        verbose_name=_("Версия ТК"),
    )

    work = models.ForeignKey(
        "app_works.Work",
        on_delete=models.PROTECT,
        verbose_name=_("Работа"),
        help_text=_("Выберите работу из справочника"),
    )
    calculation_method = models.CharField(
        max_length=16,
        choices=Work.CostingMethod.choices,
        default=Work.CostingMethod.SERVICE,
        verbose_name=_("Метод расчёта"),
        help_text=_("По какому методу фиксируем стоимость этой работы."),
    )

    # СНАПШОТЫ
    work_name = models.CharField(
        max_length=255,
        verbose_name=_("Название (снапшот)"),
        editable=False,
        help_text=_("Заполняется автоматически"),
    )
    unit_ref = models.ForeignKey(
        Unit,
        verbose_name=_("Единица измерения"),
        help_text=_("Выберите из справочника"),
        on_delete=models.PROTECT,
        related_name="tecnicalcardversworks",
    )
    price_per_unit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Цена за ед. (снапшот)"),
        editable=False,
    )

    qty_per_unit = models.DecimalField(
        max_digits=16,
        decimal_places=6,
        default=0,
        verbose_name=_("Количество на 1 ед. выпуска"),
    )

    order = models.PositiveIntegerField(
        default=0,
        db_index=True,
        verbose_name=_("Порядок"),
    )

    class Meta:
        ordering = ["order", "id"]
        verbose_name = _("Работа версии ТК")
        verbose_name_plural = _("Работы версии ТК")

    def __str__(self):
        return f"{self.work_name} ({self.qty_per_unit} {self.unit_ref})"

    def save(self, *args, **kwargs):
        """Автоматически копируем данные из справочника Work."""
        if self.work:
            method = self.work.resolve_calculation_method(self.calculation_method)
            self.calculation_method = method
            method_label = dict(Work.CostingMethod.choices).get(method, method)
            unit = self.work.get_unit_for_method(method)
            price = self.work.get_price_for_method(method)

            if unit is None or price is None:
                raise ValidationError(
                    _(
                        "Для метода '{method}' не заполнены обязательные данные работы."
                    ).format(
                        method=method_label,
                    )
                )

            self.work_name = self.work.name
            self.unit_ref = self.work.unit_ref
            self.price_per_unit = self.work.price_per_unit
            self.unit_ref = unit
            self.price_per_unit = price

        super().save(*args, **kwargs)

    @property
    def line_cost_per_unit(self):
        """Стоимость строки на 1 ед. выпуска ТК."""
        if self.price_per_unit is None:
            return None
        return (self.price_per_unit or 0) * (self.qty_per_unit or 0)


# СИГНАЛЫ
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver


@receiver([post_save, post_delete], sender=TechnicalCardVersionMaterial)
@receiver([post_save, post_delete], sender=TechnicalCardVersionWork)
def _recalc_tc_totals(sender, instance, **kwargs):
    """Автоматически пересчитываем итоги версии при изменении строк."""
    instance.technical_card_version.recalc_totals(save=True)
