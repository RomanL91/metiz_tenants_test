"""
Сервисный слой для автокомплита и сопоставления технических карт.

Принципы:
- Single Responsibility: каждый метод выполняет одну задачу
- Database Optimization: минимизация запросов к БД (N+1 prevention)
- Reusability: переиспользуемые компоненты
- Testability: легко тестируемая логика без зависимостей от Django views

Оптимизации:
- Использование select_related для оптимизации запросов
- Кэширование нормализованных единиц измерения
- Batch-обработка для минимизации запросов к БД
"""

from typing import List, Dict, Optional, Tuple
from django.db.models import QuerySet

from app_outlay.views.autocomplete_view.tc_matcher import TCMatcher
from app_technical_cards.models import TechnicalCard, TechnicalCardVersion


class AutocompleteService:
    """
    Сервис поиска технических карт.

    Ответственность:
    - Поиск ТК по частичному совпадению названия
    - Оптимизация запросов к БД
    - Формирование результатов для UI
    """

    @staticmethod
    def search_technical_cards(query: str, limit: int = 20) -> List[Dict[str, any]]:
        """
        Поиск технических карт по названию.

        Оптимизации:
        - select_related('unit_ref') - избегаем N+1 при доступе к единицам
        - values() - загружаем только нужные поля
        - [:limit] - ограничение на уровне БД

        Args:
            query: Поисковый запрос (регистронезависимый)
            limit: Максимальное количество результатов

        Returns:
            List[Dict]: Список результатов в формате:
                [
                    {"id": 1, "text": "Установка окна [шт]"},
                    {"id": 2, "text": "Штукатурка стен [м2]"}
                ]

        Example:
            >>> service = AutocompleteService()
            >>> results = service.search_technical_cards("окно", limit=10)
            >>> len(results)
            5
        """
        if not query or not query.strip():
            return []

        # Оптимизированный запрос с select_related для избежания N+1
        queryset = (
            TechnicalCard.objects.filter(name__icontains=query.strip())
            .select_related("unit_ref")  # Оптимизация: загружаем единицы за один запрос
            .only("id", "name", "unit_ref__symbol")[  # Загружаем только нужные поля
                :limit
            ]
        )

        # Формируем результат
        results = []
        for card in queryset:
            results.append(
                {"id": card.id, "text": f"{card.name} [{card.unit_ref.symbol}]"}
            )

        return results


class TCMatchingService:
    """
    Сервис сопоставления строк Excel с техническими картами.

    Ответственность:
    - Batch-сопоставление множества элементов
    - Делегирование логики нечёткого поиска в TCMatcher
    - Оптимизация запросов к БД

    Использует Strategy Pattern:
    - Делегирует алгоритм сопоставления в TCMatcher
    - Сам отвечает только за оркестрацию и оптимизацию
    """

    def __init__(self, matcher=None, **matcher_kwargs):
        """
        Инициализация сервиса.

        Args:
            matcher: Экземпляр matcher'а для сопоставления.
                    Если None, создаётся TCMatcher с дефолтными параметрами.
                    Можно передать mock для тестирования.
            **matcher_kwargs: Параметры для конфигурации TCMatcher:
                - similarity_threshold: float (default: 0.5)
                - bonus_for_one_unit: float (default: 0.1)
                - penalty_for_units: float (default: 0.5)
                - weight_for_word_similarity: float (default: 0.7)
                - weight_for_similarity_of_symbols: float (default: 0.3)

        Example:
            # Дефолтные параметры
            service = TCMatchingService()

            # Кастомные параметры
            service = TCMatchingService(
                similarity_threshold=0.7,
                bonus_for_one_unit=0.2
            )

            # С кастомным matcher'ом
            custom_matcher = CustomMatcher()
            service = TCMatchingService(matcher=custom_matcher)
        """
        # Dependency Injection для тестируемости
        if matcher is None:
            # Создаём экземпляр с параметрами
            matcher = TCMatcher(**matcher_kwargs)

        self.matcher = matcher

    def batch_match_items(self, items: List[Dict[str, any]]) -> List[Dict[str, any]]:
        """
        Batch-сопоставление элементов с техническими картами.

        Делегирует логику нечёткого поиска в TCMatcher.
        Отвечает за валидацию и форматирование результатов.

        Args:
            items: Список элементов для сопоставления:
                [
                    {"row_index": 1, "name": "Установка окна", "unit": "шт"},
                    {"row_index": 2, "name": "Штукатурка", "unit": "м2"}
                ]

        Returns:
            List[Dict]: Результаты сопоставления:
                [
                    {
                        "row_index": 1,
                        "name": "Установка окна",
                        "unit": "шт",
                        "matched_tc_id": 123,
                        "matched_tc_text": "Установка окна ПВХ",
                        "similarity": 0.85
                    },
                    ...
                ]

        Optimization:
            - Все запросы к БД выполняются внутри TCMatcher
            - Результаты возвращаются одним batch'ем

        Example:
            >>> service = TCMatchingService()
            >>> items = [{"row_index": 1, "name": "окно", "unit": "шт"}]
            >>> results = service.batch_match_items(items)
            >>> results[0]['matched_tc_id']
            123
        """
        if not items:
            return []

        # Делегируем логику сопоставления в TCMatcher
        # TCMatcher.batch_match уже оптимизирован и возвращает нужный формат
        results = self.matcher.batch_match(items)

        return results

    def match_single_item(
        self, name: str, unit: str
    ) -> Tuple[Optional[int], str, float]:
        """
        Сопоставление одного элемента с ТК.

        Используется когда нужно сопоставить один элемент,
        а не batch. Например, для динамического автокомплита.

        Args:
            name: Название работы/материала
            unit: Единица измерения

        Returns:
            Tuple[tc_id, tc_name, similarity]:
                - tc_id: ID найденной ТК или None
                - tc_name: Название ТК или ""
                - similarity: Коэффициент схожести (0.0-1.0)

        Example:
            >>> service = TCMatchingService()
            >>> tc_id, name, score = service.match_single_item("окно", "шт")
            >>> score >= 0.5
            True
        """
        # Используем существующий метод TCMatcher
        tc_version, similarity = self.matcher.find_matching_tc(name, unit)

        if tc_version:
            return (tc_version.card_id, tc_version.card.name, similarity)

        return None, "", 0.0


class TCSearchOptimizer:
    """
    Оптимизатор запросов для поиска ТК.

    Utility класс для различных оптимизаций:
    - Кэширование часто используемых данных
    - Предзагрузка связанных объектов
    - Оптимизация фильтров

    Можно расширять при необходимости.
    """

    @staticmethod
    def prefetch_card_data(queryset: QuerySet) -> QuerySet:
        """
        Предзагрузка всех необходимых данных для карточек.

        Использует select_related для оптимизации:
        - unit_ref: единица измерения
        - versions: опубликованные версии

        Args:
            queryset: Исходный QuerySet технических карт

        Returns:
            QuerySet: Оптимизированный QuerySet с prefetch'ем

        Example:
            >>> qs = TechnicalCard.objects.filter(name__icontains="окно")
            >>> optimized = TCSearchOptimizer.prefetch_card_data(qs)
            >>> list(optimized)  # Выполнится минимум запросов
        """
        return queryset.select_related("unit_ref").prefetch_related("versions")

    @staticmethod
    def get_active_versions_map(card_ids: List[int]) -> Dict[int, TechnicalCardVersion]:
        """
        Получить мапу card_id -> последняя опубликованная версия.

        Оптимизация для batch-операций:
        - Загружает все версии одним запросом
        - Возвращает dict для быстрого lookup'а

        Args:
            card_ids: Список ID технических карт

        Returns:
            Dict[card_id, version]: Мапа ID карты -> последняя версия

        Example:
            >>> card_ids = [1, 2, 3]
            >>> versions = TCSearchOptimizer.get_active_versions_map(card_ids)
            >>> versions[1].version
            '20250101-120000'
        """
        if not card_ids:
            return {}

        # Загружаем все версии одним запросом с select_related
        versions = (
            TechnicalCardVersion.objects.filter(card_id__in=card_ids, is_published=True)
            .select_related("card")
            .order_by("card_id", "-created_at")
            .distinct("card_id")  # Берём только последнюю версию для каждой карты
        )

        # Формируем dict для быстрого доступа
        return {v.card_id: v for v in versions}
