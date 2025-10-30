"""
Нормализация единиц измерения.

Следует принципам:
- Strategy Pattern: разные стратегии нормализации
- Extensibility: легко добавить новые языки/правила
- Immutability: не мутирует данные
"""

import re
from typing import Protocol


class UnitNormalizerStrategy(Protocol):
    """Протокол стратегии нормализации единиц измерения."""

    def normalize(self, unit: str) -> str:
        """
        Нормализация единицы измерения.

        Args:
            unit: Исходная единица

        Returns:
            str: Нормализованная единица
        """
        ...


class RussianUnitNormalizer:
    """
    Нормализатор единиц измерения для русского языка.

    Правила:
    - м² → м2
    - м³ → м3
    - Различные варианты написания → единый формат
    - Удаление лишних символов
    """

    # Паттерны для различных единиц
    PATTERNS = {
        "м2": r"(м\^?2|м2|квм|мкв|квадратн\w*метр\w*)",
        "м3": r"(м\^?3|м3|кубм|мкуб|кубическ\w*метр\w*)",
        "шт": r"(шт|штука|штуки|штук)",
        "пм": r"(пм|погм|погонныйметр|погонныхметров)",
        "компл": r"(компл|комплект|комплекта|комплектов)",
        "м": r"^м$|^метр$|^метров$|^метра$",
        "т": r"^т$|^тонна$|^тонн$|^тонны$",
        "кг": r"^кг$|^килограмм$|^килограмма$|^килограммов$",
    }

    def normalize(self, unit: str) -> str:
        """
        Нормализация единицы измерения.

        Args:
            unit: Исходная единица (может содержать пробелы, точки)

        Returns:
            str: Нормализованная единица

        Example:
            >>> normalizer = RussianUnitNormalizer()
            >>> normalizer.normalize("м²")
            'м2'
            >>> normalizer.normalize("кв. м.")
            'м2'
            >>> normalizer.normalize("штука")
            'шт'
        """
        if not unit:
            return ""

        # Базовая очистка
        s = unit.lower().strip()
        s = s.replace("\u00b2", "2").replace("\u00b3", "3")

        # Удаление пробелов, точек, запятых
        compact = "".join(ch for ch in s if ch not in " .,")

        # Проверка по паттернам
        for normalized, pattern in self.PATTERNS.items():
            if re.fullmatch(pattern, compact):
                return normalized

        # Если не совпало - возвращаем компактный вариант
        return compact


class UnitNormalizer:
    """
    Фасад для работы с нормализацией единиц.

    Позволяет легко менять стратегию нормализации.
    """

    def __init__(self, strategy: UnitNormalizerStrategy = None):
        """
        Args:
            strategy: Стратегия нормализации.
                     По умолчанию: RussianUnitNormalizer
        """
        self.strategy = strategy or RussianUnitNormalizer()

    def normalize(self, unit: str) -> str:
        """
        Нормализация единицы через стратегию.

        Args:
            unit: Исходная единица

        Returns:
            str: Нормализованная единица

        Example:
            >>> normalizer = UnitNormalizer()
            >>> normalizer.normalize("м²")
            'м2'
        """
        return self.strategy.normalize(unit)

    def normalize_set(self, units: set) -> set:
        """
        Нормализация набора единиц.

        Args:
            units: Набор исходных единиц

        Returns:
            set: Набор нормализованных единиц

        Example:
            >>> normalizer = UnitNormalizer()
            >>> normalizer.normalize_set({'м²', 'шт', 'кв.м'})
            {'м2', 'шт'}
        """
        return {self.normalize(u) for u in units if u}
