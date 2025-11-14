"""
Views (контроллеры) для анализа сметы.

Архитектура:
- Thin Controllers: минимум логики, делегирование в сервис
- JSON Response: возвращает данные для графиков
- Clear Flow: валидация → сервис → ответ
"""

from django.http import JsonResponse
from django.views import View

from app_outlay.views.export_excel_view.overhead_calculator import \
    OverheadCalculator

from .exceptions import AnalysisError
from .services import AnalysisService


class EstimateAnalysisDataView(View):
    """
        API для получения данных анализа сметы.

        **Endpoint:** GET /api/v1/estimates/{estimate_id}/analysis-data/

        **Response Format:**
    ```json
        {
            "ok": true,
            "has_data": true,
            "summary": {
                "base_total": 125000.0,
                "final_with_overhead": 165000.0,
                "avg_markup_percent": 32.0,
                ...
            },
            "price_breakdown": {...},
            "top_positions": [...],
            "groups_distribution": [...],
            "overhead_breakdown": [...],
            "materials_vs_works": {...}
        }
    ```

        **Use Case:**
        Предоставление данных для интерактивных графиков
        и детального анализа сметы на фронтенде.

        **Permissions:**
        Доступ через Django Admin (admin_site.admin_view)

        **Performance:**
        - Оптимизированные запросы (select_related, prefetch_related)
        - Batch-обработка расчётов
        - Переиспользование компонентов
    """

    def get(self, request, estimate_id: int):
        """
        Обработка GET запроса анализа.

        Args:
            request: Django Request
            estimate_id: ID сметы из URL

        Returns:
            JsonResponse: Данные анализа или ошибка

        Example:
            GET /api/v1/estimates/123/analysis-data/

            Response 200:
            {
                "ok": true,
                "has_data": true,
                "summary": {...},
                ...
            }

            Response 404:
            {
                "ok": false,
                "error": "Смета с ID 123 не найдена"
            }
        """
        try:
            # Шаг 1: Создание сервиса
            service = AnalysisService(
                estimate_id=estimate_id,
                overhead_calculator_cls=OverheadCalculator,
            )

            # Шаг 2: Выполнение анализа
            result = service.analyze()

            # Шаг 3: Возврат результата
            return JsonResponse(result, status=200)

        except AnalysisError as e:
            # Доменные ошибки → 404 или 400
            status_code = 404 if "не найдена" in e.message.lower() else 400

            # Если нет техкарт - это не ошибка, а нормальное состояние
            if "нет привязанных техкарт" in e.message.lower():
                return JsonResponse(
                    {
                        "ok": True,
                        "has_data": False,
                        "message": "В смете нет привязанных техкарт",
                    },
                    status=200,
                )

            return JsonResponse(
                {"ok": False, "error": e.message, "details": e.details},
                status=status_code,
            )

        except Exception as e:
            # Неожиданные ошибки → 500
            return JsonResponse(
                {
                    "ok": False,
                    "error": "Внутренняя ошибка при анализе",
                    "details": {"error": str(e)},
                },
                status=500,
            )
