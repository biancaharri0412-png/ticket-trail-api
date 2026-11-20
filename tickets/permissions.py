from django.db.models import Q
from rest_framework.permissions import SAFE_METHODS, BasePermission

from accounts.models import User

from .models import Ticket


def is_manager_or_admin(user):
    return user.role in (User.Role.MANAGER, User.Role.ADMIN)


def visible_tickets(user):
    """Return only the tickets this user is allowed to see."""
    tickets = Ticket.objects.filter(is_deleted=False)
    if is_manager_or_admin(user):
        return tickets
    if user.role == User.Role.AGENT:
        # Agents see their own work, the unassigned queue, and tickets they raised.
        return tickets.filter(
            Q(assignee=user) | Q(assignee__isnull=True) | Q(requester=user)
        )
    return tickets.filter(requester=user)  # requesters: their own tickets only


class TicketPermission(BasePermission):
    """Decides who may perform each action on a ticket."""

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        if view.action == "destroy":
            return user.role == User.Role.ADMIN
        return True

    def has_object_permission(self, request, view, obj):
        user = request.user
        action = view.action

        if action == "partial_update":
            if is_manager_or_admin(user):
                return True
            # Requesters may edit their own ticket only while it is still Open.
            return obj.requester_id == user.id and obj.status == Ticket.Status.OPEN

        if action == "assign":
            if is_manager_or_admin(user):
                return True
            # Agents may only pick up a ticket nobody has taken yet.
            return user.role == User.Role.AGENT and obj.assignee_id is None

        if action == "change_status":
            if is_manager_or_admin(user):
                return True
            if user.role == User.Role.AGENT:
                return obj.assignee_id == user.id
            return obj.requester_id == user.id

        return True  # retrieve, comments, history (the queryset already limits access)


class IsAdminOrReadOnly(BasePermission):
    """Anyone logged in may read; only administrators may change."""

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role == User.Role.ADMIN