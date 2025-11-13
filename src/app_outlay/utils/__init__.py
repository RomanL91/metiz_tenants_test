"""
Утилиты для работы с Excel файлами.

Обеспечивает:
- Чтение листов Excel с кэшированием
- Нормализация данных
- Оптимизированная работа с большими файлами
"""

from .excel_cache import ExcelCacheManager
from .excel_reader import ExcelSheetReader, ExcelWorkbookReader

__all__ = [
    "ExcelSheetReader",
    "ExcelWorkbookReader",
    "ExcelCacheManager",
]
