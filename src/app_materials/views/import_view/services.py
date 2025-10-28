from typing import Dict, List, Any
from django.core.files.uploadedfile import UploadedFile
from django.utils.translation import gettext as _

from .exceptions import (
    InvalidFileFormatException,
    InvalidFileStructureException,
    FileProcessingException,
    ValidationException,
)


class MaterialImportResult:
    """DTO для результата импорта"""

    def __init__(
        self,
        status: str,
        created: int = 0,
        updated: int = 0,
        skipped: int = 0,
        errors: List[Dict[str, Any]] = None,
        message: str = "",
    ):
        self.status = status
        self.created = created
        self.updated = updated
        self.skipped = skipped
        self.errors = errors or []
        self.message = message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "errors": self.errors,
            "message": self.message,
        }


class FileValidator:
    """Валидатор файлов импорта"""

    ALLOWED_EXTENSIONS = [".xlsx", ".xls"]
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

    @classmethod
    def validate(cls, file: UploadedFile) -> None:
        """Валидация загруженного файла"""
        cls._validate_extension(file)
        cls._validate_size(file)

    @classmethod
    def _validate_extension(cls, file: UploadedFile) -> None:
        file_name = file.name.lower()
        if not any(file_name.endswith(ext) for ext in cls.ALLOWED_EXTENSIONS):
            raise InvalidFileFormatException(
                _("Неверный формат файла. Разрешены: {extensions}").format(
                    extensions=", ".join(cls.ALLOWED_EXTENSIONS)
                )
            )

    @classmethod
    def _validate_size(cls, file: UploadedFile) -> None:
        if file.size > cls.MAX_FILE_SIZE:
            raise InvalidFileFormatException(
                _("Размер файла превышает {max_size}MB").format(
                    max_size=cls.MAX_FILE_SIZE // (1024 * 1024)
                )
            )


class ExcelParser:
    """Парсер Excel файлов"""

    REQUIRED_COLUMNS = ["Наименование", "Единица измерения", "Цена"]
    OPTIONAL_COLUMNS = ["Поставщик", "НДС %"]

    def parse(self, file: UploadedFile) -> List[Dict[str, Any]]:
        """
        Парсинг Excel файла
        Пока возвращаем моковые данные
        """
        # TODO: Реальная реализация с openpyxl/pandas
        mock_data = [
            {
                "Наименование": "Цемент М500",
                "Единица измерения": "тонна",
                "Цена": 45000,
                "Поставщик": "ТОО Стройматериалы",
                "НДС %": 12,
            },
            {
                "Наименование": "Песок речной",
                "Единица измерения": "м³",
                "Цена": 3500,
                "Поставщик": "ИП Карьер",
                "НДС %": 12,
            },
            {
                "Наименование": "Щебень гранитный",
                "Единица измерения": "м³",
                "Цена": 5200,
                "Поставщик": None,
                "НДС %": None,
            },
        ]
        return mock_data

    def validate_structure(self, data: List[Dict[str, Any]]) -> None:
        """Валидация структуры данных"""
        if not data:
            raise InvalidFileStructureException(_("Файл не содержит данных"))

        first_row = data[0]
        missing_columns = [col for col in self.REQUIRED_COLUMNS if col not in first_row]

        if missing_columns:
            raise InvalidFileStructureException(
                _("Отсутствуют обязательные колонки: {columns}").format(
                    columns=", ".join(missing_columns)
                )
            )


class MaterialImportService:
    """Сервис импорта материалов"""

    def __init__(self):
        self.file_validator = FileValidator()
        self.excel_parser = ExcelParser()

    def import_materials(self, file: UploadedFile) -> MaterialImportResult:
        """
        Основной метод импорта материалов
        Пока возвращаем моковый результат
        """
        try:
            # Валидация файла
            self.file_validator.validate(file)

            # Парсинг
            data = self.excel_parser.parse(file)

            # Валидация структуры
            self.excel_parser.validate_structure(data)

            # TODO: Реальная обработка и сохранение
            result = self._process_mock_import(data)

            return result

        except (
            InvalidFileFormatException,
            InvalidFileStructureException,
            FileProcessingException,
        ) as e:
            raise
        except Exception as e:
            raise FileProcessingException(
                _("Неожиданная ошибка при обработке файла: {error}").format(
                    error=str(e)
                )
            )

    def _process_mock_import(self, data: List[Dict[str, Any]]) -> MaterialImportResult:
        """Моковая обработка импорта"""
        created = 15
        updated = 3
        skipped = 2
        errors = [
            {
                "row": 5,
                "field": "Цена",
                "error": "Некорректное значение цены",
            },
            {
                "row": 12,
                "field": "Единица измерения",
                "error": "Единица измерения не найдена в справочнике",
            },
        ]

        status = "success" if not errors else "partial"
        message = _("Импорт завершен успешно")

        if errors:
            message = _(
                "Импорт завершен с ошибками. Обработано: {total}, ошибок: {errors}"
            ).format(total=created + updated, errors=len(errors))

        return MaterialImportResult(
            status=status,
            created=created,
            updated=updated,
            skipped=skipped,
            errors=errors,
            message=message,
        )
