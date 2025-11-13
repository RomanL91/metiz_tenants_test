"""
Вспомогательные классы для работы с Excel строками.

Следует принципам:
- Single Responsibility: только работа с row/cells
- Immutability: не мутирует данные
- Clear API: явные методы
"""

from typing import Any, Dict, List


class ExcelRowHelper:
    """
    Помощник для работы со строками Excel.

    Предоставляет удобные методы для доступа к ячейкам
    по индексам и ролям колонок.
    """

    @staticmethod
    def get_column_indices(col_roles: List[str], target_role: str) -> List[int]:
        """
        Получение всех индексов колонок с заданной ролью.

        Args:
            col_roles: Список ролей всех колонок
            target_role: Искомая роль

        Returns:
            List[int]: Список индексов (0-based)

        Example:
            >>> roles = ['NAME', 'QTY', 'NAME', 'PRICE']
            >>> ExcelRowHelper.get_column_indices(roles, 'NAME')
            [0, 2]
        """
        return [i for i, role in enumerate(col_roles or []) if role == target_role]

    @staticmethod
    def get_cell_value(row: Dict[str, Any], col_index: int) -> str:
        """
        Безопасное получение значения ячейки.

        Args:
            row: Строка в формате {'row_index': int, 'cells': List[str]}
            col_index: Индекс колонки (0-based)

        Returns:
            str: Значение ячейки или пустая строка

        Example:
            >>> row = {'row_index': 1, 'cells': ['A', 'B', 'C']}
            >>> ExcelRowHelper.get_cell_value(row, 1)
            'B'
            >>> ExcelRowHelper.get_cell_value(row, 10)
            ''
        """
        cells = row.get("cells") or []
        if 0 <= col_index < len(cells):
            value = cells[col_index]
            return value if value is not None else ""
        return ""

    @staticmethod
    def get_first_nonempty_value(row: Dict[str, Any], col_indices: List[int]) -> str:
        """
        Получение первого непустого значения из списка колонок.

        Args:
            row: Строка Excel
            col_indices: Список индексов для проверки

        Returns:
            str: Первое непустое значение или пустая строка

        Example:
            >>> row = {'cells': ['', '', 'Value', 'Other']}
            >>> ExcelRowHelper.get_first_nonempty_value(row, [0, 1, 2])
            'Value'
        """
        for idx in col_indices:
            value = ExcelRowHelper.get_cell_value(row, idx).strip()
            if value:
                return value
        return ""

    @staticmethod
    def has_positive_quantity(row: Dict[str, Any], qty_col_indices: List[int]) -> bool:
        """
        Проверка наличия положительного количества.

        Args:
            row: Строка Excel
            qty_col_indices: Индексы колонок с количеством

        Returns:
            bool: True если найдено qty > 0

        Example:
            >>> row = {'cells': ['Name', '0', '5.5']}
            >>> ExcelRowHelper.has_positive_quantity(row, [1, 2])
            True
        """
        for idx in qty_col_indices:
            raw = ExcelRowHelper.get_cell_value(row, idx)
            raw = raw.replace(" ", "").replace(",", ".")
            try:
                if float(raw) > 0:
                    return True
            except (ValueError, TypeError):
                pass
        return False

    @staticmethod
    def extract_optional_columns(
        row: Dict[str, Any],
        col_roles: List[str],
        optional_role_ids: List[str],
    ) -> Dict[str, str]:
        """
        Извлечение значений опциональных колонок.

        Args:
            row: Строка Excel
            col_roles: Список всех ролей колонок
            optional_role_ids: Список ID опциональных ролей

        Returns:
            Dict[str, str]: Словарь {role_id: value}

        Example:
            >>> row = {'cells': ['Name', '100', '200']}
            >>> roles = ['NAME', 'PRICE1', 'PRICE2']
            >>> optional = ['PRICE1', 'PRICE2']
            >>> ExcelRowHelper.extract_optional_columns(row, roles, optional)
            {'PRICE1': '100', 'PRICE2': '200'}
        """
        result = {}
        for role_id in optional_role_ids:
            indices = ExcelRowHelper.get_column_indices(col_roles, role_id)
            if indices:
                value = ExcelRowHelper.get_cell_value(row, indices[0])
                result[role_id] = value
            else:
                result[role_id] = ""
        return result
