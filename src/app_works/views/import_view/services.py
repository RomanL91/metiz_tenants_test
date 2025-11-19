from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Set, Tuple

import openpyxl
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext as _

from app_suppliers.models import Supplier
from app_units.models import Unit
from app_works.models import Work
from app_works.views.import_view.exceptions import (
    FileProcessingException,
    InvalidFileFormatException,
    InvalidFileStructureException,
)
from core.utils.numbers import round_decimal_value


class WorkImportResult:
    """DTO для результата импорта работ"""

    def __init__(
        self,
        status: str,
        created: int = 0,
        updated: int = 0,
        skipped: int = 0,
        errors: Optional[List[Dict[str, Any]]] = None,
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
    """Валидатор файла импорта работ"""

    ALLOWED_EXTENSIONS = [".xlsx", ".xls"]
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

    @classmethod
    def validate(cls, file: UploadedFile) -> None:
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
    """Парсер Excel файлов для импорта работ"""

    REQUIRED_COLUMNS = ["Наименование", "Единица измерения", "Цена"]
    OPTIONAL_COLUMNS = ["Поставщик", "Расценка за человеко-час", "Считать только по ЧЧ"]
    ALL_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

    def parse(self, file: UploadedFile) -> List[Dict[str, Any]]:
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
        except InvalidFileStructureException:
            raise
        except Exception as exc:
            raise FileProcessingException(
                _("Ошибка при чтении файла: {error}").format(error=str(exc))
            )

    def _extract_headers(self, sheet) -> Dict[str, int]:
        headers: Dict[str, int] = {}
        for cell in sheet[1]:
            if cell.value:
                header_name = str(cell.value).strip()
                if header_name in self.ALL_COLUMNS:
                    headers[header_name] = cell.column - 1
        return headers

    def _validate_headers(self, headers: Dict[str, int]) -> None:
        missing = [column for column in self.REQUIRED_COLUMNS if column not in headers]
        if missing:
            raise InvalidFileStructureException(
                _("Отсутствуют обязательные колонки: {columns}").format(
                    columns=", ".join(missing)
                )
            )

    def _extract_data(self, sheet, headers: Dict[str, int]) -> List[Dict[str, Any]]:
        data: List[Dict[str, Any]] = []
        for row_index, row in enumerate(sheet.iter_rows(min_row=2), start=2):
            row_data: Dict[str, Any] = {"_row": row_index}
            for column_name, column_index in headers.items():
                row_data[column_name] = row[column_index].value

            if self._is_empty_row(row_data):
                continue

            data.append(row_data)

        if not data:
            raise InvalidFileStructureException(_("Файл не содержит данных"))

        return data

    def _is_empty_row(self, row_data: Dict[str, Any]) -> bool:
        return all(
            row_data.get(column) is None or str(row_data.get(column)).strip() == ""
            for column in self.REQUIRED_COLUMNS
        )


class WorkDataValidator:
    """Валидатор данных строки работы"""

    @staticmethod
    def validate_row(row: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        name = row.get("Наименование")
        if not name or str(name).strip() == "":
            return False, _("Наименование не может быть пустым")

        price = row.get("Цена")
        if price is None or str(price).strip() == "":
            return False, _("Цена не может быть пустой")

        try:
            price_decimal = round_decimal_value(price)
            if price_decimal <= 0:
                return False, _("Цена должна быть больше нуля")
        except (InvalidOperation, ValueError):
            return False, _("Некорректное значение цены")

        return True, None


class WorkImportProcessor:
    """Процессор импорта работ"""

    BATCH_SIZE = 500

    def __init__(self) -> None:
        self.units_cache: Dict[str, Unit] = {}
        self.suppliers_cache: Dict[str, Supplier] = {}
        self.existing_works: Dict[Tuple[str, int, Optional[int]], Work] = {}
        self._load_units()
        self._load_suppliers()

    def _load_units(self) -> None:
        for unit in Unit.objects.all():
            self.units_cache[unit.symbol.strip().lower()] = unit

    def _load_suppliers(self) -> None:
        """Кэширование поставщиков по name"""
        for supplier in Supplier.objects.all():
            self.suppliers_cache[supplier.name.strip().lower()] = supplier

    def _load_existing_works(self, keys: Set[Tuple[str, int, Optional[int]]]) -> None:
        if not keys:
            self.existing_works = {}
            return

        names = {name for name, _, _ in keys}
        unit_ids = {unit_id for _, unit_id, _ in keys}
        supplier_ids = {
            supplier_id for _, _, supplier_id in keys if supplier_id is not None
        }
        require_null_supplier = any(supplier_id is None for _, _, supplier_id in keys)

        query = Work.objects.filter(name__in=names, unit_ref_id__in=unit_ids)

        supplier_conditions = Q()
        if supplier_ids:
            supplier_conditions |= Q(supplier_ref_id__in=supplier_ids)
        if require_null_supplier:
            supplier_conditions |= Q(supplier_ref__isnull=True)

        if supplier_conditions:
            query = query.filter(supplier_conditions)

        existing = query.select_related("unit_ref", "supplier_ref")

        self.existing_works = {
            (work.name.strip(), work.unit_ref_id, work.supplier_ref_id): work
            for work in existing
        }

    def process_data(
        self, data: List[Dict[str, Any]]
    ) -> Tuple[int, int, int, List[Dict[str, Any]]]:
        validator = WorkDataValidator()
        errors: List[Dict[str, Any]] = []
        valid_rows: List[Dict[str, Any]] = []

        for row in data:
            row_number = row.get("_row", 0)
            is_valid, error_message = validator.validate_row(row)
            if not is_valid:
                errors.append(
                    {"row": row_number, "field": "Общая", "error": error_message}
                )
                continue

            try:
                prepared_row = self._prepare_row_data(row)
                valid_rows.append(prepared_row)
            except Exception as exc:
                errors.append({"row": row_number, "field": "Общая", "error": str(exc)})

        if not valid_rows:
            return 0, 0, 0, errors

        self._ensure_suppliers_exist(valid_rows)

        self._attach_suppliers(valid_rows)

        existing_keys = {row["work_key"] for row in valid_rows}

        self._load_existing_works(existing_keys)

        created, updated, skipped = self._bulk_upsert_works(valid_rows)
        return created, updated, skipped, errors

    def _prepare_row_data(self, row: Dict[str, Any]) -> Dict[str, Any]:
        name = str(row.get("Наименование")).strip()
        unit_symbol = str(row.get("Единица измерения")).strip()
        price = round_decimal_value(row.get("Цена"))

        unit = self._get_unit(unit_symbol)

        supplier_name = row.get("Поставщик")
        supplier_key = None
        supplier_name_clean = None
        if supplier_name and str(supplier_name).strip():
            supplier_name_clean = str(supplier_name).strip()
            supplier_key = supplier_name_clean.lower()

        price_per_labor_hour = None
        labor_hour_value = row.get("Расценка за человеко-час")
        if labor_hour_value is not None and str(labor_hour_value).strip() != "":
            try:
                price_per_labor_hour = round_decimal_value(labor_hour_value)
            except (InvalidOperation, ValueError):
                pass

        calculate_only_by_labor = False
        labor_flag = row.get("Считать только по ЧЧ")
        if labor_flag:
            labor_flag_str = str(labor_flag).strip().lower()
            if labor_flag_str in ("да", "yes", "true", "1", "+"):
                calculate_only_by_labor = True

        return {
            "name": name,
            "unit": unit,
            "price": price,
            "supplier_key": supplier_key,
            "supplier_name": supplier_name_clean,
            "row_number": row.get("_row", 0),
            "price_per_labor_hour": price_per_labor_hour,
            "calculate_only_by_labor": calculate_only_by_labor,
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

    def _attach_suppliers(self, valid_rows: List[Dict[str, Any]]) -> None:
        """Добавляет объекты поставщиков и ключи работ к строкам"""
        for row in valid_rows:
            supplier = None
            supplier_key = row.get("supplier_key")
            if supplier_key:
                supplier = self.suppliers_cache.get(supplier_key)

            supplier_id = supplier.id if supplier else None

            row["supplier"] = supplier
            row["supplier_id"] = supplier_id
            row["work_key"] = (row["name"], row["unit"].id, supplier_id)

    def _bulk_upsert_works(
        self, valid_rows: List[Dict[str, Any]]
    ) -> Tuple[int, int, int]:
        works_to_create: List[Work] = []
        works_to_update: List[Work] = []
        processed_keys: Set[Tuple[str, int, Optional[int]]] = set()
        created = 0
        updated = 0
        skipped = 0

        for row in valid_rows:
            key = row["work_key"]

            if key in processed_keys:
                skipped += 1
                continue

            existing = self.existing_works.get(key)

            if existing:
                existing.price_per_unit = row["price"]
                existing.supplier_ref = row.get("supplier")
                existing.price_per_labor_hour = row.get("price_per_labor_hour")
                existing.calculate_only_by_labor = row.get("calculate_only_by_labor", False)
                existing.is_active = True
                works_to_update.append(existing)
                processed_keys.add(key)
                updated += 1
                continue

            work = Work(
                name=row["name"],
                unit_ref=row["unit"],
                price_per_unit=row["price"],
                price_per_labor_hour=row.get("price_per_labor_hour"),
                calculate_only_by_labor=row.get("calculate_only_by_labor", False),
                supplier_ref=row.get("supplier"),
                is_active=True,
            )
            works_to_create.append(work)
            processed_keys.add(key)

            if len(works_to_create) >= self.BATCH_SIZE:
                created += len(
                    Work.objects.bulk_create(works_to_create, ignore_conflicts=True)
                )
                works_to_create = []

        if works_to_create:
            created += len(
                Work.objects.bulk_create(works_to_create, ignore_conflicts=True)
            )

        if works_to_update:
            Work.objects.bulk_update(
                works_to_update,
                ["price_per_unit", "supplier_ref", "price_per_labor_hour",
                 "calculate_only_by_labor", "is_active"]
            )

        return created, updated, skipped

    def _get_unit(self, unit_symbol: str) -> Unit:
        unit_key = unit_symbol.strip().lower()
        if unit_key not in self.units_cache:
            raise ValueError(
                _("Единица измерения '{unit}' не найдена в справочнике").format(
                    unit=unit_symbol
                )
            )
        return self.units_cache[unit_key]


class WorkImportService:
    """Сервис импорта работ"""

    def __init__(self) -> None:
        self.file_validator = FileValidator()
        self.excel_parser = ExcelParser()

    def import_works(self, file: UploadedFile) -> WorkImportResult:
        try:
            self.file_validator.validate(file)
            data = self.excel_parser.parse(file)

            with transaction.atomic():
                processor = WorkImportProcessor()
                created, updated, skipped, errors = processor.process_data(data)

            status_value = self._determine_status(created, updated, errors)
            message = self._build_message(created, updated, skipped, errors)

            return WorkImportResult(
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
        ):
            raise
        except Exception as exc:
            raise FileProcessingException(
                _("Неожиданная ошибка при обработке файла: {error}").format(
                    error=str(exc)
                )
            )

    def _determine_status(
        self, created: int, updated: int, errors: List[Dict[str, Any]]
    ) -> str:
        if errors and (created > 0 or updated > 0):
            return "partial"
        if errors:
            return "error"
        return "success"

    def _build_message(
        self, created: int, updated: int, skipped: int, errors: List[Dict[str, Any]]
    ) -> str:
        if not errors:
            return _(
                "Импорт завершен успешно. Создано: {created}, обновлено: {updated}, пропущено: {skipped}"
            ).format(created=created, updated=updated, skipped=skipped)

        return _(
            "Импорт завершен с ошибками. Создано: {created}, обновлено: {updated}, пропущено: {skipped}, ошибок: {errors}"
        ).format(
            created=created,
            updated=updated,
            skipped=skipped,
            errors=len(errors),
        )
