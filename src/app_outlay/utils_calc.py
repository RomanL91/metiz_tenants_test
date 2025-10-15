from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.db.models.functions import Coalesce
from django.db.models import F, Sum, DecimalField, Value, ExpressionWrapper

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


def _base_costs_live(v: TechnicalCardVersion) -> UnitCosts:
    """
    Базовая стоимость на 1 ед. выпуска ТК по живым ценам (БЕЗ надбавок).
    Только чистая сумма материалов и работ из справочников.

    Используется для расчета накладных расходов.
    """
    # Материалы
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
            Value(0),
            output_field=DecimalField(max_digits=18, decimal_places=2),
        )
    ).get(
        "s"
    ) or Decimal(
        "0"
    )

    # Работы
    w_q = Coalesce(F("qty_per_unit"), Value(0))
    w_p = Coalesce(F("work__price_per_unit"), Value(0))
    w_line = ExpressionWrapper(
        w_q * w_p, output_field=DecimalField(max_digits=18, decimal_places=6)
    )
    w_base = v.work_items.select_related("work").annotate(line=w_line).aggregate(
        s=Coalesce(
            Sum("line"),
            Value(0),
            output_field=DecimalField(max_digits=18, decimal_places=2),
        )
    ).get("s") or Decimal("0")

    return UnitCosts(mat=m_base, work=w_base)


def _unit_costs_live(v: TechnicalCardVersion) -> UnitCosts:
    """
    Стоимость на 1 ед. выпуска ТК по ЖИВЫМ ценам из справочников (Material/Work).
    Порядок расчёта как в recalc_totals():
      1) База = сумма(qty_per_unit * live_price)
      2) Общая стоимость = база * (1 + markup% + transport%)  [транспорт ТОЛЬКО на базу]
      3) Цена продажи = общая стоимость * (1 + margin%)

    Возвращаем продажные цены за ед. выпуска: UnitCosts(mat=<materials_sale>, work=<works_sale>)

    ВНИМАНИЕ: Эта функция НЕ учитывает накладные расходы.
    Для расчета с НР используйте calc_for_tc() с параметром overhead_context.
    """
    # ------- 1) БАЗА по живым ценам -------
    base = _base_costs_live(v)
    m_base = base.mat
    w_base = base.work

    # ------- Проценты из «живой головы» ТК (а не из снапшота версии) -------
    tc = getattr(v, "card", None) or getattr(v, "technical_card", None)

    m_markup = (
        _dec(getattr(tc, "materials_markup_percent", 0)) / Decimal("100")
        if tc
        else Decimal("0")
    )
    w_markup = (
        _dec(getattr(tc, "works_markup_percent", 0)) / Decimal("100")
        if tc
        else Decimal("0")
    )
    transport = (
        _dec(getattr(tc, "transport_costs_percent", 0)) / Decimal("100")
        if tc
        else Decimal("0")
    )
    m_margin = (
        _dec(getattr(tc, "materials_margin_percent", 0)) / Decimal("100")
        if tc
        else Decimal("0")
    )
    w_margin = (
        _dec(getattr(tc, "works_margin_percent", 0)) / Decimal("100")
        if tc
        else Decimal("0")
    )

    # ------- 2) ОБЩАЯ СТОИМОСТЬ (надбавки + транспорт на базу) -------
    m_total = m_base * (Decimal("1") + m_markup + transport)
    w_total = w_base * (Decimal("1") + w_markup + transport)

    # ------- 3) ПРОДАЖА (маржинальность) -------
    m_sale = m_total * (Decimal("1") + m_margin)
    w_sale = w_total * (Decimal("1") + w_margin)

    return UnitCosts(mat=m_sale, work=w_sale)


def calc_for_tc(
    tc_or_ver_id: int, qty, overhead_context: dict = None
) -> tuple[dict, list[str]]:
    """
    Калькуляция для ТК по живым ценам справочников с учетом накладных расходов.

    :param tc_or_ver_id: ID карточки или версии ТК
    :param qty: количество
    :param overhead_context: контекст накладных расходов (опционально):
        {
            'total_base_mat': Decimal,     # общая база материалов всех ТК в смете
            'total_base_work': Decimal,    # общая база работ всех ТК в смете
            'overhead_amount': Decimal,    # сумма НР
            'overhead_mat_pct': Decimal,   # % НР на материалы (0-100)
            'overhead_work_pct': Decimal,  # % НР на работы (0-100)
        }

    Возвращает (calc_dict, order_list), где calc_dict содержит:
    - UNIT_PRICE_OF_MATERIAL: цена материалов на 1 ед. выпуска ТК (с НР и надбавками)
    - UNIT_PRICE_OF_WORK: цена работ на 1 ед. выпуска ТК (с НР и надбавками)
    - UNIT_PRICE_OF_MATERIALS_AND_WORKS: цена МАТ+РАБ на 1 ед.
    - PRICE_FOR_ALL_MATERIAL: итого материалы (× qty)
    - PRICE_FOR_ALL_WORK: итого работы (× qty)
    - TOTAL_PRICE: общая цена (× qty)

    Порядок расчета с НР:
    1. База (живые цены без надбавок)
    2. + Накладные расходы (пропорционально базе)
    3. × Надбавки ТК (markup, transport)
    4. × Маржинальность ТК (margin)
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

    # ------- 1) БАЗА (без надбавок ТК) -------
    base = _base_costs_live(ver)
    base_mat = base.mat
    base_work = base.work

    # ------- 2) ПРИМЕНЯЕМ НАКЛАДНЫЕ РАСХОДЫ К БАЗЕ -------
    oh_mat = Decimal("0")
    oh_work = Decimal("0")

    if overhead_context:
        total_base_mat = _dec(overhead_context.get("total_base_mat", 0))
        total_base_work = _dec(overhead_context.get("total_base_work", 0))
        overhead_amount = _dec(overhead_context.get("overhead_amount", 0))
        overhead_mat_pct = _dec(overhead_context.get("overhead_mat_pct", 0))
        overhead_work_pct = _dec(overhead_context.get("overhead_work_pct", 0))

        total_base = total_base_mat + total_base_work

        if total_base > 0 and overhead_amount > 0:
            # НР_процент = НР_сумма / общая_база_всех_ТК
            oh_percent = overhead_amount / total_base

            # НР на МАТ этой строки = база_МАТ × НР_процент × (% на материалы / 100)
            oh_mat = base_mat * oh_percent * (overhead_mat_pct / Decimal("100"))

            # НР на РАБ этой строки = база_РАБ × НР_процент × (% на работы / 100)
            oh_work = base_work * oh_percent * (overhead_work_pct / Decimal("100"))

    # База с учетом НР
    base_mat_with_oh = base_mat + oh_mat
    base_work_with_oh = base_work + oh_work

    # ------- 3) ПРИМЕНЯЕМ НАДБАВКИ ТК -------
    tc = getattr(ver, "card", None) or getattr(ver, "technical_card", None)

    m_markup = (
        _dec(getattr(tc, "materials_markup_percent", 0)) / Decimal("100")
        if tc
        else Decimal("0")
    )
    w_markup = (
        _dec(getattr(tc, "works_markup_percent", 0)) / Decimal("100")
        if tc
        else Decimal("0")
    )
    transport = (
        _dec(getattr(tc, "transport_costs_percent", 0)) / Decimal("100")
        if tc
        else Decimal("0")
    )
    m_margin = (
        _dec(getattr(tc, "materials_margin_percent", 0)) / Decimal("100")
        if tc
        else Decimal("0")
    )
    w_margin = (
        _dec(getattr(tc, "works_margin_percent", 0)) / Decimal("100")
        if tc
        else Decimal("0")
    )

    # Общая стоимость (надбавки + транспорт на базу с НР)
    m_total = base_mat_with_oh * (Decimal("1") + m_markup + transport)
    w_total = base_work_with_oh * (Decimal("1") + w_markup + transport)

    # ------- 4) ПРОДАЖА (маржинальность) -------
    m_sale = m_total * (Decimal("1") + m_margin)
    w_sale = w_total * (Decimal("1") + w_margin)

    # Цены на 1 ед. выпуска ТК
    unit_mat = _round2(m_sale)
    unit_work = _round2(w_sale)
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
