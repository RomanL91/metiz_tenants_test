"""
Контроллер для API расчёта технических карт в контексте сметы.

Ответственность:
- Обработка HTTP запросов
- Валидация входных данных
- Делегирование в сервисный слой
- Формирование HTTP ответов

Принципы:
- Thin Controller: минимум логики, максимум делегирования
- Single Responsibility: только обработка HTTP
- Error Handling: централизованная обработка ошибок
"""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from app_outlay.exceptions import (EstimateCalcException,
                                   EstimateNotFoundError,
                                   InvalidCalculationParamsError,
                                   TechnicalCardNotFoundError)
from app_outlay.views.estimate_calc_view.serializers import (
    ErrorResponseSerializer, EstimateCalcQuerySerializer,
    EstimateCalcResponseSerializer)
from app_outlay.views.estimate_calc_view.services import \
    EstimateCalculationFacade


class EstimateCalcAPIView(APIView):
    """
    API для расчёта показателей ТК с учётом накладных расходов сметы.

    **Endpoint:** GET /api/estimate/{estimate_id}/calc/

    **Query Parameters:**
    - tc (required): ID технической карты (card_id)
    - qty (required): Количество (поддерживает запятую и точку)

    **Response Format:**
    ```json
    {
        "ok": true,
        "calc": {
            "UNIT_PRICE_OF_MATERIAL": 150.50,
            "UNIT_PRICE_OF_WORK": 200.00,
            "UNIT_PRICE_OF_MATERIALS_AND_WORKS": 350.50,
            "PRICE_FOR_ALL_MATERIAL": 1505.00,
            "PRICE_FOR_ALL_WORK": 2000.00,
            "TOTAL_PRICE": 3505.00
        },
        "order": [
            "UNIT_PRICE_OF_MATERIAL",
            "UNIT_PRICE_OF_WORK",
            ...
        ]
    }
    ```

    **Use Case:**
    Используется для динамического пересчёта строк сметы при изменении
    количества или выборе ТК. Учитывает накладные расходы сметы.

    **Permissions:**
    Требуется аутентификация (IsAuthenticated)

    **Performance:**
    - Контекст НР кешируется в памяти (lru_cache)
    - Оптимизированные запросы к БД (select_related, prefetch_related)
    """

    permission_classes = [IsAuthenticated]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Dependency Injection: создаём фасад при инициализации view
        self.calc_facade = EstimateCalculationFacade()

    @extend_schema(
        summary="Расчёт показателей ТК с учётом НР",
        description=(
            "Рассчитывает показатели технической карты с учётом накладных расходов сметы. "
            "Возвращает стоимости на единицу и итоговые суммы с учётом количества."
        ),
        parameters=[
            OpenApiParameter(
                name="estimate_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                required=True,
                description="ID сметы",
            ),
            OpenApiParameter(
                name="tc",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description="ID технической карты (card_id)",
            ),
            OpenApiParameter(
                name="qty",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Количество (поддерживает запятую и точку)",
            ),
        ],
        responses={
            200: EstimateCalcResponseSerializer,
            400: ErrorResponseSerializer,
            404: ErrorResponseSerializer,
            500: ErrorResponseSerializer,
        },
        tags=["Estimate Calculations"],
    )
    def get(self, request, estimate_id: int):
        """
        Обработка GET запроса расчёта ТК.

        Алгоритм:
        1. Валидация query параметров
        2. Вызов сервиса расчёта
        3. Формирование ответа

        Args:
            request: DRF Request объект
            estimate_id: ID сметы из URL path

        Returns:
            Response: DRF Response с результатами расчёта или ошибкой
        """
        try:
            # Шаг 1: Валидация входных данных
            serializer = EstimateCalcQuerySerializer(data=request.query_params)
            serializer.is_valid(raise_exception=True)

            validated_data = serializer.validated_data
            tc_id = validated_data["tc"]
            quantity = validated_data["qty"]

            # Шаг 2: Вызов сервиса (бизнес-логика)
            calc, order = self.calc_facade.calculate_tc_for_estimate(
                estimate_id=estimate_id,
                tc_id=tc_id,
                quantity=quantity,
            )

            # Шаг 3: Формирование успешного ответа
            return Response(
                {
                    "ok": True,
                    "calc": calc,
                    "order": order,
                },
                status=status.HTTP_200_OK,
            )

        except EstimateNotFoundError as e:
            return self._error_response(
                message=str(e),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        except TechnicalCardNotFoundError as e:
            return self._error_response(
                message=str(e),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        except InvalidCalculationParamsError as e:
            return self._error_response(
                message=str(e),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        except EstimateCalcException as e:
            # Общий обработчик для всех кастомных исключений модуля
            return self._error_response(
                message=str(e),
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        except Exception as e:
            # Неожиданная ошибка
            return self._error_response(
                message="Внутренняя ошибка сервера",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @staticmethod
    def _error_response(message: str, status_code: int) -> Response:
        """
        Формирование ответа с ошибкой в единообразном формате.

        Args:
            message: Сообщение об ошибке
            status_code: HTTP статус код

        Returns:
            Response с ошибкой
        """
        return Response(
            {
                "ok": False,
                "error": message,
            },
            status=status_code,
        )
