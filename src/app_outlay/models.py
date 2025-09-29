from django.db import models


class Estimate(models.Model):
    name = models.CharField(
        max_length=255,
        db_index=True,
    )
    currency = models.CharField(
        max_length=8,
        default="RUB",
        blank=True,
    )

    def __str__(self) -> str:
        return self.name


class Group(models.Model):
    estimate = models.ForeignKey(
        Estimate, on_delete=models.CASCADE, related_name="groups"
    )
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )
    name = models.CharField(max_length=255)
    order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["estimate", "order"])]
        ordering = ["order", "id"]
        verbose_name = "Группа сметы"
        verbose_name_plural = "Группы сметы"

    def __str__(self) -> str:
        return f"{self.name} (#{self.pk})"


class GroupTechnicalCardLink(models.Model):
    """
    В смете используется ЗАФИКСИРОВАННАЯ версия ТК + количество выпуска (в ед. output_unit версии ТК).
    Все итоговые суммы легко считаются на лету из агрегатов версии.
    """

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="techcard_links",
    )
    technical_card_version = models.ForeignKey(
        "app_technical_cards.TechnicalCardVersion",
        on_delete=models.PROTECT,
        related_name="group_links",
    )

    quantity = models.DecimalField(
        max_digits=16,
        decimal_places=3,
        default=1,
    )  # сколько единиц выпуска ТК нужно по смете
    order = models.PositiveIntegerField(
        default=0,
        db_index=True,
    )
    pinned_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        unique_together = [("group", "technical_card_version")]
        ordering = ["order", "id"]
        verbose_name = "ТК в группе сметы"
        verbose_name_plural = "ТК в группах сметы"

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
