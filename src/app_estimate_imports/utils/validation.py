"""Утилиты валидации данных"""

import re
from typing import List

from .constants import NODE_TYPES, ROLE_IDS


class ValidationError(Exception):
    """Ошибка валидации"""

    pass


class DataValidator:
    """Валидатор данных импорта"""

    @staticmethod
    def validate_uid(uid: str) -> bool:
        """Проверяет корректность UID"""
        if not uid or not isinstance(uid, str):
            return False
        return len(uid.strip()) > 0

    @staticmethod
    def validate_label(label: str) -> bool:
        """Проверяет корректность метки"""

        return label in NODE_TYPES

    @staticmethod
    def validate_row_range(row_range: List[int]) -> bool:
        """Проверяет корректность диапазона строк"""
        if not isinstance(row_range, list) or len(row_range) != 2:
            return False

        start, end = row_range
        if not isinstance(start, int) or not isinstance(end, int):
            return False

        return start > 0 and end >= start

    @staticmethod
    def validate_group_name(name: str) -> bool:
        """Проверяет корректность имени группы"""
        if not name or not isinstance(name, str):
            return False
        return len(name.strip()) > 0

    @staticmethod
    def validate_color(color: str) -> bool:
        """Проверяет корректность цвета в формате hex"""
        if not color or not isinstance(color, str):
            return False
        return re.match(r"^#[0-9A-Fa-f]{6}$", color) is not None

    @classmethod
    def validate_group_data(
        cls, name: str, rows: List[List[int]], color: str = "#E0F7FA"
    ) -> None:
        """Валидирует данные группы, выбрасывает ValidationError при ошибках"""
        if not cls.validate_group_name(name):
            raise ValidationError("Некорректное имя группы")

        if not rows or not isinstance(rows, list):
            raise ValidationError("Диапазоны строк обязательны")

        for row_range in rows:
            if not cls.validate_row_range(row_range):
                raise ValidationError(f"Некорректный диапазон строк: {row_range}")

        if not cls.validate_color(color):
            raise ValidationError(f"Некорректный цвет: {color}")

    @classmethod
    def validate_schema_config(
        cls, col_roles: List[str], unit_allow_raw: str, require_qty: bool
    ) -> None:
        """Валидирует конфигурацию схемы"""

        if not isinstance(col_roles, list):
            raise ValidationError("col_roles должен быть списком")

        for role in col_roles:
            if role not in ROLE_IDS:
                raise ValidationError(f"Неизвестная роль колонки: {role}")

        if not isinstance(unit_allow_raw, str):
            raise ValidationError("unit_allow_raw должен быть строкой")

        if not isinstance(require_qty, bool):
            raise ValidationError("require_qty должен быть булевым значением")
