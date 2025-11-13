from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth.admin import GroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, Permission
from django.utils.translation import gettext_lazy as _

from app_users.models import Role, User
from core.i18n.permissions import human_permission_name

# Безопасно скрыть штатный Group-админ, чтобы показать Role
try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass


# ===== 1) Кастомные подписи для списков «Прав» =====
class PermissionModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj: Permission) -> str:
        # «Может добавлять «Смету»», «Может изменять «Материал»», …
        return str(human_permission_name(obj))


# ===== 2) Role (proxy на Group) с красивыми подписями прав =====
class RoleForm(forms.ModelForm):
    permissions = PermissionModelMultipleChoiceField(
        label=_("Права"),
        queryset=Permission.objects.select_related("content_type").order_by(
            "content_type__app_label", "content_type__model", "codename"
        ),
        required=False,
        widget=FilteredSelectMultiple(_("Права"), is_stacked=False),
    )

    class Meta:
        model = Role
        fields = "__all__"


@admin.register(Role)
class RoleAdmin(GroupAdmin):
    form = RoleForm
    # при желании можно добавить list_display, search_fields и т.п.


# ===== 3) Пользователь: поле «user_permissions» с теми же подписями =====
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (
            _("Персональная информация"),
            {"fields": ("first_name", "last_name", "email")},
        ),
        (_("Роли и права"), {"fields": ("groups", "user_permissions")}),
        (_("Статусы"), {"fields": ("is_active", "is_staff", "is_superuser")}),
        (_("Даты"), {"fields": ("last_login", "date_joined")}),
    )

    # Мы вручную задаём FilteredSelectMultiple, так что filter_horizontal можно не использовать
    filter_horizontal = ()

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        # «Роли» (группы)
        if db_field.name == "groups":
            kwargs.setdefault("queryset", Group.objects.all().order_by("name"))
            return forms.ModelMultipleChoiceField(
                label=_("Роли"),
                queryset=kwargs["queryset"],
                required=False,
                widget=FilteredSelectMultiple(_("Роли"), is_stacked=False),
                help_text=_("Роли (группы) этого пользователя."),
            )

        # «Права пользователя» с человеческими подписями
        if db_field.name == "user_permissions":
            kwargs.setdefault(
                "queryset",
                Permission.objects.select_related("content_type").order_by(
                    "content_type__app_label", "content_type__model", "codename"
                ),
            )
            return PermissionModelMultipleChoiceField(
                label=_("Права пользователя"),
                queryset=kwargs["queryset"],
                required=False,
                widget=FilteredSelectMultiple(
                    _("Права пользователя"), is_stacked=False
                ),
            )

        return super().formfield_for_manytomany(db_field, request, **kwargs)
