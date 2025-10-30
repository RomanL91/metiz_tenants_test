"""
Калькуляторы для расчёта метрик сметы.

Следует принципам:
- Single Responsibility: каждый калькулятор — одна задача
- Immutability: не мутирует входные данные
- Batch Processing: обработка списков за один проход
"""

from decimal import Decimal
from typing import List, Dict, NamedTuple
from dataclasses import dataclass

from app_outlay.models import GroupTechnicalCardLink
from app_outlay.views.estimate_calc_view.utils_calc import (
    calc_for_tc,
    _base_costs_live,
    _dec,
)


class BaseCosts(NamedTuple):
    """Результат расчёта базовых затрат."""

    materials: Decimal
    works: Decimal

    @property
    def total(self) -> Decimal:
        return self.materials + self.works


class SalesCosts(NamedTuple):
    """Результат расчёта продажных цен."""

    materials: Decimal
    works: Decimal

    @property
    def total(self) -> Decimal:
        return self.materials + self.works


@dataclass
class PositionCalculation:
    """Результат расчёта одной позиции."""

    name: str
    group_name: str
    group_id: int
    qty: float
    unit: str
    base_materials: Decimal
    base_works: Decimal
    sales_materials_no_oh: Decimal
    sales_works_no_oh: Decimal
    sales_materials_with_oh: Decimal
    sales_works_with_oh: Decimal

    @property
    def base_total(self) -> Decimal:
        return self.base_materials + self.base_works

    @property
    def sales_total_no_oh(self) -> Decimal:
        return self.sales_materials_no_oh + self.sales_works_no_oh

    @property
    def sales_total_with_oh(self) -> Decimal:
        return self.sales_materials_with_oh + self.sales_works_with_oh


class BaseCalculator:
    """
    Калькулятор базовых затрат (себестоимость).

    Использует живые цены из техкарт через _base_costs_live.
    """

    @staticmethod
    def calculate_position_base(
        link: GroupTechnicalCardLink,
    ) -> BaseCosts:
        """
        Расчёт базовых затрат для одной позиции.

        Args:
            link: Связь группа-техкарта с количеством

        Returns:
            BaseCosts: Затраты на материалы и работы

        Example:
            >>> base = BaseCalculator.calculate_position_base(link)
            >>> base.materials
            Decimal('1250.00')
        """
        ver = link.technical_card_version
        if not ver:
            return BaseCosts(Decimal("0"), Decimal("0"))

        qty = _dec(getattr(link, "quantity", 1))
        base = _base_costs_live(ver)

        return BaseCosts(
            materials=_dec(base.mat) * qty,
            works=_dec(base.work) * qty,
        )

    @classmethod
    def calculate_total_base(
        cls,
        tc_links: List[GroupTechnicalCardLink],
    ) -> BaseCosts:
        """
        Batch-расчёт базовых затрат для списка позиций.

        Оптимизация: один проход по списку.

        Args:
            tc_links: Список связей группа-техкарта

        Returns:
            BaseCosts: Суммарные затраты

        Example:
            >>> base = BaseCalculator.calculate_total_base(links)
            >>> base.total
            Decimal('125000.00')
        """
        total_mat = Decimal("0")
        total_work = Decimal("0")

        for link in tc_links:
            costs = cls.calculate_position_base(link)
            total_mat += costs.materials
            total_work += costs.works

        return BaseCosts(materials=total_mat, works=total_work)


class SalesCalculator:
    """
    Калькулятор продажных цен.

    Использует calc_for_tc с поддержкой НР и НДС.
    Оптимизирован для batch-обработки.
    """

    @staticmethod
    def calculate_position_sales(
        link: GroupTechnicalCardLink,
        overhead_context: Dict = None,
    ) -> tuple[SalesCosts, SalesCosts]:
        """
        Расчёт продаж для одной позиции (с НР и без НР).

        Args:
            link: Связь группа-техкарта
            overhead_context: Контекст НР/НДС (или None)

        Returns:
            Tuple[SalesCosts без НР, SalesCosts с НР]

        Example:
            >>> no_oh, with_oh = SalesCalculator.calculate_position_sales(link, ctx)
            >>> no_oh.total
            Decimal('1500.00')
            >>> with_oh.total
            Decimal('1650.00')
        """
        ver = link.technical_card_version
        if not ver:
            empty = SalesCosts(Decimal("0"), Decimal("0"))
            return empty, empty

        qty = _dec(getattr(link, "quantity", 1))

        # Продажи без НР
        calc_no_oh, _ = calc_for_tc(ver.card_id, float(qty), overhead_context=None)
        sales_no_oh = SalesCosts(
            materials=_dec(calc_no_oh.get("PRICE_FOR_ALL_MATERIAL", 0)),
            works=_dec(calc_no_oh.get("PRICE_FOR_ALL_WORK", 0)),
        )

        # Продажи с НР (если есть контекст)
        if overhead_context:
            calc_with_oh, _ = calc_for_tc(
                ver.card_id, float(qty), overhead_context=overhead_context
            )
            sales_with_oh = SalesCosts(
                materials=_dec(calc_with_oh.get("PRICE_FOR_ALL_MATERIAL", 0)),
                works=_dec(calc_with_oh.get("PRICE_FOR_ALL_WORK", 0)),
            )
        else:
            sales_with_oh = sales_no_oh

        return sales_no_oh, sales_with_oh

    @classmethod
    def calculate_all_positions(
        cls,
        tc_links: List[GroupTechnicalCardLink],
        overhead_context: Dict = None,
    ) -> List[PositionCalculation]:
        """
        Batch-расчёт всех позиций сметы.

        Оптимизация: минимум обращений к calc_for_tc.

        Args:
            tc_links: Список связей (с prefetch group, tc_version, card)
            overhead_context: Контекст НР/НДС

        Returns:
            List[PositionCalculation]: Расчёты всех позиций

        Example:
            >>> positions = SalesCalculator.calculate_all_positions(links, ctx)
            >>> len(positions)
            150
        """
        results = []

        for link in tc_links:
            ver = link.technical_card_version
            if not ver:
                continue

            # База
            base = BaseCalculator.calculate_position_base(link)

            # Продажи
            sales_no_oh, sales_with_oh = cls.calculate_position_sales(
                link, overhead_context
            )

            results.append(
                PositionCalculation(
                    name=(ver.card.name or "")[:120],
                    group_name=link.group.name,
                    group_id=link.group.id,
                    qty=float(getattr(link, "quantity", 1)),
                    unit=ver.output_unit or "",
                    base_materials=base.materials,
                    base_works=base.works,
                    sales_materials_no_oh=sales_no_oh.materials,
                    sales_works_no_oh=sales_no_oh.works,
                    sales_materials_with_oh=sales_with_oh.materials,
                    sales_works_with_oh=sales_with_oh.works,
                )
            )

        return results


class MetricsCalculator:
    """
    Калькулятор метрик и KPI сметы.

    Вычисляет:
    - Средняя наценка
    - Процент НР
    - Распределение МАТ/РАБ
    """

    @staticmethod
    def calculate_markup_percent(sales: Decimal, base: Decimal) -> Decimal:
        """
        Расчёт процента наценки.

        Args:
            sales: Продажная цена
            base: Себестоимость

        Returns:
            Decimal: Процент наценки

        Example:
            >>> MetricsCalculator.calculate_markup_percent(
            ...     Decimal('1500'), Decimal('1000')
            ... )
            Decimal('50.00')
        """
        if base <= 0:
            return Decimal("0")
        return ((sales - base) / base * 100).quantize(Decimal("0.01"))

    @staticmethod
    def calculate_overhead_percent(
        sales_with_oh: Decimal, sales_no_oh: Decimal
    ) -> Decimal:
        """
        Расчёт процента НР от продаж.

        Args:
            sales_with_oh: Продажи с НР
            sales_no_oh: Продажи без НР

        Returns:
            Decimal: Процент НР

        Example:
            >>> MetricsCalculator.calculate_overhead_percent(
            ...     Decimal('1650'), Decimal('1500')
            ... )
            Decimal('10.00')
        """
        if sales_no_oh <= 0:
            return Decimal("0")
        overhead = sales_with_oh - sales_no_oh
        return (overhead / sales_no_oh * 100).quantize(Decimal("0.01"))

    @classmethod
    def calculate_summary(
        cls,
        positions: List[PositionCalculation],
        overhead_total_by_calc: Decimal,
    ) -> Dict:
        """
        Расчёт сводной информации по смете.

        Args:
            positions: Список рассчитанных позиций
            overhead_total_by_calc: Сумма НР (разница между с НР и без НР)

        Returns:
            Dict: Сводка метрик

        Example:
            >>> summary = MetricsCalculator.calculate_summary(positions, oh_amt)
            >>> summary['avg_markup_percent']
            42.5
        """
        # Агрегация
        base_mat = sum(p.base_materials for p in positions)
        base_work = sum(p.base_works for p in positions)
        base_total = base_mat + base_work

        sales_mat_no_oh = sum(p.sales_materials_no_oh for p in positions)
        sales_work_no_oh = sum(p.sales_works_no_oh for p in positions)
        sales_total_no_oh = sales_mat_no_oh + sales_work_no_oh

        sales_mat_with_oh = sum(p.sales_materials_with_oh for p in positions)
        sales_work_with_oh = sum(p.sales_works_with_oh for p in positions)
        sales_total_with_oh = sales_mat_with_oh + sales_work_with_oh

        # Метрики
        avg_markup = cls.calculate_markup_percent(sales_total_no_oh, base_total)
        overhead_percent = cls.calculate_overhead_percent(
            sales_total_with_oh, sales_total_no_oh
        )

        # НР: разница между "с НР" и "без НР"
        oh_mat = sales_mat_with_oh - sales_mat_no_oh
        oh_work = sales_work_with_oh - sales_work_no_oh

        return {
            "base_materials": float(base_mat),
            "base_works": float(base_work),
            "base_total": float(base_total),
            "final_materials": float(sales_mat_no_oh),
            "final_works": float(sales_work_no_oh),
            "final_before_overhead": float(sales_total_no_oh),
            "overhead_total": float(overhead_total_by_calc),
            "final_with_overhead": float(sales_total_with_oh),
            "avg_markup_percent": float(avg_markup),
            "overhead_percent": float(overhead_percent),
            "positions_count": len(positions),
            "oh_split": {
                "materials": float(oh_mat),
                "works": float(oh_work),
            },
        }
