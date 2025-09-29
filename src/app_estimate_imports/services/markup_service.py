from typing import Dict, List

from app_estimate_imports.models import ImportedEstimateFile, ParseMarkup
from app_estimate_imports.services.base_service import BaseService


class MarkupService(BaseService):
    """Сервис для работы с разметкой файлов"""

    def ensure_markup_exists(self, file_obj: ImportedEstimateFile) -> ParseMarkup:
        """Гарантирует существование разметки для файла"""
        if hasattr(file_obj, "markup"):
            return file_obj.markup

        parse_result = getattr(file_obj, "parse_result", None)
        if not parse_result:
            raise ValueError("ParseResult не найден для файла")

        markup = ParseMarkup.objects.create(
            file=file_obj, parse_result=parse_result, annotation={}
        )
        return markup

    def get_labels(self, markup: ParseMarkup) -> Dict[str, str]:
        """Получает словарь меток из разметки"""
        return (markup.annotation or {}).get("labels", {})

    def set_label(
        self, file_obj: ImportedEstimateFile, uid: str, label: str, title: str = ""
    ) -> None:
        """Устанавливает метку для узла"""
        markup = self.ensure_markup_exists(file_obj)
        annotation = markup.annotation or {}
        labels = annotation.get("labels", {})

        labels[uid] = label
        if title:
            titles = annotation.get("titles", {})
            titles[uid] = title
            annotation["titles"] = titles

        annotation["labels"] = labels
        markup.annotation = annotation
        markup.save(update_fields=["annotation"])

    def get_tech_cards(self, markup: ParseMarkup) -> List[Dict]:
        """Получает список техкарт из разметки"""
        return (markup.annotation or {}).get("tech_cards", [])

    def set_tech_card_members(
        self,
        file_obj: ImportedEstimateFile,
        tc_uid: str,
        works: List[str],
        materials: List[str],
    ) -> None:
        """Устанавливает состав техкарты"""
        markup = self.ensure_markup_exists(file_obj)
        annotation = markup.annotation or {}
        tech_cards = annotation.get("tech_cards", [])

        # Найти существующую техкарту или создать новую
        tc_entry = None
        for entry in tech_cards:
            if entry.get("uid") == tc_uid:
                tc_entry = entry
                break

        if not tc_entry:
            tc_entry = {"uid": tc_uid}
            tech_cards.append(tc_entry)

        tc_entry["works"] = works
        tc_entry["materials"] = materials

        annotation["tech_cards"] = tech_cards
        markup.annotation = annotation
        markup.save(update_fields=["annotation"])
