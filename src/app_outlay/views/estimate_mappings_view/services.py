"""
Сервисный слой для сохранения маппингов.
"""

from typing import Dict, List, Tuple
from decimal import Decimal

from django.db import transaction

from app_outlay.models import Group, GroupTechnicalCardLink
from app_outlay.repositories import EstimateRepository, TechnicalCardRepository


class GroupHierarchyService:
    """Сервис управления иерархией групп."""

    def __init__(self, estimate_id: int):
        self.estimate_id = estimate_id
        self._cache: Dict[str, Group] = {}

    def get_or_create_hierarchy(self, section_path: str, order_hint: int = 0) -> Group:
        """
        Создаёт иерархию групп по пути "Родитель / Дочерняя / Внучатая".
        Возвращает самую глубокую группу.
        """
        if section_path in self._cache:
            return self._cache[section_path]

        parts = [p.strip() for p in section_path.split("/") if p.strip()]

        parent = None
        current_path = ""

        for idx, part in enumerate(parts):
            if current_path:
                current_path += f" / {part}"
            else:
                current_path = part

            if current_path in self._cache:
                parent = self._cache[current_path]
                continue

            group, created = Group.objects.get_or_create(
                estimate_id=self.estimate_id,
                name=part,
                parent=parent,
                defaults={"order": order_hint + idx},
            )

            self._cache[current_path] = group
            parent = group

        return parent


class MappingSaveService:
    """Сервис сохранения сопоставлений ТК."""

    def __init__(
        self,
        estimate_repo: EstimateRepository = None,
        tc_repo: TechnicalCardRepository = None,
    ):
        self.estimate_repo = estimate_repo or EstimateRepository()
        self.tc_repo = tc_repo or TechnicalCardRepository()

    @transaction.atomic
    def save_mappings(
        self,
        estimate_id: int,
        mappings: List[Dict],
        deletions: List[int],
    ) -> Dict[str, int]:
        """
        Сохранение маппингов и удаление указанных строк.

        Returns:
            Dict с счетчиками: created, updated, deleted
        """
        estimate = self.estimate_repo.get_by_id_or_raise(estimate_id)

        stats = {
            "created": 0,
            "updated": 0,
            "deleted": 0,
        }

        # КРИТИЧНО: Удаляем ВСЕ старые линки с указанными row_index из ВСЕЙ сметы
        # (не только из deletions, но и из mappings для предотвращения дубликатов)
        all_row_indices = set(deletions)
        all_row_indices.update(
            m.get("row_index") for m in mappings if m.get("row_index")
        )

        if all_row_indices:
            deleted_count, _ = GroupTechnicalCardLink.objects.filter(
                group__estimate=estimate,
                source_row_index__in=all_row_indices,
            ).delete()
            stats["deleted"] = deleted_count

        # Сохранение
        if mappings:
            hierarchy_service = GroupHierarchyService(estimate_id)
            created, updated = self._save_mappings_batch(
                estimate, mappings, hierarchy_service
            )
            stats["created"] = created
            stats["updated"] = updated

        return stats

    def _save_mappings_batch(
        self,
        estimate,
        mappings: List[Dict],
        hierarchy_service: GroupHierarchyService,
    ) -> Tuple[int, int]:
        """Сохранение батча маппингов."""
        by_section = {}
        for m in mappings:
            section = m.get("section", "Без группы")
            if section not in by_section:
                by_section[section] = []
            by_section[section].append(m)

        created_count = 0
        updated_count = 0

        for section_idx, (section_name, items) in enumerate(by_section.items()):
            group = hierarchy_service.get_or_create_hierarchy(
                section_name, order_hint=section_idx * 100
            )

            for idx, item in enumerate(items):
                tc_id = item.get("tc_id")
                quantity = Decimal(str(item.get("quantity", 0)))
                row_index = item.get("row_index")

                if not tc_id or quantity <= 0:
                    continue

                tc_version = self.tc_repo.get_published_version(tc_id)
                if not tc_version:
                    continue

                # Всегда создаём новые линки (старые удалены выше)
                GroupTechnicalCardLink.objects.create(
                    group=group,
                    technical_card_version=tc_version,
                    quantity=quantity,
                    order=idx,
                    source_row_index=row_index,
                )
                created_count += 1

        return created_count, updated_count
