"""Утилиты для хеширования"""

import hashlib


class HashUtils:
    """Утилиты хеширования"""

    @staticmethod
    def short_hash(text: str, length: int = 8) -> str:
        """Создает короткий хеш от текста"""
        if not text:
            return ""

        hash_obj = hashlib.sha256(text.encode("utf-8"))
        return hash_obj.hexdigest()[:length]

    @staticmethod
    def node_id(sheet_index: int, tag: str, value: str) -> str:
        """Создает ID узла по параметрам"""
        return f"s{sheet_index}-{tag}-{HashUtils.short_hash(value)}"
