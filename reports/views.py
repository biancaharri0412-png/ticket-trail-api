from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from tickets.models import Ticket


class IsStaffRole(BasePermission):
    """Agents, managers, and administrators may see reports. Requesters may not."""

    def has_permission(self, request, view):
        user = request.user
        return user.is_authenticated and user.role in (
            User.Role.AGENT, User.Role.MANAGER, User.Role.ADMIN
        )


def count_by(queryset, field, choices):
    """Count tickets per value of a field, including values with zero tickets."""
    found = dict(queryset.order_by().values_list(field).annotate(n=Count("id")))
    return {value: found.get(value, 0) for value, _label in choices}


class SummaryView(APIView):
    permission_classes = [IsStaffRole]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        user = request.user
        tickets = Ticket.objects.filter(is_deleted=False)
        is_manager = user.role in (User.Role.MANAGER, User.Role.ADMIN)

        if not is_manager:
            tickets = tickets.filter(assignee=user)  # agents see only their own numbers

        # Average time from creation to resolution, for tickets that were resolved.
        average = tickets.filter(resolved_at__isnull=False).aggregate(
            average=Avg(
                ExpressionWrapper(
                    F("resolved_at") - F("created_at"), output_field=DurationField()
                )
            )
        )["average"]

        data = {
            "scope": "all tickets" if is_manager else "your assigned tickets",
            "total": tickets.count(),
            "by_status": count_by(tickets, "status", Ticket.Status.choices),
            "by_priority": count_by(tickets, "priority", Ticket.Priority.choices),
            "by_category": dict(sorted(
                tickets.order_by().values_list("category__name").annotate(n=Count("id"))
            )),
            "average_resolution_hours": (
                round(average.total_seconds() / 3600, 1) if average else None
            ),
        }

        if is_manager:
            data["unassigned_open"] = (
                tickets.filter(assignee__isnull=True)
                .exclude(status=Ticket.Status.CLOSED)
                .count()
            )
            # Open workload per agent: tickets that are neither resolved nor closed.
            finished = [Ticket.Status.RESOLVED, Ticket.Status.CLOSED]
            data["agent_workload"] = list(
                User.objects.filter(
                    role__in=[User.Role.AGENT, User.Role.MANAGER], is_active=True
                )
                .annotate(
                    open_tickets=Count(
                        "tickets_assigned",
                        filter=Q(tickets_assigned__is_deleted=False)
                        & ~Q(tickets_assigned__status__in=finished),
                    )
                )
                .order_by("-open_tickets", "full_name")
                .values("id", "full_name", "open_tickets")
            )
        return Response(data)