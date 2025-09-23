from django.contrib.auth.models import AbstractUser, Group


class Role(Group):
    class Meta:
        proxy = True
        verbose_name = "Роль"
        verbose_name_plural = "Роли"


class User(AbstractUser):
    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
