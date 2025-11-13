from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

PERMISSION_LABELS = {
    "add": pgettext_lazy("permission", "Может добавлять {model}"),
    "change": pgettext_lazy("permission", "Может изменять {model}"),
    "delete": pgettext_lazy("permission", "Может удалять {model}"),
    "view": pgettext_lazy("permission", "Может просматривать {model}"),
}


def human_permission_name(perm):
    # Разбираем codename: "<action>_<model>"
    action, _, rest = perm.codename.partition("_")

    # Пытаемся получить verbose_name модели; иначе берём имя из ContentType или исходное название права
    model_cls = perm.content_type.model_class()
    model_name = (
        getattr(getattr(model_cls, "_meta", None), "verbose_name", None)
        or getattr(perm.content_type, "name", None)
        or perm.name
    )

    label = PERMISSION_LABELS.get(action)
    if label:
        # «Может добавлять «Смету»» — модель оборачиваем в ёлочки
        return format_lazy(label, model=format_lazy("«{}»", model_name))

    # Фолбэк для нестандартных действий: export, publish, и т.п.
    return format_lazy(
        _("Разрешение: {action} {model}"),
        action=action,
        model=format_lazy("«{}»", model_name),
    )
