from django.db import models


class Estimate(models.Model):
    name = models.CharField(max_length=255, db_index=True)

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

    def __str__(self) -> str:
        return f"{self.name} (#{self.pk})"


class GroupTechnicalCardLink(models.Model):
    """
    В смете/группе мы используем ЗАФИКСИРОВАННУЮ версию техкарты.
    Это гарантирует неизменность истории.
    """

    group = models.ForeignKey(
        Group, on_delete=models.CASCADE, related_name="techcard_links"
    )
    technical_card_version = models.ForeignKey(
        "app_technical_cards.TechnicalCardVersion",
        on_delete=models.PROTECT,
        related_name="group_links",
    )
    order = models.PositiveIntegerField(default=0, db_index=True)
    pinned_at = models.DateTimeField(
        auto_now_add=True
    )  # когда «прикрутили» версию к смете

    class Meta:
        unique_together = [("group", "technical_card_version")]
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return f"{self.group} → {self.technical_card_version}"
