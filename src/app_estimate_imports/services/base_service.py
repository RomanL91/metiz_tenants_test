from abc import ABC
from typing import List

from django.contrib import messages
from django.http import HttpRequest


class BaseService(ABC):
    """Базовый класс для всех сервисов с общей функциональностью"""

    def __init__(self):
        self._errors: List[str] = []
        self._warnings: List[str] = []

    @property
    def has_errors(self) -> bool:
        return len(self._errors) > 0

    @property
    def errors(self) -> List[str]:
        return self._errors.copy()

    def add_error(self, message: str) -> None:
        self._errors.append(message)

    def add_warning(self, message: str) -> None:
        self._warnings.append(message)

    def clear_messages(self) -> None:
        self._errors.clear()
        self._warnings.clear()

    def add_messages_to_request(self, request: HttpRequest) -> None:
        """Добавляет накопленные сообщения"""
        for error in self._errors:
            messages.error(request, error)
        for warning in self._warnings:
            messages.warning(request, warning)
