"""Модели «Сметы» (app_outlay).

Что хранится в модуле:
- Estimate — контейнер сметы (название, базовая валюта, связь с источником импорта и индекс листа Excel,
  по которому строилось превью).
- Group — группы/разделы сметы с произвольной вложенностью (parent → children) и порядком отображения.
- GroupTechnicalCardLink — привязка ЗАФИКСИРОВАННОЙ версии технической карты (TechnicalCardVersion) к группе сметы
  с указанием её количества выпуска. Итоговые суммы рассчитываются «на лету» на основе агрегатов версии ТК.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from decimal import Decimal


class Estimate(models.Model):
    name = models.CharField(
        _("Название сметы"),
        max_length=255,
        db_index=True,
        help_text=_(
            "Короткое наименование сметы (как будет отображаться в списках и заголовках)."
        ),
    )
    currency = models.CharField(
        _("Валюта сметы"),
        max_length=8,
        default="RUB",
        blank=True,
        help_text=_("Буквенный код валюты (ISO 4217), например: RUB, KZT, USD."),
    )
    source_file = models.ForeignKey(
        "app_estimate_imports.ImportedEstimateFile",
        verbose_name=_("Источник (импортированный файл)"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="derived_estimates",
        help_text=_(
            "От какого импортированного файла построена смета (для превью/трассировки)."
        ),
    )
    source_sheet_index = models.PositiveIntegerField(
        _("Индекс листа Excel"),
        null=True,
        blank=True,
        default=0,
        help_text=_(
            "Номер листа Excel, по которому строилось превью (0 — первый лист)."
        ),
    )

    class Meta:
        verbose_name = _("Смета")
        verbose_name_plural = _("Сметы")

    def __str__(self) -> str:
        return self.name

    @property
    def active_overhead_costs(self):
        """Активные накладные расходы для этой сметы."""
        return self.overhead_cost_links.filter(is_active=True).select_related(
            "overhead_cost_container"
        )

    @property
    def total_overhead_amount(self):
        """Общая сумма всех активных накладных расходов."""
        from decimal import Decimal

        total = sum(
            link.snapshot_total_amount or Decimal("0.00")
            for link in self.active_overhead_costs
        )
        return total

    def calculate_totals_with_overhead(
        self, base_materials: Decimal, base_works: Decimal
    ) -> dict:
        """
        Рассчитывает итоги с учётом накладных расходов.

        :param base_materials: Базовая сумма материалов из ТК
        :param base_works: Базовая сумма работ из ТК
        :return: dict с ключами:
            - base_materials: исходная сумма материалов
            - base_works: исходная сумма работ
            - base_total: исходная общая сумма
            - overhead_materials: доп. сумма на материалы от НР
            - overhead_works: доп. сумма на работы от НР
            - overhead_total: общая сумма НР
            - final_materials: итоговая сумма материалов
            - final_works: итоговая сумма работ
            - final_total: итоговая общая сумма
            - overhead_details: список деталей по каждому НР
        """

        # Базовые суммы
        result = {
            "base_materials": base_materials,
            "base_works": base_works,
            "base_total": base_materials + base_works,
            "overhead_materials": Decimal("0.00"),
            "overhead_works": Decimal("0.00"),
            "overhead_total": Decimal("0.00"),
            "overhead_details": [],
        }

        # Проходим по всем активным НР
        active_overheads = self.overhead_cost_links.filter(
            is_active=True
        ).select_related("overhead_cost_container")

        for link in active_overheads:
            # Берём снапшот суммы (зафиксированную при применении)
            total_amount = link.snapshot_total_amount or Decimal("0.00")

            # Берём снапшот процентов распределения
            mat_pct = link.snapshot_materials_percentage or Decimal("0.00")
            work_pct = link.snapshot_works_percentage or Decimal("0.00")

            # Рассчитываем распределение
            materials_part = total_amount * (mat_pct / Decimal("100.00"))
            works_part = total_amount * (work_pct / Decimal("100.00"))

            # Накапливаем
            result["overhead_materials"] += materials_part
            result["overhead_works"] += works_part
            result["overhead_total"] += total_amount

            # Сохраняем детали для вывода
            result["overhead_details"].append(
                {
                    "name": link.overhead_cost_container.name,
                    "total": total_amount,
                    "materials_part": materials_part,
                    "works_part": works_part,
                    "materials_pct": mat_pct,
                    "works_pct": work_pct,
                }
            )

        # Итоговые суммы с учётом НР
        result["final_materials"] = (
            result["base_materials"] + result["overhead_materials"]
        )
        result["final_works"] = result["base_works"] + result["overhead_works"]
        result["final_total"] = result["final_materials"] + result["final_works"]

        return result


class Group(models.Model):
    estimate = models.ForeignKey(
        Estimate,
        verbose_name=_("Смета"),
        on_delete=models.CASCADE,
        related_name="groups",
        help_text=_("К какой смете относится данная группа/раздел."),
    )
    parent = models.ForeignKey(
        "self",
        verbose_name=_("Родительская группа"),
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        help_text=_(
            "Если указано — группа будет вложенной (дочерней) относительно родительской."
        ),
    )
    name = models.CharField(
        _("Название группы"),
        max_length=255,
        help_text=_("Отображаемое название раздела/группы в смете."),
    )
    order = models.PositiveIntegerField(
        _("Порядок"),
        default=0,
        db_index=True,
        help_text=_(
            "Порядок сортировки групп внутри одной сметы/родителя (меньше — выше)."
        ),
    )

    class Meta:
        indexes = [models.Index(fields=["estimate", "order"])]
        ordering = ["order", "id"]
        verbose_name = _("Группа сметы")
        verbose_name_plural = _("Группы сметы")

    def __str__(self) -> str:
        return f"{self.name} (#{self.pk})"


class GroupTechnicalCardLink(models.Model):
    """
    В смете используется ЗАФИКСИРОВАННАЯ версия ТК + количество выпуска (в ед. output_unit версии ТК).
    Все итоговые суммы легко считаются на лету из агрегатов версии.
    """

    group = models.ForeignKey(
        Group,
        verbose_name=_("Группа сметы"),
        on_delete=models.CASCADE,
        related_name="techcard_links",
        help_text=_(
            "Раздел/группа сметы, к которой привязывается версия технической карты."
        ),
    )
    technical_card_version = models.ForeignKey(
        "app_technical_cards.TechnicalCardVersion",
        verbose_name=_("Версия технической карты"),
        on_delete=models.PROTECT,
        related_name="group_links",
        help_text=_("Зафиксированная версия ТК, используемая в расчётах сметы."),
    )

    quantity = models.DecimalField(
        _("Количество выпуска"),
        max_digits=16,
        decimal_places=3,
        default=1,
        help_text=_(
            "Сколько единиц выпуска ТК требуется по смете (в единицах output_unit версии ТК)."
        ),
    )
    order = models.PositiveIntegerField(
        _("Порядок"),
        default=0,
        db_index=True,
        help_text=_("Порядок сортировки ТК внутри группы (меньше — выше)."),
    )
    pinned_at = models.DateTimeField(
        _("Дата фиксации версии"),
        auto_now_add=True,
        help_text=_(
            "Когда именно версия ТК была зафиксирована (связь добавлена в смету)."
        ),
    )
    source_row_index = models.PositiveIntegerField(
        _("Индекс строки в источнике"),
        null=True,
        blank=True,
        help_text=_(
            "Номер строки в исходном Excel файле (для трассировки сопоставлений)."
        ),
    )

    class Meta:
        # unique_together = [("group", "technical_card_version")]
        ordering = ["order", "id"]
        verbose_name = _("ТК в группе сметы")
        verbose_name_plural = _("ТК в группах сметы")

    def __str__(self) -> str:
        return f"{self.group} → {self.technical_card_version}"

    # Удобные вычисляемые свойства для вывода «как в смете»
    @property
    def unit(self) -> str:
        return self.technical_card_version.output_unit or ""

    @property
    def unit_cost_materials(self):
        return self.technical_card_version.materials_cost_per_unit

    @property
    def unit_cost_works(self):
        return self.technical_card_version.works_cost_per_unit

    @property
    def unit_cost_total(self):
        return self.technical_card_version.total_cost_per_unit

    @property
    def total_cost_materials(self):
        return (self.unit_cost_materials or 0) * (self.quantity or 0)

    @property
    def total_cost_works(self):
        return (self.unit_cost_works or 0) * (self.quantity or 0)

    @property
    def total_cost(self):
        return (self.unit_cost_total or 0) * (self.quantity or 0)


class EstimateOverheadCostLink(models.Model):
    """
    Связь сметы с контейнером накладных расходов.
    Одна смета может иметь несколько контейнеров накладных расходов.
    """

    estimate = models.ForeignKey(
        Estimate,
        verbose_name=_("Смета"),
        on_delete=models.CASCADE,
        related_name="overhead_cost_links",
        help_text=_("Смета, к которой применяются накладные расходы."),
    )

    overhead_cost_container = models.ForeignKey(
        "app_overhead_costs.OverheadCostContainer",
        verbose_name=_("Контейнер накладных расходов"),
        on_delete=models.PROTECT,
        related_name="estimate_links",
        help_text=_("Контейнер накладных расходов, применяемый к смете."),
    )

    order = models.PositiveIntegerField(
        _("Порядок применения"),
        default=0,
        db_index=True,
        help_text=_(
            "Порядок применения накладных расходов (если важна последовательность)."
        ),
    )

    applied_at = models.DateTimeField(
        _("Дата применения"),
        auto_now_add=True,
        help_text=_("Когда контейнер был добавлен к смете."),
    )

    is_active = models.BooleanField(
        _("Активен"),
        default=True,
        help_text=_("Неактивные связи не учитываются в расчётах."),
    )

    # Снапшоты для истории (на момент применения)
    snapshot_total_amount = models.DecimalField(
        _("Сумма НР (снапшот)"),
        max_digits=16,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Общая сумма накладных расходов на момент применения."),
    )

    snapshot_materials_percentage = models.DecimalField(
        _("% на материалы (снапшот)"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Процент на материалы на момент применения."),
    )

    snapshot_works_percentage = models.DecimalField(
        _("% на работы (снапшот)"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Процент на работы на момент применения."),
    )

    class Meta:
        ordering = ["order", "id"]
        verbose_name = _("Накладные расходы в смете")
        verbose_name_plural = _("Накладные расходы в сметах")
        indexes = [
            models.Index(fields=["estimate", "order"]),
        ]

    def __str__(self) -> str:
        return f"{self.estimate.name} ← {self.overhead_cost_container.name}"

    def save(self, *args, **kwargs):
        """При сохранении автоматически создаём снапшоты."""
        if not self.pk or not self.snapshot_total_amount:
            # Создаём снапшоты только при первом сохранении
            self.snapshot_total_amount = self.overhead_cost_container.total_amount
            self.snapshot_materials_percentage = (
                self.overhead_cost_container.materials_percentage
            )
            self.snapshot_works_percentage = (
                self.overhead_cost_container.works_percentage
            )
        super().save(*args, **kwargs)

    @property
    def current_total_amount(self):
        """Текущая сумма контейнера (может отличаться от снапшота)."""
        return self.overhead_cost_container.total_amount

    @property
    def has_changes(self) -> bool:
        """Проверка: изменился ли контейнер с момента применения."""
        return (
            self.snapshot_total_amount != self.current_total_amount
            or self.snapshot_materials_percentage
            != self.overhead_cost_container.materials_percentage
            or self.snapshot_works_percentage
            != self.overhead_cost_container.works_percentage
        )
