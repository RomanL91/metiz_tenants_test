from django.db import models


class TechnicalCard(models.Model):
    """
    Живая «голова» ТК (редактируемый черновик/эталон).
    Версии создаются снимками, и именно к версиям будут привязываться сметы.
    """

    name = models.CharField(max_length=255, db_index=True)

    def __str__(self) -> str:
        return self.name


class TechnicalCardVersion(models.Model):
    """
    НЕИЗМЕНЯЕМАЯ версия ТК (снапшот на момент фиксации).
    Сметы/группы используют только этот объект.
    """

    card = models.ForeignKey(
        TechnicalCard, on_delete=models.CASCADE, related_name="versions"
    )
    version = models.PositiveIntegerField()  # 1, 2, 3, ...
    name = models.CharField(max_length=255)  # фиксируем имя на момент версии
    created_at = models.DateTimeField(auto_now_add=True)
    is_published = models.BooleanField(default=True)  # на будущее (черновые версии)

    class Meta:
        unique_together = [("card", "version")]
        ordering = ["card_id", "-version"]

    def __str__(self) -> str:
        return f"{self.card.name} v{self.version}"


# Пока ТК = перечень материалов и работ.
# Фиксируем состав в версиях ТК отдельными строками (снимок названия; позже добавим qty/unit/цены).
class TechnicalCardVersionMaterial(models.Model):
    technical_card_version = models.ForeignKey(
        TechnicalCardVersion, on_delete=models.CASCADE, related_name="material_items"
    )
    # Сохраняем ID для трассировки и СНАПШОТ имени, чтобы история не «плыла», если переименуем Material.
    material = models.ForeignKey(
        "app_materials.Material",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="version_links",
    )
    material_name = models.CharField(max_length=255)  # снапшот имени
    order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ["order", "id"]


class TechnicalCardVersionWork(models.Model):
    technical_card_version = models.ForeignKey(
        TechnicalCardVersion, on_delete=models.CASCADE, related_name="work_items"
    )
    work = models.ForeignKey(
        "app_works.Work",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="version_links",
    )
    work_name = models.CharField(max_length=255)  # снапшот имени
    order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ["order", "id"]
