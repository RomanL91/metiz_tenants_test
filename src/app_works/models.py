from django.db import models


class Work(models.Model):
    """
    РАБОТА — базовая сущность с одним главным полем name.
    Детали (категория, трудозатраты, разряды) добавим по мере проектирования.
    Или другие идеи..
    Но пока так.
    """

    name = models.CharField(
        max_length=255,
        db_index=True,
    )
    unit = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="ед. изм. (напр. 'чел·ч', 'м2')",
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
        verbose_name = "Работа"
        verbose_name_plural = "Работы"
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return self.name

    class Meta:
        verbose_name = "Работа"
        verbose_name_plural = "Работы"
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return self.name
