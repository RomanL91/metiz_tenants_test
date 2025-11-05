import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, List

from django.db import transaction
from django.utils import timezone

from app_technical_cards.models import (
    TechnicalCard,
    TechnicalCardVersion,
    TechnicalCardVersionMaterial,
    TechnicalCardVersionWork,
)
from app_materials.models import Material
from app_works.models import Work


TRIGGER_FIELDS = {
    "materials_markup_percent",
    "works_markup_percent",
    "transport_costs_percent",
    "materials_margin_percent",
    "works_margin_percent",
}


@dataclass
class ItemSpec:
    ref_id: int
    qty: Decimal


@dataclass
class CompositionPayload:
    materials: List[ItemSpec]
    works: List[ItemSpec]


def _to_decimal(x: Any) -> Decimal:
    if x is None:
        return Decimal("0")
    s = str(x).replace(" ", "").replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def parse_payload_from_hidden(raw: str | None) -> CompositionPayload:
    mats: List[ItemSpec] = []
    wrks: List[ItemSpec] = []
    if not raw:
        return CompositionPayload(mats, wrks)
    try:
        data = json.loads(raw)
    except Exception:
        data = {}
    for key, collector in (("materials", mats), ("works", wrks)):
        for it in data.get(key) or []:
            rid = it.get("ref_id") or it.get("id")
            qty = _to_decimal(it.get("qty"))
            if isinstance(rid, int) and qty >= 0:
                collector.append(ItemSpec(ref_id=rid, qty=qty))
    return CompositionPayload(mats, wrks)


def composition_payload_from_post(request) -> CompositionPayload:
    return parse_payload_from_hidden(request.POST.get("_tc_initial_composition"))


def _next_version_str() -> str:
    return timezone.now().strftime("%Y%m%d-%H%M%S")


@transaction.atomic
def create_version_from_payload(
    tc: TechnicalCard, payload: CompositionPayload
) -> TechnicalCardVersion:
    ver = TechnicalCardVersion.objects.create(
        card=tc,
        version=_next_version_str(),
        materials_markup_percent=tc.materials_markup_percent,
        works_markup_percent=tc.works_markup_percent,
        transport_costs_percent=tc.transport_costs_percent,
        materials_margin_percent=tc.materials_margin_percent,
        works_margin_percent=tc.works_margin_percent,
    )

    # материалы
    if payload.materials:
        mats = {
            m.pk: m
            for m in Material.objects.filter(
                pk__in=[i.ref_id for i in payload.materials]
            )
        }
        bulk = []
        for idx, i in enumerate(payload.materials, start=1):
            m = mats.get(i.ref_id)
            if not m:
                continue
            bulk.append(
                TechnicalCardVersionMaterial(
                    technical_card_version=ver,
                    material=m,
                    material_name=m.name,
                    unit_ref=m.unit_ref,
                    price_per_unit=m.price_per_unit,
                    qty_per_unit=i.qty,
                    order=idx,
                )
            )
        if bulk:
            TechnicalCardVersionMaterial.objects.bulk_create(bulk)

    # работы
    if payload.works:
        wrks = {
            w.pk: w
            for w in Work.objects.filter(pk__in=[i.ref_id for i in payload.works])
        }
        bulk = []
        for idx, i in enumerate(payload.works, start=1):
            w = wrks.get(i.ref_id)
            if not w:
                continue
            bulk.append(
                TechnicalCardVersionWork(
                    technical_card_version=ver,
                    work=w,
                    work_name=w.name,
                    unit_ref=w.unit_ref,
                    price_per_unit=w.price_per_unit,
                    qty_per_unit=i.qty,
                    order=idx,
                )
            )
        if bulk:
            TechnicalCardVersionWork.objects.bulk_create(bulk)

    # итоги
    ver.recalc_totals(save=True)
    return ver


@transaction.atomic
def create_version_from_latest(tc: TechnicalCard) -> TechnicalCardVersion:
    last = tc.latest_version
    if not last:
        return create_version_from_payload(tc, CompositionPayload([], []))

    ver = TechnicalCardVersion.objects.create(
        card=tc,
        version=_next_version_str(),
        materials_markup_percent=tc.materials_markup_percent,
        works_markup_percent=tc.works_markup_percent,
        transport_costs_percent=tc.transport_costs_percent,
        materials_margin_percent=tc.materials_margin_percent,
        works_margin_percent=tc.works_margin_percent,
    )

    # клон материалов
    for r in last.material_items.all():
        row = TechnicalCardVersionMaterial.objects.create(
            technical_card_version=ver,
            material=r.material,
            qty_per_unit=r.qty_per_unit,
            order=r.order,
        )
        # переносим снапшот-цену (иначе возьмётся текущая)
        if r.price_per_unit is not None:
            row.price_per_unit = r.price_per_unit
            row.save(update_fields=["price_per_unit"])

    # клон работ
    for r in last.work_items.all():
        row = TechnicalCardVersionWork.objects.create(
            technical_card_version=ver,
            work=r.work,
            qty_per_unit=r.qty_per_unit,
            order=r.order,
        )
        if r.price_per_unit is not None:
            row.price_per_unit = r.price_per_unit
            row.save(update_fields=["price_per_unit"])

    ver.recalc_totals(save=True)
    return ver


def composition_differs_from_latest(
    tc: TechnicalCard, payload: CompositionPayload
) -> bool:
    last = tc.latest_version
    if not last:
        return bool(payload.materials or payload.works)

    def norm(items):
        return sorted(
            [(i.ref_id, str(Decimal(i.qty).normalize())) for i in items],
            key=lambda t: (t[0], t[1]),
        )

    cur_m = norm(payload.materials)
    cur_w = norm(payload.works)

    last_m = []
    for r in last.material_items.all():
        last_m.append((r.material_id, str(Decimal(r.qty_per_unit).normalize())))
    last_m.sort(key=lambda t: (t[0], t[1]))

    last_w = []
    for r in last.work_items.all():
        last_w.append((r.work_id, str(Decimal(r.qty_per_unit).normalize())))
    last_w.sort(key=lambda t: (t[0], t[1]))

    return cur_m != last_m or cur_w != last_w


def handle_tc_save(tc: TechnicalCard, request, *, change: bool, changed_fields=None):
    """
    Хук для admin.save_model:
    - читаем скрытый состав,
    - решаем, нужно ли делать новую версию,
    - создаём из payload или клонируем последнюю (если менялись только проценты).
    """
    payload = composition_payload_from_post(request)
    created = None

    if payload.materials or payload.works:
        need = True
        if change:
            try:
                need = composition_differs_from_latest(tc, payload)
            except Exception:
                need = True
        if need:
            created = create_version_from_payload(tc, payload)
        else:
            if changed_fields and (TRIGGER_FIELDS & set(changed_fields)):
                created = create_version_from_latest(tc)
    else:
        if changed_fields and (TRIGGER_FIELDS & set(changed_fields)):
            created = create_version_from_latest(tc)

    return created
