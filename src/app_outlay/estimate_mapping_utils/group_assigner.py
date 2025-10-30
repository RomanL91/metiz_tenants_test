"""
Распределение техкарт по группам и построение дерева.

Следует принципам:
- Builder Pattern: пошаговое построение дерева
- Immutability: не мутирует исходные данные
- Clear Algorithm: явный алгоритм распределения
"""

from typing import List, Dict, Any, Tuple


class GroupTreeBuilder:
    """
    Строитель дерева групп с распределением техкарт.

    Алгоритм:
    1. Расчёт глубины каждой группы
    2. Построение дерева children
    3. Распределение ТК по самым глубоким группам
    4. Сборка результата
    """

    def __init__(self, groups: List[Dict]):
        """
        Args:
            groups: Список нормализованных групп от GroupAnnotationLoader
        """
        self.groups = groups
        self.groups_by_id = {g["uid"]: g for g in groups}
        self._calculate_depths()

    def _calculate_depths(self):
        """
        Расчёт глубины каждой группы в иерархии.

        Глубина = количество предков до корня.
        """

        def calculate_depth(uid: str) -> int:
            """Рекурсивный расчёт глубины."""
            depth = 0
            current = self.groups_by_id.get(uid)

            while current and current.get("parent_uid"):
                depth += 1
                parent_uid = current["parent_uid"]
                current = self.groups_by_id.get(parent_uid)

                # Защита от циклов
                if depth > 100:
                    break

            return depth

        for group in self.groups:
            group["_depth"] = calculate_depth(group["uid"])

    def _group_covers_row(self, group: Dict, row_index: int) -> bool:
        """
        Проверка покрытия строки группой.

        Args:
            group: Группа с ranges
            row_index: Индекс строки (1-based)

        Returns:
            bool: True если строка входит в один из диапазонов группы
        """
        for start, end in group.get("rows") or []:
            if start <= row_index <= end:
                return True
        return False

    def assign_tcs_to_groups(self, tcs: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """
        Распределение техкарт по группам.

        Алгоритм:
        - Каждая ТК присваивается самой ГЛУБОКОЙ группе, которая её покрывает
        - Если нет подходящей группы → loose

        Args:
            tcs: Список детектированных ТК
                [{'row_index': int, 'name': str, ...}, ...]

        Returns:
            Tuple[tree, loose]:
                - tree: Дерево корневых групп с children и tcs
                - loose: ТК без группы

        Example:
            >>> builder = GroupTreeBuilder(groups)
            >>> tree, loose = builder.assign_tcs_to_groups(tcs)
            >>> len(loose)
            5
        """
        # Распределение ТК по группам
        tcs_by_group = {g["uid"]: [] for g in self.groups}
        loose = []

        for tc in tcs:
            row_index = tc.get("row_index")

            # Найти все группы, покрывающие эту строку
            covering_groups = [
                g for g in self.groups if self._group_covers_row(g, row_index)
            ]

            if covering_groups:
                # Выбрать самую глубокую
                covering_groups.sort(key=lambda x: x["_depth"], reverse=True)
                deepest = covering_groups[0]
                tcs_by_group[deepest["uid"]].append(tc)
            else:
                loose.append(tc)

        # Построение дерева
        tree = self._build_tree(tcs_by_group)

        return tree, loose

    def _build_tree(self, tcs_by_group: Dict[str, List[Dict]]) -> List[Dict]:
        """
        Построение дерева групп с прикреплёнными ТК.

        Args:
            tcs_by_group: Словарь {group_uid: [tc, tc, ...]}

        Returns:
            List[Dict]: Список корневых групп с рекурсивными children

        Structure:
            [
                {
                    'uid': str,
                    'name': str,
                    'color': str,
                    'rows': List,
                    'tcs': List[Dict],
                    'children': [...]  # рекурсивно
                },
                ...
            ]
        """
        # Группировка по parent
        children_map = {g["uid"]: [] for g in self.groups}
        roots = []

        for group in self.groups:
            parent_uid = group.get("parent_uid")
            if parent_uid and parent_uid in children_map:
                children_map[parent_uid].append(group)
            else:
                roots.append(group)

        def build_node(group: Dict) -> Dict:
            """Рекурсивная сборка узла дерева."""
            node = {
                "uid": group["uid"],
                "name": group["name"],
                "color": group["color"],
                "rows": group["rows"],
                "tcs": tcs_by_group.get(group["uid"], []),
                "children": [],
            }

            # Рекурсивно добавляем детей
            for child_group in children_map.get(group["uid"], []):
                node["children"].append(build_node(child_group))

            return node

        # Строим дерево от корней
        tree = [build_node(root) for root in roots]

        return tree

    def get_flat_list_with_tcs(self, tree: List[Dict]) -> List[Dict]:
        """
        Преобразование дерева в плоский список групп с ТК.

        Args:
            tree: Дерево групп

        Returns:
            List[Dict]: Плоский список
                [
                    {
                        'path': 'Root / Child / Subchild',
                        'color': '#fff',
                        'tcs': [...]
                    },
                    ...
                ]

        Example:
            >>> flat = builder.get_flat_list_with_tcs(tree)
            >>> flat[0]['path']
            'Общестроительные работы / Фундаменты'
        """
        result = []

        def flatten(node: Dict, parent_path: str = None):
            """Рекурсивное выравнивание."""
            name = node.get("name", "Группа")
            path = name if parent_path is None else f"{parent_path} / {name}"

            if node.get("tcs"):
                result.append(
                    {
                        "path": path,
                        "color": node.get("color", "#eef"),
                        "tcs": node["tcs"],
                    }
                )

            for child in node.get("children", []):
                flatten(child, path)

        for root in tree:
            flatten(root)

        return result
