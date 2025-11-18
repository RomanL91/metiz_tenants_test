"""
REST API endpoints для использования в окружении админки.

Назначение модуля:
- Предоставляет набор HTTP-эндпоинтов (JSON) для операций со схемой колонок
  и группировки строк, которые вызываются из UI в админке (через fetch/AJAX).
- Все обработчики наследуются от BaseHandler и потому имеют доступ к доменным
  сервисам (MarkupService, SchemaService, GroupService) и вспомогательным методам.
"""

import json

from django.http import HttpRequest, HttpResponse

from app_estimate_imports.handlers.base_handler import BaseHandler
from app_estimate_imports.services.color_group_service import ColorGroupService


class ApiHandler(BaseHandler):
    """Обработчик API endpoints"""

    def save_schema_api(self, request: HttpRequest, pk: int) -> HttpResponse:
        """
        API для сохранения схемы колонок листа (ролей и правил выделения ТК).

        Ожидаемый JSON-payload:
        {
            "col_roles": ["NONE" | "NAME_OF_WORK" | "UNIT" | "QTY" | ...],
            "sheet_index": <int>,
            "unit_allow_raw": "<строка со списком юнитов через запятую>",
            "require_qty": <bool>
        }

        Поведение:
        - создаёт/обновляет объект разметки (markup) при необходимости;
        - сохраняет конфигурацию схемы в annotation->schema->sheets[sheet_i].

        :param request: текущий HttpRequest
        :param pk: первичный ключ импортированного файла
        :return: JSON {"ok": true} при успехе или {"ok": false, "error": "..."} при ошибке
        """
        obj = self.get_object_or_error(request, pk)
        if not obj:
            return self._error_response("file_not_found", 404)

        try:
            payload = json.loads(request.body.decode("utf-8"))
            col_roles = payload.get("col_roles", [])
            sheet_i = int(payload.get("sheet_index", 0))
            unit_allow_raw = payload.get("unit_allow_raw", "")
            require_qty = bool(payload.get("require_qty"))

            # ensure_markup_exists гарантирует наличие ParseMarkup и возвращает его
            markup = self.markup_service.ensure_markup_exists(obj)
            # Сохраняем схему через доменный сервис
            self.schema_service.save_schema_config(
                markup, sheet_i, col_roles, unit_allow_raw, require_qty
            )

            return self._success_response()
        except Exception as e:
            return self._error_response(str(e), 400)

    # def extract_from_grid_api(self, request: HttpRequest, pk: int) -> HttpResponse:
    #     """
    #     API для извлечения разметки из таблицы.

    #     Ожидаемый JSON-payload:
    #     {
    #         "col_roles": [...],
    #         "sheet_index": int,
    #         "unit_allow_raw": str,
    #         "require_qty": bool
    #     }
    #     """
    #     obj = self.get_object_or_error(request, pk)
    #     if not obj:
    #         return self._error_response("file_not_found", 404)

    #     try:
    #         payload = json.loads(request.body.decode("utf-8"))
    #         # TODO: Implement extraction logic
    #         # This would need to be implemented based on your requirements

    #         return self._success_response()
    #     except Exception as e:
    #         return self._error_response(str(e), 400)

    def groups_list_api(self, request: HttpRequest, pk: int) -> HttpResponse:
        """
        API для получения списка групп по листу.

        Query-string параметры:
          - sheet_index: номер листа (int), по умолчанию 0

        Формат ответа:
          {"ok": true, "groups": [ {uid, name, parent_uid, color, rows:[[s,e], ...]}, ... ]}

        :param request: текущий HttpRequest
        :param pk: первичный ключ импортированного файла
        :return: JSON со списком групп
        """
        obj = self.get_object_or_error(request, pk)
        if not obj:
            return self._error_response("file_not_found", 404)

        sheet_i = int(request.GET.get("sheet_index", 0))
        markup = self.markup_service.ensure_markup_exists(obj)
        groups = self.group_service.load_groups(markup, sheet_i)

        return HttpResponse(
            json.dumps({"ok": True, "groups": groups}), content_type="application/json"
        )

    def groups_create_api(self, request: HttpRequest, pk: int) -> HttpResponse:
        """
        API для создания новой группы/подгруппы.

        Ожидаемый JSON-payload:
          {
            "sheet_index": <int>,
            "name": "<название группы>",
            "rows": [[start, end], ...],         // диапазоны строк (1-based)
            "parent_uid": "<uid родителя>|null", // необязателен
            "color": "<#RRGGBB>"                 // необязателен, дефолт "#E0F7FA"
          }

        Возможные ошибки (400/500):
          - пустое имя/некорректные диапазоны;
          - указанный родитель не найден или не покрывает диапазоны дочерней группы;
          - общие исключения при сохранении/валидации.

        Формат успешного ответа:
          {"ok": true, "group": {...}}  // созданная группа в нормализованном виде

        :param request: текущий HttpRequest
        :param pk: первичный ключ импортированного файла
        :return: JSON-ответ
        """
        obj = self.get_object_or_error(request, pk)
        if not obj:
            return self._error_response("file_not_found", 404)

        try:
            payload = json.loads(request.body.decode("utf-8"))
            sheet_i = int(payload.get("sheet_index", 0))
            name = payload.get("name", "").strip()
            rows = payload.get("rows", [])
            parent_uid = payload.get("parent_uid")
            color = payload.get("color", "#E0F7FA")

            markup = self.markup_service.ensure_markup_exists(obj)
            group = self.group_service.create_group(
                markup, sheet_i, name, rows, parent_uid, color
            )

            return HttpResponse(
                json.dumps({"ok": True, "group": group}),
                content_type="application/json",
            )
        except ValueError as e:
            # Валидируемые ошибки доменного уровня → 400 Bad Request
            return self._error_response(str(e), 400)
        except Exception as e:
            # Непредвиденная ошибка → 500 Internal Server Error
            return self._error_response(str(e), 500)

    def groups_delete_api(self, request: HttpRequest, pk: int) -> HttpResponse:
        """
        API для удаления группы (вместе с её потомками).

        Ожидаемый JSON-payload:
          {
            "sheet_index": <int>,
            "uid": "<идентификатор группы>"
          }

        Поведение:
          - Удаляет группу и рекурсивно все вложенные подгруппы.
          - Сохраняет обновлённую разметку в ParseMarkup.

        :param request: текущий HttpRequest
        :param pk: первичный ключ импортированного файла
        :return: {"ok": true} при успехе или {"ok": false, "error": "..."} при ошибке
        """
        obj = self.get_object_or_error(request, pk)
        if not obj:
            return self._error_response("file_not_found", 404)

        try:
            payload = json.loads(request.body.decode("utf-8"))
            sheet_i = int(payload.get("sheet_index", 0))
            uid = payload.get("uid")

            if not uid:
                return self._error_response("no_uid", 400)

            markup = self.markup_service.ensure_markup_exists(obj)
            self.group_service.delete_group(markup, sheet_i, uid)

            return self._success_response()
        except Exception as e:
            return self._error_response(str(e), 500)

    def auto_groups_from_colors_api(
        self, request: HttpRequest, pk: int
    ) -> HttpResponse:
        """
        API для автоматического создания групп на основе цветов.

        POST данные:
        {
            "sheet_index": int,
            "name_of_work_col": int,
            "force": bool  // true если пользователь подтвердил перезапись
        }

        Возвращает:
        {
            "ok": bool,
            "groups_created": int,
            "had_existing_groups": bool,
            "warnings": list,
            "error": str (опционально),
            "requires_confirmation": bool (опционально),
            "message": str (опционально)
        }
        """
        obj = self.get_object_or_error(request, pk)
        if not obj:
            return self._error_response("file_not_found", 404)

        try:
            payload = json.loads(request.body.decode("utf-8"))
            sheet_index = payload.get("sheet_index", 0)
            name_col = payload.get("name_of_work_col")
            force = payload.get("force", False)
            hidden_rows = payload.get("hidden_rows") or []
            hidden_cols = payload.get("hidden_cols") or []

            if name_col is None:
                return self._error_response("Не указана колонка NAME_OF_WORK", 400)

            # Проверяем наличие разметки (используем сервис из self)
            markup = self.markup_service.ensure_markup_exists(obj)

            # Запускаем анализ (создаем новый инстанс ColorGroupService)
            color_service = ColorGroupService()
            result = color_service.analyze_colors_and_create_groups(
                markup=markup,
                sheet_index=sheet_index,
                name_of_work_col_index=name_col,
                warn_if_groups_exist=not force,
                hidden_rows=hidden_rows,
                hidden_cols=hidden_cols,
            )

            # Если требуется подтверждение
            if not result.get("ok") and result.get("requires_confirmation"):
                return HttpResponse(
                    json.dumps(
                        {
                            "ok": False,
                            "requires_confirmation": True,
                            "message": result.get("error"),
                            "had_existing_groups": result.get(
                                "had_existing_groups", False
                            ),
                        }
                    ),
                    content_type="application/json",
                )

            # Собираем предупреждения из сервиса
            warnings = []
            if hasattr(color_service, "_warnings"):
                warnings = color_service._warnings

            # Возвращаем результат
            return HttpResponse(
                json.dumps(
                    {
                        "ok": result.get("ok", False),
                        "groups_created": result.get("groups_created", 0),
                        "had_existing_groups": result.get("had_existing_groups", False),
                        "warnings": warnings,
                        "error": result.get("error"),
                    }
                ),
                content_type="application/json",
            )

        except json.JSONDecodeError:
            return self._error_response("Invalid JSON", 400)
        except Exception as e:
            return self._error_response(f"Ошибка создания групп: {str(e)}", 500)

    def _success_response(self) -> HttpResponse:
        """
        Возвращает успешный JSON ответ.

        Унифицированный метод, чтобы не дублировать код:
          {"ok": true}
        """
        return HttpResponse(json.dumps({"ok": True}), content_type="application/json")

    def _error_response(self, error: str, status: int = 400) -> HttpResponse:
        """
        Возвращает JSON ответ с ошибкой и заданным HTTP-статусом.

        :param error: текст ошибки для поля "error"
        :param status: HTTP-статус ответа (по умолчанию 400)
        :return: HttpResponse с JSON {"ok": false, "error": "..."}
        """
        return HttpResponse(
            json.dumps({"ok": False, "error": error}),
            content_type="application/json",
            status=status,
        )
