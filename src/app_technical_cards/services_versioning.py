# src/app_technical_cards/services_versioning.py
from __future__ import annotations

from decimal import Decimal
from typing import Sequence
import logging

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

log = logging.getLogger("app_technical_cards.versioning")

PercentFields = (
    "materials_markup_percent",
    "works_markup_percent",
    "transport_costs_percent",
    "materials_margin_percent",
    "works_margin_percent",
)


def _next_version_value(card: TechnicalCard) -> str:
    # Строковый, монотонный таймстамп — не конфликтует с CharField в модели
    return timezone.now().strftime("%Y%m%d-%H%M%S")


def _snapshot_percents_from_card(card: TechnicalCard) -> dict:
    return {f: getattr(card, f) for f in PercentFields}


@transaction.atomic
def create_version_from_payload(
    *,
    card: TechnicalCard,
    materials: Sequence[dict],
    works: Sequence[dict],
    publish: bool = False,
) -> TechnicalCardVersion:
    log.debug(
        "create_version_from_payload(card_id=%s) START mats=%s works=%s",
        getattr(card, "id", None),
        len(materials or []),
        len(works or []),
    )
    print(
        "[TC] create_version_from_payload: card_id=",
        getattr(card, "id", None),
        " mats=",
        len(materials or []),
        " works=",
        len(works or []),
    )

    ver = TechnicalCardVersion.objects.create(
        card=card,
        version=_next_version_value(card),
        is_published=publish,
        **_snapshot_percents_from_card(card),
    )

    # Материалы
    if materials:
        mats = Material.objects.in_bulk([m["ref_id"] for m in materials])
        order = 1
        for m in materials:
            src = mats.get(m["ref_id"])
            if not src:
                log.warning("Material id=%s not found, skip", m["ref_id"])
                continue
            qty = Decimal(str(m.get("qty", "0")))
            TechnicalCardVersionMaterial.objects.create(
                technical_card_version=ver,
                material=src,
                material_name=src.name,
                unit_ref=src.unit_ref,
                qty_per_unit=qty,
                price_per_unit=src.price_per_unit,
                order=order,
            )
            order += 1

    # Работы
    if works:
        works_map = Work.objects.in_bulk([w["ref_id"] for w in works])
        order = 1
        for w in works:
            src = works_map.get(w["ref_id"])
            if not src:
                log.warning("Work id=%s not found, skip", w["ref_id"])
                continue
            qty = Decimal(str(w.get("qty", "0")))
            TechnicalCardVersionWork.objects.create(
                technical_card_version=ver,
                work=src,
                work_name=src.name,
                unit_ref=src.unit_ref,
                qty_per_unit=qty,
                price_per_unit=src.price_per_unit,
                order=order,
            )
            order += 1

    if hasattr(ver, "recalc_totals"):
        ver.recalc_totals(save=True)

    log.debug(
        "create_version_from_payload DONE: version_id=%s, version=%s",
        ver.id,
        ver.version,
    )
    print(
        "[TC] create_version_from_payload: DONE version_id=",
        ver.id,
        " version=",
        ver.version,
    )
    return ver


@transaction.atomic
def create_version_from_latest(
    *, card: TechnicalCard, publish: bool = False
) -> TechnicalCardVersion:
    log.debug("create_version_from_latest(card_id=%s) START", getattr(card, "id", None))
    print("[TC] create_version_from_latest: card_id=", getattr(card, "id", None))

    latest = (
        TechnicalCardVersion.objects.filter(card=card).order_by("-created_at").first()
    )
    ver = TechnicalCardVersion.objects.create(
        card=card,
        version=_next_version_value(card),
        is_published=publish,
        **_snapshot_percents_from_card(card),
    )
    if latest:
        mats = list(
            TechnicalCardVersionMaterial.objects.filter(
                technical_card_version=latest
            ).select_related("material", "unit_ref")
        )
        for m in mats:
            TechnicalCardVersionMaterial.objects.create(
                technical_card_version=ver,
                material=m.material,
                material_name=m.material_name,
                unit_ref=m.unit_ref,
                qty_per_unit=m.qty_per_unit,
                price_per_unit=m.price_per_unit,
                order=m.order,
            )
        works = list(
            TechnicalCardVersionWork.objects.filter(
                technical_card_version=latest
            ).select_related("work", "unit_ref")
        )
        for w in works:
            TechnicalCardVersionWork.objects.create(
                technical_card_version=ver,
                work=w.work,
                work_name=w.work_name,
                unit_ref=w.unit_ref,
                qty_per_unit=w.qty_per_unit,
                price_per_unit=w.price_per_unit,
                order=w.order,
            )

    if hasattr(ver, "recalc_totals"):
        ver.recalc_totals(save=True)

    log.debug(
        "create_version_from_latest DONE: version_id=%s, version=%s",
        ver.id,
        ver.version,
    )
    print(
        "[TC] create_version_from_latest: DONE version_id=",
        ver.id,
        " version=",
        ver.version,
    )
    return ver
