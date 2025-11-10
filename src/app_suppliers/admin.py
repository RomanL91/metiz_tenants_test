from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import Supplier


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    # Таблица
    list_display = (
        "name",
        "supplier_type",
        "vat_registered",
        "phone",
        "email",
        "is_active",
    )
    list_display_links = ("name",)
    list_editable = ("vat_registered", "is_active")
    list_filter = ("supplier_type", "vat_registered", "is_active")
    search_fields = ("name", "legal_name", "phone", "email", "website")
    ordering = ("name", "id")
    list_per_page = 50
    empty_value_display = "—"

    # Форма
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            _("Основное"),
            {"fields": ("name", "legal_name", "supplier_type", "vat_registered")},
        ),
        (_("Контакты"), {"fields": ("phone", "email", "website")}),
        (_("Прочее"), {"fields": ("notes", "is_active")}),
        (
            _("Служебные поля"),
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse", "entity-meta"),
            },
        ),
    )

    # Удобства
    save_on_top = True
    save_as = True

    # Действия
    actions = [
        "mark_active",
        "mark_inactive",
        "mark_vat_registered",
        "mark_vat_not_registered",
    ]

    @admin.action(description=_("Отметить как активных"))
    def mark_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(
            request, _("Обновлено записей: %(count)s") % {"count": updated}
        )

    @admin.action(description=_("Снять активность"))
    def mark_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(
            request, _("Обновлено записей: %(count)s") % {"count": updated}
        )

    @admin.action(description=_("Отметить как плательщиков НДС"))
    def mark_vat_registered(self, request, queryset):
        updated = queryset.update(vat_registered=True)
        self.message_user(
            request, _("Обновлено записей: %(count)s") % {"count": updated}
        )

    @admin.action(description=_("Отметить как НЕ плательщиков НДС"))
    def mark_vat_not_registered(self, request, queryset):
        updated = queryset.update(vat_registered=False)
        self.message_user(
            request, _("Обновлено записей: %(count)s") % {"count": updated}
        )


# (опционально) Инлайн материалов, если у вас есть FK Material.supplier_ref → Supplier
try:
    from app_materials.models import Material

    class MaterialInline(admin.TabularInline):
        model = Material
        fields = ("name", "unit_ref", "price_per_unit", "is_active")
        readonly_fields = ()
        extra = 0
        show_change_link = True
        fk_name = "supplier_ref"  # важно: имя FK в модели Material

    # Добавляем инлайн к уже зарегистрированному админ-классу
    SupplierAdmin.inlines = [MaterialInline]
except Exception:
    # Нет модели или поля FK — просто пропустим инлайн
    pass
