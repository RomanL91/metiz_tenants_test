from typing import Dict, List, Any, Tuple, Optional
from decimal import Decimal, InvalidOperation
from django.core.files.uploadedfile import UploadedFile
from django.utils.translation import gettext as _
from django.db import transaction
import openpyxl

from app_materials.models import Material
from app_units.models import Unit
from app_suppliers.models import Supplier

from .exceptions import (
    InvalidFileFormatException,
    InvalidFileStructureException,
    FileProcessingException,
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
    ALL_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

    def parse(self, file: UploadedFile) -> List[Dict[str, Any]]:
        """Парсинг Excel файла"""
        try:
            workbook = openpyxl.load_workbook(file, read_only=True, data_only=True)
            sheet = workbook.active

            headers = self._extract_headers(sheet)
            self._validate_headers(headers)

            data = self._extract_data(sheet, headers)

            workbook.close()

            return data

        except openpyxl.utils.exceptions.InvalidFileException:
            raise InvalidFileFormatException(
                _(
                    "Не удалось прочитать файл. Убедитесь, что это корректный Excel файл."
                )
            )
        except Exception as e:
            raise FileProcessingException(
                _("Ошибка при чтении файла: {error}").format(error=str(e))
            )

    def _extract_headers(self, sheet) -> Dict[str, int]:
        """Извлечение заголовков из первой строки"""
        headers = {}
        for cell in sheet[1]:
            if cell.value:
                header_name = str(cell.value).strip()
                if header_name in self.ALL_COLUMNS:
                    headers[header_name] = cell.column - 1

        return headers

    def _validate_headers(self, headers: Dict[str, int]) -> None:
        """Валидация наличия обязательных заголовков"""
        missing = [col for col in self.REQUIRED_COLUMNS if col not in headers]

        if missing:
            raise InvalidFileStructureException(
                _("Отсутствуют обязательные колонки: {columns}").format(
                    columns=", ".join(missing)
                )
            )

    def _extract_data(self, sheet, headers: Dict[str, int]) -> List[Dict[str, Any]]:
        """Извлечение данных из строк"""
        data = []

        for row_idx, row in enumerate(sheet.iter_rows(min_row=2), start=2):
            row_data = {"_row": row_idx}

            for col_name, col_idx in headers.items():
                cell_value = row[col_idx].value
                row_data[col_name] = cell_value

            if self._is_empty_row(row_data):
                continue

            data.append(row_data)

        if not data:
            raise InvalidFileStructureException(_("Файл не содержит данных"))

        return data

    def _is_empty_row(self, row_data: Dict[str, Any]) -> bool:
        """Проверка, пустая ли строка"""
        return all(
            row_data.get(col) is None or str(row_data.get(col)).strip() == ""
            for col in self.REQUIRED_COLUMNS
        )


class MaterialDataValidator:
    """Валидатор данных материала"""

    @staticmethod
    def validate_row(
        row: Dict[str, Any], row_number: int
    ) -> Tuple[bool, Optional[str]]:
        """
        Валидация строки данных
        Возвращает (is_valid, error_message)
        """
        name = row.get("Наименование")
        if not name or str(name).strip() == "":
            return False, _("Наименование не может быть пустым")

        price = row.get("Цена")
        if price is None or str(price).strip() == "":
            return False, _("Цена не может быть пустой")

        try:
            price_decimal = Decimal(str(price))
            if price_decimal <= 0:
                return False, _("Цена должна быть больше нуля")
        except (InvalidOperation, ValueError):
            return False, _("Некорректное значение цены")

        vat = row.get("НДС %")
        if vat is not None and str(vat).strip() != "":
            try:
                vat_decimal = Decimal(str(vat))
                if vat_decimal < 0 or vat_decimal > 100:
                    return False, _("НДС должен быть в диапазоне от 0 до 100")
            except (InvalidOperation, ValueError):
                return False, _("Некорректное значение НДС")

        return True, None


class MaterialImportProcessor:
    """Процессор импорта материалов"""

    def __init__(self):
        self.units_cache: Dict[str, Unit] = {}
        self.suppliers_cache: Dict[str, Supplier] = {}
        self._load_units()
        self._load_suppliers()

    def _load_units(self) -> None:
        """Кэширование единиц измерения"""
        for unit in Unit.objects.all():
            self.units_cache[unit.symbol.strip().lower()] = unit

    def _load_suppliers(self) -> None:
        """Кэширование поставщиков"""
        for supplier in Supplier.objects.all():
            self.suppliers_cache[supplier.legal_name.strip().lower()] = supplier

    def process_data(
        self, data: List[Dict[str, Any]]
    ) -> Tuple[int, int, int, List[Dict[str, Any]]]:
        """
        Обработка данных и создание материалов
        Возвращает (created, updated, skipped, errors)
        """
        created = 0
        updated = 0
        skipped = 0
        errors = []

        validator = MaterialDataValidator()

        for row in data:
            row_number = row.get("_row", 0)

            is_valid, error_message = validator.validate_row(row, row_number)
            if not is_valid:
                errors.append(
                    {
                        "row": row_number,
                        "field": "Общая",
                        "error": error_message,
                    }
                )
                continue

            try:
                result = self._process_single_row(row)
                if result == "created":
                    created += 1
                elif result == "updated":
                    updated += 1
                elif result == "skipped":
                    skipped += 1

            except Exception as e:
                errors.append(
                    {
                        "row": row_number,
                        "field": "Общая",
                        "error": str(e),
                    }
                )

        return created, updated, skipped, errors

    def _process_single_row(self, row: Dict[str, Any]) -> str:
        """
        Обработка одной строки
        Возвращает: 'created', 'updated', 'skipped'
        """
        name = str(row.get("Наименование")).strip()
        unit_name = str(row.get("Единица измерения")).strip()
        price = Decimal(str(row.get("Цена")))

        unit = self._get_unit(unit_name, row.get("_row", 0))

        existing_material = Material.objects.filter(name=name, unit_ref=unit).first()

        if existing_material:
            return "skipped"

        supplier = self._get_or_create_supplier(row.get("Поставщик"))

        vat_percent = None
        vat_value = row.get("НДС %")
        if vat_value is not None and str(vat_value).strip() != "":
            vat_percent = Decimal(str(vat_value))

        Material.objects.create(
            name=name,
            unit_ref=unit,
            price_per_unit=price,
            supplier_ref=supplier,
            vat_percent=vat_percent,
            is_active=True,
        )

        return "created"

    def _get_unit(self, unit_name: str, row_number: int) -> Unit:
        """Получение единицы измерения из кэша"""
        unit_key = unit_name.strip().lower()

        if unit_key not in self.units_cache:
            raise ValueError(
                _("Единица измерения '{unit}' не найдена в справочнике").format(
                    unit=unit_name
                )
            )

        return self.units_cache[unit_key]

    def _get_or_create_supplier(
        self, supplier_name: Optional[Any]
    ) -> Optional[Supplier]:
        """Получение или создание поставщика"""
        if not supplier_name or str(supplier_name).strip() == "":
            return None

        supplier_key = str(supplier_name).strip().lower()

        if supplier_key in self.suppliers_cache:
            return self.suppliers_cache[supplier_key]

        supplier_name_clean = str(supplier_name).strip()

        supplier = Supplier.objects.create(
            name=supplier_name_clean,
            legal_name=supplier_name_clean,
            supplier_type=Supplier.SupplierType.LEGAL,
            vat_registered=True,
            is_active=True,
        )

        self.suppliers_cache[supplier_key] = supplier

        return supplier


class MaterialImportService:
    """Сервис импорта материалов"""

    def __init__(self):
        self.file_validator = FileValidator()
        self.excel_parser = ExcelParser()

    def import_materials(self, file: UploadedFile) -> MaterialImportResult:
        """Основной метод импорта материалов"""
        try:
            self.file_validator.validate(file)

            data = self.excel_parser.parse(file)

            with transaction.atomic():
                processor = MaterialImportProcessor()
                created, updated, skipped, errors = processor.process_data(data)

            status_value = self._determine_status(created, updated, errors)
            message = self._build_message(created, updated, skipped, errors)

            return MaterialImportResult(
                status=status_value,
                created=created,
                updated=updated,
                skipped=skipped,
                errors=errors,
                message=message,
            )

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

    def _determine_status(
        self, created: int, updated: int, errors: List[Dict[str, Any]]
    ) -> str:
        """Определение статуса импорта"""
        if errors and (created > 0 or updated > 0):
            return "partial"
        elif errors:
            return "error"
        else:
            return "success"

    def _build_message(
        self, created: int, updated: int, skipped: int, errors: List[Dict[str, Any]]
    ) -> str:
        """Формирование сообщения о результате"""
        if not errors:
            return _(
                "Импорт завершен успешно. Создано: {created}, обновлено: {updated}, пропущено: {skipped}"
            ).format(created=created, updated=updated, skipped=skipped)
        else:
            return _(
                "Импорт завершен с ошибками. Создано: {created}, обновлено: {updated}, пропущено: {skipped}, ошибок: {errors}"
            ).format(
                created=created,
                updated=updated,
                skipped=skipped,
                errors=len(errors),
            )
