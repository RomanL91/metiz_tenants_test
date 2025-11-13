"""
Главный класс детектирования техкарт в Excel.

Следует принципам:
- Facade Pattern: единый интерфейс для всех операций
- Composition: использует все вспомогательные классы
- Clear Flow: явный алгоритм детектирования
"""

from typing import Dict, List, Set, Tuple

from .excel_helpers import ExcelRowHelper
from .exceptions import InvalidSchemaError
from .group_assigner import GroupTreeBuilder
from .group_loader import GroupAnnotationLoader
from .unit_normalizer import UnitNormalizer


class TechnicalCardDetector:
    """
    Детектор техкарт в Excel с группировкой.

    Фасад для всех операций детектирования:
    - Поиск строк с ТК по критериям
    - Загрузка групп из annotation
    - Распределение ТК по группам
    - Сбор данных для UI

    Example:
        >>> detector = TechnicalCardDetector(
        ...     col_roles=['NAME', 'UNIT', 'QTY'],
        ...     unit_allow_set={'м2', 'шт'},
        ...     require_qty=True
        ... )
        >>> tcs = detector.detect_from_rows(excel_rows)
        >>> len(tcs)
        50
    """

    # Обязательные роли для детектирования
    REQUIRED_ROLES = ["NAME_OF_WORK", "UNIT"]

    def __init__(
        self,
        col_roles: List[str],
        unit_allow_set: Set[str] = None,
        require_qty: bool = False,
        optional_role_ids: List[str] = None,
        unit_normalizer: UnitNormalizer = None,
    ):
        """
        Args:
            col_roles: Список ролей колонок из схемы
            unit_allow_set: Разрешённые единицы (уже нормализованные)
            require_qty: Требовать qty > 0
            optional_role_ids: Роли для извлечения (PRICE_*, TOTAL_*, ...)
            unit_normalizer: Нормализатор единиц (default: UnitNormalizer())

        Raises:
            InvalidSchemaError: Если отсутствуют обязательные роли
        """
        self.col_roles = col_roles
        self.unit_allow_set = unit_allow_set or set()
        self.require_qty = require_qty
        self.optional_role_ids = optional_role_ids or []
        self.unit_normalizer = unit_normalizer or UnitNormalizer()

        # Валидация схемы
        self._validate_schema()

        # Индексы колонок
        self.name_cols = ExcelRowHelper.get_column_indices(col_roles, "NAME_OF_WORK")
        self.unit_cols = ExcelRowHelper.get_column_indices(col_roles, "UNIT")
        self.qty_cols = ExcelRowHelper.get_column_indices(col_roles, "QTY")

    def _validate_schema(self):
        """
        Валидация схемы колонок.

        Raises:
            InvalidSchemaError: Если нет обязательных ролей
        """
        missing = []
        for role in self.REQUIRED_ROLES:
            if role not in self.col_roles:
                missing.append(role)

        if missing:
            raise InvalidSchemaError(sheet_index=0, missing_roles=missing)

    def detect_from_rows(self, rows: List[Dict]) -> List[Dict]:
        """
        Детектирование ТК из списка строк Excel.

        Args:
            rows: Строки от ExcelSheetReader.read_all_rows()
                [{'row_index': int, 'cells': [...]}, ...]

        Returns:
            List[Dict]: Детектированные ТК
                [
                    {
                        'row_index': int,
                        'name': str,
                        'unit': str,
                        'qty': str
                    },
                    ...
                ]

        Example:
            >>> tcs = detector.detect_from_rows(excel_rows)
            >>> tcs[0]
            {'row_index': 10, 'name': 'Бетон М300', 'unit': 'м3', 'qty': '5.5'}
        """
        detected = []

        for row in rows:
            if self._is_tc_row(row):
                tc = self._extract_tc_data(row)
                detected.append(tc)

        return detected

    def _is_tc_row(self, row: Dict) -> bool:
        """
        Проверка является ли строка техкартой.

        Критерии:
        - Есть название
        - Есть единица измерения
        - Единица в allow_set (если задан)
        - Есть qty > 0 (если require_qty)

        Args:
            row: Строка Excel

        Returns:
            bool: True если это ТК
        """
        # Название
        name = ExcelRowHelper.get_first_nonempty_value(row, self.name_cols)
        if not name:
            return False

        # Единица измерения
        unit_raw = ExcelRowHelper.get_first_nonempty_value(row, self.unit_cols)
        if not unit_raw:
            return False

        # Проверка в allow_set
        if self.unit_allow_set:
            unit_normalized = self.unit_normalizer.normalize(unit_raw)
            if unit_normalized not in self.unit_allow_set:
                return False

        # Проверка количества
        if self.require_qty:
            if not ExcelRowHelper.has_positive_quantity(row, self.qty_cols):
                return False

        return True

    def _extract_tc_data(self, row: Dict) -> Dict:
        """
        Извлечение данных ТК из строки.

        Args:
            row: Строка Excel (прошедшая валидацию)

        Returns:
            Dict: Данные ТК
        """
        name = ExcelRowHelper.get_first_nonempty_value(row, self.name_cols)
        unit = ExcelRowHelper.get_first_nonempty_value(row, self.unit_cols)
        qty = ExcelRowHelper.get_first_nonempty_value(row, self.qty_cols)

        return {
            "row_index": row.get("row_index"),
            "name": name,
            "unit": unit,
            "qty": qty,
        }

    def collect_candidates_with_optional_columns(self, rows: List[Dict]) -> List[Dict]:
        """
        Сбор кандидатов для таблицы сопоставления с опциональными колонками.

        Используется для UI админки.

        Args:
            rows: Строки Excel

        Returns:
            List[Dict]: Кандидаты с расширенными данными
                [
                    {
                        'row_index': int,
                        'name': str,
                        'unit': str,
                        'qty': str,
                        'excel_optional': {role_id: value, ...}
                    },
                    ...
                ]

        Example:
            >>> candidates = detector.collect_candidates_with_optional_columns(rows)
            >>> candidates[0]['excel_optional']['TOTAL_PRICE']
            '12345.67'
        """
        candidates = []

        for row in rows:
            # Берём только строки с названием или единицей
            name = ExcelRowHelper.get_first_nonempty_value(row, self.name_cols)
            unit = ExcelRowHelper.get_first_nonempty_value(row, self.unit_cols)

            if not name and not unit:
                continue

            qty = ExcelRowHelper.get_first_nonempty_value(row, self.qty_cols)

            # Опциональные колонки
            excel_optional = ExcelRowHelper.extract_optional_columns(
                row, self.col_roles, self.optional_role_ids
            )

            candidates.append(
                {
                    "row_index": row.get("row_index"),
                    "name": name,
                    "unit": unit,
                    "qty": qty,
                    "excel_optional": excel_optional,
                }
            )

        return candidates

    def build_tree_with_groups(
        self, tcs: List[Dict], annotation: Dict, sheet_index: int
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Построение дерева групп с распределением ТК.

        Полный процесс:
        1. Загрузка групп из annotation
        2. Распределение ТК по группам
        3. Построение дерева

        Args:
            tcs: Детектированные ТК
            annotation: Annotation из markup
            sheet_index: Индекс листа

        Returns:
            Tuple[tree, loose]:
                - tree: Дерево групп с ТК
                - loose: ТК без группы

        Example:
            >>> tree, loose = detector.build_tree_with_groups(tcs, annotation, 0)
            >>> len(tree)
            3
            >>> len(loose)
            5
        """
        # Загрузка групп
        loader = GroupAnnotationLoader()
        groups = loader.load_groups(annotation, sheet_index)

        if not groups:
            # Нет групп — всё в loose
            return [], tcs

        # Построение дерева и распределение
        builder = GroupTreeBuilder(groups)
        tree, loose = builder.assign_tcs_to_groups(tcs)

        return tree, loose
