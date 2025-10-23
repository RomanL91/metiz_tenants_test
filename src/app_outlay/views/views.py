from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from app_outlay.models import Estimate
from app_outlay.serializers.serializers import EstimateSettingsSerializer


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def estimate_settings(request, estimate_id):
    """
    Получение и обновление настроек конкретной сметы.

    GET /api/estimates/{estimate_id}/settings/
    Получить текущие настройки сметы.

    POST /api/estimates/{estimate_id}/settings/
    Полностью перезаписать настройки сметы.

    Пример GET ответа:
    {
        "id": 1,
        "name": "Смета объекта А",
        "settings_data": {
            "object_name": "Жилой комплекс",
            "vat_rate": 20
        }
    }

    Пример POST запроса:
    {
        "settings_data": {
            "object_name": "Новое название",
            "vat_rate": 20
        }
    }
    """
    estimate = get_object_or_404(Estimate, pk=estimate_id)

    if request.method == "GET":
        # Получение настроек
        serializer = EstimateSettingsSerializer(estimate)
        return Response(serializer.data)

    elif request.method == "POST":
        # Обновление настроек
        serializer = EstimateSettingsSerializer(
            estimate, data=request.data, partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
