"""
Расчёт накладных расходов и НДС для экспорта.

Следует принципам:
- Single Responsibility: только расчёт НР/НДС
- Immutability: возвращает новый контекст, не мутирует данные
- Clear API: явный контракт методов
"""

from decimal import Decimal
from typing import Dict, Optional, List

from app_outlay.models import GroupTechnicalCardLink
from app_outlay.views.estimate_calc_view.utils_calc import _base_costs_live, _dec
from app_outlay.views.estimate_calc_view.services import OverheadContextService


class OverheadCalculator:
    """
    Калькулятор накладных расходов и НДС.

    Ответственность:
    - Сбор активных НР из сметы
    - Расчёт средневзвешенных процентов МАТ/РАБ
    - Подготовка контекста для calc_for_tc
    - Добавление параметров НДС
    """

    def __init__(self):
        self.context_service = OverheadContextService()

    @staticmethod
    def calculate_overhead_context(estimate):
        service = OverheadContextService()
        return service.calculate_context(estimate)

    @staticmethod
    def get_overhead_breakdown(estimate) -> List[Dict]:
        """
        Получение детализации НР для логирования/отладки.

        Args:
            estimate: Объект Estimate

        Returns:
            List[Dict]: Список контейнеров НР с деталями
                [
                    {
                        'name': str,
                        'total': float,
                        'materials_pct': float,
                        'works_pct': float
                    },
                    ...
                ]
        """
        overhead_links = estimate.overhead_cost_links.filter(
            is_active=True
        ).select_related("overhead_cost_container")

        breakdown = []
        for ol in overhead_links:
            amount = (
                _dec(ol.snapshot_total_amount)
                if ol.snapshot_total_amount is not None
                else _dec(ol.overhead_cost_container.total_amount)
            )
            mat_pct = (
                _dec(ol.snapshot_materials_percentage)
                if ol.snapshot_materials_percentage is not None
                else _dec(ol.overhead_cost_container.materials_percentage)
            )
            work_pct = (
                _dec(ol.snapshot_works_percentage)
                if ol.snapshot_works_percentage is not None
                else _dec(ol.overhead_cost_container.works_percentage)
            )

            breakdown.append(
                {
                    "name": ol.overhead_cost_container.name,
                    "total": float(amount),
                    "materials_pct": float(mat_pct or 0),
                    "works_pct": float(work_pct or 0),
                }
            )

        return breakdown
