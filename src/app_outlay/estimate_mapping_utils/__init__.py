"""
Утилиты для детектирования и сопоставления техкарт в сметах.

Обеспечивает:
- Детектирование строк с техкартами в Excel
- Загрузку групп из annotation
- Распределение техкарт по группам
- Нормализация единиц измерения
"""

from .tc_detector import TechnicalCardDetector
from .group_loader import GroupAnnotationLoader
from .group_assigner import GroupTreeBuilder
from .unit_normalizer import UnitNormalizer, RussianUnitNormalizer

__all__ = [
    "TechnicalCardDetector",
    "GroupAnnotationLoader",
    "GroupTreeBuilder",
    "UnitNormalizer",
    "RussianUnitNormalizer",
]
