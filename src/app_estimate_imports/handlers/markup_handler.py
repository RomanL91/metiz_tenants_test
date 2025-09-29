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

from uuid import uuid4

from django.db import transaction
from django.contrib import messages
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect

from app_estimate_imports.handlers.base_handler import BaseHandler

from app_estimate_imports.models import ParseMarkup


ALLOWED_LABELS = {"TECH_CARD", "WORK", "MATERIAL", "GROUP"}


class MarkupHandler(BaseHandler):
    """Обработчик операций с разметкой"""

    @transaction.atomic
    def _apply_label(
        self, file_obj, uid: str, label: str, title: str | None = None
    ) -> None:
        if label not in ALLOWED_LABELS:
            raise ValueError(f"Недопустимая метка: {label}")
        markup = self.ensure_markup_exists(file_obj)
        ann = markup.annotation
        ann["labels"][uid] = label
        if title:
            ann.setdefault("names", {})[uid] = title  # ← словарь имён для uid
        markup.annotation = ann
        markup.save(update_fields=["annotation"])

    def list_nodes(self, parse_result) -> list[dict]:
        """
        Плоский список узлов дерева: [{uid, title, path}]
        path — собираем из titles родителей (для читаемости).
        """
        nodes: list[dict] = []

        def walk(node: dict, parents: list[str]):
            uid = node.get("uid")
            title = node.get("title") or ""
            path = " / ".join([*parents, title]) if title else " / ".join(parents)
            if uid:
                nodes.append({"uid": uid, "title": title, "path": path})
            for ch in node.get("children") or []:
                walk(ch, [*parents, title] if title else parents)

        for sheet in parse_result.data.get("sheets") or []:
            for b in sheet.get("blocks") or []:
                walk(b, [sheet.get("name") or "Лист"])
        return nodes

    def ensure_markup_exists(self, file_obj) -> ParseMarkup:
        """
        Гарантирует наличие ParseMarkup и uid'ов в ParseResult.data.
        """
        pr = getattr(file_obj, "parse_result", None)
        if not pr:
            raise ValueError("Нет ParseResult для файла")

        # Проставим uid всем узлам
        pr.data = self.ensure_uids_in_tree(pr.data)
        pr.save(update_fields=["data"])

        markup = getattr(file_obj, "markup", None)
        if not markup:
            markup = ParseMarkup.objects.create(
                file=file_obj,
                parse_result=pr,
                annotation={"labels": {}, "tech_cards": []},
            )
        else:
            ann = markup.annotation or {}
            ann.setdefault("labels", {})
            ann.setdefault("tech_cards", [])
            markup.annotation = ann
            markup.save(update_fields=["annotation"])
        return markup

    def _walk_blocks(self, blocks: list, prefix: str):
        for i, b in enumerate(blocks):
            if "uid" not in b or not b["uid"]:
                b["uid"] = f"{prefix}-b{i}-{uuid4().hex[:8]}"
            children = b.get("children") or []
            if isinstance(children, list) and children:
                self._walk_blocks(children, prefix=b["uid"])

    def build_markup_skeleton(self, parse_result) -> dict:
        """
        Строит черновик:
        - labels: все найденные uid -> "GROUP" (можно править руками в админке)
        - tech_cards: []
        """
        data = self.ensure_uids_in_tree(parse_result.data)
        labels: dict[str, str] = {}

        def collect(blocks: list):
            for b in blocks:
                uid = b.get("uid")
                if uid:
                    labels[uid] = "GROUP"
                ch = b.get("children") or []
                if ch:
                    collect(ch)

        for sheet in data.get("sheets") or []:
            collect(sheet.get("blocks") or [])

        return {"labels": labels, "tech_cards": []}

    def ensure_uids_in_tree(self, data: dict) -> dict:
        """
        Проставляет uid каждому узлу в sheets[].blocks[*] и формирует blocks из rows при необходимости.
        Узел: {"title": "...", "children": [...], "uid": "..."}.
        """
        if not data:
            return {"sheets": []}
        sheets = data.get("sheets") or []
        for si, sheet in enumerate(sheets):
            if "blocks" in sheet and isinstance(sheet["blocks"], list):
                self._walk_blocks(sheet["blocks"], prefix=f"s{si}")
            else:
                # преобразуем rows -> blocks (title = первая непустая ячейка)
                blocks = []
                for ri, row in enumerate(sheet.get("rows") or []):
                    cells = row.get("cells") or []
                    title = next((c for c in cells if c), "")
                    if not title:
                        continue
                    blocks.append(
                        {
                            "title": title,
                            "children": [],
                            "uid": f"s{si}-r{ri}-{uuid4().hex[:8]}",
                        }
                    )
                sheet["blocks"] = blocks
        return data

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
            obj.parse_result.data = self.ensure_uids_in_tree(obj.parse_result.data)
            obj.parse_result.save(update_fields=["data"])

            # Создаем скелет разметки
            markup.annotation = self.build_markup_skeleton(obj.parse_result)
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

        markup = self.ensure_markup_exists(obj)
        nodes = self.list_nodes(obj.parse_result)
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
            self._apply_label(obj, uid, label)
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
