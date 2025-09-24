from django.db import models
from django.contrib.postgres.indexes import GinIndex


def upload_to_estimates(instance, filename: str) -> str:
    # можно заменить на S3/MinIO storage; путь оставим простым
    return f"imports/estimates/{filename}"


class ImportedEstimateFile(models.Model):
    """
    Исходный Excel: хранится файл и базовые метаданные.
    Всё остальное можно вычислять сервисом при загрузке/парсинге.
    """

    file = models.FileField(upload_to=upload_to_estimates)
    original_name = models.CharField(max_length=255)
    sha256 = models.CharField(max_length=64, db_index=True, blank=True, default="")
    size_bytes = models.BigIntegerField(default=0)
    sheet_count = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:
        return self.original_name


class ParseResult(models.Model):
    """
    Результат парсинга: универсальный JSON-слепок.
    Минимально — OneToOne к файлу (по одному «актуальному» результату).
    """

    file = models.OneToOneField(
        ImportedEstimateFile, on_delete=models.CASCADE, related_name="parse_result"
    )
    data = models.JSONField()  # JSONB в Postgres
    estimate_name = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            GinIndex(name="parse_result_data_gin", fields=["data"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"ParseResult #{self.pk} for {self.file.original_name}"


class ParseMarkup(models.Model):
    """
    Разметка поверх ParseResult.data: кем является узел и связи ТК ↔ (работы/материалы).
    Ссылаемся на узлы через их UID внутри ParseResult.data.
    """

    file = models.OneToOneField(
        ImportedEstimateFile, on_delete=models.CASCADE, related_name="markup"
    )
    parse_result = models.OneToOneField(
        ParseResult, on_delete=models.CASCADE, related_name="markup"
    )
    # Структура JSON:
    # {
    #   "labels": { "<uid>": "TECH_CARD" | "WORK" | "MATERIAL" | "GROUP" },
    #   "tech_cards": [
    #       {"uid": "<tc_uid>", "works": ["<work_uid>", ...], "materials": ["<mat_uid>", ...]}
    #   ]
    # }
    annotation = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Разметка сметы"
        verbose_name_plural = "Разметки смет"

    def __str__(self) -> str:
        return f"Markup for {self.file.original_name}"
