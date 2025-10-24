"""
Сервисный слой для расчёта технических карт с учётом накладных расходов.

Ответственность:
- Бизнес-логика расчётов
- Подготовка контекста НР
- Кеширование расчётов
- Делегирование доступа к данным в репозитории

Принципы:
- Single Responsibility: каждый сервис отвечает за свою область
- Dependency Injection: зависимости передаются через конструктор
- Caching: кеширование контекста НР для избежания повторных запросов
"""

from functools import lru_cache
from decimal import Decimal
from typing import Dict, Optional, Tuple, List

from app_outlay.models import Estimate
from app_outlay.views.estimate_calc_view.utils_calc import calc_for_tc as calc_tc_util

from app_outlay.repositories import (
    EstimateRepository,
    OverheadCostRepository,
    TechnicalCardRepository,
)
from app_outlay.exceptions import (
    TechnicalCardNotFoundError,
    OverheadContextCalculationError,
)


class OverheadContextService:
    """
    Сервис для расчёта контекста накладных расходов сметы.

    Контекст НР содержит:
    - Общую базу (МАТ/РАБ) всех ТК в смете
    - Общую сумму НР
    - Средневзвешенные проценты распределения НР

    Кеширование:
    - Использует lru_cache для избежания повторных запросов к БД
    - Кеш инвалидируется при изменении сметы (через estimate_id)
    """

    def __init__(
        self,
        estimate_repo: EstimateRepository = None,
        overhead_repo: OverheadCostRepository = None,
    ):
        """
        Инициализация сервиса.

        Args:
            estimate_repo: Репозиторий смет (Dependency Injection)
            overhead_repo: Репозиторий НР (Dependency Injection)
        """
        self.estimate_repo = estimate_repo or EstimateRepository()
        self.overhead_repo = overhead_repo or OverheadCostRepository()

    @lru_cache(maxsize=100)
    def _calculate_context_cached(self, estimate_id: int) -> Optional[Dict]:
        """
        Кешированный расчёт контекста НР.

        ВНИМАНИЕ:
        Метод кеширует результат по estimate_id.
        При изменении НР сметы нужно либо сбросить кеш,
        либо использовать версионирование (например, updated_at).

        Args:
            estimate_id: ID сметы

        Returns:
            Dict с контекстом НР или None если НР не используются
        """
        estimate = self.estimate_repo.get_by_id_or_raise(estimate_id)

        # 1. Получаем активные накладные расходы
        overhead_links = self.estimate_repo.get_overhead_links(estimate)

        if not overhead_links.exists():
            return None

        # 2. Агрегируем данные НР
        overhead_data = self.overhead_repo.aggregate_overhead_data(overhead_links)

        overhead_amount = overhead_data["overhead_amount"]
        if overhead_amount <= 0:
            return None

        # 3. Рассчитываем базовые итоги (МАТ/РАБ) по всем ТК сметы
        base_totals = self.estimate_repo.calculate_base_totals(estimate)

        # 4. Формируем контекст для utils_calc.calc_for_tc()
        return {
            "total_base_mat": base_totals["total_base_mat"],
            "total_base_work": base_totals["total_base_work"],
            "overhead_amount": overhead_amount,
            "overhead_mat_pct": overhead_data["avg_materials_pct"],
            "overhead_work_pct": overhead_data["avg_works_pct"],
        }

    def calculate_context(self, estimate: Estimate) -> Optional[Dict]:
        """
        Получить контекст НР для сметы (с кешированием).

        Args:
            estimate: Объект сметы

        Returns:
            Dict с контекстом НР или None если НР не используются
        """
        try:
            return self._calculate_context_cached(estimate.id)
        except Exception as e:
            raise OverheadContextCalculationError(str(e)) from e

    @staticmethod
    def clear_cache():
        """
        Очистить кеш контекстов НР.

        Использовать при изменении НР сметы.
        """
        OverheadContextService._calculate_context_cached.cache_clear()


class TechnicalCardCalculationService:
    """
    Сервис для расчёта технических карт с учётом НР.

    Делегирует основную логику расчёта в app_outlay.utils_calc.calc_for_tc(),
    но добавляет валидацию и обработку ошибок.
    """

    def __init__(self, tc_repo: TechnicalCardRepository = None):
        """
        Инициализация сервиса.

        Args:
            tc_repo: Репозиторий ТК (Dependency Injection)
        """
        self.tc_repo = tc_repo or TechnicalCardRepository()

    def calculate(
        self,
        tc_id: int,
        quantity: float,
        overhead_context: Optional[Dict] = None,
    ) -> Tuple[Dict[str, Decimal], List[str]]:
        """
        Рассчитать показатели ТК с учётом НР.

        Args:
            tc_id: ID технической карты или версии
            quantity: Количество
            overhead_context: Контекст НР (опционально)

        Returns:
            Tuple:
                - Dict[str, Decimal]: Расчёты по ключам (UNIT_PRICE_OF_MATERIAL, etc)
                - List[str]: Порядок ключей для отображения

        Raises:
            TechnicalCardNotFoundError: Если ТК не найдена
        """
        # Валидация существования ТК
        if not self.tc_repo.version_exists(tc_id):
            raise TechnicalCardNotFoundError(tc_id)

        # Делегируем расчёт в утилиту
        calc, order = calc_tc_util(
            tc_or_ver_id=tc_id,
            qty=quantity,
            overhead_context=overhead_context,
        )

        return calc, order


class EstimateCalculationFacade:
    """
    Фасад для координации расчётов сметы.

    Паттерн Facade:
    - Упрощает взаимодействие между сервисами
    - Предоставляет единую точку входа для расчётов
    - Скрывает сложность от контроллеров
    """

    def __init__(
        self,
        estimate_repo: EstimateRepository = None,
        overhead_service: OverheadContextService = None,
        tc_calc_service: TechnicalCardCalculationService = None,
    ):
        """
        Инициализация фасада.

        Args:
            estimate_repo: Репозиторий смет
            overhead_service: Сервис контекста НР
            tc_calc_service: Сервис расчёта ТК
        """
        self.estimate_repo = estimate_repo or EstimateRepository()
        self.overhead_service = overhead_service or OverheadContextService()
        self.tc_calc_service = tc_calc_service or TechnicalCardCalculationService()

    def calculate_tc_for_estimate(
        self,
        estimate_id: int,
        tc_id: int,
        quantity: float,
    ) -> Tuple[Dict[str, float], List[str]]:
        """
        Рассчитать ТК в контексте сметы (с учётом её НР).

        Алгоритм:
        1. Получить смету
        2. Рассчитать контекст НР сметы
        3. Рассчитать ТК с учётом контекста НР
        4. Вернуть результат

        Args:
            estimate_id: ID сметы
            tc_id: ID технической карты
            quantity: Количество

        Returns:
            Tuple:
                - Dict[str, float]: Расчёты (конвертированные в float для JSON)
                - List[str]: Порядок ключей

        Raises:
            EstimateNotFoundError: Если смета не найдена
            TechnicalCardNotFoundError: Если ТК не найдена
        """
        # 1. Получаем смету (с валидацией)
        estimate = self.estimate_repo.get_by_id_or_raise(estimate_id)

        # 2. Рассчитываем контекст НР
        overhead_context = self.overhead_service.calculate_context(estimate)

        # 3. Рассчитываем ТК
        calc, order = self.tc_calc_service.calculate(
            tc_id=tc_id,
            quantity=quantity,
            overhead_context=overhead_context,
        )

        # 4. Конвертируем Decimal -> float для JSON
        calc_float = {k: float(v) for k, v in calc.items()}

        return calc_float, order
