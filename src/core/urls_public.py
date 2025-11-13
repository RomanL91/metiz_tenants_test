from django.http import HttpResponse
from django.urls import path


def whoami_public(request):
    return HttpResponse("schema=public", content_type="text/plain")


def host_echo_public(request):
    return HttpResponse(f"host={request.get_host()}", content_type="text/plain")


urlpatterns = [
    path("__whoami__/", whoami_public),
    path("__host__/", host_echo_public),
]
