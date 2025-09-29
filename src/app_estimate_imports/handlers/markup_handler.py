"""
Обработчик операций с разметкой (markup) в административном интерфейсе.

Назначение модуля
-----------------
- Генерация «скелета» разметки из результата парсинга Excel.
- Просмотр и интерактивная разметка узлов (labeler): установка меток TECH_CARD/WORK/MATERIAL/GROUP.
- Просмотр соответствий UID → Название для отладочных и навигационных целей.

Особенности
-----------
- Вся бизнес-логика хранения/получения разметки делегируется соответствующим сервисам.
- Методы возвращают готовые HTTP-ответы (HTML или JSON/redirect) для встраивания в админку.
"""

from django.contrib import messages
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect

from app_estimate_imports.handlers.base_handler import BaseHandler
from app_estimate_imports.utils_markup import ensure_uids_in_tree
from app_estimate_imports.services_markup import build_markup_skeleton


class MarkupHandler(BaseHandler):
    """Обработчик операций с разметкой"""

    def generate_skeleton(self, request: HttpRequest, pk: int) -> HttpResponse:
        """
        Генерирует черновик разметки на основе ParseResult.

        Алгоритм:
        1) Проверяет наличие ParseResult у файла.
        2) Гарантирует наличие объекта разметки (markup) для файла.
        3) Обновляет данные ParseResult, чтобы все узлы имели стабильные UID.
        4) Строит «скелет» разметки и сохраняет его в markup.annotation.

        :param request: Текущий HTTP-запрос.
        :param pk: Первичный ключ импортированного файла (ImportedEstimateFile).
        :returns: HTTP-redirect на страницу изменения объекта файла.
        """
        obj = self.get_object_or_error(request, pk)
        if not obj or not hasattr(obj, "parse_result"):
            messages.error(request, "Нет ParseResult для генерации")
            return self.redirect_back_or_change(request)

        try:
            # Гарантируем наличие разметки
            markup = self.markup_service.ensure_markup_exists(obj)

            # Обновляем данные с UID'ами
            obj.parse_result.data = ensure_uids_in_tree(obj.parse_result.data)
            obj.parse_result.save(update_fields=["data"])

            # Создаем скелет разметки
            markup.annotation = build_markup_skeleton(obj.parse_result)
            markup.save(update_fields=["annotation"])

            messages.success(request, "Черновик разметки создан")
        except Exception as e:
            messages.error(request, f"Ошибка генерации: {e!r}")

        return HttpResponseRedirect(f"../{pk}/change/")

    def show_labeler(self, request: HttpRequest, pk: int) -> HttpResponse:
        """
        Показывает интерфейс разметки узлов (labeler).

        На странице отображается таблица узлов с возможностью:
        - назначить метку (TECH_CARD/WORK/MATERIAL/GROUP);
        - для техкарт — перейти к настройке состава («Состав ТК»).

        :param request: Текущий HTTP-запрос.
        :param pk: Первичный ключ импортированного файла.
        :returns: HTML-страница с таблицей узлов для разметки.
        """
        obj = self.get_object_or_error(request, pk)
        if not obj or not hasattr(obj, "parse_result"):
            messages.error(request, "Нет ParseResult")
            return self.redirect_back_or_change(request)

        from ..services_markup import ensure_markup_exists, list_nodes

        markup = ensure_markup_exists(obj)
        nodes = list_nodes(obj.parse_result)
        labels = (markup.annotation or {}).get("labels", {})

        # Генерация HTML таблицы
        rows = []
        for node in nodes:
            uid = node["uid"]
            title = node["title"] or "—"
            path = node["path"]
            current_label = labels.get(uid, "—")

            buttons = self._generate_label_buttons(uid)
            extra = self._generate_extra_buttons(uid, current_label)

            rows.append(
                f"""
                <tr>
                    <td><code>{uid}</code></td>
                    <td>{title}</td>
                    <td>{path}</td>
                    <td>{current_label}</td>
                    <td>{buttons}{extra}</td>
                </tr>
            """
            )

        html = f"""
            <h2>Разметка узлов ({obj.original_name})</h2>
            <p>Кликните метку для нужного UID. Для ТЕХКАРТ нажмите «Состав ТК», чтобы выбрать её работы и материалы.</p>
            <table class="adminlist">
                <thead>
                    <tr>
                        <th>UID</th>
                        <th>Название</th>
                        <th>Путь</th>
                        <th>Метка</th>
                        <th>Действия</th>
                    </tr>
                </thead>
                <tbody>{"".join(rows)}</tbody>
            </table>
            <p><a class="button" href="../change/">Назад</a></p>
        """

        return HttpResponse(mark_safe(html))

    def set_label(self, request: HttpRequest, pk: int) -> HttpResponse:
        """
        Присваивает метку конкретному узлу и возвращает к labeler.

        Ожидает query-параметры:
          - uid: идентификатор узла в разметке;
          - label: целевая метка (TECH_CARD/WORK/MATERIAL/GROUP).

        :param request: Текущий HTTP-запрос (с параметрами uid и label).
        :param pk: Первичный ключ импортированного файла.
        :returns: HTTP-redirect обратно на страницу labeler.
        """
        obj = self.get_object_or_error(request, pk)
        if not obj:
            return HttpResponseRedirect(f"../labeler/")

        uid = request.GET.get("uid")
        label = request.GET.get("label")

        if not uid or not label:
            messages.error(request, "uid/label не переданы")
            return HttpResponseRedirect(f"../labeler/")

        try:
            from ..services_markup import set_label

            set_label(obj, uid, label)
            messages.success(request, f"{uid} → {label}")
        except Exception as e:
            messages.error(request, f"Ошибка: {e!r}")

        return HttpResponseRedirect(f"../labeler/")

    def show_uids(self, request: HttpRequest, pk: int) -> HttpResponse:
        """
        Показывает таблицу соответствий UID → Название.

        Используется для быстрой навигации/диагностики: какое «человеческое»
        имя было сопоставлено конкретному UID.

        :param request: Текущий HTTP-запрос.
        :param pk: Первичный ключ импортированного файла.
        :returns: HTML-страница с таблицей соответствий.
        """
        obj = self.get_object_or_error(request, pk)
        if not obj or not hasattr(obj, "parse_result"):
            messages.error(request, "Нет ParseResult")
            return self.redirect_back_or_change(request)

        from app_outlay.services_materialize import _index_titles_by_uid

        mapping = _index_titles_by_uid(obj.parse_result.data)

        rows = "".join(
            f"<tr><td><code>{uid}</code></td><td>{title}</td></tr>"
            for uid, title in mapping.items()
        )

        html = f"""
        <h2>UID → Название ({obj.original_name})</h2>
        <table class="adminlist">
        <thead><tr><th>UID</th><th>Название</th></tr></thead>
        <tbody>{rows}</tbody>
        </table>
        <p><a class="button" href="../change/">Назад</a></p>
        """

        return HttpResponse(mark_safe(html))

    def _generate_label_buttons(self, uid: str) -> str:
        """
        Генерирует HTML-кнопки для установки меток узлу.

        Список меток фиксированный: TECH_CARD, WORK, MATERIAL, GROUP.
        Кнопки ведут на ../set-label/?uid=<uid>&label=<LABEL>.

        :param uid: Идентификатор узла, для которого рендерим кнопки.
        :returns: HTML-строка с кнопками, готовая к вставке в таблицу.
        """
        labels = ["TECH_CARD", "WORK", "MATERIAL", "GROUP"]
        buttons = []

        for label in labels:
            button = format_html(
                '<a class="button" href="../set-label/?uid={}&label={}">{}</a>',
                uid,
                label,
                label,
            )
            buttons.append(button)

        return "&nbsp;".join(buttons)

    def _generate_extra_buttons(self, uid: str, current_label: str) -> str:
        """
        Генерирует дополнительные действия для узла (если это ТЕХКАРТА).

        Для метки TECH_CARD добавляется кнопка «Состав ТК», ведущая на
        ../compose/?tc_uid=<uid>, где можно настроить работы и материалы.

        :param uid: Идентификатор узла.
        :param current_label: Текущая метка узла.
        :returns: HTML-фрагмент с дополнительными кнопками (или пустая строка).
        """
        if current_label == "TECH_CARD":
            return format_html(
                '&nbsp;&nbsp;<a class="button" href="../compose/?tc_uid={}">Состав ТК</a>',
                uid,
            )
        return ""
