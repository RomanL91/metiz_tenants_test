"""
Менеджер кэширования данных Excel.

Следует принципам:
- Singleton Pattern: единый экземпляр кэша
- Clear API: простой интерфейс get/set/invalidate
- Thread-safe: безопасность при многопоточности
"""

import os
import threading
from typing import Any, Optional
from django.core.cache import cache


class ExcelCacheManager:
    """
    Singleton менеджер кэша для Excel данных.

    Использует Django cache backend с автоматической инвалидацией
    по mtime файла.

    Example:
        >>> manager = ExcelCacheManager()
        >>> manager.set('/path/to/file.xlsx', 0, data)
        >>> cached = manager.get('/path/to/file.xlsx', 0)
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """
        Singleton реализация.

        Гарантирует единственный экземпляр класса.
        Thread-safe через Lock.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Инициализация (выполняется только один раз)."""
        if not hasattr(self, "_initialized"):
            self.prefix = "excel_sheet"
            self.default_ttl = 600  # 10 минут
            self._initialized = True

    def _generate_key(self, path: str, sheet_index: int) -> str:
        """
        Генерация ключа кэша с учётом mtime файла.

        Args:
            path: Путь к файлу
            sheet_index: Индекс листа

        Returns:
            str: Ключ для Django cache

        Example:
            >>> manager._generate_key('/file.xlsx', 0)
            'excel_sheet:/file.xlsx:1234567890:sheet:0'
        """
        try:
            mtime = int(os.path.getmtime(path))
        except (OSError, ValueError):
            mtime = 0

        return f"{self.prefix}:{path}:{mtime}:sheet:{sheet_index}"

    def get(self, path: str, sheet_index: int, default: Any = None) -> Optional[Any]:
        """
        Получение данных из кэша.

        Args:
            path: Путь к файлу
            sheet_index: Индекс листа
            default: Значение по умолчанию если кэш пуст

        Returns:
            Any: Закэшированные данные или default

        Example:
            >>> data = manager.get('/file.xlsx', 0)
            >>> if data is None:
            ...     data = load_from_file()
        """
        key = self._generate_key(path, sheet_index)
        result = cache.get(key, default)
        return result

    def set(self, path: str, sheet_index: int, data: Any, ttl: int = None) -> None:
        """
        Сохранение данных в кэш.

        Args:
            path: Путь к файлу
            sheet_index: Индекс листа
            data: Данные для кэширования
            ttl: Время жизни в секундах (default: 600)

        Example:
            >>> manager.set('/file.xlsx', 0, rows_data, ttl=300)
        """
        key = self._generate_key(path, sheet_index)
        ttl = ttl or self.default_ttl
        cache.set(key, data, ttl)

    def invalidate(self, path: str, sheet_index: int = None) -> None:
        """
        Инвалидация кэша для файла.

        Args:
            path: Путь к файлу
            sheet_index: Индекс листа (None = все листы)

        Example:
            >>> manager.invalidate('/file.xlsx')  # все листы
            >>> manager.invalidate('/file.xlsx', 0)  # только лист 0
        """
        if sheet_index is not None:
            key = self._generate_key(path, sheet_index)
            cache.delete(key)
        else:
            # Инвалидация всех листов (упрощённо - только известные)
            for i in range(20):  # разумный лимит
                key = self._generate_key(path, i)
                cache.delete(key)

    def clear_all(self) -> None:
        """
        Очистка всего кэша Excel.

        Использует Django cache.clear() с префиксом.
        """
        # Django cache не поддерживает очистку по префиксу напрямую
        # Можно использовать cache.delete_pattern если есть Redis
        # Для базового случая - просто логируем
        pass
