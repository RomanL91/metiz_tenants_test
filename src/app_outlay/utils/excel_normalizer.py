"""
Нормализация данных из Excel ячеек.

Следует принципам:
- Strategy Pattern: разные стратегии нормализации
- Immutability: не мутирует исходные данные
- Extensibility: легко добавить новые стратегии
"""

from typing import Any, List, Protocol


class CellNormalizerStrategy(Protocol):
    """Протокол стратегии нормализации ячейки."""

    def normalize(self, value: Any) -> str:
        """
        Нормализация значения ячейки.

        Args:
            value: Значение из openpyxl

        Returns:
            str: Нормализованная строка
        """
        ...


class DefaultCellNormalizer:
    """
    Стандартная нормализация ячеек.

    Правила:
    - None → ""
    - Числа → str() с trim
    - Строки → strip()
    """

    def normalize(self, value: Any) -> str:
        """
        Нормализация значения по умолчанию.

        Args:
            value: Любое значение

        Returns:
            str: Строка с trimmed пробелами

        Example:
            >>> normalizer = DefaultCellNormalizer()
            >>> normalizer.normalize(None)
            ''
            >>> normalizer.normalize("  test  ")
            'test'
            >>> normalizer.normalize(123.45)
            '123.45'
        """
        if value is None:
            return ""
        return str(value).strip()


class StrictCellNormalizer:
    """
    Строгая нормализация с валидацией.

    Дополнительно:
    - Удаляет лишние пробелы внутри
    - Заменяет спецсимволы
    """

    def normalize(self, value: Any) -> str:
        """
        Строгая нормализация с очисткой.

        Args:
            value: Любое значение

        Returns:
            str: Очищенная строка

        Example:
            >>> normalizer = StrictCellNormalizer()
            >>> normalizer.normalize("  test   value  ")
            'test value'
        """
        if value is None:
            return ""

        # Базовая нормализация
        result = str(value).strip()

        # Удаление лишних пробелов внутри
        import re

        result = re.sub(r"\s+", " ", result)

        return result


class RowNormalizer:
    """
    Нормализатор строк Excel.

    Использует Strategy для нормализации каждой ячейки.
    """

    def __init__(self, cell_strategy: CellNormalizerStrategy = None):
        """
        Args:
            cell_strategy: Стратегия нормализации ячеек.
                          По умолчанию: DefaultCellNormalizer
        """
        self.cell_strategy = cell_strategy or DefaultCellNormalizer()

    def normalize_row(self, cells: List[Any], max_cols: int = None) -> List[str]:
        """
        Нормализация всех ячеек строки.

        Args:
            cells: Список значений ячеек
            max_cols: Максимальное количество колонок (для padding)

        Returns:
            List[str]: Нормализованные значения

        Example:
            >>> normalizer = RowNormalizer()
            >>> normalizer.normalize_row([None, 'test', 123], max_cols=5)
            ['', 'test', '123', '', '']
        """
        # Нормализуем каждую ячейку
        normalized = [self.cell_strategy.normalize(cell) for cell in cells]

        # Padding до max_cols если нужно
        if max_cols and len(normalized) < max_cols:
            normalized.extend([""] * (max_cols - len(normalized)))

        return normalized
