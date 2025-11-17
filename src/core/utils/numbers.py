"""
Утилиты для работы с числовыми значениями.
"""

from decimal import Decimal, InvalidOperation
from typing import Any


def _quantizer(precision: int) -> Decimal:
    return Decimal("1").scaleb(-precision)


def round_decimal_value(value: Any, precision: int = 2) -> Decimal:
    """
    Округляет значение до указанной точности.

    Возвращает Decimal, чтобы сохранить точность для дальнейших операций.
    """

    decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    return decimal_value.quantize(_quantizer(precision))


def format_number_to_string(value: Any, precision: int = 2) -> str:
    """
    Приводит значение к строке с округлением чисел до указанной точности.

    Поддерживает числа и строковые представления чисел (включая формат с запятой).
    Прочие значения возвращаются как trimmed строки.
    """

    if value is None:
        return ""

    if isinstance(value, bool):
        return str(value).strip()

    try:
        decimal_value: Decimal | None = None

        if isinstance(value, (int, float, Decimal)):
            decimal_value = round_decimal_value(value, precision)
        elif isinstance(value, str):
            candidate = value.strip()
            if candidate == "":
                return ""
            normalized_candidate = (
                candidate.replace(",", ".", 1)
                if "," in candidate and "." not in candidate
                else candidate
            )
            decimal_value = round_decimal_value(normalized_candidate, precision)

        if decimal_value is not None:
            return str(decimal_value)
    except (InvalidOperation, ValueError):
        return str(value).strip()

    return str(value).strip()
