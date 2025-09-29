"""Утилиты для работы с файлами"""

import hashlib
from typing import BinaryIO


class FileUtils:
    """Утилиты для работы с файлами"""

    @staticmethod
    def compute_sha256(file_obj: BinaryIO) -> str:
        """Вычисляет SHA256 хеш файла"""
        hash_sha256 = hashlib.sha256()

        # Читаем файл блоками для экономии памяти
        for chunk in iter(lambda: file_obj.read(4096), b""):
            hash_sha256.update(chunk)

        file_obj.seek(0)  # Возвращаем указатель в начало
        return hash_sha256.hexdigest()

    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """Форматирует размер файла в читаемый вид"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
