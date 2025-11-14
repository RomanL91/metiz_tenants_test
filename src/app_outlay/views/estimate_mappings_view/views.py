"""
Контроллер для API сохранения маппингов.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from app_outlay.exceptions import EstimateNotFoundError

from .serializers import (SaveMappingsRequestSerializer,
                          SaveMappingsResponseSerializer)
from .services import MappingSaveService


class EstimateMappingsSaveAPIView(APIView):
    """API сохранения сопоставлений ТК."""

    permission_classes = [IsAuthenticated]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.save_service = MappingSaveService()

    @extend_schema(
        summary="Сохранение сопоставлений ТК",
        request=SaveMappingsRequestSerializer,
        responses={
            200: SaveMappingsResponseSerializer,
            400: {"description": "Некорректные данные"},
            404: {"description": "Смета не найдена"},
        },
        tags=["Estimate Mappings"],
    )
    def post(self, request, estimate_id: int):
        serializer = SaveMappingsRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            stats = self.save_service.save_mappings(
                estimate_id=estimate_id,
                mappings=serializer.validated_data["mappings"],
                deletions=serializer.validated_data["deletions"],
            )

            return Response(
                {
                    "ok": True,
                    "created": stats["created"],
                    "updated": stats["updated"],
                    "deleted": stats["deleted"],
                    "total": stats["created"] + stats["updated"],
                },
                status=status.HTTP_200_OK,
            )

        except EstimateNotFoundError as e:
            return Response(
                {"ok": False, "error": str(e)},
                status=status.HTTP_404_NOT_FOUND,
            )

        except Exception as e:
            print(f"---- e ---- >>> {e}")
            return Response(
                {"ok": False, "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
