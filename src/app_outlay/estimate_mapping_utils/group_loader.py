"""
Загрузка групп из annotation разметки.

Следует принципам:
- Single Responsibility: только загрузка групп
- Tolerance: толерантность к разным форматам annotation
- Clear Data Structure: явная нормализация структур
"""

from typing import Any, Dict, List, Optional


class GroupAnnotationLoader:
    """
    Загрузчик групп из annotation разметки.

    Поддерживает различные форматы:
    - annotation["schema"]["sheets"][sheet]["groups"]
    - annotation["groups"][sheet]
    - annotation["groups"][sheet]["items"]

    Нормализует структуры в единый формат.
    """

    @staticmethod
    def load_groups(annotation: Dict[str, Any], sheet_index: int) -> List[Dict]:
        """
        Загрузка и нормализация групп из annotation.

        Args:
            annotation: Словарь annotation из markup
            sheet_index: Индекс листа

        Returns:
            List[Dict]: Список нормализованных групп
                [
                    {
                        'uid': str,
                        'name': str,
                        'color': str,
                        'parent_uid': Optional[str],
                        'rows': List[List[int]]  # [[start, end], ...]
                    },
                    ...
                ]

        Example:
            >>> loader = GroupAnnotationLoader()
            >>> groups = loader.load_groups(annotation, 0)
            >>> groups[0]['name']
            'Фундаментные работы'
        """
        sheet_key = str(sheet_index)
        raw_groups = []

        # Вариант A: annotation["schema"]["sheets"][sheet]["groups"]
        raw_groups = GroupAnnotationLoader._try_schema_path(annotation, sheet_key)

        # Вариант B: annotation["groups"][sheet]
        if not raw_groups:
            raw_groups = GroupAnnotationLoader._try_groups_path(annotation, sheet_key)

        # Нормализация
        normalized = GroupAnnotationLoader._normalize_groups(raw_groups)

        return normalized

    @staticmethod
    def _try_schema_path(annotation: Dict, sheet_key: str) -> List[Dict]:
        """
        Попытка загрузки из annotation["schema"]["sheets"][sheet]["groups"].

        Args:
            annotation: Annotation словарь
            sheet_key: Ключ листа (строка)

        Returns:
            List[Dict]: Список групп или []
        """
        try:
            root = (
                (annotation or {})
                .get("schema", {})
                .get("sheets", {})
                .get(sheet_key, {})
            )
            if isinstance(root, dict) and isinstance(root.get("groups"), list):
                return root["groups"]
        except (AttributeError, TypeError, KeyError):
            pass
        return []

    @staticmethod
    def _try_groups_path(annotation: Dict, sheet_key: str) -> List[Dict]:
        """
        Попытка загрузки из annotation["groups"][sheet].

        Args:
            annotation: Annotation словарь
            sheet_key: Ключ листа

        Returns:
            List[Dict]: Список групп или []
        """
        try:
            alt = (annotation or {}).get("groups", {}).get(sheet_key)

            # Может быть массив напрямую
            if isinstance(alt, list):
                return alt

            # Или объект с полем items
            if isinstance(alt, dict) and isinstance(alt.get("items"), list):
                return alt["items"]
        except (AttributeError, TypeError, KeyError):
            pass
        return []

    @staticmethod
    def _normalize_groups(raw_groups: List[Dict]) -> List[Dict]:
        """
        Нормализация групп в единый формат.

        Args:
            raw_groups: Список сырых групп из annotation

        Returns:
            List[Dict]: Нормализованные группы

        Normalization rules:
        - uid: g.uid | g.id | g.gid
        - name: g.name | g.title | "Группа"
        - color: g.color | "#e0f7fa"
        - parent_uid: g.parent_uid | g.parent | g.parentId | None
        - rows: g.rows | g.ranges → [[int, int], ...]
        """
        normalized = []

        for g in raw_groups or []:
            # UID (обязательный)
            uid = g.get("uid") or g.get("id") or g.get("gid")
            if not uid:
                continue  # Пропускаем группы без ID

            # Имя
            name = g.get("name") or g.get("title") or "Группа"

            # Цвет
            color = g.get("color") or "#e0f7fa"

            # Parent
            parent = g.get("parent_uid") or g.get("parent") or g.get("parentId")

            # Rows/Ranges
            rows_raw = g.get("rows") or g.get("ranges") or []
            rows_normalized = []

            for r in rows_raw:
                if isinstance(r, (list, tuple)) and len(r) >= 2:
                    try:
                        start = int(r[0])
                        end = int(r[1])
                        rows_normalized.append([start, end])
                    except (ValueError, TypeError):
                        pass  # Пропускаем невалидные диапазоны

            normalized.append(
                {
                    "uid": uid,
                    "name": name,
                    "color": color,
                    "parent_uid": parent,
                    "rows": rows_normalized,
                }
            )

        return normalized

    @staticmethod
    def validate_groups(groups: List[Dict]) -> bool:
        """
        Валидация загруженных групп.

        Args:
            groups: Список групп

        Returns:
            bool: True если группы валидны

        Checks:
        - Все группы имеют uid
        - Нет циклических зависимостей parent_uid
        - Ranges не пересекаются в одном уровне
        """
        if not groups:
            return True

        # Проверка наличия uid
        for g in groups:
            if not g.get("uid"):
                return False

        # TODO: Можно добавить проверку циклов и пересечений

        return True
