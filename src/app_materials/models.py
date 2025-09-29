from django.db import models


class Material(models.Model):
    """
    МАТЕРИАЛ — базовая сущность с одним главным полем name.
    Историчность смет обеспечивается на уровне версий техкарт (снапшоты),
    а здесь держим живой справочник материалов.
    """

    name = models.CharField(
        max_length=255,
        db_index=True,
    )
    unit = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="ед. изм. (напр. 'м3', 'шт')",
    )
    price_per_unit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    code = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
    )
    is_active = models.BooleanField(
        default=True,
    )

    class Meta:
        verbose_name = "Материал"
        verbose_name_plural = "Материалы"
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return self.name
