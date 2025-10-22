from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Tuple, Dict, List

from django.db.models import F, Sum, DecimalField, Value, ExpressionWrapper
from django.db.models.functions import Coalesce

from app_technical_cards.models import TechnicalCard, TechnicalCardVersion


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


def _round2(x: Decimal) -> Decimal:
    """Округление до 2 знаков банковским правилом."""
    return _dec(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# --- МОДЕЛЬ ДАННЫХ -------------------------------------------------------------


@dataclass
class UnitCosts:
    """Стоимость на 1 ед. выпуска ТК (без учёта НР)."""

    mat: Decimal = Decimal("0")
    work: Decimal = Decimal("0")


# --- ДОСТАВАНИЕ ВЕРСИИ ТК ------------------------------------------------------


def _get_version(tc_or_ver_id: int) -> Optional[TechnicalCardVersion]:
    """
    Возвращает версию ТК по:
      - ID версии, если существует;
      - ИЛИ по ID карточки — последнюю (по id) версию.
    """
    ver = (
        TechnicalCardVersion.objects.filter(pk=tc_or_ver_id)
        .select_related("card")
        .first()
    )
    if ver:
        return ver

    # Иначе считаем, что передали ID TechnicalCard
    ver = (
        TechnicalCardVersion.objects.filter(card_id=tc_or_ver_id)
        .order_by("-id")
        .select_related("card")
        .first()
    )
    return ver


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


def _unit_costs_live(v: TechnicalCardVersion) -> UnitCosts:
    """
    Стоимость на 1 ед. выпуска ТК из живых цен с применением НАДБАВОК/ТРАНСПОРТА/МАРЖИ
    (НО БЕЗ НАКЛАДНЫХ РАСХОДОВ).
    """
    tc: Optional[TechnicalCard] = getattr(v, "card", None) or getattr(
        v, "technical_card", None
    )
    base = _base_costs_live(v)
    m_base, w_base = base.mat, base.work

    # Надбавки/транспорт/маржинальность из карточки (в процентах → доли)
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

    # 1) Надбавки + транспорт (на базу)
    m_total = m_base * (Decimal("1") + m_markup + transport)
    w_total = w_base * (Decimal("1") + w_markup + transport)

    # 2) Продажа (маржинальность)
    m_sale = m_total * (Decimal("1") + m_margin)
    w_sale = w_total * (Decimal("1") + w_margin)

    return UnitCosts(mat=m_sale, work=w_sale)


# --- ОСНОВНАЯ ФУНКЦИЯ ДЛЯ ТК ---------------------------------------------------


def calc_for_tc(
    tc_or_ver_id: int,
    qty,
    overhead_context: Dict[str, object] | None = None,
) -> Tuple[Dict[str, Decimal], List[str]]:
    """
    Калькуляция для одной ТК (по её живым ценам) с учётом накладных расходов.

    ПОРЯДОК:
      1) База по живым ценам (мат/раб) — используется для распределения НР.
      2) Применяем надбавки/транспорт к базе, затем маржу → получаем «продажные» цены МАТ и РАБ.
      3) Накладные расходы ДОБАВЛЯЕМ ПОСЛЕ маржи:
         • делим OH на корзины МАТ/РАБ по заданным %;
         • каждую корзину распределяем пропорционально базовой стоимости в своей категории.

    :param tc_or_ver_id: ID версии ТК или карточки (тогда берётся последняя версия)
    :param qty: количество использований ТК в смете (может быть Decimal/float/str/int)
    :param overhead_context: словарь:
        {
            "total_base_mat": Decimal,   # суммарная база МАТ по всей смете
            "total_base_work": Decimal,  # суммарная база РАБ по всей смете
            "overhead_amount": Decimal,  # общая сумма НР (денег)
            "overhead_mat_pct": Decimal, # доля НР на МАТ (в %)
            "overhead_work_pct": Decimal # доля НР на РАБ (в %)
        }
    :return: (calc: dict, order: list[str])
    """
    order = list(DEFAULT_ORDER)
    qty_dec = _dec(qty)

    ver = _get_version(tc_or_ver_id)
    if not ver:
        # Пустой ответ, если ТК/версия не найдены
        zero = _round2(Decimal("0"))
        calc = {
            RID_UNIT_PRICE_OF_MATERIAL: zero,
            RID_UNIT_PRICE_OF_WORK: zero,
            RID_UNIT_PRICE_OF_MATERIALS_AND_WORKS: zero,
            RID_PRICE_FOR_ALL_MATERIAL: zero,
            RID_PRICE_FOR_ALL_WORK: zero,
            RID_TOTAL_PRICE: zero,
        }
        return calc, order

    # 1) База по живым ценам — нужна для распределения НР
    base = _base_costs_live(ver)
    base_mat, base_work = base.mat, base.work

    # 2) «Продажные» цены без НР (надбавки/транспорт → маржа)
    sale = _unit_costs_live(ver)
    sale_mat, sale_work = sale.mat, sale.work

    # 3) Распределяем НР (ПОСЛЕ маржи) — считаем добавки на 1 ед.
    oh_mat = Decimal("0")
    oh_work = Decimal("0")

    if overhead_context:
        total_base_mat = _dec(overhead_context.get("total_base_mat", 0))
        total_base_work = _dec(overhead_context.get("total_base_work", 0))
        overhead_amount = _dec(overhead_context.get("overhead_amount", 0))
        overhead_mat_pct = _dec(overhead_context.get("overhead_mat_pct", 0))
        overhead_work_pct = _dec(overhead_context.get("overhead_work_pct", 0))

        if overhead_amount > 0:
            # 3.1) Разделяем OH на корзины МАТ/РАБ
            oh_mat_total = overhead_amount * (overhead_mat_pct / Decimal("100"))
            oh_work_total = overhead_amount * (overhead_work_pct / Decimal("100"))

            # 3.2) Внутри каждой корзины — распределение пропорционально базовой стоимости
            if total_base_mat > 0:
                oh_mat = base_mat * (oh_mat_total / total_base_mat)
            # если total_base_mat == 0 → вся мат-корзина не распределится (охранное поведение)
            if total_base_work > 0:
                oh_work = base_work * (oh_work_total / total_base_work)

    # 4) Готовые цены на 1 ед. (продажа + OH-прибавки ПОСЛЕ маржи)
    unit_mat = _round2(sale_mat + oh_mat)
    unit_work = _round2(sale_work + oh_work)
    unit_both = _round2(unit_mat + unit_work)

    # 5) Итоговые суммы по количеству
    sum_mat = _round2(unit_mat * qty_dec)
    sum_work = _round2(unit_work * qty_dec)
    total = _round2(unit_both * qty_dec)

    calc = {
        RID_UNIT_PRICE_OF_MATERIAL: unit_mat,
        RID_UNIT_PRICE_OF_WORK: unit_work,
        RID_UNIT_PRICE_OF_MATERIALS_AND_WORKS: unit_both,
        RID_PRICE_FOR_ALL_MATERIAL: sum_mat,
        RID_PRICE_FOR_ALL_WORK: sum_work,
        RID_TOTAL_PRICE: total,
    }
    return calc, order
