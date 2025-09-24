from django.db import models


class Material(models.Model):
    """
    МАТЕРИАЛ — базовая сущность с одним главным полем name.
    Историчность смет обеспечивается на уровне версий техкарт (снапшоты),
    а здесь держим живой справочник материалов.
    """

    name = models.CharField(max_length=255, db_index=True)

    class Meta:
        verbose_name = "Материал"
        verbose_name_plural = "Материалы"
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return self.name
