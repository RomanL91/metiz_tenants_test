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
RID_TOTAL_PRICE_WITHOUT_VAT = "TOTAL_PRICE_WITHOUT_VAT"  # Итого без НДС
RID_VAT_AMOUNT = "VAT_AMOUNT"  # Сумма НДС

DEFAULT_ORDER: List[str] = [
    RID_UNIT_PRICE_OF_MATERIAL,
    RID_UNIT_PRICE_OF_WORK,
    RID_UNIT_PRICE_OF_MATERIALS_AND_WORKS,
    RID_PRICE_FOR_ALL_MATERIAL,
    RID_PRICE_FOR_ALL_WORK,
    RID_TOTAL_PRICE_WITHOUT_VAT,
    RID_VAT_AMOUNT,
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
    Возвращает ПОСЛЕДНЮЮ ОПУБЛИКОВАННУЮ версию ТК.

    Логика:
    1. Если tc_or_ver_id - это ID TechnicalCard → берём последнюю опубликованную версию
    2. Если tc_or_ver_id - это ID конкретной TechnicalCardVersion → берём её карточку, затем последнюю версию

    ВАЖНО: Цены берутся из живых справочников, архитектура (qty) - из последней версии.
    """

    # Сначала пробуем найти версию по ID
    existing_version = (
        TechnicalCardVersion.objects.filter(pk=tc_or_ver_id)
        .select_related("card")
        .first()
    )

    if existing_version:
        # Нашли версию → берём её карточку и ищем последнюю опубликованную версию этой карточки
        card_id = existing_version.card_id
    else:
        # Не нашли версию → считаем что передали ID карточки
        card_id = tc_or_ver_id

    # Возвращаем ПОСЛЕДНЮЮ опубликованную версию карточки
    latest_version = (
        TechnicalCardVersion.objects.filter(card_id=card_id, is_published=True)
        .order_by("-created_at", "-id")
        .select_related("card")
        .first()
    )

    return latest_version


# --- БАЗА: «ЖИВЫЕ» ЦЕНЫ ИЗ СПРАВОЧНИКОВ ---------------------------------------


def _base_costs_live(v: TechnicalCardVersion) -> UnitCosts:
    """
    Базовая стоимость на 1 ед. выпуска ТК по ЖИВЫМ ценам (БЕЗ надбавок/маржи/НР).
    Архитектура (qty) из последней версии, цены из живых справочников.
    Используется как база для распределения НР.
    """

    # Материалы: сумма (qty_per_unit из версии × price_per_unit из ЖИВОГО справочника)
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

    # Работы: сумма (qty_per_unit из версии × price_per_unit из ЖИВОГО справочника)
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
    Стоимость на 1 ед. выпуска ТК с применением НАДБАВОК/ТРАНСПОРТА/МАРЖИ:
    - База: из _base_costs_live() (живые цены × qty из версии)
    - Проценты: из ЖИВОЙ карточки TechnicalCard (чтобы можно было менять без новой версии)
    """
    tc: Optional[TechnicalCard] = getattr(v, "card", None) or getattr(
        v, "technical_card", None
    )
    base = _base_costs_live(v)
    m_base, w_base = base.mat, base.work

    # Надбавки/транспорт/маржинальность из ЖИВОЙ карточки (в процентах → доли)
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
    Калькуляция для одной ТК (по её живым ценам) с учётом накладных расходов и НДС.

    ПОРЯДОК:
      1) База по живым ценам (мат/раб) — используется для распределения НР.
      2) Применяем надбавки/транспорт к базе, затем маржу → получаем «продажные» цены МАТ и РАБ.
      3) Накладные расходы ДОБАВЛЯЕМ ПОСЛЕ маржи.
         Распределение НР по ТК идёт по доле «база × количество» в своей категории:
             доля_i = (base_i × qty_i) / Σ(base_j × qty_j)
      4) НДС применяется ПОСЛЕДНИМ к итоговой сумме (TOTAL_PRICE).

      overhead_context (опционально) может содержать:
        {
            "total_base_mat": Decimal,    # Σ(база МАТ × qty) по всей смете
            "total_base_work": Decimal,   # Σ(база РАБ × qty) по всей смете
            "overhead_amount": Decimal,   # общая сумма НР (деньги)
            "overhead_mat_pct": Decimal,  # % НР на МАТ (0..100)
            "overhead_work_pct": Decimal, # % НР на РАБ (0..100)
            "include_self": bool,         # включить ли текущую строку в знаменатель Σ
            "vat_active": bool,           # НДС активен
            "vat_rate": int,              # ставка НДС (0-100%)
        }
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

    # 1) База по живым ценам — на 1 ед.
    base = _base_costs_live(ver)
    base_mat, base_work = base.mat, base.work

    # 2) «Продажные» цены без НР (на 1 ед.)
    sale = _unit_costs_live(ver)
    sale_mat, sale_work = sale.mat, sale.work

    # 3) Распределяем НР — СНАЧАЛА считаем добавку на ВСЮ строку (line OH),
    #    затем полученную сумму делим обратно на qty для цен/ед.
    oh_mat_line = Decimal("0")
    oh_work_line = Decimal("0")

    if overhead_context:
        total_base_mat = _dec(overhead_context.get("total_base_mat", 0))
        total_base_work = _dec(overhead_context.get("total_base_work", 0))
        overhead_amount = _dec(overhead_context.get("overhead_amount", 0))
        overhead_mat_pct = _dec(overhead_context.get("overhead_mat_pct", 0))
        overhead_work_pct = _dec(overhead_context.get("overhead_work_pct", 0))
        include_self = bool(overhead_context.get("include_self", False))

        if overhead_amount > 0 and qty_dec >= 0:
            # Корзины НР
            oh_mat_total = overhead_amount * (overhead_mat_pct / Decimal("100"))
            oh_work_total = overhead_amount * (overhead_work_pct / Decimal("100"))

            # Доли текущей строки в базах (с учётом кол-ва этой строки)
            base_mat_share = base_mat * qty_dec
            base_work_share = base_work * qty_dec

            # Знаменатель: Σ(база × qty) по смете; при необходимости включаем текущую строку
            denom_mat = total_base_mat + (
                base_mat_share if include_self else Decimal("0")
            )
            denom_work = total_base_work + (
                base_work_share if include_self else Decimal("0")
            )

            if denom_mat > 0 and base_mat_share > 0:
                oh_mat_line = base_mat_share * (oh_mat_total / denom_mat)

            if denom_work > 0 and base_work_share > 0:
                oh_work_line = base_work_share * (oh_work_total / denom_work)

    # 4) Цены / ед.: продажа + (НР/ед., если qty>0)
    add_mat_per_unit = (oh_mat_line / qty_dec) if qty_dec > 0 else Decimal("0")
    add_work_per_unit = (oh_work_line / qty_dec) if qty_dec > 0 else Decimal("0")

    unit_mat = _round2(sale_mat + add_mat_per_unit)
    unit_work = _round2(sale_work + add_work_per_unit)
    unit_both = _round2(unit_mat + unit_work)

    # 5) Итоги по количеству (точное сложение «продажа×qty + НР_строки»)
    sum_mat = _round2(sale_mat * qty_dec + oh_mat_line)
    sum_work = _round2(sale_work * qty_dec + oh_work_line)
    total_without_vat = _round2(sum_mat + sum_work)

    # 6) Применяем НДС к TOTAL_PRICE (последний шаг)
    vat_active = (
        overhead_context.get("vat_active", False) if overhead_context else False
    )
    vat_rate = overhead_context.get("vat_rate", 0) if overhead_context else 0

    vat_amount = Decimal("0")
    total_with_vat = total_without_vat

    if vat_active and vat_rate > 0:
        vat_amount = _round2(total_without_vat * (_dec(vat_rate) / Decimal("100")))
        total_with_vat = _round2(total_without_vat + vat_amount)

    calc = {
        RID_UNIT_PRICE_OF_MATERIAL: unit_mat,
        RID_UNIT_PRICE_OF_WORK: unit_work,
        RID_UNIT_PRICE_OF_MATERIALS_AND_WORKS: unit_both,
        RID_PRICE_FOR_ALL_MATERIAL: sum_mat,
        RID_PRICE_FOR_ALL_WORK: sum_work,
        RID_TOTAL_PRICE_WITHOUT_VAT: total_without_vat,
        RID_VAT_AMOUNT: vat_amount,
        RID_TOTAL_PRICE: total_with_vat,
    }
    return calc, order
