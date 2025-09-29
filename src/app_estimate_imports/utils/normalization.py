"""Утилиты нормализации данных"""

import re
from typing import Set


class TextNormalizer:
    """Нормализатор текста"""

    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """Нормализует пробелы в тексте"""
        if not text:
            return ""
        text = str(text).strip()
        return re.sub(r"\s+", " ", text)

    @staticmethod
    def clean_cell_value(value) -> str:
        """Очищает значение ячейки"""
        if value is None:
            return ""
        return TextNormalizer.normalize_whitespace(str(value))


class UnitNormalizer:
    """Нормализатор единиц измерения"""

    # Паттерны для нормализации единиц
    UNIT_PATTERNS = {
        "м2": r"(м\^?2|м2|квм|мкв|квадратн\w*метр\w*)",
        "м3": r"(м\^?3|м3|кубм|мкуб|кубическ\w*метр\w*)",
        "шт": r"(шт|штука|штуки|штук)",
        "пм": r"(пм|погм|погонныйметр|погонных\s*метров)",
        "компл": r"(компл|комплект|комплекта|комплектов)",
    }

    @classmethod
    def normalize(cls, unit: str) -> str:
        """Нормализует единицу измерения"""
        if not unit:
            return ""

        # Базовая очистка
        clean = unit.lower().strip()
        clean = clean.replace("\u00b2", "2").replace("\u00b3", "3")
        compact = "".join(ch for ch in clean if ch not in " .,")

        # Поиск по паттернам
        for normalized, pattern in cls.UNIT_PATTERNS.items():
            if re.fullmatch(pattern, compact):
                return normalized

        return compact

    @classmethod
    def parse_allowed_units(cls, unit_allow_raw: str) -> Set[str]:
        """Парсит строку разрешенных единиц в множество"""
        if not unit_allow_raw:
            return set()

        units = set()
        for unit_str in unit_allow_raw.split(","):
            normalized = cls.normalize(unit_str)
            if normalized:
                units.add(normalized)

        return units
