import re
from difflib import SequenceMatcher

from app_technical_cards.models import TechnicalCard, TechnicalCardVersion
from app_outlay.estimate_mapping_utils import UnitNormalizer


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

    def __init__(
        self,
        similarity_threshold: float = None,
        bonus_for_one_unit: float = None,
        penalty_for_units: float = None,
        weight_for_word_similarity: float = None,
        weight_for_similarity_of_symbols: float = None,
        unit_normalizer: UnitNormalizer = None,
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
        """Найти наиболее подходящую версию ТК."""

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
        # Оптимизация: загружаем только нужные поля
        all_cards = TechnicalCard.objects.select_related("unit_ref").only(
            "id", "name", "unit_ref__symbol"
        )

        best_match_id = None
        best_score = 0.0

        for card in all_cards:
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
                best_match_id = card.id

        if best_match_id and best_score >= self.similarity_threshold:
            card = TechnicalCard.objects.get(id=best_match_id)
            version = (
                card.versions.filter(is_published=True).order_by("-created_at").first()
            )
            return version, best_score

        return None, 0.0

    def batch_match(self, items: list[dict]) -> list[dict]:
        """Массовое сопоставление."""
        results = []
        for item in items:
            tc_version, similarity = self.find_matching_tc(
                item.get("name", ""), item.get("unit", "")
            )

            result = item.copy()
            if tc_version:
                result["matched_tc_id"] = tc_version.card_id
                result["matched_tc_text"] = str(tc_version.card.name)
                result["similarity"] = round(similarity, 2)
            else:
                result["matched_tc_id"] = None
                result["matched_tc_text"] = ""
                result["similarity"] = 0.0

            results.append(result)

        return results
