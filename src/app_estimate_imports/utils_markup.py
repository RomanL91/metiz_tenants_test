from __future__ import annotations
import uuid


def ensure_uids_in_tree(data: dict) -> dict:
    """
    Проставляет uid каждому узлу в sheets[].blocks[*] и формирует blocks из rows при необходимости.
    Узел: {"title": "...", "children": [...], "uid": "..."}.
    """
    if not data:
        return {"sheets": []}
    sheets = data.get("sheets") or []
    for si, sheet in enumerate(sheets):
        if "blocks" in sheet and isinstance(sheet["blocks"], list):
            _walk_blocks(sheet["blocks"], prefix=f"s{si}")
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
                        "uid": f"s{si}-r{ri}-{uuid.uuid4().hex[:8]}",
                    }
                )
            sheet["blocks"] = blocks
    return data


def _walk_blocks(blocks: list, prefix: str):
    for i, b in enumerate(blocks):
        if "uid" not in b or not b["uid"]:
            b["uid"] = f"{prefix}-b{i}-{uuid.uuid4().hex[:8]}"
        children = b.get("children") or []
        if isinstance(children, list) and children:
            _walk_blocks(children, prefix=b["uid"])
