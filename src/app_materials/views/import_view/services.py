# path: src/app_materials/views/import_view/services.py
from typing import Dict, List, Any, Tuple, Optional, Set
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
        """Валидация строки данных"""
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
    """Процессор импорта материалов с оптимизациями против N+1"""

    BATCH_SIZE = 500

    def __init__(self):
        self.units_cache: Dict[str, Unit] = {}
        self.suppliers_cache: Dict[str, Supplier] = {}
        self.existing_materials: Set[Tuple[str, int]] = set()

        self._load_units()
        self._load_suppliers()

    def _load_units(self) -> None:
        """Кэширование единиц измерения по symbol"""
        for unit in Unit.objects.all():
            self.units_cache[unit.symbol.strip().lower()] = unit

    def _load_suppliers(self) -> None:
        """Кэширование поставщиков по name"""
        for supplier in Supplier.objects.all():
            self.suppliers_cache[supplier.name.strip().lower()] = supplier

    def _load_existing_materials(self, names: List[str], unit_ids: List[int]) -> None:
        """Предзагрузка существующих материалов (избегаем N+1)"""
        existing = Material.objects.filter(
            name__in=names, unit_ref_id__in=unit_ids
        ).values_list("name", "unit_ref_id")

        self.existing_materials = set(existing)

    def process_data(
        self, data: List[Dict[str, Any]]
    ) -> Tuple[int, int, int, List[Dict[str, Any]]]:
        """Основная обработка с оптимизациями"""
        validator = MaterialDataValidator()
        errors = []
        valid_rows = []

        for row in data:
            row_number = row.get("_row", 0)

            is_valid, error_message = validator.validate_row(row, row_number)
            if not is_valid:
                errors.append(
                    {"row": row_number, "field": "Общая", "error": error_message}
                )
                continue

            try:
                prepared_row = self._prepare_row_data(row)
                valid_rows.append(prepared_row)
            except Exception as e:
                errors.append({"row": row_number, "field": "Общая", "error": str(e)})

        if not valid_rows:
            return 0, 0, 0, errors

        names = [r["name"] for r in valid_rows]
        unit_ids = list(set([r["unit"].id for r in valid_rows]))
        self._load_existing_materials(names, unit_ids)

        self._ensure_suppliers_exist(valid_rows)

        created, skipped = self._bulk_create_materials(valid_rows)

        return created, 0, skipped, errors

    def _prepare_row_data(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Подготовка данных строки"""
        name = str(row.get("Наименование")).strip()
        unit_symbol = str(row.get("Единица измерения")).strip()
        price = Decimal(str(row.get("Цена")))

        unit = self._get_unit(unit_symbol, row.get("_row", 0))

        supplier_name = row.get("Поставщик")
        supplier_key = None
        supplier_name_clean = None
        if supplier_name and str(supplier_name).strip():
            supplier_name_clean = str(supplier_name).strip()
            supplier_key = supplier_name_clean.lower()

        vat_percent = None
        vat_value = row.get("НДС %")
        if vat_value is not None and str(vat_value).strip() != "":
            vat_percent = Decimal(str(vat_value))

        return {
            "name": name,
            "unit": unit,
            "price": price,
            "supplier_key": supplier_key,
            "supplier_name": supplier_name_clean,
            "vat_percent": vat_percent,
            "row_number": row.get("_row", 0),
        }

    def _ensure_suppliers_exist(self, valid_rows: List[Dict[str, Any]]) -> None:
        """Создание новых поставщиков батчем с заполнением legal_name"""
        new_supplier_names = {}
        for row in valid_rows:
            supplier_key = row.get("supplier_key")
            supplier_name = row.get("supplier_name")
            if supplier_key and supplier_key not in self.suppliers_cache:
                new_supplier_names[supplier_key] = supplier_name

        if not new_supplier_names:
            return

        new_suppliers = [
            Supplier(
                name=name,
                legal_name=name,
                supplier_type=Supplier.SupplierType.LEGAL,
                vat_registered=True,
                is_active=True,
            )
            for name in new_supplier_names.values()
        ]

        Supplier.objects.bulk_create(new_suppliers, ignore_conflicts=True)

        created_or_existing = Supplier.objects.filter(
            name__in=list(new_supplier_names.values())
        )

        for supplier in created_or_existing:
            self.suppliers_cache[supplier.name.strip().lower()] = supplier

    def _bulk_create_materials(
        self, valid_rows: List[Dict[str, Any]]
    ) -> Tuple[int, int]:
        """Bulk создание материалов батчами"""
        materials_to_create = []
        created = 0
        skipped = 0

        for row in valid_rows:
            name = row["name"]
            unit = row["unit"]

            if (name, unit.id) in self.existing_materials:
                skipped += 1
                continue

            supplier = None
            supplier_key = row.get("supplier_key")
            if supplier_key:
                supplier = self.suppliers_cache.get(supplier_key)

            materials_to_create.append(
                Material(
                    name=name,
                    unit_ref=unit,
                    price_per_unit=row["price"],
                    supplier_ref=supplier,
                    vat_percent=row["vat_percent"],
                    is_active=True,
                )
            )

            if len(materials_to_create) >= self.BATCH_SIZE:
                created += len(
                    Material.objects.bulk_create(
                        materials_to_create, ignore_conflicts=True
                    )
                )
                materials_to_create = []

        if materials_to_create:
            created += len(
                Material.objects.bulk_create(materials_to_create, ignore_conflicts=True)
            )

        return created, skipped

    def _get_unit(self, unit_symbol: str, row_number: int) -> Unit:
        """Получение единицы измерения из кэша по symbol"""
        unit_key = unit_symbol.strip().lower()

        if unit_key not in self.units_cache:
            raise ValueError(
                _("Единица измерения '{unit}' не найдена в справочнике").format(
                    unit=unit_symbol
                )
            )

        return self.units_cache[unit_key]


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
