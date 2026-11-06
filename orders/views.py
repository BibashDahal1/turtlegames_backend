from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from visitors.permissions import IsVisitor

from .serializers import OrderCreateSerializer, order_confirmation


class OrderCreateView(APIView):
    """
    POST /api/orders/   (registered visitors only)

    Places an order request. There are deliberately NO endpoints to list or read orders:
    visitor emails are not verified, so showing past orders (names, phone, address) to
    whoever holds a token could expose someone else's details. You manage orders in the admin.
    """

    permission_classes = [IsVisitor]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "order_create"

    def post(self, request):
        serializer = OrderCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return Response(order_confirmation(order), status=status.HTTP_201_CREATED)