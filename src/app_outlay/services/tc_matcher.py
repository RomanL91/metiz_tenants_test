# app_outlay/services/tc_matcher.py
from django.db.models import Q
from app_technical_cards.models import TechnicalCard, TechnicalCardVersion
import re
from difflib import SequenceMatcher


class TCMatcher:
    """Сервис для автоматического сопоставления строк Excel с ТК."""

    SIMILARITY_THRESHOLD = 0.5
    BONUS_FOR_ONE_UNIT = 0.1
    PENALTY_FOR_UNITS = 0.5
    WEIGHT_FOR_WORD_SIMILARITY = 0.7
    WEIGHT_FOR_SIMILARITY_OF_SYMBOLS = 0.3

    @staticmethod
    def normalize_unit(unit: str) -> str:
        """Нормализация единиц измерения."""
        if isinstance(unit, str):
            s = (unit or "").lower().strip()
            s = s.replace("\u00b2", "2").replace("\u00b3", "3")
            compact = "".join(ch for ch in s if ch not in " .,")
        else:
            return

        patterns = {
            r"(м\^?2|м2|квм|мкв|квадрат\w*метр\w*)": "м2",
            r"(м\^?3|м3|кубм|мкуб|кубическ\w*метр\w*)": "м3",
            r"(шт|штука|штуки|штук)": "шт",
            r"(пм|погм|погонныйметр|погонныхметров)": "пм",
            r"(компл|комплект|комплекта|комплектов)": "компл",
            r"(кг|килограмм|килограммов)": "кг",
            r"(т|тонна|тонн)": "т",
            r"(л|литр|литров)": "л",
            r"(м|метр|метров)": "м",
        }

        for pattern, normalized in patterns.items():
            if re.fullmatch(pattern, compact or ""):
                return normalized

        return compact or s

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

    @classmethod
    def find_matching_tc(
        cls, name: str, unit: str
    ) -> tuple[TechnicalCardVersion | None, float]:
        """Найти наиболее подходящую версию ТК."""
        if not name or not name.strip():
            return None, 0.0
        normalized_unit = cls.normalize_unit(unit)
        search_name = name.strip().lower()

        # Шаг 1: Точное совпадение (название + единица)
        exact_match = cls._find_exact_match(name, normalized_unit)
        if exact_match:
            return exact_match, 1.0

        # Шаг 2: Нечёткий поиск
        fuzzy_match, score = cls._find_fuzzy_match(search_name, normalized_unit)
        if fuzzy_match and score >= cls.SIMILARITY_THRESHOLD:
            return fuzzy_match, score

        return None, 0.0

    @classmethod
    def _find_exact_match(
        cls, name: str, normalized_unit: str
    ) -> TechnicalCardVersion | None:
        """Точное совпадение названия + единица."""
        exact_cards = TechnicalCard.objects.filter(name__iexact=name.strip())

        for card in exact_cards:
            if cls.normalize_unit(card.unit_ref) == normalized_unit:
                return (
                    card.versions.filter(is_published=True)
                    .order_by("-created_at")
                    .first()
                )

        return None

    @classmethod
    def _find_fuzzy_match(
        cls, search_name: str, normalized_unit: str
    ) -> tuple[TechnicalCardVersion | None, float]:
        """Нечёткий поиск с строгой проверкой ключевых слов."""
        all_cards = TechnicalCard.objects.all().values("id", "name", "unit_ref")

        best_match_id = None
        best_score = 0.0
        for card_data in all_cards:
            print("-----tyt")
            card_unit_norm = cls.normalize_unit(card_data["unit_ref"])
            card_name_lower = card_data["name"].lower()

            # 1. Схожесть по символам (SequenceMatcher)
            char_similarity = SequenceMatcher(
                None, search_name, card_name_lower
            ).ratio()

            # 2. Схожесть по словам (ключевые слова)
            word_similarity = cls.calculate_word_similarity(
                search_name, card_name_lower
            )

            # 3. Взвешенная схожесть: слова важнее символов
            # 70% вес на слова, 30% на символы
            combined_similarity = (word_similarity * cls.WEIGHT_FOR_WORD_SIMILARITY) + (
                char_similarity * cls.WEIGHT_FOR_SIMILARITY_OF_SYMBOLS
            )

            # 4. Единица измерения
            if card_unit_norm and normalized_unit:
                if card_unit_norm == normalized_unit:
                    # Небольшой бонус если единицы совпадают
                    combined_similarity = min(
                        combined_similarity + cls.BONUS_FOR_ONE_UNIT, 1.0
                    )
                else:
                    # ЖЁСТКИЙ штраф если единицы разные
                    combined_similarity = combined_similarity * cls.PENALTY_FOR_UNITS

            if combined_similarity > best_score:
                best_score = combined_similarity
                best_match_id = card_data["id"]

        if best_match_id and best_score >= cls.SIMILARITY_THRESHOLD:
            card = TechnicalCard.objects.get(id=best_match_id)
            version = (
                card.versions.filter(is_published=True).order_by("-created_at").first()
            )
            return version, best_score

        return None, 0.0

    @classmethod
    def batch_match(cls, items: list[dict]) -> list[dict]:
        """Массовое сопоставление."""
        results = []
        for item in items:
            tc_version, similarity = cls.find_matching_tc(
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
