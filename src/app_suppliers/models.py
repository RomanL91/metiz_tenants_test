from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.db.models import Q, UniqueConstraint
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _


class Supplier(models.Model):
    """
    Поставщик (контрагент). Основное поле — name.
    Храним ключевые реквизиты, статус НДС и базовые контакты.
    """

    class SupplierType(models.TextChoices):
        LEGAL = "LEGAL", _("Юрлицо")
        SOLE = "SOLE", _("ИП")
        PERSON = "PERSON", _("Физлицо")

    name = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name=_("Короткое название"),
        help_text=_("Как принято называть поставщика в работе (для интерфейса)."),
    )
    legal_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Юридическое наименование"),
        help_text=_("Полное юридическое наименование, если отличается."),
    )
    supplier_type = models.CharField(
        max_length=12,
        choices=SupplierType.choices,
        default=SupplierType.LEGAL,
        verbose_name=_("Тип поставщика"),
        help_text=_("Юрлицо / ИП / Физлицо."),
    )
    tax_id = models.CharField(
        max_length=10,
        blank=True,
        default="",
        verbose_name=_("ИНН"),
        help_text=_("10 цифр, если известен."),
        validators=[
            RegexValidator(regex=r"^\d{10}$", message=_("Должно быть 10 цифр."))
        ],
    )

    # НДС: статус и дефолтная ставка для материалов этого поставщика
    vat_registered = models.BooleanField(
        default=True,
        verbose_name=_("Плательщик НДС"),
        help_text=_("Отметьте, если поставщик является плательщиком НДС."),
    )

    # Контакты
    phone = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name=_("Телефон"),
        help_text=_("Контактный телефон."),
    )
    email = models.EmailField(
        blank=True,
        default="",
        verbose_name=_("E-mail"),
        help_text=_("Рабочий e-mail."),
    )
    website = models.URLField(
        blank=True,
        default="",
        verbose_name=_("Сайт"),
        help_text=_("Сайт или страница с каталогом."),
    )

    notes = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Заметки"),
        help_text=_("Любая полезная информация: условия поставки, график и т.д."),
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Активен"),
        help_text=_("Снимите отметку, чтобы скрыть из выбора без удаления."),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Создано"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Обновлено"),
    )

    class Meta:
        verbose_name = _("Поставщик")
        verbose_name_plural = _("Поставщики")
        ordering = ["name", "id"]
        constraints = [
            # case-insensitive уникальность имени
            UniqueConstraint(
                Lower("name"),
                name="uniq_supplier_name_ci",
            ),
            # уникальность БИН/ИИН, если заполнен
            UniqueConstraint(
                fields=["tax_id"],
                name="uniq_supplier_tax_id_nonempty",
                condition=~Q(tax_id=""),
            ),
        ]

    def __str__(self) -> str:
        base = self.name
        if self.tax_id:
            return f"{base} ({self.tax_id})"
        return base
