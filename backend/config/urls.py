from django.urls import include, path

urlpatterns = [
    path("api/", include("accounts.urls")),
    path("api/", include("recon.urls")),
    path("api/", include("ask.urls")),
]
