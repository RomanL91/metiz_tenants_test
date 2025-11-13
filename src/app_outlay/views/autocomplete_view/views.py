"""
Views (контроллеры) для автокомплита и batch-сопоставления технических карт.

Архитектура:
- Thin Controllers: минимум логики, максимум делегирования
- DRF APIView: используем стандартные DRF паттерны
- Clear Separation: валидация → сервис → ответ

Принципы:
- Single Responsibility: каждый view отвечает за один endpoint
- DRY: переиспользование сериализаторов и сервисов
- SOLID: зависимости через DI (сервисы передаются явно)
"""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    AutocompleteQuerySerializer,
    AutocompleteResultSerializer,
    BatchMatchRequestSerializer,
    BatchMatchResultSerializer,
)
from .services import AutocompleteService, TCMatchingService


class TechnicalCardAutocompleteView(APIView):
    """
    Поиск технических карт по названию (автокомплит).

    **Endpoint:** GET /api/outlay/autocomplete/

    **Query Parameters:**
    - q (required): поисковый запрос (мин. 1 символ)
    - limit (optional): максимальное кол-во результатов (1-100, default: 20)

    **Response Format:**
    ```json
    {
        "results": [
            {"id": 1, "text": "Установка окна ПВХ [шт]"},
            {"id": 2, "text": "Установка окна алюминиевого [шт]"}
        ]
    }
    ```

    **Use Case:**
    Используется для динамического автокомплита при выборе ТК
    в интерфейсе сопоставления сметы.

    **Permissions:**
    Требуется аутентификация (IsAuthenticated)

    **Performance:**
    - Оптимизирован с select_related для избежания N+1
    - Лимит результатов применяется на уровне БД
    - Загружаются только необходимые поля (id, name, unit)
    """

    permission_classes = [IsAuthenticated]

    # DRF Spectacular Schema (для автогенерации документации)
    @extend_schema(
        summary="Автокомплит технических карт",
        description=(
            "Поиск технических карт по частичному совпадению названия. "
            "Используется для динамического автокомплита в UI."
        ),
        parameters=[
            OpenApiParameter(
                name="q",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Поисковый запрос (мин. 1 символ)",
            ),
            OpenApiParameter(
                name="limit",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Макс. количество результатов (default: 20, max: 100)",
            ),
        ],
        responses={
            200: AutocompleteResultSerializer(many=True),
            400: OpenApiTypes.OBJECT,
        },
        tags=["Autocomplete"],
    )
    def get(self, request):
        """
        Обработка GET запроса автокомплита.

        Алгоритм:
        1. Валидация query параметров
        2. Вызов сервиса поиска
        3. Формирование ответа

        Args:
            request: DRF Request объект

        Returns:
            Response: DRF Response с результатами поиска

        Example:
            GET /api/outlay/autocomplete/?q=окно&limit=10

            Response 200:
            {
                "results": [
                    {"id": 123, "text": "Установка окна [шт]"}
                ]
            }
        """
        # Шаг 1: Валидация входных данных
        serializer = AutocompleteQuerySerializer(data=request.query_params)

        if not serializer.is_valid():
            return Response(
                {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
            )

        validated_data = serializer.validated_data
        query = validated_data["q"]
        limit = validated_data.get("limit", 20)

        # Шаг 2: Вызов сервиса (бизнес-логика)
        service = AutocompleteService()
        results = service.search_technical_cards(query=query, limit=limit)

        # Шаг 3: Формирование ответа
        return Response({"results": results}, status=status.HTTP_200_OK)


class TechnicalCardBatchMatchView(APIView):
    """
    Batch-сопоставление строк Excel с техническими картами.

    **Endpoint:** POST /api/outlay/autocomplete/batch-match/

    **Request Body:**
    ```json
    {
        "items": [
            {"row_index": 1, "name": "Установка окна", "unit": "шт"},
            {"row_index": 2, "name": "Штукатурка стен", "unit": "м2"}
        ]
    }
    ```

    **Response Format:**
    ```json
    {
        "results": [
            {
                "row_index": 1,
                "name": "Установка окна",
                "unit": "шт",
                "matched_tc_id": 123,
                "matched_tc_card_id": 123,
                "matched_tc_version_id": 456,
                "matched_tc_text": "Установка окна ПВХ",
                "similarity": 0.85
            },
            {
                "row_index": 2,
                "name": "Штукатурка стен",
                "unit": "м2",
                "matched_tc_id": null,
                "matched_tc_text": "",
                "similarity": 0.0
            }
        ]
    }
    ```

    **Use Case:**
    Автоматическое сопоставление всех строк импортированной сметы
    с базой технических карт. Используется алгоритм нечёткого поиска
    с учётом схожести названия и единиц измерения.

    **Permissions:**
    Требуется аутентификация (IsAuthenticated)

    **Limitations:**
    - Максимум 1000 элементов за один запрос
    - Каждый row_index должен быть уникальным

    **Performance:**
    - Batch-обработка минимизирует количество запросов к БД
    - Алгоритм сопоставления оптимизирован для больших объёмов
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Batch-сопоставление строк с ТК",
        description=(
            "Массовое сопоставление строк Excel с техническими картами. "
            "Использует алгоритм нечёткого поиска с анализом схожести "
            "названия и единиц измерения."
        ),
        request=BatchMatchRequestSerializer,
        responses={
            200: BatchMatchResultSerializer(many=True),
            400: OpenApiTypes.OBJECT,
        },
        tags=["Autocomplete"],
    )
    def post(self, request):
        """
        Обработка POST запроса batch-сопоставления.

        Алгоритм:
        1. Валидация request body
        2. Вызов сервиса сопоставления
        3. Формирование ответа

        Args:
            request: DRF Request объект

        Returns:
            Response: DRF Response с результатами сопоставления

        Example:
            POST /api/outlay/autocomplete/batch-match/
            Body: {"items": [{"row_index": 1, "name": "окно", "unit": "шт"}]}

            Response 200:
            {
                "results": [
                    {
                        "row_index": 1,
                        "name": "окно",
                        "unit": "шт",
                        "matched_tc_id": 123,
                        "matched_tc_text": "Установка окна ПВХ",
                        "similarity": 0.85
                    }
                ]
            }
        """
        # Шаг 1: Валидация входных данных
        serializer = BatchMatchRequestSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
            )

        validated_data = serializer.validated_data
        items = validated_data["items"]

        # Шаг 2: Вызов сервиса (бизнес-логика)
        service = TCMatchingService()
        results = service.batch_match_items(items=items)

        # Шаг 3: Формирование ответа
        return Response({"results": results}, status=status.HTTP_200_OK)
