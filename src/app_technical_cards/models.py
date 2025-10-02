from django.db import models
from django.db.models import Sum, F, DecimalField
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


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
    output_unit = models.CharField(
        max_length=32,
        blank=True,
        default="",
        verbose_name=_("Ед. выпуска"),
        help_text=_("ед. выпуска ТК (напр. 'м', 'м2')"),
    )

    class Meta:
        verbose_name = _("Техкарта")
        verbose_name_plural = _("Техкарты")

    def __str__(self) -> str:
        return self.name

    @property
    def latest_version(self):
        return self.versions.order_by("-created_at").first()

    def create_version(self, user=None):
        """
        Создать новую версию ТК.
        Версия автоматически генерируется на основе даты/времени.
        """
        # Генерируем версию: YYYYMMDD-HHMMSS
        version_string = timezone.now().strftime("%Y%m%d-%H%M%S")

        new_version = TechnicalCardVersion.objects.create(
            card=self,
            version=version_string,
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

    # Версия генерируется автоматически: YYYYMMDD-HHMMSS или просто created_at
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

    # Денормализованные агрегаты (на 1 ед. выпуска ТК):
    materials_cost_per_unit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Стоимость материалов за ед."),
    )
    works_cost_per_unit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Стоимость работ за ед."),
    )
    total_cost_per_unit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Общая стоимость за ед."),
    )

    class Meta:
        unique_together = [("card", "version")]
        ordering = ["card_id", "-created_at"]
        verbose_name = _("Версия техкарты")
        verbose_name_plural = _("Версии техкарт")

    def __str__(self) -> str:
        return f"{self.card.name} [{self.version}]"

    def save(self, *args, **kwargs):
        """Автоматически генерируем версию если её нет."""
        if not self.version:
            self.version = timezone.now().strftime("%Y%m%d-%H%M%S")
        super().save(*args, **kwargs)

    # Свойства для удобного доступа к данным карточки
    @property
    def name(self):
        """Название берётся из родительской карточки."""
        return self.card.name

    @property
    def output_unit(self):
        """Единица выпуска берётся из родительской карточки."""
        return self.card.output_unit

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

    # Связь на живой справочник - ОСНОВНОЕ ПОЛЕ для редактирования
    material = models.ForeignKey(
        "app_materials.Material",
        on_delete=models.PROTECT,
        verbose_name=_("Материал"),
        help_text=_("Выберите материал из справочника"),
    )

    # СНАПШОТЫ (заполняются автоматически из material при сохранении)
    material_name = models.CharField(
        max_length=255,
        verbose_name=_("Название (снапшот)"),
        editable=False,  # Не показывать в формах
        help_text=_("Заполняется автоматически"),
    )
    unit = models.CharField(
        max_length=32,
        blank=True,
        default="",
        verbose_name=_("Ед. изм. (снапшот)"),
        editable=False,
    )
    price_per_unit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Цена за ед. (снапшот)"),
        editable=False,
    )

    # Норма расхода на 1 ед. выпуска ТК - ЕДИНСТВЕННОЕ редактируемое поле
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
        return f"{self.material_name} ({self.qty_per_unit} {self.unit})"

    def save(self, *args, **kwargs):
        """Автоматически копируем данные из справочника Material."""
        if self.material:
            self.material_name = self.material.name
            self.unit = self.material.unit
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

    # Связь на живой справочник - ОСНОВНОЕ ПОЛЕ для редактирования
    work = models.ForeignKey(
        "app_works.Work",
        on_delete=models.PROTECT,
        verbose_name=_("Работа"),
        help_text=_("Выберите работу из справочника"),
    )

    # СНАПШОТЫ (заполняются автоматически из work при сохранении)
    work_name = models.CharField(
        max_length=255,
        verbose_name=_("Название (снапшот)"),
        editable=False,
        help_text=_("Заполняется автоматически"),
    )
    unit = models.CharField(
        max_length=32,
        blank=True,
        default="",
        verbose_name=_("Ед. изм. (снапшот)"),
        editable=False,
    )
    price_per_unit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Цена за ед. (снапшот)"),
        editable=False,
    )

    # Норма трудозатрат на 1 ед. выпуска ТК - ЕДИНСТВЕННОЕ редактируемое поле
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
        return f"{self.work_name} ({self.qty_per_unit} {self.unit})"

    def save(self, *args, **kwargs):
        """Автоматически копируем данные из справочника Work."""
        if self.work:
            self.work_name = self.work.name
            self.unit = self.work.unit
            self.price_per_unit = self.work.price_per_unit
        super().save(*args, **kwargs)

    @property
    def line_cost_per_unit(self):
        """Стоимость строки на 1 ед. выпуска ТК."""
        if self.price_per_unit is None:
            return None
        return (self.price_per_unit or 0) * (self.qty_per_unit or 0)


# СИГНАЛЫ
# Автоматический пересчёт агрегатов версии ТК при изменении состава
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


@receiver([post_save, post_delete], sender=TechnicalCardVersionMaterial)
@receiver([post_save, post_delete], sender=TechnicalCardVersionWork)
def _recalc_tc_totals(sender, instance, **kwargs):
    """Автоматически пересчитываем итоги версии при изменении строк."""
    instance.technical_card_version.recalc_totals(save=True)
