"""
Репозиторий для работы с данными сметы.

Ответственность:
- Доступ к данным Estimate, EstimateOverheadCostLink, GroupTechnicalCardLink
- Оптимизация запросов (select_related, prefetch_related)
- Избежание N+1 проблем
- Агрегация данных из БД

Принципы:
- Single Responsibility: только доступ к данным
- N+1 Prevention: оптимизация запросов через select/prefetch_related
- Query Optimization: только необходимые поля через .only()
"""

from decimal import Decimal
from typing import Dict, List, Optional

from django.db.models import Prefetch, QuerySet

from app_outlay.exceptions import EstimateNotFoundError
from app_outlay.models import Estimate, EstimateOverheadCostLink, GroupTechnicalCardLink
from app_outlay.views.estimate_calc_view.utils_calc import _base_costs_live, _dec
from app_technical_cards.models import (
    TechnicalCard,
    TechnicalCardVersion,
    TechnicalCardVersionMaterial,
    TechnicalCardVersionWork,
)
from core.base_repository import BaseRepository


class EstimateRepository(BaseRepository[Estimate]):
    """
    Репозиторий для работы со сметами.

    Оптимизации:
    - select_related для связанных моделей
    - prefetch_related для M2M
    - .only() для выборки только нужных полей
    """

    model = Estimate

    def get_by_id_or_raise(self, estimate_id: int) -> Estimate:
        """
        Получить смету по ID или выбросить исключение.

        Args:
            estimate_id: ID сметы

        Returns:
            Объект сметы

        Raises:
            EstimateNotFoundError: Если смета не найдена
        """
        estimate = self.get_by_id(estimate_id)
        if not estimate:
            raise EstimateNotFoundError(estimate_id)
        return estimate

    def get_overhead_links(
        self, estimate: Estimate
    ) -> QuerySet[EstimateOverheadCostLink]:
        """
        Получить активные накладные расходы сметы.

        Оптимизация:
        - select_related('overhead_cost_container') для избежания N+1
        - фильтрация по is_active на уровне БД

        Args:
            estimate: Объект сметы

        Returns:
            QuerySet активных накладных расходов
        """
        return (
            EstimateOverheadCostLink.objects.filter(estimate=estimate, is_active=True)
            .select_related("overhead_cost_container")
            .order_by("order", "id")
        )

    def get_tc_links_for_base_calculation(
        self, estimate: Estimate
    ) -> QuerySet[GroupTechnicalCardLink]:
        """
        Получить связи ТК для расчёта базы (МАТ/РАБ).

        Оптимизация:
        - select_related('technical_card_version') для версий ТК
        - .only() для загрузки только нужных полей

        Args:
            estimate: Объект сметы

        Returns:
            QuerySet связей ТК с минимальным набором полей
        """
        return (
            GroupTechnicalCardLink.objects.filter(group__estimate=estimate)
            .select_related("technical_card_version")
            .only("id", "quantity", "technical_card_version__id")
        )

    def calculate_base_totals(self, estimate: Estimate) -> Dict[str, Decimal]:
        """
        Рассчитать базовые итоги (МАТ/РАБ) для всех ТК в смете.

        ВАЖНО: Этот метод используется для подготовки контекста НР.
        Расчёт идёт по "живым" ценам из справочников (без надбавк).

        Args:
            estimate: Объект сметы

        Returns:
            Dict с ключами:
                - total_base_mat: Decimal
                - total_base_work: Decimal

        Note:
            Расчёт базы делегируется в utils_calc._base_costs_live()
        """
        tc_links = self.get_tc_links_for_base_calculation(estimate)

        total_base_mat = Decimal("0")
        total_base_work = Decimal("0")

        for link in tc_links:
            ver = link.technical_card_version
            if not ver:
                continue

            base = _base_costs_live(ver)
            qty = _dec(link.quantity)

            total_base_mat += base.mat * qty
            total_base_work += base.work * qty

        return {
            "total_base_mat": total_base_mat,
            "total_base_work": total_base_work,
        }


class OverheadCostRepository:
    """
    Репозиторий для работы с накладными расходами.

    Ответственность:
    - Агрегация данных НР для сметы
    - Расчёт средневзвешенных процентов распределения
    """

    @staticmethod
    def aggregate_overhead_data(
        links: QuerySet[EstimateOverheadCostLink],
    ) -> Dict[str, Decimal]:
        """
        Агрегировать данные накладных расходов.

        Рассчитывает:
        - Общую сумму НР
        - Средневзвешенные проценты распределения на МАТ/РАБ

        Args:
            links: QuerySet активных накладных расходов

        Returns:
            Dict с ключами:
                - overhead_amount: Decimal
                - avg_materials_pct: Decimal (0-100)
                - avg_works_pct: Decimal (0-100)
        """
        total_overhead = Decimal("0")
        weighted_mat_pct = Decimal("0")
        weighted_work_pct = Decimal("0")

        for link in links:
            # Используем snapshot или текущее значение из контейнера
            amount = (
                link.snapshot_total_amount
                or link.overhead_cost_container.total_amount
                or Decimal("0")
            )

            mat_pct = (
                link.snapshot_materials_percentage
                or link.overhead_cost_container.materials_percentage
                or Decimal("0")
            )

            work_pct = (
                link.snapshot_works_percentage
                or link.overhead_cost_container.works_percentage
                or Decimal("0")
            )

            total_overhead += amount
            weighted_mat_pct += mat_pct * amount
            weighted_work_pct += work_pct * amount

        # Средневзвешенные проценты
        if total_overhead > 0:
            avg_mat_pct = weighted_mat_pct / total_overhead
            avg_work_pct = weighted_work_pct / total_overhead
        else:
            avg_mat_pct = Decimal("0")
            avg_work_pct = Decimal("0")

        return {
            "overhead_amount": total_overhead,
            "avg_materials_pct": avg_mat_pct,
            "avg_works_pct": avg_work_pct,
        }


class TechnicalCardRepository:
    """Репозиторий доступа к техническим картам и их версиям."""

    @staticmethod
    def card_exists(card_id: int) -> bool:
        """Проверить существование карточки ТК."""
        return TechnicalCard.objects.filter(pk=card_id).exists()

    @staticmethod
    def get_latest_published_version(card_id: int) -> Optional[TechnicalCardVersion]:
        """
        Получить последнюю опубликованную версию для карточки.

        Args:
            card_id: ID карточки ТК

        Returns:
            TechnicalCardVersion или None
        """
        return (
            TechnicalCardVersion.objects.filter(card_id=card_id, is_published=True)
            .select_related("card")
            .order_by("-created_at", "-id")
            .first()
        )

    @staticmethod
    def bulk_get_latest_published_versions(
        card_ids: List[int],
    ) -> Dict[int, TechnicalCardVersion]:
        """
        Bulk получение последних опубликованных версий для множества карточек.

        ОПТИМИЗАЦИЯ:
        - Один запрос для всех версий
        - Prefetch materials и works
        - Prefetch связанных справочников (material, work)

        Args:
            card_ids: Список ID карточек

        Returns:
            Dict[card_id -> TechnicalCardVersion] с предзагруженными связями
        """
        if not card_ids:
            return {}

        # Prefetch материалов с живыми ценами из справочников
        materials_prefetch = Prefetch(
            "material_items",
            queryset=TechnicalCardVersionMaterial.objects.select_related(
                "material", "unit_ref"
            ).order_by("order", "id"),
        )

        # Prefetch работ с живыми ценами из справочников
        works_prefetch = Prefetch(
            "work_items",
            queryset=TechnicalCardVersionWork.objects.select_related(
                "work", "unit_ref"
            ).order_by("order", "id"),
        )

        # Получаем все последние опубликованные версии одним запросом
        versions = (
            TechnicalCardVersion.objects.filter(
                card_id__in=card_ids, is_published=True
            )
            .select_related("card", "card__unit_ref")
            .prefetch_related(materials_prefetch, works_prefetch)
            .order_by("card_id", "-created_at", "-id")
        )

        # Группируем по card_id (берём первую = последнюю по дате)
        result = {}
        for version in versions:
            if version.card_id not in result:
                result[version.card_id] = version

        return result
