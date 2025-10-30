from django.urls import path
from django.http import HttpResponse


def whoami_public(request):
    return HttpResponse("schema=public", content_type="text/plain")


def host_echo_public(request):
    return HttpResponse(f"host={request.get_host()}", content_type="text/plain")


urlpatterns = [
    path("__whoami__/", whoami_public),
    path("__host__/", host_echo_public),
]
from django.conf import settings
from django.http import JsonResponse


def debug_info_public(request):
    from django.db import connection

    info = {
        "HTTP_HOST": request.META.get("HTTP_HOST"),
        # "get_host()": request.get_host(),
        # "schema": getattr(connection, "schema_name", "?"),
        # "ROOT_URLCONF": settings.ROOT_URLCONF,
        # "request.urlconf": getattr(request, "urlconf", None),
    }
    return JsonResponse(info, json_dumps_params={"ensure_ascii": False})


urlpatterns += [path("__debug__/", debug_info_public)]
from django.http import JsonResponse


def debug_404(request, exception):
    from django.db import connection
    from django.conf import settings

    info = {
        "where": "PUBLIC urls_public.py",
        # "HTTP_HOST": request.META.get("HTTP_HOST"),
        # "get_host()": request.get_host(),
        # "schema": getattr(connection, "schema_name", "?"),
        # "ROOT_URLCONF": settings.ROOT_URLCONF,
        # "request.urlconf": getattr(request, "urlconf", None),
        # "path": request.path,
    }
    return JsonResponse(info, status=404, json_dumps_params={"ensure_ascii": False})


handler404 = debug_404
