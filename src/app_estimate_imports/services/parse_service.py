"""Сервис для операций парсинга"""

from app_estimate_imports.services.base_service import BaseService
from app_estimate_imports.services.services import parse_and_store


class ParseService(BaseService):
    """Сервис для парсинга файлов"""

    def parse_file(self, file_obj) -> bool:
        """Парсит один файл"""
        try:
            parse_and_store(file_obj)
            return True
        except Exception as e:
            self.add_error(f"Ошибка парсинга {file_obj.original_name}: {e!r}")
            return False

    def parse_multiple_files(self, files) -> tuple[int, int]:
        """Парсит несколько файлов, возвращает (успешных, неудачных)"""
        success_count = 0
        error_count = 0

        for file_obj in files:
            if self.parse_file(file_obj):
                success_count += 1
            else:
                error_count += 1

        return success_count, error_count
