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
