"""
Контроллеры для API НДС (пока моки).
"""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from app_outlay.exceptions import EstimateNotFoundError
from app_outlay.repositories import EstimateRepository

from .serializers import (
    ErrorResponseSerializer,
    VatSetRateRequestSerializer,
    VatStatusResponseSerializer,
    VatToggleRequestSerializer,
)
from .services import VatManagementService


class BaseVatAPIView(APIView):
    """Базовый класс для API НДС."""

    permission_classes = [IsAuthenticated]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.estimate_repo = EstimateRepository()
        self.service = VatManagementService()

    def handle_error(self, e: Exception):
        """Централизованная обработка ошибок."""
        if isinstance(e, EstimateNotFoundError):
            return Response(
                {"ok": False, "error": str(e)},
                status=status.HTTP_404_NOT_FOUND,
            )
        else:
            return Response(
                {"ok": False, "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class EstimateVatStatusAPIView(BaseVatAPIView):
    """API получения статуса НДС."""

    @extend_schema(
        summary="Получить статус НДС",
        responses={200: VatStatusResponseSerializer},
        tags=["Estimate VAT"],
    )
    def get(self, request, estimate_id: int):
        """Получить статус НДС сметы."""
        try:
            estimate = self.estimate_repo.get_by_id_or_raise(estimate_id)
            data = self.service.get_vat_status(estimate)
            return Response({"ok": True, **data}, status=status.HTTP_200_OK)
        except Exception as e:
            return self.handle_error(e)


class EstimateVatToggleAPIView(BaseVatAPIView):
    """API переключения НДС."""

    @extend_schema(
        summary="Включить/выключить НДС",
        request=VatToggleRequestSerializer,
        responses={200: VatStatusResponseSerializer},
        tags=["Estimate VAT"],
    )
    def post(self, request, estimate_id: int):
        """Переключить состояние НДС."""
        serializer = VatToggleRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            estimate = self.estimate_repo.get_by_id_or_raise(estimate_id)
            data = self.service.toggle_vat(
                estimate=estimate,
                is_active=serializer.validated_data["is_active"],
            )
            return Response({"ok": True, **data}, status=status.HTTP_200_OK)
        except Exception as e:
            return self.handle_error(e)


class EstimateVatSetRateAPIView(BaseVatAPIView):
    """API установки ставки НДС."""

    @extend_schema(
        summary="Установить ставку НДС",
        request=VatSetRateRequestSerializer,
        responses={200: VatStatusResponseSerializer},
        tags=["Estimate VAT"],
    )
    def post(self, request, estimate_id: int):
        """Установить ставку НДС."""
        serializer = VatSetRateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            estimate = self.estimate_repo.get_by_id_or_raise(estimate_id)
            data = self.service.set_vat_rate(
                estimate=estimate,
                rate=serializer.validated_data["rate"],
            )
            return Response({"ok": True, **data}, status=status.HTTP_200_OK)
        except Exception as e:
            return self.handle_error(e)
