"""
Обработчик операций с разметкой (markup) - вспомогательные методы.

Назначение модуля
-----------------
- Обеспечение наличия разметки и UID'ов в структуре данных.
- Построение базовой структуры разметки из результата парсинга.

Особенности
-----------
- Содержит только вспомогательные методы, используемые другими сервисами.
- UI-методы удалены, так как разметка теперь происходит автоматически.
"""

from uuid import uuid4

from app_estimate_imports.handlers.base_handler import BaseHandler
from app_estimate_imports.models import ParseMarkup


class MarkupHandler(BaseHandler):
    """Обработчик операций с разметкой - только вспомогательные методы"""

    def ensure_markup_exists(self, file_obj) -> ParseMarkup:
        """
        Гарантирует наличие ParseMarkup и uid'ов в ParseResult.data.

        Используется другими сервисами для обеспечения базовой структуры разметки.
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

    def ensure_uids_in_tree(self, data: dict) -> dict:
        """
        Проставляет uid каждому узлу в sheets[].blocks[*] и формирует blocks из rows при необходимости.
        Узел: {"title": "...", "children": [...], "uid": "..."}.

        Используется для обеспечения стабильных идентификаторов узлов дерева.
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

    def build_markup_skeleton(self, parse_result) -> dict:
        """
        Строит базовую структуру разметки:
        - labels: все найденные uid -> "GROUP" (можно править руками в админке)
        - tech_cards: []

        Может использоваться для автоматической инициализации разметки.
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

    def _walk_blocks(self, blocks: list, prefix: str):
        """
        Рекурсивно проходит по блокам и проставляет uid'ы.

        Вспомогательный метод для ensure_uids_in_tree.
        """
        for i, b in enumerate(blocks):
            if "uid" not in b or not b["uid"]:
                b["uid"] = f"{prefix}-b{i}-{uuid4().hex[:8]}"
            children = b.get("children") or []
            if isinstance(children, list) and children:
                self._walk_blocks(children, prefix=b["uid"])
