import re
from difflib import SequenceMatcher
from typing import Dict, List

from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import Value

from app_outlay.estimate_mapping_utils import UnitNormalizer
from app_technical_cards.models import TechnicalCard, TechnicalCardVersion


class TCMatcher:
    """
    Сервис для автоматического сопоставления строк Excel с ТК.

    Параметры алгоритма сопоставления настраиваются через конструктор.
    """

    # Дефолтные значения параметров
    DEFAULT_SIMILARITY_THRESHOLD = 0.5
    DEFAULT_BONUS_FOR_ONE_UNIT = 0.1
    DEFAULT_PENALTY_FOR_UNITS = 0.5
    DEFAULT_WEIGHT_FOR_WORD_SIMILARITY = 0.7
    DEFAULT_WEIGHT_FOR_SIMILARITY_OF_SYMBOLS = 0.3
    DEFAULT_TRIGRAM_THRESHOLD = 0.1
    DEFAULT_MAX_DB_CANDIDATES = 10

    def __init__(
        self,
        similarity_threshold: float = None,
        bonus_for_one_unit: float = None,
        penalty_for_units: float = None,
        weight_for_word_similarity: float = None,
        weight_for_similarity_of_symbols: float = None,
        unit_normalizer: UnitNormalizer = None,
        trigram_similarity_threshold: float | None = None,
        max_db_candidates: int | None = None,
    ):
        """
        Инициализация matcher'а с конфигурируемыми параметрами.

        Args:
            similarity_threshold: Минимальный порог схожести (0.0-1.0)
            bonus_for_one_unit: Бонус за совпадение единиц измерения
            penalty_for_units: Штраф за несовпадение единиц (множитель)
            weight_for_word_similarity: Вес схожести по словам (0.0-1.0)
            weight_for_similarity_of_symbols: Вес схожести по символам (0.0-1.0)

        Example:
            # Дефолтные параметры
            matcher = TCMatcher()

            # Кастомные параметры
            matcher = TCMatcher(
                similarity_threshold=0.7,  # Более строгий порог
                bonus_for_one_unit=0.2     # Больший бонус за единицы
            )
        """
        self.similarity_threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else self.DEFAULT_SIMILARITY_THRESHOLD
        )
        self.bonus_for_one_unit = (
            bonus_for_one_unit
            if bonus_for_one_unit is not None
            else self.DEFAULT_BONUS_FOR_ONE_UNIT
        )
        self.penalty_for_units = (
            penalty_for_units
            if penalty_for_units is not None
            else self.DEFAULT_PENALTY_FOR_UNITS
        )
        self.weight_for_word_similarity = (
            weight_for_word_similarity
            if weight_for_word_similarity is not None
            else self.DEFAULT_WEIGHT_FOR_WORD_SIMILARITY
        )
        self.weight_for_similarity_of_symbols = (
            weight_for_similarity_of_symbols
            if weight_for_similarity_of_symbols is not None
            else self.DEFAULT_WEIGHT_FOR_SIMILARITY_OF_SYMBOLS
        )
        self.unit_normalizer = unit_normalizer or UnitNormalizer()
        self.trigram_similarity_threshold = (
            trigram_similarity_threshold
            if trigram_similarity_threshold is not None
            else self.DEFAULT_TRIGRAM_THRESHOLD
        )
        self.max_db_candidates = (
            max_db_candidates
            if max_db_candidates is not None
            else self.DEFAULT_MAX_DB_CANDIDATES
        )

    def normalize_unit(self, unit: str) -> str:
        return self.unit_normalizer.normalize(unit)

    @staticmethod
    def extract_keywords(text: str) -> set[str]:
        """Извлечь ключевые слова из текста (слова длиннее 3 символов)."""
        words = re.findall(r"\b\w+\b", text.lower())
        # Исключаем общие слова и берём только значимые
        stop_words = {"гост", "снип", "для", "при", "или"}
        return {w for w in words if len(w) > 3 and w not in stop_words}

    @classmethod
    def calculate_word_similarity(cls, search_text: str, card_text: str) -> float:
        """
        Вычислить схожесть на уровне слов.
        Проверяет сколько ключевых слов из поиска есть в карточке.
        """
        search_keywords = cls.extract_keywords(search_text)
        card_keywords = cls.extract_keywords(card_text)

        if not search_keywords:
            return 0.0

        # Сколько ключевых слов из поиска найдено в карточке
        matched = len(search_keywords & card_keywords)
        return matched / len(search_keywords)

    def find_matching_tc(
        self, name: str, unit: str
    ) -> tuple[TechnicalCardVersion | None, float]:
        """Найти наиболее подходящую версию ТК (одиночный поиск)."""

        if not name or not name.strip():
            return None, 0.0
        normalized_unit = self.normalize_unit(unit)
        search_name = name.strip().lower()

        # Шаг 1: Точное совпадение (название + единица)
        exact_match = self._find_exact_match(name, normalized_unit)

        if exact_match:
            return exact_match, 1.0

        # Шаг 2: Нечёткий поиск
        fuzzy_match, score = self._find_fuzzy_match(search_name, normalized_unit)

        if fuzzy_match and score >= self.similarity_threshold:
            return fuzzy_match, score

        return None, 0.0

    def _find_exact_match(
        self, name: str, normalized_unit: str
    ) -> TechnicalCardVersion | None:
        """Точное совпадение названия + единица."""
        exact_cards = TechnicalCard.objects.filter(name__iexact=name.strip())

        for card in exact_cards:
            if self.normalize_unit(card.unit_ref.symbol) == normalized_unit:
                return (
                    card.versions.filter(is_published=True)
                    .order_by("-created_at")
                    .first()
                )

        return None

    def _find_fuzzy_match(
        self, search_name: str, normalized_unit: str
    ) -> tuple[TechnicalCardVersion | None, float]:
        """Нечёткий поиск с строгой проверкой ключевых слов."""
        candidate_cards = self._get_candidates(search_name)

        best_card: TechnicalCard | None = None
        best_score = 0.0

        for card in candidate_cards:
            card_unit_norm = self.normalize_unit(card.unit_ref.symbol)
            card_name_lower = card.name.lower()

            # 1. Схожесть по символам (SequenceMatcher)
            char_similarity = SequenceMatcher(
                None, search_name, card_name_lower
            ).ratio()

            # 2. Схожесть по словам (ключевые слова)
            word_similarity = self.calculate_word_similarity(
                search_name, card_name_lower
            )

            # 3. Взвешенная схожесть: слова важнее символов
            combined_similarity = (
                word_similarity * self.weight_for_word_similarity
            ) + (char_similarity * self.weight_for_similarity_of_symbols)

            # 4. Единица измерения
            if card_unit_norm and normalized_unit:
                if card_unit_norm == normalized_unit:
                    # Небольшой бонус если единицы совпадают
                    combined_similarity = min(
                        combined_similarity + self.bonus_for_one_unit, 1.0
                    )
                else:
                    # ЖЁСТКИЙ штраф если единицы разные
                    combined_similarity = combined_similarity * self.penalty_for_units

            if combined_similarity > best_score:
                best_score = combined_similarity
                best_card = card

        if best_card and best_score >= self.similarity_threshold:
            version = (
                best_card.versions.filter(is_published=True)
                .order_by("-created_at")
                .first()
            )
            return version, best_score

        return None, 0.0
    
    def _get_candidates(self, search_name: str) -> list[TechnicalCard]:
        """Сузить набор карточек с помощью триграммного поиска в БД."""

        base_qs = TechnicalCard.objects.select_related("unit_ref").only(
            "id", "name", "unit_ref__symbol"
        )
        annotated_qs = base_qs.annotate(
            trigram_similarity=TrigramSimilarity("name", Value(search_name))
        ).order_by("-trigram_similarity")

        if self.trigram_similarity_threshold is not None:
            filtered_qs = annotated_qs.filter(
                trigram_similarity__gte=self.trigram_similarity_threshold
            )
            candidates = list(filtered_qs[: self.max_db_candidates])
            if candidates:
                return candidates

        return list(annotated_qs[: self.max_db_candidates])


    def batch_match(self, items: list[dict]) -> list[dict]:
        """
        Batch-сопоставление с оптимизацией.

        Для небольших батчей (<100) использует обычный поиск.
        Для больших батчей (≥100) предзагружает все ТК.
        """
        if not items:
            return []

        # Для маленьких батчей - обычный поиск (быстрее из-за раннего выхода)
        if len(items) < 100:
            return self._batch_match_simple(items)

        # Для больших батчей - оптимизированный поиск
        return self._batch_match_optimized(items)

    def _batch_match_simple(self, items: list[dict]) -> list[dict]:
        """
        Простое batch-сопоставление (для маленьких батчей).

        Использует find_matching_tc для каждого элемента.
        Быстрее для <100 элементов из-за раннего выхода при точном совпадении.
        """
        results = []
        for item in items:
            tc_version, similarity = self.find_matching_tc(
                item.get("name", ""), item.get("unit", "")
            )

            result = item.copy()
            if tc_version:
                result["matched_tc_id"] = tc_version.card_id
                result["matched_tc_card_id"] = tc_version.card_id
                result["matched_tc_version_id"] = tc_version.id
                result["matched_tc_text"] = str(tc_version.card.name)
                result["similarity"] = round(similarity, 2)
            else:
                result["matched_tc_id"] = None
                result["matched_tc_card_id"] = None
                result["matched_tc_version_id"] = None
                result["matched_tc_text"] = ""
                result["similarity"] = 0.0

            results.append(result)

        return results

    def _batch_match_optimized(self, items: list[dict]) -> list[dict]:
        """
        Оптимизированное batch-сопоставление (для больших батчей).

        Предзагружает все ТК одним запросом.
        Быстрее для ≥100 элементов.
        """
        # 1. Предзагрузка ВСЕХ техкарт одним запросом
        all_cards = list(
            TechnicalCard.objects.select_related("unit_ref").only(
                "id", "name", "unit_ref__symbol"
            )
        )

        # 2. Предзагрузка всех версий одним запросом
        card_ids = [card.id for card in all_cards]
        versions_map = {}

        if card_ids:
            versions = (
                TechnicalCardVersion.objects.filter(
                    card_id__in=card_ids, is_published=True
                )
                .select_related("card")
                .order_by("card_id", "-created_at")
                .distinct("card_id")
            )
            versions_map = {v.card_id: v for v in versions}

        # 3. Кэш нормализованных единиц
        unit_cache = {
            card.id: self.normalize_unit(card.unit_ref.symbol) for card in all_cards
        }

        # 4. Batch-обработка БЕЗ дополнительных запросов к БД
        results = []
        for item in items:
            best_match = self._find_best_match_from_cache(
                item, all_cards, unit_cache, versions_map
            )
            results.append(best_match)

        return results

    def _find_best_match_from_cache(
        self,
        item: dict,
        all_cards: List[TechnicalCard],
        unit_cache: Dict[int, str],
        versions_map: Dict[int, TechnicalCardVersion],
    ) -> dict:
        """
        Поиск лучшего совпадения из предзагруженных данных.

        Args:
            item: Элемент для сопоставления {'name': str, 'unit': str, ...}
            all_cards: Список всех техкарт
            unit_cache: Кэш нормализованных единиц {card_id: normalized_unit}
            versions_map: Мапа версий {card_id: version}

        Returns:
            dict: Результат сопоставления
        """
        name = item.get("name", "").strip()
        unit = item.get("unit", "")

        result = item.copy()

        # Базовые значения
        result["matched_tc_id"] = None
        result["matched_tc_card_id"] = None
        result["matched_tc_version_id"] = None
        result["matched_tc_text"] = ""
        result["similarity"] = 0.0

        if not name:
            return result

        normalized_unit = self.normalize_unit(unit)
        search_name = name.lower()

        # Шаг 1: Точное совпадение (быстрая проверка)
        for card in all_cards:
            if card.name.lower() == search_name:
                card_unit = unit_cache.get(card.id, "")
                if card_unit == normalized_unit:
                    # Точное совпадение найдено!
                    version = versions_map.get(card.id)
                    if version:
                        result["matched_tc_id"] = card.id
                        result["matched_tc_card_id"] = card.id
                        result["matched_tc_version_id"] = version.id
                        result["matched_tc_text"] = card.name
                        result["similarity"] = 1.0
                        return result

        # Шаг 2: Нечёткий поиск
        best_card_id = None
        best_score = 0.0

        for card in all_cards:
            card_name_lower = card.name.lower()
            card_unit = unit_cache.get(card.id, "")

            # Схожесть по символам
            char_similarity = SequenceMatcher(
                None, search_name, card_name_lower
            ).ratio()

            # Схожесть по словам
            word_similarity = self.calculate_word_similarity(
                search_name, card_name_lower
            )

            # Взвешенная схожесть
            combined_similarity = (
                word_similarity * self.weight_for_word_similarity
            ) + (char_similarity * self.weight_for_similarity_of_symbols)

            # Учёт единиц измерения
            if card_unit and normalized_unit:
                if card_unit == normalized_unit:
                    combined_similarity = min(
                        combined_similarity + self.bonus_for_one_unit, 1.0
                    )
                else:
                    combined_similarity = combined_similarity * self.penalty_for_units

            # Обновление лучшего совпадения
            if combined_similarity > best_score:
                best_score = combined_similarity
                best_card_id = card.id

        # Проверка порога схожести
        if best_card_id and best_score >= self.similarity_threshold:
            version = versions_map.get(best_card_id)
            if version:
                result["matched_tc_id"] = best_card_id
                result["matched_tc_card_id"] = best_card_id
                result["matched_tc_version_id"] = version.id
                result["matched_tc_text"] = version.card.name
                result["similarity"] = round(best_score, 2)

        return result
