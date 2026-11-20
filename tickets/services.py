from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from accounts.models import User

from .models import Ticket, TicketHistory

Status = Ticket.Status

# Which statuses each role may set. The workflow rules apply on top of this.
ROLE_TARGETS = {
    User.Role.REQUESTER: [Status.CLOSED, Status.OPEN],
    User.Role.AGENT: [Status.IN_PROGRESS, Status.WAITING, Status.RESOLVED],
    User.Role.MANAGER: list(Status),
    User.Role.ADMIN: list(Status),
}


def record_history(ticket, user, field, old, new):
    """Add one row to the audit trail."""
    TicketHistory.objects.create(
        ticket=ticket,
        changed_by=user,
        field=field,
        old_value=str(old)[:255],
        new_value=str(new)[:255],
    )


def change_status(ticket, user, new_status):
    if new_status == ticket.status:
        raise ValidationError(f"The ticket is already '{ticket.status}'.")
    if new_status not in ROLE_TARGETS[user.role]:
        raise PermissionDenied("Your role cannot set that status.")
    # Administrators may override the workflow; everyone else must follow it.
    if user.role != User.Role.ADMIN and not ticket.can_transition_to(new_status):
        raise ValidationError(
            f"A ticket cannot move from '{ticket.status}' to '{new_status}'."
        )

    old_status = ticket.status
    with transaction.atomic():  # the change and its history succeed or fail together
        ticket.status = new_status
        if new_status == Status.RESOLVED:
            ticket.resolved_at = timezone.now()
        elif new_status != Status.CLOSED:
            ticket.resolved_at = None  # reopened or back in progress
        ticket.save()
        record_history(ticket, user, "status", old_status, new_status)
    return ticket


def assign_ticket(ticket, user, assignee):
    if ticket.status == Status.CLOSED:
        raise ValidationError("Closed tickets cannot be assigned.")
    if user.role == User.Role.AGENT and assignee.id != user.id:
        raise PermissionDenied("Agents can only assign tickets to themselves.")

    old = ticket.assignee.full_name if ticket.assignee else "Unassigned"
    with transaction.atomic():
        ticket.assignee = assignee
        ticket.save()
        record_history(ticket, user, "assignee", old, assignee.full_name)
    return ticket