from django.urls import path

from .views import CartDetailsView, CartItemDetailView, CartItemsView, CartView

urlpatterns = [
    path("cart/", CartView.as_view(), name="cart"),
    path("cart/details/", CartDetailsView.as_view(), name="cart-details"),
    path("cart/items/", CartItemsView.as_view(), name="cart-items"),
    path("cart/items/<slug:slug>/", CartItemDetailView.as_view(), name="cart-item"),
]