# utils_calc.py
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from app_technical_cards.models import (
    TechnicalCard,
    TechnicalCardVersion,
)

RID_UNIT_PRICE_OF_MATERIAL = "UNIT_PRICE_OF_MATERIAL"
RID_UNIT_PRICE_OF_WORK = "UNIT_PRICE_OF_WORK"
RID_UNIT_PRICE_OF_MATERIALS_AND_WORKS = "UNIT_PRICE_OF_MATERIALS_AND_WORKS"
RID_PRICE_FOR_ALL_MATERIAL = "PRICE_FOR_ALL_MATERIAL"
RID_PRICE_FOR_ALL_WORK = "PRICE_FOR_ALL_WORK"
RID_TOTAL_PRICE = "TOTAL_PRICE"

DEFAULT_ORDER = [
    RID_UNIT_PRICE_OF_MATERIAL,
    RID_UNIT_PRICE_OF_WORK,
    RID_UNIT_PRICE_OF_MATERIALS_AND_WORKS,
    RID_PRICE_FOR_ALL_MATERIAL,
    RID_PRICE_FOR_ALL_WORK,
    RID_TOTAL_PRICE,
]


def _dec(x) -> Decimal:
    try:
        return x if isinstance(x, Decimal) else Decimal(str(x))
    except Exception:
        return Decimal("0")


def _round2(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _resolve_version(tc_or_ver_id: int) -> Optional[TechnicalCardVersion]:
    """
    ВАЖНО: сначала трактуем как ID карточки (TechnicalCard),
    и только если карточки с таким id нет — как ID версии.
    Это предотвращает коллизии id между таблицами.
    """
    card = TechnicalCard.objects.filter(pk=tc_or_ver_id).first()
    if card:
        return (
            card.versions.filter(is_published=True).order_by("-version").first()
            or card.versions.order_by("-version").first()
        )
    # карточки нет — пробуем как id версии
    v = (
        TechnicalCardVersion.objects.filter(pk=tc_or_ver_id)
        .select_related("card")
        .first()
    )
    return v


@dataclass
class UnitCosts:
    mat: Decimal = Decimal("0")
    work: Decimal = Decimal("0")


def _unit_costs_live(v: TechnicalCardVersion) -> UnitCosts:
    """
    Стоимость на 1 ед. выпуска ТК СТРОГО по живым ценам из справочников.

    Логика:
    - Берём нормы расхода (qty_per_unit) из строк версии ТК
    - Цены берём ТОЛЬКО из живых справочников Material/Work
    - Если нет связи на справочник ИЛИ цена NULL → вклад = 0
    - НИКАКИХ фолбэков на снапшоты (price_per_unit из строк версии)
    """
    m_sum = Decimal("0")
    for mi in v.material_items.select_related("material").all():
        # Проверяем: есть ли связь И заполнена ли цена в живом справочнике
        if mi.material and mi.material.price_per_unit is not None:
            # ранее считали себестоимость, заменили на окончательную - маржинальную
            # live_price = _dec(mi.material.price_per_unit)
            margin_price = _dec(v.materials_sale_price_per_unit)
            qty = _dec(mi.qty_per_unit or 0)
            m_sum += margin_price * qty
        # Иначе: вклад этой строки = 0

    w_sum = Decimal("0")
    for wi in v.work_items.select_related("work").all():
        # Проверяем: есть ли связь И заполнена ли цена в живом справочнике
        if wi.work and wi.work.price_per_unit is not None:
            # live_price = _dec(wi.work.price_per_unit)
            margin_price = _dec(v.works_sale_price_per_unit)
            qty = _dec(wi.qty_per_unit or 0)
            w_sum += margin_price * qty
        # Иначе: вклад этой строки = 0

    return UnitCosts(mat=m_sum, work=w_sum)


def calc_for_tc(tc_or_ver_id: int, qty) -> tuple[dict, list[str]]:
    """
    Калькуляция для ТК по живым ценам справочников.

    Возвращает (calc_dict, order_list), где calc_dict содержит:
    - UNIT_PRICE_OF_MATERIAL: цена материалов на 1 ед. выпуска ТК
    - UNIT_PRICE_OF_WORK: цена работ на 1 ед. выпуска ТК
    - UNIT_PRICE_OF_MATERIALS_AND_WORKS: цена МАТ+РАБ на 1 ед.
    - PRICE_FOR_ALL_MATERIAL: итого материалы (× qty)
    - PRICE_FOR_ALL_WORK: итого работы (× qty)
    - TOTAL_PRICE: общая цена (× qty)
    """
    order = list(DEFAULT_ORDER)
    ver = _resolve_version(tc_or_ver_id)

    if not ver:
        # Версия не найдена — возвращаем нули
        zero = Decimal("0")
        return (
            {
                RID_UNIT_PRICE_OF_MATERIAL: zero,
                RID_UNIT_PRICE_OF_WORK: zero,
                RID_UNIT_PRICE_OF_MATERIALS_AND_WORKS: zero,
                RID_PRICE_FOR_ALL_MATERIAL: zero,
                RID_PRICE_FOR_ALL_WORK: zero,
                RID_TOTAL_PRICE: zero,
            },
            order,
        )

    qty_dec = _dec(qty)
    costs = _unit_costs_live(ver)

    # Цены на 1 ед. выпуска ТК
    unit_mat = _round2(costs.mat)
    unit_work = _round2(costs.work)
    unit_both = _round2(unit_mat + unit_work)

    # Итоговые суммы (× количество)
    sum_mat = _round2(unit_mat * qty_dec)
    sum_work = _round2(unit_work * qty_dec)
    total = _round2(unit_both * qty_dec)

    calc = {
        RID_UNIT_PRICE_OF_MATERIAL: unit_mat,  # ЦЕНА МАТ/ЕД
        RID_UNIT_PRICE_OF_WORK: unit_work,  # ЦЕНА РАБОТЫ/ЕД
        RID_UNIT_PRICE_OF_MATERIALS_AND_WORKS: unit_both,  # ЦЕНА МАТ+РАБ/ЕД
        RID_PRICE_FOR_ALL_MATERIAL: sum_mat,  # ИТОГО МАТЕРИАЛ
        RID_PRICE_FOR_ALL_WORK: sum_work,  # ИТОГО РАБОТА
        RID_TOTAL_PRICE: total,  # ОБЩАЯ ЦЕНА
    }
    return calc, order
