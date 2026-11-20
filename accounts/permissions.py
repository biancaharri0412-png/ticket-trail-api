from rest_framework.permissions import BasePermission

from .models import User


class IsAdminRole(BasePermission):
    """Only users whose role is Administrator."""

    def has_permission(self, request, view):
        user = request.user
        return user.is_authenticated and user.role == User.Role.ADMIN