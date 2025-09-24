from django import template

register = template.Library()


@register.filter
def index(seq, i):
    """Безопасно вернуть элемент по индексу из list/tuple; иначе пусто."""
    try:
        return seq[int(i)]
    except Exception:
        return ""


@register.filter
def excel_col(i):
    """0 -> A, 25 -> Z, 26 -> AA ..."""
    i = int(i)
    name = ""
    while True:
        i, r = divmod(i, 26)
        name = chr(65 + r) + name
        if i == 0:
            break
        i -= 1
    return name
