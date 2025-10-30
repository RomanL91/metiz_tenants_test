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


class OverheadCalculator:
    """
    Калькулятор накладных расходов и НДС.

    Ответственность:
    - Сбор активных НР из сметы
    - Расчёт средневзвешенных процентов МАТ/РАБ
    - Подготовка контекста для calc_for_tc
    - Добавление параметров НДС
    """

    @staticmethod
    def calculate_overhead_context(
        estimate,
        tc_links: List[GroupTechnicalCardLink],
    ) -> Optional[Dict]:
        """
        Подготовка контекста НР для расчётов.

        Алгоритм:
        1. Загрузка активных overhead_links
        2. Расчёт total_overhead_amt и weighted процентов
        3. Расчёт total_base_mat/work из техкарт
        4. Формирование overhead_context
        5. Добавление параметров НДС из настроек

        Args:
            estimate: Объект Estimate
            tc_links: QuerySet связей GroupTechnicalCardLink

        Returns:
            Dict или None: Контекст для передачи в calc_for_tc
                {
                    'total_base_mat': Decimal,
                    'total_base_work': Decimal,
                    'overhead_amount': Decimal,
                    'overhead_mat_pct': Decimal,
                    'overhead_work_pct': Decimal,
                    'vat_active': bool,
                    'vat_rate': int
                }

        Example:
            >>> ctx = OverheadCalculator.calculate_overhead_context(estimate, links)
            >>> ctx['vat_active']
            True
            >>> ctx['vat_rate']
            20
        """
        # Шаг 1: Загрузка активных НР
        overhead_links = estimate.overhead_cost_links.filter(
            is_active=True
        ).select_related("overhead_cost_container")

        total_overhead_amt = Decimal("0")
        amount_weighted_mat_pct = Decimal("0")
        amount_weighted_work_pct = Decimal("0")

        for ol in overhead_links:
            # Используем snapshot если есть, иначе текущие значения
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

            total_overhead_amt += amount
            amount_weighted_mat_pct += (mat_pct or 0) * amount
            amount_weighted_work_pct += (work_pct or 0) * amount

        # Если НР нет — контекст может быть None (но проверим НДС ниже)
        if total_overhead_amt <= 0:
            overhead_context = None
        else:
            # Шаг 2: Средневзвешенные проценты
            avg_mat_pct = amount_weighted_mat_pct / total_overhead_amt  # 0..100
            avg_work_pct = amount_weighted_work_pct / total_overhead_amt

            # Шаг 3: Расчёт базы из техкарт (живые цены)
            total_base_mat = Decimal("0")
            total_base_work = Decimal("0")

            for link in tc_links:
                ver = link.technical_card_version
                if not ver:
                    continue
                qty = _dec(getattr(link, "quantity", 1))
                base = _base_costs_live(ver)
                total_base_mat += _dec(base.mat) * qty
                total_base_work += _dec(base.work) * qty

            # Шаг 4: Формирование контекста
            overhead_context = {
                "total_base_mat": total_base_mat,
                "total_base_work": total_base_work,
                "overhead_amount": total_overhead_amt,
                "overhead_mat_pct": avg_mat_pct,  # в процентах (0..100)
                "overhead_work_pct": avg_work_pct,  # в процентах (0..100)
            }

        # Шаг 5: Добавление НДС в контекст
        settings = estimate.settings_data or {}
        vat_active = settings.get("vat_active", False)
        vat_rate = settings.get("vat_rate", 20)

        # Если НР нет, но НДС есть — создаём контекст только для НДС
        if overhead_context is None and vat_active:
            overhead_context = {}

        # Добавляем НДС если контекст существует
        if overhead_context is not None:
            overhead_context["vat_active"] = vat_active
            overhead_context["vat_rate"] = vat_rate

        return overhead_context

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
