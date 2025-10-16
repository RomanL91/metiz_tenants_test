from django.db import models
from django.contrib.postgres.indexes import GinIndex
from django.utils.translation import gettext_lazy as _


def upload_to_estimates(instance, filename: str) -> str:
    # можно заменить на S3/MinIO storage; путь оставим простым
    return f"imports/estimates/{filename}"


class ImportedEstimateFile(models.Model):
    """
    Исходный Excel: хранится файл и базовые метаданные.
    Всё остальное можно вычислять сервисом при загрузке/парсинге.
    """

    file = models.FileField(
        upload_to=upload_to_estimates,
        verbose_name=_("Файл Excel"),
        help_text=_("Оригинальный файл сметы, загруженный пользователем."),
    )
    original_name = models.CharField(
        max_length=255,
        verbose_name=_("Оригинальное имя файла"),
        help_text=_("Имя файла на стороне пользователя (как было при загрузке)."),
    )
    sha256 = models.CharField(
        max_length=64,
        db_index=True,
        blank=True,
        default="",
        verbose_name=_("SHA-256"),
        help_text=_("Контрольная сумма для дедупликации и проверки целостности."),
    )
    size_bytes = models.BigIntegerField(
        default=0,
        verbose_name=_("Размер, байт"),
        help_text=_("Размер исходного файла в байтах."),
    )
    sheet_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Количество листов"),
        help_text=_("Сколько листов обнаружено в Excel-документе."),
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Загружено"),
        help_text=_("Дата и время загрузки файла."),
    )

    class Meta:
        verbose_name = _("Импортированный файл сметы")
        verbose_name_plural = _("Импортированные файлы смет")
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:
        return self.original_name


class ParseResult(models.Model):
    """
    Результат парсинга: универсальный JSON-слепок.
    Минимально — OneToOne к файлу (по одному «актуальному» результату).
    """

    file = models.OneToOneField(
        ImportedEstimateFile,
        on_delete=models.CASCADE,
        related_name="parse_result",
        verbose_name=_("Файл"),
        help_text=_("Файл, к которому относится данный результат парсинга."),
    )
    data = models.JSONField(
        verbose_name=_("Данные парсинга"),
        help_text=_(
            "Универсальный JSON-слепок, полученный из Excel (JSONB в Postgres)."
        ),
    )
    estimate_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Название сметы"),
        help_text=_("Имя/заголовок сметы, извлечённый из данных (если найден)."),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Создано"),
        help_text=_("Дата и время формирования результата парсинга."),
    )

    class Meta:
        verbose_name = _("Результат парсинга")
        verbose_name_plural = _("Результаты парсинга")
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
        ImportedEstimateFile,
        on_delete=models.CASCADE,
        related_name="markup",
        verbose_name=_("Файл"),
        help_text=_("Файл-источник, для которого выполняется разметка."),
    )
    parse_result = models.OneToOneField(
        ParseResult,
        on_delete=models.CASCADE,
        related_name="markup",
        verbose_name=_("Результат парсинга"),
        help_text=_(
            "Конкретный результат парсинга, на основе которого делается разметка."
        ),
    )
    # Структура JSON:
    # {
    #   "labels": { "<uid>": "TECH_CARD" | "WORK" | "MATERIAL" | "GROUP" },
    #   "tech_cards": [
    #       {"uid": "<tc_uid>", "works": ["<work_uid>", ...], "materials": ["<mat_uid>", ...]}
    #   ]
    # }
    annotation = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Аннотация"),
        help_text=_(
            "JSON-структура разметки: роли узлов и связи техкарт с работами и материалами "
            "(ключи — UID из данных парсинга)."
        ),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Обновлено"),
        help_text=_("Дата и время последнего изменения разметки."),
    )

    class Meta:
        verbose_name = _("Разметка сметы")
        verbose_name_plural = _("Разметки смет")

    def __str__(self) -> str:
        return f"Markup for {self.file.original_name}"
