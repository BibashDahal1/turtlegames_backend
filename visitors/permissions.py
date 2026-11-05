from rest_framework.permissions import BasePermission

from .models import Visitor


class IsVisitor(BasePermission):
    """Allows only requests carrying a valid visitor cookie."""

    def has_permission(self, request, view):
        return isinstance(request.user, Visitor)