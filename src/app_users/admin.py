from django.contrib import admin

from app_users.models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    pass
    # list_display = ["id", "email", "is_active"]
    # list_display_links = ["id", "email"]
    # search_fields = ["email"]
    # fieldsets = [
    #     (
    #         None,
    #         {
    #             "fields": [
    #                 "email",
    #                 "password",
    #             ],
    #         },
    #     ),
    #     (
    #         "Administrative",
    #         {
    #             "fields": [
    #                 "tenants",
    #                 "last_login",
    #                 "is_active",
    #                 "is_verified",
    #             ],
    #         },
    #     ),
    # ]
