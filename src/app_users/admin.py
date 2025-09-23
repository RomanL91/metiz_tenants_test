from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin, UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group

from app_users.models import Role, User

# Скрыть оригинальные Group из админки
admin.site.unregister(Group)


# Показать Role с тем же функционалом, что и Group
@admin.register(Role)
class RoleAdmin(GroupAdmin):
    # можно кастомизировать список полей/фильтров
    pass


# Переименовать секции у User и явно показать "Роли"
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Персональная информация", {"fields": ("first_name", "last_name", "email")}),
        ("Роли и права", {"fields": ("groups", "user_permissions")}),
        ("Статусы", {"fields": ("is_active", "is_staff", "is_superuser")}),
        ("Даты", {"fields": ("last_login", "date_joined")}),
    )
    filter_horizontal = ("groups", "user_permissions")

    # (опц.) Чуть подкрасить лейбл ManyToMany поля "groups" → "Роли"
    def formfield_for_manytomany(self, db_field, request, **kwargs):
        formfield = super().formfield_for_manytomany(db_field, request, **kwargs)
        if db_field.name == "groups":
            formfield.label = "Роли"
            formfield.help_text = "Роли (группы) этого пользователя."
        return formfield
