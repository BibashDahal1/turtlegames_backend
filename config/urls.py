from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/visitors/", include("visitors.urls")),
    path("api/orders/", include("orders.urls")),
    path("api/payments/", include("payments.urls")),
    path("api/", include("games.urls")),
]