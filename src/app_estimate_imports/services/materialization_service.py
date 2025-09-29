"""Сервис материализации смет из разметки"""

from .base_service import BaseService
from app_outlay.services_materialize import materialize_estimate_from_markup


class MaterializationService(BaseService):
    """Сервис для создания смет из размеченных данных"""

    def materialize_estimate(self, file_obj) -> bool:
        """Создает смету из разметки файла"""
        try:
            if not hasattr(file_obj, "markup"):
                self.add_error("Нет разметки для материализации")
                return False

            # Используем существующий сервис материализации

            estimate = materialize_estimate_from_markup(file_obj.markup)
            return estimate

        except Exception as e:
            self.add_error(f"Ошибка материализации: {e}")
            return False
