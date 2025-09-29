import secrets
from typing import Dict, List, Optional

from app_estimate_imports.services.base_service import BaseService


class GroupService(BaseService):
    """Сервис для работы с группами строк"""

    def load_groups(self, markup, sheet_index: int) -> List[Dict]:
        """Загружает группы для листа с нормализацией"""
        annotation = markup.annotation or {}
        sheet_key = str(sheet_index)
        groups_all = []

        # Ищем в нескольких местах annotation
        schema = annotation.get("schema", {})
        sheets_schema = schema.get("sheets", {})
        sheet_data = sheets_schema.get(sheet_key)

        if isinstance(sheet_data, dict) and isinstance(sheet_data.get("groups"), list):
            groups_all = sheet_data["groups"]

        # Нормализация групп
        normalized = []
        for group in groups_all or []:
            uid = group.get("uid") or group.get("id") or group.get("gid")
            if not uid:
                continue

            name = group.get("name") or group.get("title") or "Группа"
            parent = group.get("parent_uid") or group.get("parent") or None
            color = group.get("color") or "#90caf9"
            rows = group.get("rows") or group.get("ranges") or []

            # Нормализация диапазонов
            normalized_rows = []
            for row_range in rows:
                if isinstance(row_range, (list, tuple)) and len(row_range) >= 2:
                    try:
                        normalized_rows.append([int(row_range[0]), int(row_range[1])])
                    except (ValueError, TypeError):
                        continue

            normalized.append(
                {
                    "uid": uid,
                    "name": name,
                    "parent_uid": parent,
                    "color": color,
                    "rows": normalized_rows,
                }
            )

        return normalized

    def create_group(
        self,
        markup,
        sheet_index: int,
        name: str,
        rows: List[List[int]],
        parent_uid: Optional[str] = None,
        color: str = "#E0F7FA",
    ) -> Dict:
        """Создает новую группу"""
        if not name.strip() or not rows:
            raise ValueError("Имя группы и диапазоны строк обязательны")

        groups = self.load_groups(markup, sheet_index)

        # Проверка покрытия родителем
        if parent_uid:
            parent = next((g for g in groups if g["uid"] == parent_uid), None)
            if not parent:
                raise ValueError("Родительская группа не найдена")
            if not self._ranges_cover(parent.get("rows", []), rows):
                raise ValueError("Родительская группа не покрывает указанные строки")

        # Создание группы
        uid = "grp_" + secrets.token_hex(8)
        new_group = {
            "uid": uid,
            "name": name.strip(),
            "color": color,
            "parent_uid": parent_uid,
            "rows": rows,
        }

        # Сохранение
        groups.append(new_group)
        self._save_groups(markup, sheet_index, groups)

        return new_group

    def delete_group(self, markup, sheet_index: int, uid: str) -> None:
        """Удаляет группу и всех её потомков"""
        groups = self.load_groups(markup, sheet_index)

        # Сбор всех потомков
        to_delete = set()

        def collect_descendants(group_uid):
            to_delete.add(group_uid)
            for group in groups:
                if group.get("parent_uid") == group_uid:
                    collect_descendants(group["uid"])

        collect_descendants(uid)

        # Фильтрация
        filtered_groups = [g for g in groups if g["uid"] not in to_delete]
        self._save_groups(markup, sheet_index, filtered_groups)

    def _ranges_cover(
        self, parent_ranges: List[List[int]], child_ranges: List[List[int]]
    ) -> bool:
        """Проверяет, что родительские диапазоны покрывают дочерние"""
        for start, end in child_ranges:
            covered = any(
                p_start <= start and end <= p_end for p_start, p_end in parent_ranges
            )
            if not covered:
                return False
        return True

    def _save_groups(self, markup, sheet_index: int, groups: List[Dict]) -> None:
        """Сохраняет группы в разметку"""
        annotation = markup.annotation or {}
        schema = annotation.get("schema", {})
        sheets_schema = schema.get("sheets", {})

        sheet_config = sheets_schema.get(str(sheet_index), {})
        sheet_config["groups"] = groups

        sheets_schema[str(sheet_index)] = sheet_config
        schema["sheets"] = sheets_schema
        annotation["schema"] = schema

        markup.annotation = annotation
        markup.save(update_fields=["annotation"])
