"""
Сервисный слой для анализа сметы.

Следует принципам:
- Single Responsibility: оркестрация анализа
- Database Optimization: минимизация запросов (N+1 prevention)
- Reusability: переиспользование компонентов
- Clear Flow: явный алгоритм работы
"""

from typing import Dict, List

from app_outlay.models import Estimate, GroupTechnicalCardLink
from app_outlay.views.export_excel_view.overhead_calculator import OverheadCalculator

from .exceptions import EstimateNotFoundError, NoTechnicalCardsError
from .calculators import (
    SalesCalculator,
    MetricsCalculator,
    PositionCalculation,
)
from .aggregators import (
    GroupAggregator,
    PositionAggregator,
    ChartDataBuilder,
)


class AnalysisService:
    """
    Сервис анализа сметы с детальными метриками.

    Ответственность:
    - Загрузка данных сметы (с оптимизацией запросов)
    - Подготовка контекста НР/НДС (через OverheadCalculator)
    - Расчёт всех метрик (через Calculators)
    - Агрегация данных (через Aggregators)
    - Формирование итогового результата
    """

    def __init__(
        self,
        estimate_id: int,
        *,
        overhead_calculator_cls=OverheadCalculator,
    ):
        """
        Args:
            estimate_id: ID сметы для анализа
                        overhead_calculator_cls: класс с методом calculate_overhead_context,
                по умолчанию используем OverheadCalculator из Excel экспорта.
        """
        self.estimate_id = estimate_id
        self.estimate = None
        self.tc_links = []
        self.overhead_context = None
        self._overhead_calculator_cls = overhead_calculator_cls
        self.positions: List[PositionCalculation] = []

    def analyze(self) -> Dict:
        """
        Полный анализ сметы.

        Алгоритм:
        1. Загрузка данных (estimate + tc_links с оптимизацией)
        2. Подготовка контекста НР/НДС
        3. Расчёт всех позиций
        4. Агрегация метрик
        5. Формирование результата

        Returns:
            Dict: Полные данные анализа
                {
                    'ok': True,
                    'has_data': True,
                    'summary': {...},
                    'price_breakdown': {...},
                    'top_positions': [...],
                    'groups_distribution': [...],
                    'overhead_breakdown': [...],
                    'materials_vs_works': {...},
                    'materials_vs_works_after_oh': {...}
                }

        Raises:
            EstimateNotFoundError: Смета не найдена
            NoTechnicalCardsError: В смете нет техкарт

        Example:
            >>> service = AnalysisService(estimate_id=123)
            >>> result = service.analyze()
            >>> result['summary']['base_total']
            125000.0
        """
        # Шаг 1: Загрузка данных
        self._load_estimate()
        self._load_technical_card_links()

        if not self.tc_links:
            raise NoTechnicalCardsError(estimate_id=self.estimate_id)

        # Шаг 2: Подготовка контекста НР/НДС
        self._prepare_overhead_context()

        # Шаг 3: Расчёт всех позиций
        self._calculate_positions()

        # Шаг 4: Агрегация метрик
        result = self._aggregate_results()

        return result

    def _load_estimate(self):
        """
        Загрузка сметы из БД.

        Оптимизация: prefetch overhead_cost_links.

        Raises:
            EstimateNotFoundError: Смета не найдена
        """
        try:
            self.estimate = Estimate.objects.prefetch_related(
                "overhead_cost_links__overhead_cost_container"
            ).get(id=self.estimate_id)
        except Estimate.DoesNotExist:
            raise EstimateNotFoundError(estimate_id=self.estimate_id)

    def _load_technical_card_links(self):
        """
        Загрузка связей техкарт с оптимизацией запросов.

        Оптимизация:
        - select_related для избежания N+1
        - order_by для стабильного порядка
        - only/defer для загрузки только нужных полей (опционально)
        """
        self.tc_links = list(
            GroupTechnicalCardLink.objects.filter(group__estimate=self.estimate)
            .select_related(
                "technical_card_version",
                "technical_card_version__card",
                "group",
            )
            .order_by("group__order", "order")
        )

    def _prepare_overhead_context(self):
        """
        Подготовка контекста НР и НДС.

        Переиспользует OverheadCalculator из export_excel_view.
        Это избегает дублирования логики расчёта НР.
        """
        self.overhead_context = (
            self._overhead_calculator_cls.calculate_overhead_context(
                estimate=self.estimate,
            )
        )

    def _calculate_positions(self):
        """
        Расчёт всех позиций сметы.

        Использует SalesCalculator для batch-обработки.
        Результаты сохраняются в self.positions.
        """
        self.positions = SalesCalculator.calculate_all_positions(
            tc_links=self.tc_links,
            overhead_context=self.overhead_context,
        )

    def _aggregate_results(self) -> Dict:
        """
        Агрегация всех результатов в итоговую структуру.

        Returns:
            Dict: Полные данные анализа
        """
        # Агрегация сумм
        base_mat = sum(p.base_materials for p in self.positions)
        base_work = sum(p.base_works for p in self.positions)
        base_total = base_mat + base_work

        sales_mat_no_oh = sum(p.sales_materials_no_oh for p in self.positions)
        sales_work_no_oh = sum(p.sales_works_no_oh for p in self.positions)
        sales_total_no_oh = sales_mat_no_oh + sales_work_no_oh

        sales_mat_with_oh = sum(p.sales_materials_with_oh for p in self.positions)
        sales_work_with_oh = sum(p.sales_works_with_oh for p in self.positions)
        sales_total_with_oh = sales_mat_with_oh + sales_work_with_oh

        overhead_total_by_calc = sales_total_with_oh - sales_total_no_oh

        # Сводная информация
        summary = MetricsCalculator.calculate_summary(
            positions=self.positions,
            overhead_total_by_calc=overhead_total_by_calc,
        )

        # Графики
        price_breakdown = ChartDataBuilder.build_price_breakdown(
            base_total=base_total,
            sales_no_oh=sales_total_no_oh,
            sales_with_oh=sales_total_with_oh,
        )

        materials_vs_works, materials_vs_works_after_oh = (
            ChartDataBuilder.build_materials_vs_works(
                base_mat=base_mat,
                base_work=base_work,
                sales_mat_no_oh=sales_mat_no_oh,
                sales_work_no_oh=sales_work_no_oh,
                sales_mat_with_oh=sales_mat_with_oh,
                sales_work_with_oh=sales_work_with_oh,
            )
        )

        # Топ позиций
        top_positions = PositionAggregator.get_top_positions(
            positions=self.positions,
            top_n=10,
        )

        # Группы
        groups_distribution = GroupAggregator.aggregate_by_groups(
            positions=self.positions
        )

        # Детализация НР
        overhead_breakdown = OverheadCalculator.get_overhead_breakdown(self.estimate)

        return {
            "ok": True,
            "has_data": True,
            "summary": summary,
            "price_breakdown": price_breakdown,
            "top_positions": top_positions,
            "groups_distribution": groups_distribution,
            "overhead_breakdown": overhead_breakdown,
            "materials_vs_works": materials_vs_works,
            "materials_vs_works_after_oh": materials_vs_works_after_oh,
        }

    def get_summary_only(self) -> Dict:
        """
        Быстрый расчёт только сводной информации (без группировок).

        Оптимизация: пропускаем агрегацию групп и топ-позиций.

        Returns:
            Dict: Только summary метрики

        Example:
            >>> service = AnalysisService(estimate_id=123)
            >>> summary = service.get_summary_only()
            >>> summary['base_total']
            125000.0
        """
        self._load_estimate()
        self._load_technical_card_links()

        if not self.tc_links:
            return {"ok": True, "has_data": False, "summary": {}}

        self._prepare_overhead_context()
        self._calculate_positions()

        # Только summary
        base_total = sum(p.base_total for p in self.positions)
        sales_total_no_oh = sum(p.sales_total_no_oh for p in self.positions)
        sales_total_with_oh = sum(p.sales_total_with_oh for p in self.positions)
        overhead_total_by_calc = sales_total_with_oh - sales_total_no_oh

        summary = MetricsCalculator.calculate_summary(
            positions=self.positions,
            overhead_total_by_calc=overhead_total_by_calc,
        )

        return {
            "ok": True,
            "has_data": True,
            "summary": summary,
        }
