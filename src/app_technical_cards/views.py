from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from app_technical_cards.models import TechnicalCard
from app_technical_cards.serializers import LiveCompositionSerializer


class TechnicalCardLiveCompositionView(APIView):
    """
    API endpoint для получения состава последней версии ТК
    с актуальными ценами из живых справочников.
    """

    def get(self, request, tc_id):
        tc = get_object_or_404(TechnicalCard, pk=tc_id)
        latest_version = tc.latest_version

        if not latest_version:
            return Response(
                {"detail": "У техкарты нет версий"}, status=status.HTTP_404_NOT_FOUND
            )

        # Получаем материалы и работы из версии
        materials = latest_version.material_items.select_related(
            "material", "material__unit_ref"
        ).all()

        works = latest_version.work_items.select_related("work", "work__unit_ref").all()

        # Формируем данные для сериализатора
        data = {
            "version_id": latest_version.id,
            "version_number": latest_version.version,
            "created_at": latest_version.created_at,
            "materials": materials,
            "works": works,
        }

        serializer = LiveCompositionSerializer(data)
        return Response(serializer.data)


# ==============================================================


from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework import serializers, status

from app_materials.models import Material
from app_technical_cards.models import (
    TechnicalCard,
    TechnicalCardVersion,
    TechnicalCardVersionMaterial,
    TechnicalCardVersionWork,
)
from app_works.models import Work


class _CompositionItemInSerializer(serializers.Serializer):
    ref_id = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=0)
    method = serializers.ChoiceField(
        choices=Work.CostingMethod.choices,
        required=False,
        default=Work.CostingMethod.SERVICE,
    )


class _ComposeVersionInSerializer(serializers.Serializer):
    note = serializers.CharField(allow_blank=True, required=False, default="")
    materials = _CompositionItemInSerializer(many=True, required=False)
    works = _CompositionItemInSerializer(many=True, required=False)


class TechnicalCardSaveNewVersionView(APIView):
    """
    POST /api/v1/technical-cards/<tc_id>/save-new-version/
    {
      "note": "Правки состава 31.10",
      "materials": [{"ref_id": 12, "qty": 3.5}, ...],
      "works":     [{"ref_id": 7,  "qty": 1   }, ...]
    }
    → 201: {"version_id": ..., "version": ...}
    """

    def post(self, request, tc_id):
        tc = get_object_or_404(TechnicalCard, pk=tc_id)
        ser = _ComposeVersionInSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        mat_items = data.get("materials", [])
        work_items = data.get("works", [])

        with transaction.atomic():
            latest = getattr(tc, "latest_version", None)

            new_ver = TechnicalCardVersion.objects.create(
                technical_card=tc,
                version=(latest.version + 1) if latest else 1,
                materials_markup_percent=tc.materials_markup_percent,
                works_markup_percent=tc.works_markup_percent,
                transport_costs_percent=tc.transport_costs_percent,
                materials_margin_percent=tc.materials_margin_percent,
                works_margin_percent=tc.works_margin_percent,
                note=data.get("note", ""),
            )

            mat_ids = [i["ref_id"] for i in mat_items]
            mats = {m.id: m for m in Material.objects.filter(id__in=mat_ids)}
            tcv_mats = []
            for idx, i in enumerate(mat_items, start=1):
                m = mats.get(i["ref_id"])
                if not m:
                    raise serializers.ValidationError(
                        {"materials": f"Material id={i['ref_id']} not found"}
                    )
                try:
                    method = w.resolve_calculation_method(i.get("method"))
                except ValidationError as exc:
                    raise serializers.ValidationError({"works": str(exc)}) from exc

                unit = w.get_unit_for_method(method)
                price = w.get_price_for_method(method)

                tcv_mats.append(
                    TechnicalCardVersionMaterial(
                        technical_card_version=new_ver,
                        material=m,
                        material_name=m.name,
                        unit_ref=m.unit_ref,
                        price_per_unit=m.price_per_unit,
                        qty_per_unit=i["qty"],
                        order=idx,
                    )
                )
            if tcv_mats:
                TechnicalCardVersionMaterial.objects.bulk_create(tcv_mats)

            work_ids = [i["ref_id"] for i in work_items]
            wrks = {w.id: w for w in Work.objects.filter(id__in=work_ids)}
            tcv_wrks = []
            for idx, i in enumerate(work_items, start=1):
                w = wrks.get(i["ref_id"])
                if not w:
                    raise serializers.ValidationError(
                        {"works": f"Work id={i['ref_id']} not found"}
                    )
                method = i.get("method") or Work.CostingMethod.SERVICE
                if not w.supports_calculation_method(method):
                    raise serializers.ValidationError(
                        {
                            "works": _(
                                "Работа id={id} не поддерживает метод расчёта '{method}'"
                            ).format(id=w.id, method=method)
                        }
                    )

                unit = w.get_unit_for_method(method)
                price = w.get_price_for_method(method)
                tcv_wrks.append(
                    TechnicalCardVersionWork(
                        technical_card_version=new_ver,
                        work=w,
                        work_name=w.name,
                        unit_ref=unit,
                        price_per_unit=price,
                        calculation_method=method,
                        qty_per_unit=i["qty"],
                        order=idx,
                    )
                )
            if tcv_wrks:
                TechnicalCardVersionWork.objects.bulk_create(tcv_wrks)

        return Response(
            {"version_id": new_ver.id, "version": new_ver.version},
            status=status.HTTP_201_CREATED,
        )


# =============================================================
from django.db.models import Q
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from app_materials.models import Material
from app_works.models import Work


class _SearchOutSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    unit = serializers.CharField(allow_blank=True, default="")
    price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)


class TechnicalCardSearchMaterialsView(APIView):
    """
    GET /api/v1/technical-cards/search/materials/?q=бетон&limit=10
    → [{"id":1,"name":"Бетон М300","unit":"м³","price":"19000.00"}, ...]
    """

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        try:
            limit = max(1, min(25, int(request.query_params.get("limit", "10"))))
        except ValueError:
            limit = 10

        qs = Work.objects.select_related("unit_ref", "labor_unit_ref")
        if hasattr(Material, "is_active"):
            qs = qs.filter(is_active=True)

        if q:
            cond = Q(name__icontains=q)
            if q.isdigit():
                cond |= Q(id=int(q))
            qs = qs.filter(cond)

        def _method_payload(work: Work, method_code: str) -> dict | None:
            if not work.supports_calculation_method(method_code):
                return None
            unit = work.get_unit_for_method(method_code)
            price = work.get_price_for_method(method_code)
            return {
                "code": method_code,
                "label": Work.CostingMethod(method_code).label,
                "unit": _unit_label(unit),
                "price": price,}
        
        works = list(qs.order_by("name")[:limit])

        data = []
        for work in works:
            methods = []
            for method_code in Work.CostingMethod.values:
                payload = _method_payload(work, method_code)
                if payload:
                    methods.append(payload)

            default_unit = methods[0]["unit"] if methods else _unit_label(work.unit_ref)
            default_price = methods[0]["price"] if methods else work.price_per_unit
            default_method = methods[0]["code"] if methods else Work.CostingMethod.SERVICE

            data.append(
                {
                    "id": work.id,
                    "name": work.name,
                    "unit": default_unit,
                    "price": default_price,
                    "default_method": default_method,
                    "methods": methods,
                }
            )

        return Response(data)


class TechnicalCardSearchWorksView(APIView):
    """
    GET /api/v1/technical-cards/search/works/?q=монтаж&limit=10
    → [{"id":7,"name":"Монтаж ...","unit":"ч","price":"3500.00"}, ...]
    """

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        try:
            limit = max(1, min(25, int(request.query_params.get("limit", "10"))))
        except ValueError:
            limit = 10

        qs = Work.objects.select_related("unit_ref")
        if hasattr(Work, "is_active"):
            qs = qs.filter(is_active=True)

        if q:
            cond = Q(name__icontains=q)
            if q.isdigit():
                cond |= Q(id=int(q))
            qs = qs.filter(cond)

        rows = qs.order_by("name").values(
            "id", "name", "price_per_unit", "unit_ref__symbol"
        )[:limit]

        data = [
            {
                "id": r["id"],
                "name": r["name"],
                "unit": r.get("unit_ref__symbol") or "",
                "price": r.get("price_per_unit"),
            }
            for r in rows
        ]
        return Response(data)


from decimal import Decimal
from typing import Any, Dict, List

from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response

# ===============================================================================================
from rest_framework.views import APIView

from .models import TechnicalCard
from .services_versioning import create_version_from_payload


class SaveNewVersionApiView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        card = get_object_or_404(TechnicalCard, pk=pk)
        data = request.data or {}
        mats = data.get("materials", [])
        works = data.get("works", [])
        ver = create_version_from_payload(card=card, materials=mats, works=works)
        return Response(
            {"ok": True, "version": ver.version, "id": ver.id},
            status=status.HTTP_201_CREATED,
        )


def _to_decimal(x) -> Decimal:
    try:
        return Decimal(str(x))
    except Exception:
        return Decimal("0")


def _unit_label(u) -> str:
    if not u:
        return ""
    for attr in ("symbol", "short_name", "name", "code"):
        val = getattr(u, attr, None)
        if val:
            return str(val)
    return ""


class LiveCompositionApiView(APIView):
    """
    Возвращает состав последней версии ТК:
    - массив materials и works с:
        id/ref_id, name, unit, qty_per_unit,
        version_price, live_price, price_changed, live_line_cost
    - totals.version / totals.live
    - version_number
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk: int):
        card = get_object_or_404(TechnicalCard, pk=pk)

        latest: TechnicalCardVersion | None = (
            TechnicalCardVersion.objects.filter(card=card)
            .order_by("-created_at")
            .select_related("card")
            .first()
        )

        if not latest:
            payload = {
                "version_number": 0,
                "materials": [],
                "works": [],
                "totals": {
                    "version": {"materials": 0, "works": 0, "total": 0},
                    "live": {"materials": 0, "works": 0, "total": 0},
                },
            }
            return Response(payload, status=status.HTTP_200_OK)

        mats_qs = (
            TechnicalCardVersionMaterial.objects.filter(technical_card_version=latest)
            .select_related("material", "unit_ref")
            .order_by("order", "id")
        )
        works_qs = (
            TechnicalCardVersionWork.objects.filter(technical_card_version=latest)
            .select_related("work", "unit_ref")
            .order_by("order", "id")
        )

        materials: List[Dict[str, Any]] = []
        works: List[Dict[str, Any]] = []

        mat_live_sum = Decimal("0")
        mat_ver_sum = Decimal("0")
        work_live_sum = Decimal("0")
        work_ver_sum = Decimal("0")

        for row in mats_qs:
            qty = _to_decimal(row.qty_per_unit)
            ver_price = _to_decimal(row.price_per_unit)
            live_price = _to_decimal(
                getattr(getattr(row, "material", None), "price_per_unit", ver_price)
            )
            line_live = qty * live_price
            line_ver = qty * ver_price

            mat_live_sum += line_live
            mat_ver_sum += line_ver

            materials.append(
                {
                    "id": getattr(row.material, "id", None),
                    "ref_id": getattr(row.material, "id", None),
                    "name": getattr(row, "material_name", None)
                    or getattr(row.material, "name", ""),
                    "unit": _unit_label(getattr(row, "unit_ref", None)),
                    "qty_per_unit": float(qty),
                    "version_price": float(ver_price),
                    "live_price": float(live_price),
                    "price_changed": live_price != ver_price,
                    "live_line_cost": float(line_live),
                }
            )

        for row in works_qs:
            qty = _to_decimal(row.qty_per_unit)
            ver_price = _to_decimal(row.price_per_unit)
            method = getattr(row, "calculation_method", Work.CostingMethod.SERVICE)
            live_raw_price = getattr(row.work, "get_price_for_method", None)
            if callable(live_raw_price):
                live_raw_price = row.work.get_price_for_method(method)
            else:
                live_raw_price = getattr(row.work, "price_per_unit", ver_price)
            live_price = _to_decimal(live_raw_price if live_raw_price is not None else ver_price)
            line_live = qty * live_price
            line_ver = qty * ver_price

            work_live_sum += line_live
            work_ver_sum += line_ver

            works.append(
                {
                    "id": getattr(row.work, "id", None),
                    "ref_id": getattr(row.work, "id", None),
                    "name": getattr(row, "work_name", None)
                    or getattr(row.work, "name", ""),
                    "unit": _unit_label(getattr(row, "unit_ref", None)),
                    "calculation_method": method,
                    "calculation_method_label": row.get_calculation_method_display(),
                    "qty_per_unit": float(qty),
                    "version_price": float(ver_price),
                    "live_price": float(live_price),
                    "price_changed": live_price != ver_price,
                    "live_line_cost": float(line_live),
                }
            )

        payload = {
            "version_number": latest.version,
            "materials": materials,
            "works": works,
            "totals": {
                "version": {
                    "materials": float(mat_ver_sum),
                    "works": float(work_ver_sum),
                    "total": float(mat_ver_sum + work_ver_sum),
                },
                "live": {
                    "materials": float(mat_live_sum),
                    "works": float(work_live_sum),
                    "total": float(mat_live_sum + work_live_sum),
                },
            },
        }
        return Response(payload, status=status.HTTP_200_OK)


# ===================================================================================================
from django.utils import timezone


class TechnicalCardDuplicateApiView(APIView):
    """
    POST /api/v1/technical-cards/<pk>/duplicate/
    → 201: {"id": <new_tc_id>, "name": "..."}
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        original_card = get_object_or_404(TechnicalCard, pk=pk)
        original_version = getattr(original_card, "latest_version", None)

        # Формируем имя с таймстемпом и обрезаем при необходимости
        ts = timezone.localtime().strftime("%Y%m%d-%H%M%S")  # например: 20251107-021530
        suffix = f" (копия {ts})"
        max_len = TechnicalCard._meta.get_field("name").max_length or 255
        base = original_card.name or ""
        new_name = (base[: max_len - len(suffix)]) + suffix

        with transaction.atomic():
            # 1) создаём копию "головы" ТК
            new_card = TechnicalCard.objects.create(
                name=new_name,
                unit_ref=original_card.unit_ref,
                materials_markup_percent=original_card.materials_markup_percent,
                works_markup_percent=original_card.works_markup_percent,
                transport_costs_percent=original_card.transport_costs_percent,
                materials_margin_percent=original_card.materials_margin_percent,
                works_margin_percent=original_card.works_margin_percent,
            )

            # 2) копируем последнюю версию и её состав (если версия есть)
            if original_version:
                new_version = TechnicalCardVersion.objects.create(
                    card=new_card,
                    materials_markup_percent=original_version.materials_markup_percent,
                    works_markup_percent=original_version.works_markup_percent,
                    transport_costs_percent=original_version.transport_costs_percent,
                    materials_margin_percent=original_version.materials_margin_percent,
                    works_margin_percent=original_version.works_margin_percent,
                    is_published=True,
                )

                # --- Материалы версии
                mat_items = original_version.material_items.select_related(
                    "material", "unit_ref"
                ).all()
                new_mats = []
                for item in mat_items:
                    mat_kwargs = dict(
                        technical_card_version=new_version,
                        material=item.material,
                        unit_ref=item.unit_ref,  # ВАЖНО: NOT NULL
                        qty_per_unit=item.qty_per_unit,
                        order=item.order,
                    )
                    if hasattr(item, "price_per_unit"):
                        mat_kwargs["price_per_unit"] = item.price_per_unit
                    new_mats.append(TechnicalCardVersionMaterial(**mat_kwargs))
                if new_mats:
                    TechnicalCardVersionMaterial.objects.bulk_create(new_mats)

                # --- Работы версии
                work_items = original_version.work_items.select_related(
                    "work", "unit_ref"
                ).all()
                new_works = []
                for item in work_items:
                    work_kwargs = dict(
                        technical_card_version=new_version,
                        work=item.work,
                        work_name=item.work_name,
                        unit_ref=item.unit_ref,  # ВАЖНО: NOT NULL
                        calculation_method=item.calculation_method,
                        qty_per_unit=item.qty_per_unit,
                        order=item.order,
                    )
                    if hasattr(item, "price_per_unit"):
                        work_kwargs["price_per_unit"] = item.price_per_unit
                    new_works.append(TechnicalCardVersionWork(**work_kwargs))
                if new_works:
                    TechnicalCardVersionWork.objects.bulk_create(new_works)

                # 3) пересчёт агрегатов по версии
                new_version.recalc_totals(save=True)

        return Response(
            {"id": new_card.id, "name": new_card.name},
            status=status.HTTP_201_CREATED,
        )
