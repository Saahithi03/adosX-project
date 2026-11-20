from django.urls import path

from . import views

urlpatterns = [
    path("exceptions", views.ExceptionListView.as_view()),
    path("locations", views.LocationListView.as_view()),
    path("reasons", views.ReasonListView.as_view()),
]
