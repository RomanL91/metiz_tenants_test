"""
Модуль управления НДС сметы.

Публичный API:
- EstimateVatStatusAPIView - получить статус НДС
- EstimateVatToggleAPIView - включить/выключить НДС
- EstimateVatSetRateAPIView - установить ставку НДС
"""

from .views import (
    EstimateVatStatusAPIView,
    EstimateVatToggleAPIView,
    EstimateVatSetRateAPIView,
)

__all__ = [
    "EstimateVatStatusAPIView",
    "EstimateVatToggleAPIView",
    "EstimateVatSetRateAPIView",
]
