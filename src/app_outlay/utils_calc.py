from dataclasses import dataclass
from decimal import Decimal
from typing import List

from django.db.models import F, Sum, DecimalField, Value, ExpressionWrapper
from django.db.models.functions import Coalesce

from app_technical_cards.models import TechnicalCardVersion


# --- КЛЮЧИ В РЕЗУЛЬТАТЕ -------------------------------------------------------

RID_UNIT_PRICE_OF_MATERIAL = "UNIT_PRICE_OF_MATERIAL"  # Цена материалов / 1 ед.
RID_UNIT_PRICE_OF_WORK = "UNIT_PRICE_OF_WORK"  # Цена работ / 1 ед.
RID_UNIT_PRICE_OF_MATERIALS_AND_WORKS = (
    "UNIT_PRICE_OF_MATERIALS_AND_WORKS"  # Мат+Раб / 1 ед.
)
RID_PRICE_FOR_ALL_MATERIAL = "PRICE_FOR_ALL_MATERIAL"  # Итого материалы (× qty)
RID_PRICE_FOR_ALL_WORK = "PRICE_FOR_ALL_WORK"  # Итого работы (× qty)
RID_TOTAL_PRICE = "TOTAL_PRICE"  # Итого сумма (× qty)

DEFAULT_ORDER: List[str] = [
    RID_UNIT_PRICE_OF_MATERIAL,
    RID_UNIT_PRICE_OF_WORK,
    RID_UNIT_PRICE_OF_MATERIALS_AND_WORKS,
    RID_PRICE_FOR_ALL_MATERIAL,
    RID_PRICE_FOR_ALL_WORK,
    RID_TOTAL_PRICE,
]


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---------------------------------------------------


def _dec(x) -> Decimal:
    """Надёжное преобразование к Decimal."""
    try:
        return x if isinstance(x, Decimal) else Decimal(str(x))
    except Exception:
        return Decimal("0")


# --- МОДЕЛЬ ДАННЫХ -------------------------------------------------------------


@dataclass
class UnitCosts:
    """Стоимость на 1 ед. выпуска ТК (без учёта НР)."""

    mat: Decimal = Decimal("0")
    work: Decimal = Decimal("0")


# --- БАЗА: «ЖИВЫЕ» ЦЕНЫ ИЗ СПРАВОЧНИКОВ ---------------------------------------


def _base_costs_live(v: TechnicalCardVersion) -> UnitCosts:
    """
    Базовая стоимость на 1 ед. выпуска ТК по живым ценам (БЕЗ надбавок/маржи/НР).
    Только чистая сумма материалов и работ из справочников.
    Используется как база для распределения НР.
    """

    # Материалы: сумма (qty_per_unit × material.price_per_unit)
    m_q = Coalesce(F("qty_per_unit"), Value(0))
    m_p = Coalesce(F("material__price_per_unit"), Value(0))
    m_line = ExpressionWrapper(
        m_q * m_p, output_field=DecimalField(max_digits=18, decimal_places=6)
    )
    m_base = v.material_items.select_related("material").annotate(
        line=m_line
    ).aggregate(
        s=Coalesce(
            Sum("line"),
            Value(0, output_field=DecimalField(max_digits=18, decimal_places=6)),
        )
    ).get(
        "s"
    ) or Decimal(
        "0"
    )

    # Работы: сумма (qty_per_unit × work.price_per_unit)
    w_q = Coalesce(F("qty_per_unit"), Value(0))
    w_p = Coalesce(F("work__price_per_unit"), Value(0))
    w_line = ExpressionWrapper(
        w_q * w_p, output_field=DecimalField(max_digits=18, decimal_places=6)
    )
    w_base = v.work_items.select_related("work").annotate(line=w_line).aggregate(
        s=Coalesce(
            Sum("line"),
            Value(0, output_field=DecimalField(max_digits=18, decimal_places=6)),
        )
    ).get("s") or Decimal("0")

    return UnitCosts(mat=_dec(m_base), work=_dec(w_base))
