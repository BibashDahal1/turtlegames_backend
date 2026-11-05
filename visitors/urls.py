from django.urls import path

from .views import LogoutView, MeView, RegisterView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="visitor-register"),
    path("me/", MeView.as_view(), name="visitor-me"),
    path("logout/", LogoutView.as_view(), name="visitor-logout"),
]