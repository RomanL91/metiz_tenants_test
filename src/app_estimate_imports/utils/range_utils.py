"""Утилиты для работы с диапазонами строк"""

from typing import List


class RangeUtils:
    """Утилиты для работы с диапазонами"""

    @staticmethod
    def ranges_cover(
        parent_ranges: List[List[int]], child_ranges: List[List[int]]
    ) -> bool:
        """Проверяет, что родительские диапазоны полностью покрывают дочерние"""
        for start, end in child_ranges:
            covered = any(
                p_start <= start and end <= p_end for p_start, p_end in parent_ranges
            )
            if not covered:
                return False
        return True

    @staticmethod
    def ranges_intersect(range1: List[int], range2: List[int]) -> bool:
        """Проверяет, пересекаются ли два диапазона"""
        start1, end1 = range1
        start2, end2 = range2
        return not (end1 < start2 or end2 < start1)

    @staticmethod
    def merge_ranges(ranges: List[List[int]]) -> List[List[int]]:
        """Объединяет пересекающиеся диапазоны"""
        if not ranges:
            return []

        # Сортируем по началу диапазона
        sorted_ranges = sorted(ranges, key=lambda x: x[0])
        merged = [sorted_ranges[0]]

        for current in sorted_ranges[1:]:
            last = merged[-1]

            # Если диапазоны пересекаются или смежные
            if current[0] <= last[1] + 1:
                # Расширяем последний диапазон
                merged[-1][1] = max(last[1], current[1])
            else:
                # Добавляем новый диапазон
                merged.append(current)

        return merged

    @staticmethod
    def point_in_ranges(point: int, ranges: List[List[int]]) -> bool:
        """Проверяет, попадает ли точка в какой-либо из диапазонов"""
        return any(start <= point <= end for start, end in ranges)
