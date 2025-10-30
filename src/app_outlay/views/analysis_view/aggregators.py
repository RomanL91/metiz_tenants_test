# path: src/app_outlay/views/analysis_view/aggregators.py
"""
Агрегаторы для группировки данных анализа.

Следует принципам:
- Single Responsibility: каждый агрегатор — один тип группировки
- Immutability: не мутирует входные данные
- Clear API: явные методы и типы
"""

from typing import List, Dict
from decimal import Decimal

from .calculators import PositionCalculation


class GroupAggregator:
    """
    Агрегатор данных по группам сметы.

    Группирует позиции по group_id (не склеивает одноимённые).
    """

    @staticmethod
    def aggregate_by_groups(
        positions: List[PositionCalculation],
    ) -> List[Dict]:
        """
        Агрегация позиций по группам (ID-based).

        Args:
            positions: Список рассчитанных позиций

        Returns:
            List[Dict]: Список групп с агрегированными данными,
                отсортированный по убыванию final_total

        Example:
            >>> groups = GroupAggregator.aggregate_by_groups(positions)
            >>> groups[0]
            {
                'id': 42,
                'name': 'Фундаментные работы',
                'base_total': 50000.0,
                'final_total': 65000.0
            }
        """
        groups_dict = {}

        for pos in positions:
            gid = pos.group_id

            if gid not in groups_dict:
                groups_dict[gid] = {
                    "id": gid,
                    "name": pos.group_name,
                    "base_total": Decimal("0"),
                    "final_total": Decimal("0"),
                }

            groups_dict[gid]["base_total"] += pos.base_total
            groups_dict[gid]["final_total"] += pos.sales_total_no_oh

        # Конвертируем в список и сортируем
        groups_list = [
            {
                "id": g["id"],
                "name": g["name"],
                "base_total": float(g["base_total"]),
                "final_total": float(g["final_total"]),
            }
            for g in groups_dict.values()
        ]

        groups_list.sort(key=lambda x: x["final_total"], reverse=True)
        return groups_list


class PositionAggregator:
    """
    Агрегатор для выборки топовых позиций.
    """

    @staticmethod
    def get_top_positions(
        positions: List[PositionCalculation],
        top_n: int = 10,
    ) -> List[Dict]:
        """
        Получение топ-N позиций по стоимости.

        Args:
            positions: Список рассчитанных позиций
            top_n: Количество позиций в топе

        Returns:
            List[Dict]: Топ позиций, отсортированные по убыванию total

        Example:
            >>> top = PositionAggregator.get_top_positions(positions, 5)
            >>> len(top)
            5
        """
        # Конвертируем в dict и сортируем
        positions_list = [
            {
                "name": p.name,
                "group": p.group_name,
                "qty": p.qty,
                "unit": p.unit,
                "base_mat": float(p.base_materials),
                "base_work": float(p.base_works),
                "final_mat": float(p.sales_materials_no_oh),
                "final_work": float(p.sales_works_no_oh),
                "total": float(p.sales_total_no_oh),
            }
            for p in positions
        ]

        positions_list.sort(key=lambda x: x["total"], reverse=True)
        return positions_list[:top_n]


class ChartDataBuilder:
    """
    Построитель данных для графиков.

    Форматирует данные в структуру, удобную для frontend-библиотек.
    """

    @staticmethod
    def build_price_breakdown(
        base_total: Decimal,
        sales_no_oh: Decimal,
        sales_with_oh: Decimal,
    ) -> Dict:
        """
        График: Себестоимость → Продажи → Итог с НР.

        Args:
            base_total: Общая себестоимость
            sales_no_oh: Продажи без НР
            sales_with_oh: Продажи с НР

        Returns:
            Dict: Данные для столбчатой диаграммы

        Example:
            >>> data = ChartDataBuilder.build_price_breakdown(
            ...     Decimal('100000'), Decimal('130000'), Decimal('143000')
            ... )
            >>> data['labels']
            ['Себестоимость', 'Продажи (без НР)', 'Итог (с НР)']
        """
        return {
            "labels": ["Себестоимость", "Продажи (без НР)", "Итог (с НР)"],
            "values": [
                float(base_total),
                float(sales_no_oh),
                float(sales_with_oh),
            ],
        }

    @staticmethod
    def build_materials_vs_works(
        base_mat: Decimal,
        base_work: Decimal,
        sales_mat_no_oh: Decimal,
        sales_work_no_oh: Decimal,
        sales_mat_with_oh: Decimal,
        sales_work_with_oh: Decimal,
    ) -> tuple[Dict, Dict]:
        """
        Графики: Материалы vs Работы (база и продажи).

        Args:
            base_mat: База материалы
            base_work: База работы
            sales_mat_no_oh: Продажи материалы (без НР)
            sales_work_no_oh: Продажи работы (без НР)
            sales_mat_with_oh: Продажи материалы (с НР)
            sales_work_with_oh: Продажи работы (с НР)

        Returns:
            Tuple[Dict база+продажи, Dict продажи с НР]

        Example:
            >>> base_vs_sales, after_oh = ChartDataBuilder.build_materials_vs_works(...)
            >>> base_vs_sales['labels']
            ['Материалы', 'Работы']
        """
        materials_vs_works = {
            "labels": ["Материалы", "Работы"],
            "base": [float(base_mat), float(base_work)],
            "final": [float(sales_mat_no_oh), float(sales_work_no_oh)],
        }

        materials_vs_works_after_oh = {
            "labels": ["Материалы", "Работы"],
            "values": [float(sales_mat_with_oh), float(sales_work_with_oh)],
        }

        return materials_vs_works, materials_vs_works_after_oh
