"""
Сервисный слой для экспорта сметы в Excel.

Следует принципам:
- Single Responsibility: оркестрация экспорта
- Database Optimization: минимизация запросов
- Clear Flow: явный алгоритм работы
- Error Handling: явная обработка ошибок
"""

import os
from typing import Dict, Tuple

from app_estimate_imports.services.schema_service import SchemaService
from app_outlay.models import Estimate, GroupTechnicalCardLink
from app_outlay.views.estimate_calc_view.utils_calc import calc_for_tc

from .excel_writer import ExcelWriter
from .exceptions import (
    CalculationError,
    EstimateNotFoundError,
    MarkupNotFoundError,
    NoMappingsFoundError,
    NoWritableColumnsError,
    SchemaNotFoundError,
    SourceFileNotFoundError,
)
from .overhead_calculator import OverheadCalculator


class ExcelExportService:
    """
    Сервис экспорта сметы в Excel с расчётами.

    Ответственность:
    - Валидация данных сметы
    - Загрузка схемы и сопоставлений
    - Оркестрация расчётов и записи
    - Формирование результата
    """

    # Колонки для записи результатов
    TARGET_ROLES = [
        "QTY",
        "UNIT_PRICE_OF_MATERIAL",
        "UNIT_PRICE_OF_WORK",
        "UNIT_PRICE_OF_MATERIALS_AND_WORKS",
        "PRICE_FOR_ALL_MATERIAL",
        "PRICE_FOR_ALL_WORK",
        "TOTAL_PRICE",
    ]

    def __init__(self, estimate_id: int):
        """
        Args:
            estimate_id: ID сметы для экспорта
        """
        self.estimate_id = estimate_id
        self.estimate = None
        self.sheet_index = 0
        self.col_roles = []
        self.mappings = {}
        self.overhead_context = None

    def validate_and_prepare(self):
        """
        Валидация данных сметы и подготовка к экспорту.

        Выполняет:
        1. Загрузка сметы из БД
        2. Проверка наличия source_file
        3. Проверка наличия markup
        4. Загрузка схемы колонок
        5. Проверка наличия сопоставлений

        Raises:
            EstimateNotFoundError: Смета не найдена
            SourceFileNotFoundError: Файл не найден
            MarkupNotFoundError: Разметка не найдена
            SchemaNotFoundError: Схема не определена
            NoMappingsFoundError: Нет сопоставлений
        """
        # Шаг 1: Загрузка сметы
        try:
            self.estimate = Estimate.objects.select_related("source_file").get(
                id=self.estimate_id
            )
        except Estimate.DoesNotExist:
            raise EstimateNotFoundError(estimate_id=self.estimate_id)

        # Шаг 2: Проверка source_file
        if not self.estimate.source_file or not self.estimate.source_file.file:
            raise SourceFileNotFoundError(estimate_id=self.estimate_id)

        # Шаг 3: Проверка markup
        if not hasattr(self.estimate.source_file, "markup"):
            raise MarkupNotFoundError(estimate_id=self.estimate_id)

        # Шаг 4: Загрузка схемы
        markup = self.estimate.source_file.markup
        self.sheet_index = self.estimate.source_sheet_index or 0

        try:
            self.col_roles, _, _ = SchemaService().read_sheet_schema(
                markup, self.sheet_index
            )
        except Exception:
            # Fallback: попытка загрузить из annotation
            schema = (
                (markup.annotation or {})
                .get("schema", {})
                .get("sheets", {})
                .get(str(self.sheet_index), {})
            )
            self.col_roles = schema.get("col_roles") or []

        if not self.col_roles:
            raise SchemaNotFoundError(sheet_index=self.sheet_index)

        # Шаг 5: Загрузка сопоставлений
        self._load_mappings()

        if not self.mappings:
            raise NoMappingsFoundError(estimate_id=self.estimate_id)

    def _load_mappings(self):
        """
        Загрузка сопоставлений GroupTechnicalCardLink → source_row_index.

        Оптимизация:
        - select_related для избежания N+1
        - Фильтрация только строк с source_row_index

        Результат:
        self.mappings = {
            row_index: {
                'tc_version': TechnicalCardVersion,
                'quantity': Decimal
            },
            ...
        }
        """
        all_links = (
            GroupTechnicalCardLink.objects.filter(group__estimate=self.estimate)
            .select_related("technical_card_version", "technical_card_version__card")
            .filter(source_row_index__isnull=False)
        )

        self.mappings = {}
        for link in all_links:
            self.mappings[link.source_row_index] = {
                "tc_version": link.technical_card_version,
                "quantity": link.quantity,
            }

    def prepare_overhead_context(self):
        """
        Подготовка контекста НР и НДС для расчётов.

        Делегирует логику в OverheadCalculator.
        """

        self.overhead_context = OverheadCalculator.calculate_overhead_context(
            estimate=self.estimate,
        )

    def export_to_excel(self) -> Tuple[str, str, int]:
        """
        Экспорт сметы в Excel файл.

        Алгоритм:
        1. Валидация и подготовка данных
        2. Подготовка контекста НР/НДС
        3. Открытие Excel и настройка маппинга колонок
        4. Проход по всем сопоставлениям:
           - Расчёт через calc_for_tc
           - Запись результатов в Excel
        5. Сохранение во временный файл
        6. Возврат пути и статистики

        Returns:
            Tuple[temp_path, output_filename, updated_count]:
                - temp_path: путь к временному файлу
                - output_filename: имя файла для скачивания
                - updated_count: количество обновлённых строк

        Raises:
            Любые исключения из validate_and_prepare()
            NoWritableColumnsError: Нет колонок для записи
            CalculationError: Ошибка расчёта техкарты

        Example:
            >>> service = ExcelExportService(estimate_id=123)
            >>> path, name, count = service.export_to_excel()
            >>> count
            50
        """
        # Шаг 1: Валидация и подготовка
        self.validate_and_prepare()

        # Шаг 2: Подготовка НР/НДС
        self.prepare_overhead_context()

        # Шаг 3: Открытие Excel и настройка
        xlsx_path = self.estimate.source_file.file.path
        updated_count = 0

        with ExcelWriter(xlsx_path, self.sheet_index) as writer:
            # Настройка маппинга колонок
            writer.setup_column_mapping(self.col_roles, self.TARGET_ROLES)

            if not writer.role_to_col:
                raise NoWritableColumnsError(sheet_index=self.sheet_index)

            # Шаг 4: Проход по сопоставлениям и запись
            for row_index, mapping in self.mappings.items():
                tc_version = mapping["tc_version"]
                quantity = mapping["quantity"]

                # Расчёт
                try:
                    calc, _ = calc_for_tc(
                        tc_version.card_id,
                        quantity,
                        overhead_context=self.overhead_context,
                        version=tc_version,
                    )
                except Exception as e:
                    raise CalculationError(
                        row_index=row_index,
                        tc_name=tc_version.card.name,
                        error=str(e),
                    )

                # Запись количества
                if "QTY" in writer.role_to_col:
                    writer.write_value(row_index, "QTY", float(quantity))

                # Запись расчётных значений
                cells_written = writer.write_calculated_row(row_index, calc)

                if cells_written > 0:
                    updated_count += 1

            # Шаг 5: Сохранение
            original_name = os.path.splitext(self.estimate.source_file.original_name)[0]
            output_filename = f"{original_name}_calculated.xlsx"
            temp_path = writer.save_to_temp(original_name)

        return temp_path, output_filename, updated_count

    def get_export_summary(self) -> Dict:
        """
        Получение сводной информации об экспорте.

        Returns:
            Dict: Статистика экспорта
                {
                    'estimate_id': int,
                    'estimate_name': str,
                    'total_mappings': int,
                    'has_overhead': bool,
                    'overhead_details': List[Dict],
                    'vat_active': bool,
                    'vat_rate': int
                }
        """
        overhead_details = []
        has_overhead = False
        vat_active = False
        vat_rate = 0

        if self.estimate:
            overhead_details = OverheadCalculator.get_overhead_breakdown(self.estimate)
            has_overhead = len(overhead_details) > 0

            settings = self.estimate.settings_data or {}
            vat_active = settings.get("vat_active", False)
            vat_rate = settings.get("vat_rate", 20)

        return {
            "estimate_id": self.estimate_id,
            "estimate_name": self.estimate.name if self.estimate else "",
            "total_mappings": len(self.mappings),
            "has_overhead": has_overhead,
            "overhead_details": overhead_details,
            "vat_active": vat_active,
            "vat_rate": vat_rate,
        }
