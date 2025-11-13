"""
Сервисный слой управления НР.
"""

from decimal import Decimal
from typing import Dict, List

from django.db import transaction

from app_outlay.models import Estimate, EstimateOverheadCostLink
from app_outlay.repositories import EstimateRepository, OverheadCostRepository
from app_overhead_costs.models import OverheadCostContainer


def _safe(val, default=0):
    return val if val is not None else default


def _link_base_snapshot(link):
    c = link.overhead_cost_container
    return _safe(link.snapshot_total_amount, _safe(c.total_amount, Decimal("0")))


def _link_pct_mat(link):
    c = link.overhead_cost_container
    return _safe(
        link.snapshot_materials_percentage,
        _safe(c.materials_percentage, Decimal("0")),
    )


def _link_pct_work(link):
    c = link.overhead_cost_container
    return _safe(
        link.snapshot_works_percentage,
        _safe(c.works_percentage, Decimal("0")),
    )


def _max_order_for_estimate(est):
    from django.db.models import Max

    return (
        EstimateOverheadCostLink.objects.filter(estimate=est).aggregate(m=Max("order"))[
            "m"
        ]
        or 0
    )


class OverheadAggregationService:
    """Сервис агрегации данных НР для отображения."""

    def __init__(self, overhead_repo: OverheadCostRepository = None):
        self.overhead_repo = overhead_repo or OverheadCostRepository()

    def get_grouped_payload(self, estimate: Estimate) -> Dict:
        """
        Агрегация НР по контейнерам.

        Одна строка на контейнер:
        - quantity = кол-во ссылок
        - is_active = есть ли активные
        - суммы по активным
        """
        links_qs = (
            EstimateOverheadCostLink.objects.filter(estimate=estimate)
            .select_related("overhead_cost_container")
            .order_by("order", "id")
        )

        groups = {}  # container_id -> dict

        for link in links_qs:
            cid = link.overhead_cost_container_id
            g = groups.get(cid)

            if not g:
                g = {
                    "rep": link,
                    "links": [],
                    "count": 0,
                    "active_count": 0,
                    "snap_sum": Decimal("0"),
                    "snap_sum_active": Decimal("0"),
                    "w_mat": Decimal("0"),
                    "w_work": Decimal("0"),
                    "has_changes": False,
                }
                groups[cid] = g

            g["links"].append(link)
            g["count"] += 1
            base_snap = _link_base_snapshot(link)
            g["snap_sum"] += base_snap
            g["has_changes"] = g["has_changes"] or bool(
                getattr(link, "has_changes", False)
            )

            if link.is_active:
                g["active_count"] += 1
                g["snap_sum_active"] += base_snap
                g["w_mat"] += _link_pct_mat(link) * base_snap
                g["w_work"] += _link_pct_work(link) * base_snap

        rows = []
        total_overhead_active = Decimal("0")
        total_w_mat = Decimal("0")
        total_w_work = Decimal("0")

        for cid, g in groups.items():
            rep = g["rep"]
            cont = rep.overhead_cost_container
            qty = g["count"]
            any_active = g["active_count"] > 0

            total_overhead_active += g["snap_sum_active"]
            total_w_mat += g["w_mat"]
            total_w_work += g["w_work"]

            rows.append(
                {
                    "id": rep.id,
                    "container_id": cont.id,
                    "name": cont.name,
                    "snapshot_total": float(g["snap_sum"] or 0),
                    "current_total": float(_safe(cont.total_amount, 0) * qty),
                    "materials_pct": float(_safe(cont.materials_percentage, 0)),
                    "works_pct": float(_safe(cont.works_percentage, 0)),
                    "quantity": int(qty),
                    "is_active": any_active,
                    "order": rep.order,
                    "applied_at": getattr(rep, "applied_at", None)
                    and rep.applied_at.isoformat(),
                    "has_changes": g["has_changes"],
                }
            )

        avg_mat = (
            total_w_mat / total_overhead_active
            if total_overhead_active
            else Decimal("0")
        )
        avg_work = (
            total_w_work / total_overhead_active
            if total_overhead_active
            else Decimal("0")
        )

        containers = [
            {
                "id": c.id,
                "name": c.name,
                "total": float(_safe(c.total_amount, 0)),
                "materials_pct": float(_safe(c.materials_percentage, 0)),
                "works_pct": float(_safe(c.works_percentage, 0)),
            }
            for c in OverheadCostContainer.objects.filter(is_active=True).order_by(
                "name"
            )
        ]

        return {
            "links": rows,
            "containers": containers,
            "overhead_total": float(total_overhead_active or 0),
            "avg_materials_pct": float(avg_mat or 0),
            "avg_works_pct": float(avg_work or 0),
        }


class OverheadManagementService:
    """Сервис управления НР сметы."""

    def __init__(
        self,
        estimate_repo: EstimateRepository = None,
        aggregation_service: OverheadAggregationService = None,
    ):
        self.estimate_repo = estimate_repo or EstimateRepository()
        self.aggregation_service = aggregation_service or OverheadAggregationService()

    def list_overheads(self, estimate_id: int) -> Dict:
        """Получить список НР сметы."""
        estimate = self.estimate_repo.get_by_id_or_raise(estimate_id)
        return self.aggregation_service.get_grouped_payload(estimate)

    @transaction.atomic
    def apply_overhead(self, estimate_id: int, container_id: int) -> Dict:
        """Добавить контейнер НР (создать одну связь)."""
        estimate = self.estimate_repo.get_by_id_or_raise(estimate_id)

        if not OverheadCostContainer.objects.filter(id=container_id).exists():
            raise ValueError("Контейнер НР не найден")

        max_order = _max_order_for_estimate(estimate)

        EstimateOverheadCostLink.objects.create(
            estimate=estimate,
            overhead_cost_container_id=container_id,
            order=max_order + 1,
            is_active=True,
        )

        return self.aggregation_service.get_grouped_payload(estimate)

    @transaction.atomic
    def toggle_overhead(self, estimate_id: int, link_id: int, is_active: bool) -> Dict:
        """Переключить активность всей группы НР."""
        estimate = self.estimate_repo.get_by_id_or_raise(estimate_id)

        link = EstimateOverheadCostLink.objects.select_related(
            "overhead_cost_container"
        ).get(id=link_id, estimate=estimate)

        cid = link.overhead_cost_container_id

        # вариант оптимизирован, но не вызывае сигналы
        # EstimateOverheadCostLink.objects.filter(
        #     estimate=estimate, overhead_cost_container_id=cid
        # ).update(is_active=is_active)
        # Обновляем через .save() чтобы сработали сигналы
        links_to_update = EstimateOverheadCostLink.objects.filter(
            estimate=estimate, overhead_cost_container_id=cid
        )

        for lnk in links_to_update:
            lnk.is_active = is_active
            lnk.save(update_fields=["is_active"])

        return self.aggregation_service.get_grouped_payload(estimate)

    @transaction.atomic
    def delete_overhead(self, estimate_id: int, link_id: int) -> Dict:
        """Удалить всю группу НР."""
        estimate = self.estimate_repo.get_by_id_or_raise(estimate_id)

        link = EstimateOverheadCostLink.objects.select_related(
            "overhead_cost_container"
        ).get(id=link_id, estimate=estimate)

        cid = link.overhead_cost_container_id

        EstimateOverheadCostLink.objects.filter(
            estimate=estimate, overhead_cost_container_id=cid
        ).delete()

        return self.aggregation_service.get_grouped_payload(estimate)

    @transaction.atomic
    def set_overhead_quantity(
        self, estimate_id: int, link_id: int, quantity: int
    ) -> Dict:
        """Установить количество дублей НР."""
        estimate = self.estimate_repo.get_by_id_or_raise(estimate_id)

        link = EstimateOverheadCostLink.objects.select_related(
            "overhead_cost_container"
        ).get(id=link_id, estimate=estimate)

        cid = link.overhead_cost_container_id

        qs = EstimateOverheadCostLink.objects.filter(
            estimate=estimate, overhead_cost_container_id=cid
        ).order_by("order", "id")

        cur = qs.count()

        if cur < quantity:
            max_order = _max_order_for_estimate(estimate)
            to_add = quantity - cur
            bulk = [
                EstimateOverheadCostLink(
                    estimate=estimate,
                    overhead_cost_container_id=cid,
                    order=max_order + i + 1,
                    is_active=True,
                )
                for i in range(to_add)
            ]
            EstimateOverheadCostLink.objects.bulk_create(bulk)

            # bulk_create не вызывает сигналы, дёргаем вручную
            from app_outlay.signals import invalidate_overhead_cache_on_link_change

            if bulk:
                invalidate_overhead_cache_on_link_change(
                    sender=EstimateOverheadCostLink, instance=bulk[0], created=True
                )

        elif cur > quantity:
            to_del = cur - quantity
            ids_to_delete = list(qs.values_list("id", flat=True))[-to_del:]
            EstimateOverheadCostLink.objects.filter(id__in=ids_to_delete).delete()

        return self.aggregation_service.get_grouped_payload(estimate)
