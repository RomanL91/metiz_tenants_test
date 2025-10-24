"""
Контроллеры для API накладных расходов.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema

from .serializers import (
    OverheadListResponseSerializer,
    OverheadApplyRequestSerializer,
    OverheadToggleRequestSerializer,
    OverheadDeleteRequestSerializer,
    OverheadQuantityRequestSerializer,
)
from .services import OverheadManagementService
from app_outlay.exceptions import EstimateNotFoundError


class BaseOverheadAPIView(APIView):
    """Базовый класс для API НР."""

    permission_classes = [IsAuthenticated]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.service = OverheadManagementService()

    def handle_error(self, e: Exception):
        """Централизованная обработка ошибок."""
        if isinstance(e, EstimateNotFoundError):
            return Response(
                {"ok": False, "error": str(e)},
                status=status.HTTP_404_NOT_FOUND,
            )
        elif isinstance(e, ValueError):
            return Response(
                {"ok": False, "error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        else:
            return Response(
                {"ok": False, "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class EstimateOverheadsListAPIView(BaseOverheadAPIView):
    """API списка НР."""

    @extend_schema(
        summary="Список НР сметы",
        responses={200: OverheadListResponseSerializer},
        tags=["Estimate Overheads"],
    )
    def get(self, request, estimate_id: int):
        try:
            data = self.service.list_overheads(estimate_id)
            return Response({"ok": True, **data}, status=status.HTTP_200_OK)
        except Exception as e:
            return self.handle_error(e)


class EstimateOverheadsApplyAPIView(BaseOverheadAPIView):
    """API добавления НР."""

    @extend_schema(
        summary="Добавить НР",
        request=OverheadApplyRequestSerializer,
        responses={200: OverheadListResponseSerializer},
        tags=["Estimate Overheads"],
    )
    def post(self, request, estimate_id: int):
        serializer = OverheadApplyRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            data = self.service.apply_overhead(
                estimate_id=estimate_id,
                container_id=serializer.validated_data["container_id"],
            )
            return Response({"ok": True, **data}, status=status.HTTP_200_OK)
        except Exception as e:
            return self.handle_error(e)


class EstimateOverheadsToggleAPIView(BaseOverheadAPIView):
    """API переключения активности НР."""

    @extend_schema(
        summary="Переключить активность НР",
        request=OverheadToggleRequestSerializer,
        responses={200: OverheadListResponseSerializer},
        tags=["Estimate Overheads"],
    )
    def post(self, request, estimate_id: int):
        serializer = OverheadToggleRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            data = self.service.toggle_overhead(
                estimate_id=estimate_id,
                link_id=serializer.validated_data["link_id"],
                is_active=serializer.validated_data["is_active"],
            )
            return Response({"ok": True, **data}, status=status.HTTP_200_OK)
        except Exception as e:
            return self.handle_error(e)


class EstimateOverheadsDeleteAPIView(BaseOverheadAPIView):
    """API удаления НР."""

    @extend_schema(
        summary="Удалить НР",
        request=OverheadDeleteRequestSerializer,
        responses={200: OverheadListResponseSerializer},
        tags=["Estimate Overheads"],
    )
    def post(self, request, estimate_id: int):
        serializer = OverheadDeleteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            data = self.service.delete_overhead(
                estimate_id=estimate_id,
                link_id=serializer.validated_data["link_id"],
            )
            return Response({"ok": True, **data}, status=status.HTTP_200_OK)
        except Exception as e:
            return self.handle_error(e)


class EstimateOverheadsQuantityAPIView(BaseOverheadAPIView):
    """API изменения количества НР."""

    @extend_schema(
        summary="Изменить количество НР",
        request=OverheadQuantityRequestSerializer,
        responses={200: OverheadListResponseSerializer},
        tags=["Estimate Overheads"],
    )
    def post(self, request, estimate_id: int):
        serializer = OverheadQuantityRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            data = self.service.set_overhead_quantity(
                estimate_id=estimate_id,
                link_id=serializer.validated_data["link_id"],
                quantity=serializer.validated_data["quantity"],
            )
            return Response({"ok": True, **data}, status=status.HTTP_200_OK)
        except Exception as e:
            return self.handle_error(e)
