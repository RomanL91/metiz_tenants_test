"""
Обработчик для работы с графом.

Назначение
---------
- Отрисовка страницы с графом (Cytoscape на фронте).
- REST-endpoint, отдающий JSON-данные графа (узлы/рёбра) для выбранного листа.

Зависимости
-----------
- BaseHandler: общие утилиты (доступ к admin, сообщения, получение объекта и т.д.).
- GraphService: доменная логика построения графа (из grid/markup).
"""

import json

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse

from app_estimate_imports.handlers.base_handler import BaseHandler
from app_estimate_imports.services.graph_service import GraphService


class GraphHandler(BaseHandler):
    """
    Обработчик графических представлений.

    Содержит:
    - show_graph  : рендер страницы с холстом графа и управляющими элементами.
    - graph_data_api : API, возвращающий структуру графа (nodes/edges) в JSON.

    Вся предметная логика построения графа вынесена в GraphService.
    """

    def __init__(self, admin_instance):
        super().__init__(admin_instance)
        self.graph_service = GraphService()

    def show_graph(self, request: HttpRequest, pk: int) -> HttpResponse:
        """
        Показывает графическое представление.

        Поток:
        1) Проверка, что у файла есть ParseResult (иначе сообщение и редирект назад).
        2) Определение текущего листа (query: ?sheet=<int>, дефолт 0 и границы).
        3) Подготовка контекста (названия листов, индекс активного листа).
        4) Рендер шаблона 'admin/app_estimate_imports/graph.html'.

        Параметры

        :param request: текущий HttpRequest.
        :param pk: первичный ключ ImportedEstimateFile.

        Возвращает
            HttpResponse с HTML-страницей графа.
        """
        obj = self.get_object_or_error(request, pk)
        if not obj or not hasattr(obj, "parse_result"):
            messages.error(request, "Нет ParseResult")
            return self.redirect_back_or_change(request)

        pr = obj.parse_result
        sheets = pr.data.get("sheets", [])
        sheet_i = int(request.GET.get("sheet", 0))

        if sheet_i < 0 or sheet_i >= len(sheets):
            sheet_i = 0

        sheet_names = [s.get("name", f"Лист {i+1}") for i, s in enumerate(sheets)]

        context = dict(
            self.admin.admin_site.each_context(request),
            title=f"График: {obj.original_name}",
            file=obj,
            sheet_index=sheet_i,
            sheet_names=sheet_names,
        )

        return TemplateResponse(
            request, "admin/app_estimate_imports/graph.html", context
        )

    def graph_data_api(self, request: HttpRequest, pk: int) -> HttpResponse:
        """
        API для получения данных графика (JSON).

        Ожидаемые query-параметры:
            - sheet_index: int, номер листа (по умолчанию 0).
            - type       : str, источник данных графа: 'grid' или 'markup'.
                           По умолчанию 'grid'.

        Логика:
        1) Проверяем наличие ParseResult.
        2) Выбираем тип построения (grid/markup) и вызываем соответствующий метод сервиса.
        3) Если сервис накопил предупреждения/ошибки — выводим через messages.error.
        4) Возвращаем JSON: {"ok": True, "nodes": [...], "edges": [...]}.

        На стороне клиента (graph.html) Cytoscape рендерит полученные элементы.

        Возвращает:
            HttpResponse с application/json.
        """
        obj = self.get_object_or_error(request, pk)
        if not obj or not hasattr(obj, "parse_result"):
            return self._error_response("no_parse_result", 400)

        sheet_i = int(request.GET.get("sheet_index", 0))
        # Можно переключать источник графа через ?type=grid|markup
        # graph_type = request.GET.get("type", "markup")
        graph_type = request.GET.get("type", "grid")

        try:
            # Делегируем построение графа доменному сервису
            if graph_type == "grid":
                graph_data = self.graph_service.build_graph_from_grid(obj, sheet_i)
            else:
                graph_data = self.graph_service.build_graph_from_markup(obj, sheet_i)

            # Добавляем сообщения об ошибках если есть
            # Если сервис сообщил о проблемах — прокинем их в UI админки
            if self.graph_service.has_errors:
                for error in self.graph_service.errors:
                    messages.error(request, error)

            # Возвращаем только ожидаемые ключи (узлы и рёбра)
            return HttpResponse(
                json.dumps(
                    {
                        "ok": True,
                        "nodes": graph_data["nodes"],
                        "edges": graph_data["edges"],
                    },
                    ensure_ascii=False,
                ),
                content_type="application/json",
            )

        except Exception as e:
            return self._error_response(f"Ошибка построения графа: {e}", 500)

    def _error_response(self, error: str, status: int = 400) -> HttpResponse:
        """Возвращает JSON ответ с ошибкой"""
        return HttpResponse(
            json.dumps({"ok": False, "error": error}),
            content_type="application/json",
            status=status,
        )
