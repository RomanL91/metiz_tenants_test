"""
Модуль автокомплита и сопоставления технических карт.

Обеспечивает:
- Поиск ТК по частичному совпадению названия
- Batch-сопоставление строк Excel с ТК через алгоритм нечёткого поиска
"""

from .views import TechnicalCardAutocompleteView, TechnicalCardBatchMatchView

__all__ = [
    "TechnicalCardAutocompleteView",
    "TechnicalCardBatchMatchView",
]
