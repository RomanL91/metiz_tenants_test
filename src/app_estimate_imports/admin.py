from __future__ import annotations

import json
from django.contrib import admin, messages
from django.http import HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import ImportedEstimateFile, ParseResult, ParseMarkup
from .services import parse_and_store, save_imported_file
from .services_markup import build_markup_skeleton
from app_estimate_imports.utils_markup import ensure_uids_in_tree

from app_outlay.services_materialize import materialize_estimate_from_markup

ROLE_CHOICES = [
    "NONE",
    "GROUP-1",
    "GROUP-2",
    "GROUP-3",
    "GROUP-4",
    "GROUP-5",
    "GROUP-6",
    "TECH_CARD",
    "WORK",
    "MATERIAL",
    "UNIT",
    "QTY",
]


# ----- Инлайн для просмотра JSON прямо на карточке файла -----


class ParseMarkupInline(admin.StackedInline):
    model = ParseMarkup
    can_delete = False
    extra = 0
    readonly_fields = ("updated_at", "annotation_pretty")
    fields = ("annotation", "updated_at", "annotation_pretty")

    def annotation_pretty(self, instance: ParseMarkup):
        if not instance or not instance.annotation:
            return "—"
        payload = json.dumps(instance.annotation, ensure_ascii=False, indent=2)
        return format_html(
            "<details><summary>JSON разметки</summary>"
            '<pre style="max-height:480px;overflow:auto;white-space:pre-wrap;">{}</pre>'
            "</details>",
            mark_safe(payload),
        )

    annotation_pretty.short_description = "Просмотр JSON разметки"


class ParseResultInline(admin.StackedInline):
    model = ParseResult
    can_delete = False
    extra = 0
    readonly_fields = ("estimate_name", "created_at", "pretty_json")
    fields = ("estimate_name", "created_at", "pretty_json")

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def pretty_json(self, instance: ParseResult) -> str:
        if not instance or not instance.data:
            return "—"
        try:
            payload = json.dumps(instance.data, ensure_ascii=False, indent=2)
        except Exception:
            payload = str(instance.data)
        return format_html(
            "<details><summary>Показать/скрыть JSON</summary>"
            '<pre style="max-height:480px;overflow:auto;white-space:pre-wrap;">{}</pre>'
            "</details>",
            mark_safe(payload),
        )

    pretty_json.short_description = "JSON результат"


# ----- Админ импортированного файла -----


@admin.register(ImportedEstimateFile)
class ImportedEstimateFileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "original_name",
        "size_kb",
        "sheet_count",
        "uploaded_at",
        "sha256_short",
        "has_result",
        "actions_col",
    )
    list_display_links = ("id", "original_name")
    search_fields = ("original_name", "sha256")
    readonly_fields = ("uploaded_at", "size_bytes", "sha256", "sheet_count")
    inlines = (ParseResultInline, ParseMarkupInline)
    actions = ("parse_now",)

    # — колонки —

    def size_kb(self, obj: ImportedEstimateFile) -> str:
        return f"{(obj.size_bytes or 0)/1024:.1f} KB"

    size_kb.short_description = "Размер"

    def sha256_short(self, obj: ImportedEstimateFile) -> str:
        return (obj.sha256 or "")[:12] + "…" if obj.sha256 else "—"

    sha256_short.short_description = "SHA256"

    def has_result(self, obj: ImportedEstimateFile) -> str:
        return "✅" if hasattr(obj, "parse_result") else "—"

    has_result.short_description = "JSON"

    def actions_col(self, obj):
        buttons = [
            format_html(
                '<a class="button" href="{}">Распарсить</a>', self._parse_url(obj.pk)
            )
        ]
        if hasattr(obj, "parse_result"):
            buttons.append(
                format_html(
                    '<a class="button" href="{}">Сгенерировать разметку</a>',
                    f"./{obj.pk}/generate-markup/",
                )
            )
            buttons.append(
                format_html(
                    '<a class="button" href="{}">Разметить</a>', f"./{obj.pk}/labeler/"
                )
            )
            buttons.append(
                format_html(
                    '<a class="button" href="{}">Граф</a>', f"./{obj.pk}/graph/"
                )
            )
            buttons.append(
                format_html(
                    '<a class="button" href="{}">Таблица</a>', f"./{obj.pk}/grid/"
                )
            )  # ← НОВОЕ
        if hasattr(obj, "markup"):
            buttons.append(
                format_html(
                    '<a class="button" href="{}">Создать смету</a>',
                    f"./{obj.pk}/materialize/",
                )
            )
        return mark_safe("&nbsp;".join(buttons))

    actions_col.short_description = "Действия"

    # — object-tools urls —

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:pk>/parse/",
                self.admin_site.admin_view(self.parse_view),
                name="imports_parse",
            ),
            path(
                "<int:pk>/download-json/",
                self.admin_site.admin_view(self.download_json_view),
                name="imports_download_json",
            ),
            path(
                "<int:pk>/generate-markup/",
                self.admin_site.admin_view(self.generate_markup_view),
                name="imports_generate_markup",
            ),
            path(
                "<int:pk>/materialize/",
                self.admin_site.admin_view(self.materialize_view),
                name="imports_materialize",
            ),
            path(
                "<int:pk>/uids/",
                self.admin_site.admin_view(self.uids_view),
                name="imports_uids",
            ),
            path(
                "<int:pk>/labeler/",
                self.admin_site.admin_view(self.labeler_view),
                name="imports_labeler",
            ),
            path(
                "<int:pk>/set-label/",
                self.admin_site.admin_view(self.set_label_view),
                name="imports_set_label",
            ),
            path(
                "<int:pk>/compose/",
                self.admin_site.admin_view(self.compose_view),
                name="imports_compose",
            ),
            path(
                "<int:pk>/graph/",
                self.admin_site.admin_view(self.graph_view),
                name="imports_graph",
            ),
            path(
                "<int:pk>/api/set-label/",
                self.admin_site.admin_view(self.api_set_label),
                name="imports_api_set_label",
            ),
            path(
                "<int:pk>/api/attach-members/",
                self.admin_site.admin_view(self.api_attach_members),
                name="imports_api_attach_members",
            ),
            path(
                "<int:pk>/grid/",
                self.admin_site.admin_view(self.grid_view),
                name="imports_grid",
            ),
            path(
                "<int:pk>/api/save-schema/",
                self.admin_site.admin_view(self.api_save_schema),
                name="imports_api_save_schema",
            ),
            path(
                "<int:pk>/api/extract-from-grid/",
                self.admin_site.admin_view(self.api_extract_from_grid),
                name="imports_api_extract_from_grid",
            ),
        ]
        return custom + urls

    def _parse_url(self, pk: int) -> str:
        return f"./{pk}/parse/"

    def _download_url(self, pk: int) -> str:
        return f"./{pk}/download-json/"

    # — действия / вьюхи —

    def parse_now(self, request, queryset):
        ok, fail = 0, 0
        for f in queryset:
            try:
                parse_and_store(f)
                ok += 1
            except Exception as e:
                fail += 1
                self.message_user(
                    request, f"[{f.original_name}] ошибка: {e!r}", level=messages.ERROR
                )
        if ok:
            self.message_user(
                request, f"Распарсено успешно: {ok}", level=messages.SUCCESS
            )
        if fail and not ok:
            self.message_user(
                request,
                "Ошибки при парсинге. См. сообщения выше.",
                level=messages.ERROR,
            )

    parse_now.short_description = "Распарсить (синхронно)"

    def parse_view(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj:
            self.message_user(request, "Файл не найден", level=messages.ERROR)
            return self.response_post_save_change(request, None)
        try:
            parse_and_store(obj)
            self.message_user(
                request, "Готово: JSON создан/обновлён", level=messages.SUCCESS
            )
        except Exception as e:
            self.message_user(request, f"Ошибка парсинга: {e!r}", level=messages.ERROR)
        return self.response_change(request, obj)

    def download_json_view(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj or not hasattr(obj, "parse_result"):
            self.message_user(request, "JSON ещё не создан", level=messages.WARNING)
            return (
                self.response_change(request, obj)
                if obj
                else self.response_post_save_change(request, None)
            )
        payload = json.dumps(obj.parse_result.data, ensure_ascii=False, indent=2)
        resp = HttpResponse(payload, content_type="application/json; charset=utf-8")
        safe_name = (obj.original_name or f"file_{obj.pk}").rsplit(".", 1)[0]
        resp["Content-Disposition"] = f'attachment; filename="{safe_name}.json"'
        return resp

    def generate_markup_skeleton(self, request, queryset):
        ok = 0
        for f in queryset:
            pr = getattr(f, "parse_result", None)
            if not pr:
                self.message_user(
                    request, f"[{f}] нет ParseResult", level=messages.WARNING
                )
                continue
            if not hasattr(f, "markup"):
                f.markup = ParseMarkup.objects.create(
                    file=f, parse_result=pr, annotation={}
                )
            # гарантируем uid'ы
            pr.data = ensure_uids_in_tree(pr.data)
            pr.save(update_fields=["data"])
            f.markup.annotation = build_markup_skeleton(pr)
            f.markup.save(update_fields=["annotation"])
            ok += 1
        if ok:
            self.message_user(
                request, f"Скелет разметки создан: {ok}", level=messages.SUCCESS
            )

    generate_markup_skeleton.short_description = "Сгенерировать черновик разметки"

    def generate_markup_view(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj or not hasattr(obj, "parse_result"):
            self.message_user(
                request, "Нет ParseResult для генерации", level=messages.ERROR
            )
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))
        if not hasattr(obj, "markup"):
            obj.markup = ParseMarkup.objects.create(
                file=obj, parse_result=obj.parse_result, annotation={}
            )
        obj.parse_result.data = ensure_uids_in_tree(obj.parse_result.data)
        obj.parse_result.save(update_fields=["data"])
        obj.markup.annotation = build_markup_skeleton(obj.parse_result)
        obj.markup.save(update_fields=["annotation"])
        self.message_user(request, "Черновик разметки создан", level=messages.SUCCESS)
        return HttpResponseRedirect(f"../{pk}/change/")

    def create_estimate_from_markup(self, request, queryset):
        ok = 0
        for f in queryset:
            if not hasattr(f, "markup"):
                self.message_user(
                    request, f"[{f}] нет разметки", level=messages.WARNING
                )
                continue
            try:
                materialize_estimate_from_markup(f.markup)
                ok += 1
            except Exception as e:
                self.message_user(
                    request, f"[{f}] ошибка материализации: {e!r}", level=messages.ERROR
                )
        if ok:
            self.message_user(request, f"Создано смет: {ok}", level=messages.SUCCESS)

    create_estimate_from_markup.short_description = "Создать смету из разметки"

    def materialize_view(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj or not hasattr(obj, "markup"):
            self.message_user(
                request, "Нет разметки для материализации", level=messages.ERROR
            )
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))
        materialize_estimate_from_markup(obj.markup)
        self.message_user(request, "Смета создана", level=messages.SUCCESS)
        return HttpResponseRedirect(f"../{pk}/change/")

    def uids_view(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj or not hasattr(obj, "parse_result"):
            self.message_user(request, "Нет ParseResult", level=messages.ERROR)
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))

        from app_outlay.services_materialize import (
            _index_titles_by_uid,
        )  # или вынеси в utils

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

    def labeler_view(self, request, pk: int):
        """
        Таблица узлов с кнопками: сделать TECH_CARD/WORK/MATERIAL/GROUP.
        Для узлов, помеченных как TECH_CARD, показываем кнопку «Состав ТК».
        """
        obj = self.get_object(request, pk)
        if not obj or not hasattr(obj, "parse_result"):
            self.message_user(request, "Нет ParseResult", level=messages.ERROR)
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))

        # гарантируем uid'ы и наличие markup
        from app_estimate_imports.services_markup import (
            ensure_markup_exists,
            list_nodes,
        )

        markup = ensure_markup_exists(obj)
        nodes = list_nodes(obj.parse_result)
        labels = (markup.annotation or {}).get("labels", {})

        def btn(uid, label):
            return format_html(
                '<a class="button" href="../set-label/?uid={}&label={}">{}</a>',
                uid,
                label,
                label,
            )

        rows = []
        for n in nodes:
            uid = n["uid"]
            title = n["title"] or "—"
            path = n["path"]
            cur = labels.get(uid, "—")
            buttons = "&nbsp;".join(
                [
                    btn(uid, "TECH_CARD"),
                    btn(uid, "WORK"),
                    btn(uid, "MATERIAL"),
                    btn(uid, "GROUP"),
                ]
            )
            extra = ""
            if cur == "TECH_CARD":
                extra = format_html(
                    '&nbsp;&nbsp;<a class="button" href="../compose/?tc_uid={}">Состав ТК</a>',
                    uid,
                )
            rows.append(
                f"<tr><td><code>{uid}</code></td><td>{title}</td><td>{path}</td><td>{cur}</td><td>{buttons}{extra}</td></tr>"
            )

        html = f"""
        <h2>Разметка узлов ({obj.original_name})</h2>
        <p>Кликните метку для нужного UID. Для ТЕХКАРТ нажмите «Состав ТК», чтобы выбрать её работы и материалы.</p>
        <table class="adminlist">
        <thead><tr><th>UID</th><th>Название</th><th>Путь</th><th>Метка</th><th>Действия</th></tr></thead>
        <tbody>{"".join(rows)}</tbody>
        </table>
        <p><a class="button" href="../change/">Назад</a></p>
        """
        return HttpResponse(mark_safe(html))

    def set_label_view(self, request, pk: int):
        """
        Присваивает метку узлу и возвращает в labeler.
        """
        obj = self.get_object(request, pk)
        if not obj:
            self.message_user(request, "Файл не найден", level=messages.ERROR)
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))

        uid = request.GET.get("uid")
        label = request.GET.get("label")
        if not uid or not label:
            self.message_user(request, "uid/label не переданы", level=messages.ERROR)
            return HttpResponseRedirect(f"../labeler/")

        try:
            from app_estimate_imports.services_markup import set_label

            set_label(obj, uid, label)
            self.message_user(request, f"{uid} → {label}", level=messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Ошибка: {e!r}", level=messages.ERROR)

        return HttpResponseRedirect(f"../labeler/")

    def compose_view(self, request, pk: int):
        """
        Настройка состава выбранной TECH_CARD: мультиселект WORK и MATERIAL.
        GET: форма, POST: сохранение.
        """
        obj = self.get_object(request, pk)
        if not obj or not hasattr(obj, "parse_result"):
            self.message_user(request, "Нет ParseResult", level=messages.ERROR)
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))

        from app_estimate_imports.services_markup import (
            ensure_markup_exists,
            list_nodes,
            set_tc_members,
        )

        markup = ensure_markup_exists(obj)
        labels = (markup.annotation or {}).get("labels", {})
        nodes = list_nodes(obj.parse_result)

        tc_uid = request.GET.get("tc_uid") or request.POST.get("tc_uid")
        if not tc_uid:
            self.message_user(request, "Не указан tc_uid", level=messages.ERROR)
            return HttpResponseRedirect(f"../labeler/")

        if request.method == "POST":
            works = request.POST.getlist("works")
            materials = request.POST.getlist("materials")
            try:
                set_tc_members(obj, tc_uid, works, materials)
                self.message_user(
                    request, "Состав техкарты обновлён", level=messages.SUCCESS
                )
                return HttpResponseRedirect(f"../labeler/")
            except Exception as e:
                self.message_user(request, f"Ошибка: {e!r}", level=messages.ERROR)

        # подготовим списки выбора
        work_opts = []
        material_opts = []
        cur_works, cur_materials = [], []
        # найдём текущую запись ТК
        for entry in (markup.annotation or {}).get("tech_cards", []):
            if entry.get("uid") == tc_uid:
                cur_works = entry.get("works") or []
                cur_materials = entry.get("materials") or []
                break

        for n in nodes:
            uid = n["uid"]
            title = n["title"] or uid
            if labels.get(uid) == "WORK":
                sel = "selected" if uid in cur_works else ""
                work_opts.append(
                    f'<option value="{uid}" {sel}>{title} ({uid})</option>'
                )
            elif labels.get(uid) == "MATERIAL":
                sel = "selected" if uid in cur_materials else ""
                material_opts.append(
                    f'<option value="{uid}" {sel}>{title} ({uid})</option>'
                )

        html = f"""
        <h2>Состав техкарты: {tc_uid}</h2>
        <form method="post">
        {request.csrf_processing_done or ""}
        <input type="hidden" name="tc_uid" value="{tc_uid}">
        <div style="display:flex; gap:24px;">
            <div>
            <label><strong>WORKS</strong></label><br>
            <select name="works" multiple size="15" style="min-width:360px;">{"".join(work_opts)}</select>
            </div>
            <div>
            <label><strong>MATERIALS</strong></label><br>
            <select name="materials" multiple size="15" style="min-width:360px;">{"".join(material_opts)}</select>
            </div>
        </div>
        <p style="margin-top:16px;">
            <button class="button" type="submit">Сохранить</button>
            <a class="button" href="../labeler/">Отмена</a>
        </p>
        </form>
        """
        return HttpResponse(mark_safe(html))

    def graph_view(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj or not hasattr(obj, "parse_result"):
            self.message_user(request, "Нет ParseResult", level=messages.ERROR)
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))

        # гарантируем uid'ы + наличие markup
        from app_estimate_imports.services_markup import ensure_markup_exists
        from app_estimate_imports.utils_markup import ensure_uids_in_tree

        pr = obj.parse_result
        pr.data = ensure_uids_in_tree(pr.data)
        pr.save(update_fields=["data"])
        markup = ensure_markup_exists(obj)

        graph = _build_graph(pr.data, markup.annotation or {})
        context = dict(
            self.admin_site.each_context(request),
            title=f"Граф сметы: {obj.original_name}",
            file=obj,
            graph_json=json.dumps(graph, ensure_ascii=False),
        )
        return TemplateResponse(
            request, "admin/app_estimate_imports/graph.html", context
        )

    def api_set_label(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj:
            return HttpResponse(
                json.dumps({"ok": False, "error": "file_not_found"}),
                content_type="application/json",
                status=404,
            )
        try:
            payload = json.loads(request.body.decode("utf-8"))
            uid = payload["uid"]
            label = payload["label"]
            title = payload.get("title", "")
            from app_estimate_imports.services_markup import set_label

            set_label(obj, uid, label, title=title)  # ← передаём title
            return HttpResponse(
                json.dumps({"ok": True}), content_type="application/json"
            )
        except Exception as e:
            return HttpResponse(
                json.dumps({"ok": False, "error": str(e)}),
                content_type="application/json",
                status=400,
            )

    def api_attach_members(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj:
            return HttpResponse(
                json.dumps({"ok": False, "error": "file_not_found"}),
                content_type="application/json",
                status=404,
            )

        try:
            payload = json.loads(request.body.decode("utf-8"))
            tc_uid = payload["tc_uid"]
            works = payload.get("works", [])
            materials = payload.get("materials", [])
            from app_estimate_imports.services_markup import set_tc_members

            set_tc_members(obj, tc_uid, works, materials)
            return HttpResponse(
                json.dumps({"ok": True}), content_type="application/json"
            )
        except Exception as e:
            return HttpResponse(
                json.dumps({"ok": False, "error": str(e)}),
                content_type="application/json",
                status=400,
            )

    def _ensure_markup(self, file_obj):
        from app_estimate_imports.services_markup import ensure_markup_exists

        return ensure_markup_exists(file_obj)

    def _guess_schema(self, rows):
        # как раньше, только возвращает list[str]
        max_cols = max((len(r.get("cells") or []) for r in rows), default=0)
        roles = ["NONE"] * max_cols
        header_zone = rows[:8]
        for r in header_zone:
            cells = [((c or "").strip()) for c in r.get("cells", [])]
            for ci, val in enumerate(cells):
                low = val.lower()
                if "шифр" in low:
                    roles[ci] = "TECH_CARD"
                if ("наименован" in low and "работ" in low) or low == "наименование":
                    roles[ci] = "WORK"
                if "ед.изм" in low or "ед. изм" in low:
                    roles[ci] = "UNIT"
                if "кол-во" in low or "количество" in low or low in {"колво", "кол-во"}:
                    roles[ci] = "QTY"
                if re.fullmatch(r"ур\d+", low):
                    idx = int(re.findall(r"\d+", low)[0])
                    if 1 <= idx <= 6:
                        roles[ci] = f"GROUP-{idx}"
        if not any(r.startswith("GROUP-") for r in roles) and max_cols >= 9:
            for i, tag in enumerate(
                ["GROUP-1", "GROUP-2", "GROUP-3", "GROUP-4"], start=5
            ):
                if i < max_cols and roles[i] == "NONE":
                    roles[i] = tag
        return roles

    def grid_view(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj or not hasattr(obj, "parse_result"):
            self.message_user(request, "Нет ParseResult", level=messages.ERROR)
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))

        # какой лист смотрим
        pr = obj.parse_result
        sheets = pr.data.get("sheets") or []
        sheet_i = int(request.GET.get("sheet") or 0)
        if sheet_i < 0 or sheet_i >= len(sheets):
            sheet_i = 0
        sheet = sheets[sheet_i] if sheets else {"name": "Лист1", "rows": []}
        rows = sheet.get("rows") or []
        preview_rows = rows[:200]
        max_cols = max((len(r.get("cells") or []) for r in preview_rows), default=0)
        cols = list(range(max_cols))
        sheet_names = [s.get("name") or f"Лист {i+1}" for i, s in enumerate(sheets)]

        # текущая схема по листу
        markup = self._ensure_markup(obj)
        schema = (markup.annotation or {}).get("schema") or {}
        sheets_schema = schema.get("sheets") or {}
        col_roles = (sheets_schema.get(str(sheet_i)) or {}).get("col_roles") or []

        if len(col_roles) < max_cols:
            col_roles = (col_roles + ["NONE"] * (max_cols - len(col_roles)))[:max_cols]

        # авто-угадывание, если схемы нет
        if not sheets_schema.get(str(sheet_i)):
            guess = self._guess_schema(preview_rows)
            col_roles = (guess + ["NONE"] * (max_cols - len(guess)))[:max_cols]
            schema.setdefault("sheets", {})[str(sheet_i)] = {"col_roles": col_roles}
            markup.annotation["schema"] = schema
            markup.save(update_fields=["annotation"])

        # авто-шапки колонок: первая небустая среди верхних N
        col_headers = []
        for ci in range(max_cols):
            header = ""
            for r in preview_rows[:8]:
                cells = r.get("cells") or []
                if ci < len(cells):
                    val = (cells[ci] or "").strip()
                    if val:
                        header = val
                        break
            col_headers.append(header)

        ctx = dict(
            self.admin_site.each_context(request),
            title=f"Таблица: {obj.original_name}",
            file=obj,
            sheet_index=sheet_i,
            sheet_names=sheet_names,
            rows=preview_rows,
            cols=cols,
            role_choices=ROLE_CHOICES,
            col_roles=col_roles,
            col_headers=col_headers,
        )
        return TemplateResponse(request, "admin/app_estimate_imports/grid.html", ctx)

    def api_save_schema(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj:
            return HttpResponse(
                json.dumps({"ok": False, "error": "file_not_found"}),
                content_type="application/json",
                status=404,
            )
        try:
            payload = json.loads(request.body.decode("utf-8"))
            col_roles = payload.get("col_roles") or []
            sheet_i = str(payload.get("sheet_index") or "0")
            markup = self._ensure_markup(obj)
            ann = markup.annotation or {}
            schema = ann.get("schema") or {}
            sheets_schema = schema.get("sheets") or {}
            sheets_schema[sheet_i] = {"col_roles": col_roles}
            schema["sheets"] = sheets_schema
            ann["schema"] = schema
            markup.annotation = ann
            markup.save(update_fields=["annotation"])
            return HttpResponse(
                json.dumps({"ok": True}), content_type="application/json"
            )
        except Exception as e:
            return HttpResponse(
                json.dumps({"ok": False, "error": str(e)}),
                content_type="application/json",
                status=400,
            )

    def api_extract_from_grid(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj:
            return HttpResponse(
                json.dumps({"ok": False, "error": "file_not_found"}),
                content_type="application/json",
                status=404,
            )
        try:
            payload = json.loads(request.body.decode("utf-8"))
            col_roles = payload.get("col_roles") or []
            sheet_i = int(payload.get("sheet_index") or 0)

            from app_estimate_imports.services_markup import build_annotation_from_grid

            markup = self._ensure_markup(obj)
            annotation = build_annotation_from_grid(
                obj.parse_result,
                col_roles,
                sheet_index=sheet_i,
                existing=markup.annotation,
            )
            # параллельно сохраним схему у листа
            ann = annotation
            schema = ann.get("schema") or {}
            schema.setdefault("sheets", {})[str(sheet_i)] = {"col_roles": col_roles}
            ann["schema"] = schema

            markup.annotation = ann
            markup.save(update_fields=["annotation"])
            return HttpResponse(
                json.dumps({"ok": True}), content_type="application/json"
            )
        except Exception as e:
            return HttpResponse(
                json.dumps({"ok": False, "error": str(e)}),
                content_type="application/json",
                status=400,
            )

    # — пересчёт метаданных при сохранении (удобно в админке) —

    def save_model(self, request, obj: ImportedEstimateFile, form, change):
        super().save_model(request, obj, form, change)
        # При первичном аплоаде обновим size/sha/sheet_count
        from .utils import compute_sha256, count_sheets_safely

        if obj.file and (not obj.sha256 or not obj.size_bytes or not obj.sheet_count):
            f = obj.file.open("rb")
            obj.size_bytes = obj.file.size or 0
            obj.sha256 = compute_sha256(f)
            obj.sheet_count = count_sheets_safely(obj.file.path)
            obj.save(update_fields=["size_bytes", "sha256", "sheet_count"])


# Вне класса (ниже файла admin.py) — утилита сборки графа:
import hashlib
import re


def _norm(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _guess_schema(rows: list[dict]) -> list[str]:
    max_cols = max((len(r.get("cells") or []) for r in rows), default=0)
    roles = ["NONE"] * max_cols
    header_zone = rows[:8]
    for r in header_zone:
        cells = [(_norm(c) if c is not None else "") for c in r.get("cells", [])]
        for ci, val in enumerate(cells):
            low = val.lower()
            if "шифр" in low:
                roles[ci] = "TECH_CARD"  # практично: «ШИФР» = ТК
            if ("наименован" in low and "работ" in low) or low == "наименование":
                roles[ci] = "WORK"  # чаще всего это работа/описание
            if "ед.изм" in low or "ед. изм" in low:
                roles[ci] = "UNIT"
            if "кол-во" in low or "количество" in low or low in {"колво", "кол-во"}:
                roles[ci] = "QTY"
            if re.fullmatch(r"ур\d+", low):  # ур1..ур6
                idx = int(re.findall(r"\d+", low)[0])
                if 1 <= idx <= 6:
                    roles[ci] = f"GROUP-{idx}"
    # если явно не нашли уровни — попробуем 5..8, как в твоём примере
    if not any(r.startswith("GROUP-") for r in roles) and max_cols >= 9:
        for i, tag in enumerate(["GROUP-1", "GROUP-2", "GROUP-3", "GROUP-4"], start=5):
            if i < max_cols and roles[i] == "NONE":
                roles[i] = tag
    return roles


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def _detect_schema(rows: list[dict]) -> dict:
    """
    Находит индексы ключевых колонок по заголовкам.
    Возвращает: {"ur":[i1,i2,i3,i4], "shifr":i, "name":i, "unit":i, "qty":i}
    Фолбэк — твой пример: ур1..ур4=5..8, ШИФР=11, НАИМЕНОВАНИЕ=12, ЕД.ИЗМ.=13, КОЛ-ВО=14.
    """
    idx = {"ur": [], "shifr": 11, "name": 12, "unit": 13, "qty": 14}
    hdr_candidates = rows[:8]  # ищем шапку среди первых строк
    # явные ключевые слова
    for r in hdr_candidates:
        cells = [(_norm(c) if c is not None else "") for c in r.get("cells", [])]
        for ci, val in enumerate(cells):
            low = val.lower()
            if "шифр" in low:
                idx["shifr"] = ci
            if "наименован" in low and "работ" in low:
                idx["name"] = ci
            if "ед.изм" in low or "ед. изм" in low:
                idx["unit"] = ci
            if "кол-во" in low or "количество" in low:
                idx["qty"] = ci
            if re.fullmatch(r"ур\d+", low):  # ур1, ур2, ...
                idx["ur"].append(ci)
    # если «ур» не нашли, примем 5..8
    if not idx["ur"]:
        idx["ur"] = [5, 6, 7, 8]
    return idx


def _node_id(sheet_i: int, tag: str, val: str) -> str:
    return f"s{sheet_i}-{tag}-{_short_hash(val)}"


def _add_node(
    nodes_map: dict,
    nid: str,
    label: str,
    ntype: str,
    path: str,
    role: str,
    meta: dict | None = None,
):
    if nid not in nodes_map:
        nodes_map[nid] = {
            "data": {
                "id": nid,
                "label": label or nid,
                "type": ntype
                or "GROUP",  # фактический тип (из annotation) — перезапишется на клиенте/через API
                "role": role,  # происхождение узла: UR1/UR2/UR3/UR4/SHIFR/NAME
                "path": path,
                **(meta or {}),
            }
        }


def _add_edge(edges: list, src: str, dst: str, rel: str = "parent"):
    eid = f"{src}->{dst}" if rel == "parent" else f"{src}=>{rel}:{dst}"
    edges.append({"data": {"id": eid, "source": src, "target": dst, "rel": rel}})


def _build_graph(data: dict, annotation: dict) -> dict:
    """
    Строим граф из табличного JSON: слои по колонкам.
    - Для каждого листа добавляем корень `sheet:{i}`
    - По каждой строке соединяем непустые колонки ур1..ур4 → ШИФР → НАИМЕНОВАНИЕ
    - Узлы дедупим: (лист, колонка/роль, текст)
    - Перекрашивание по меткам из annotation.labels остаётся на клиенте (type)
    - Добавляем связи TECH_CARD→WORK/MATERIAL из annotation.tech_cards
    """
    labels = (annotation or {}).get("labels", {})
    nodes_map: dict[str, dict] = {}
    edges: list[dict] = []

    sheets = data.get("sheets") or []
    for si, sheet in enumerate(sheets):
        sheet_name = sheet.get("name") or f"Лист {si+1}"
        sheet_id = f"sheet:{si}"
        _add_node(
            nodes_map,
            sheet_id,
            f"Лист: {sheet_name}",
            "GROUP",
            sheet_name,
            role="SHEET",
        )

        rows = sheet.get("rows") or []
        sch = _detect_schema(rows)

        for row in rows:
            cells = row.get("cells") or []

            # 1) уровни ур1..ур4
            level_ids = []
            path_parts = [sheet_name]
            for li, col in enumerate(sch["ur"]):
                val = (
                    _norm(cells[col])
                    if col < len(cells)
                    and cells[col]
                    not in (
                        None,
                        "",
                    )
                    else ""
                )
                if not val:
                    continue
                nid = _node_id(si, f"UR{li+1}", val)
                ntype = labels.get(nid, "GROUP")
                _add_node(
                    nodes_map,
                    nid,
                    val,
                    ntype,
                    " / ".join([*path_parts, val]),
                    role=f"UR{li+1}",
                )
                level_ids.append(nid)
                path_parts.append(val)

            # 2) шифр (кандидат на TECH_CARD)
            shifr_val = ""
            shifr_id = ""
            col = sch["shifr"]
            if col is not None and col < len(cells):
                shifr_val = _norm(cells[col])
            if shifr_val:
                shifr_id = _node_id(si, "SHIFR", shifr_val)
                ntype = labels.get(shifr_id, "GROUP")
                _add_node(
                    nodes_map,
                    shifr_id,
                    shifr_val,
                    ntype,
                    " / ".join([*path_parts, shifr_val]),
                    role="SHIFR",
                )

            # 3) наименование работ (кандидат на WORK/MATERIAL или даже имя ТК)
            name_val = ""
            name_id = ""
            col = sch["name"]
            if col is not None and col < len(cells):
                name_val = _norm(cells[col])
            if name_val:
                meta = {}
                ucol = sch.get("unit")
                qcol = sch.get("qty")
                unit = (
                    _norm(cells[ucol])
                    if (ucol is not None and ucol < len(cells))
                    else ""
                )
                qty = (
                    _norm(cells[qcol])
                    if (qcol is not None and qcol < len(cells))
                    else ""
                )
                if unit:
                    meta["unit"] = unit
                if qty:
                    meta["qty"] = qty
                name_id = _node_id(si, "NAME", name_val)
                ntype = labels.get(name_id, "GROUP")
                _add_node(
                    nodes_map,
                    name_id,
                    name_val,
                    ntype,
                    " / ".join([*path_parts, name_val]),
                    role="NAME",
                    meta=meta,
                )

            # 4) рёбра: sheet → ур* → шифр → имя
            prev = sheet_id
            for nid in level_ids:
                _add_edge(edges, prev, nid, "parent")
                prev = nid
            if shifr_id:
                _add_edge(edges, prev, shifr_id, "parent")
                prev = shifr_id
            if name_id:
                _add_edge(edges, prev, name_id, "parent")

    # TECH_CARD → WORK/MATERIAL (из разметки)
    for tc in (annotation or {}).get("tech_cards") or []:
        tcu = tc.get("uid")
        for w in tc.get("works") or []:
            _add_edge(edges, tcu, w, "work")
        for m in tc.get("materials") or []:
            _add_edge(edges, tcu, m, "material")

    return {"nodes": list(nodes_map.values()), "edges": edges}
