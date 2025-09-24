from django.db import models


class Work(models.Model):
    """
    РАБОТА — базовая сущность с одним главным полем name.
    Детали (категория, трудозатраты, разряды) добавим по мере проектирования.
    Или другие идеи..
    Но пока так.
    """

    name = models.CharField(max_length=255, db_index=True)

    class Meta:
        verbose_name = "Работа"
        verbose_name_plural = "Работы"
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return self.name
