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
from typing import Dict
from django.db.models import QuerySet

from app_outlay.models import (
    Estimate,
    EstimateOverheadCostLink,
    GroupTechnicalCardLink,
)
from app_outlay.exceptions import EstimateNotFoundError
from app_outlay.views.estimate_calc_view.utils_calc import _base_costs_live, _dec
from app_technical_cards.models import TechnicalCardVersion
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
        Расчёт идёт по "живым" ценам из справочников (без надбавок).

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
    """
    Репозиторий для работы с техническими картами.

    Примечание:
    Пока минимальный функционал, т.к. основная логика в utils_calc.py
    """

    @staticmethod
    def version_exists(tc_or_ver_id: int) -> bool:
        """
        Проверить существование версии ТК или карточки.

        Args:
            tc_or_ver_id: ID версии или ID карточки

        Returns:
            True если версия существует
        """
        # Проверяем как версию
        if TechnicalCardVersion.objects.filter(pk=tc_or_ver_id).exists():
            return True

        # Проверяем как карточку (есть ли у неё версии)
        return TechnicalCardVersion.objects.filter(card_id=tc_or_ver_id).exists()

    @staticmethod
    def get_published_version(tc_or_ver_id: int):
        """
        Получить опубликованную версию ТК.

        Args:
            tc_or_ver_id: ID версии или ID карточки

        Returns:
            TechnicalCardVersion или None
        """
        # Сначала пробуем найти версию напрямую
        version = TechnicalCardVersion.objects.filter(pk=tc_or_ver_id).first()
        if version:
            return version

        # Если не найдено, ищем опубликованную версию по ID карточки
        return TechnicalCardVersion.objects.filter(
            card_id=tc_or_ver_id, is_published=True
        ).first()
