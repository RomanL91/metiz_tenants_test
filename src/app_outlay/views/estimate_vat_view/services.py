# path: src/app_outlay/views/estimate_vat_view/services.py
"""
Сервисный слой управления НДС.
"""

from typing import Dict
from django.db import transaction
from app_outlay.models import Estimate
from app_outlay.views.estimate_calc_view.services import OverheadContextService


class VatManagementService:
    """Сервис управления НДС сметы."""

    def get_vat_status(self, estimate: Estimate) -> Dict:
        """Получить статус НДС."""
        settings = estimate.settings_data or {}
        vat_active = settings.get("vat_active", False)
        vat_rate = settings.get("vat_rate", 20)

        return {
            "vat_active": vat_active,
            "vat_rate": vat_rate,
        }

    @transaction.atomic
    def toggle_vat(self, estimate: Estimate, is_active: bool) -> Dict:
        """Включить/выключить НДС."""
        # КРИТИЧНО: создаём НОВЫЙ словарь (иначе Django не видит изменения)
        settings = dict(estimate.settings_data or {})
        settings["vat_active"] = is_active

        # Присваиваем новый словарь
        estimate.settings_data = settings
        estimate.save(update_fields=["settings_data"])

        # КРИТИЧНО: очищаем кеш расчётов
        OverheadContextService.clear_cache()

        print(
            f"✅ НДС для сметы #{estimate.id}: {'ВКЛЮЧЕН' if is_active else 'ВЫКЛЮЧЕН'}"
        )
        print(f"   settings_data после сохранения: {estimate.settings_data}")

        return {
            "vat_active": is_active,
            "vat_rate": settings.get("vat_rate", 20),
        }

    @transaction.atomic
    def set_vat_rate(self, estimate: Estimate, rate: int) -> Dict:
        """Установить ставку НДС."""
        # КРИТИЧНО: создаём НОВЫЙ словарь
        settings = dict(estimate.settings_data or {})
        settings["vat_rate"] = rate

        # Присваиваем новый словарь
        estimate.settings_data = settings
        estimate.save(update_fields=["settings_data"])

        # КРИТИЧНО: очищаем кеш расчётов
        OverheadContextService.clear_cache()

        print(f"✅ Ставка НДС для сметы #{estimate.id}: {rate}%")
        print(f"   settings_data после сохранения: {estimate.settings_data}")

        return {
            "vat_active": settings.get("vat_active", False),
            "vat_rate": rate,
        }
