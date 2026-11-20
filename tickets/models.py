from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Ticket(models.Model):
    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In Progress"
        WAITING = "waiting", "Waiting on Requester"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    # The workflow from Section 10.4 of the proposal:
    # each status maps to the statuses it is allowed to move to.
    ALLOWED_TRANSITIONS = {
        Status.OPEN: [Status.IN_PROGRESS, Status.CLOSED],
        Status.IN_PROGRESS: [Status.WAITING, Status.RESOLVED],
        Status.WAITING: [Status.IN_PROGRESS, Status.CLOSED],
        Status.RESOLVED: [Status.CLOSED, Status.OPEN],
        Status.CLOSED: [],
    }

    title = models.CharField(max_length=200)
    description = models.TextField()
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="tickets_requested",
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="tickets_assigned",
        null=True,
        blank=True,
        limit_choices_to={"role__in": ["agent", "manager"]},
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="tickets"
    )
    priority = models.CharField(
        max_length=10, choices=Priority.choices, default=Priority.MEDIUM
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)  # soft delete

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["priority"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["assignee", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(resolved_at__isnull=True)
                | Q(resolved_at__gte=F("created_at")),
                name="resolved_not_before_created",
            ),
        ]

    def can_transition_to(self, new_status):
        """True if moving from the current status to new_status is allowed."""
        return new_status in self.ALLOWED_TRANSITIONS.get(self.status, [])

    def __str__(self):
        return f"#{self.pk} {self.title}"


class Comment(models.Model):
    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name="comments"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="comments"
    )
    body = models.TextField()
    is_internal = models.BooleanField(
        default=False, help_text="Internal notes are hidden from requesters."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment by {self.author} on ticket #{self.ticket_id}"


class Attachment(models.Model):
    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name="attachments"
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attachments"
    )
    file = models.FileField(upload_to="attachments/%Y/%m/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.file.name} (ticket #{self.ticket_id})"


class TicketHistory(models.Model):
    """Append-only audit trail: rows are added, never edited or deleted."""

    ticket = models.ForeignKey(
        Ticket, on_delete=models.PROTECT, related_name="history"
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    field = models.CharField(max_length=50)
    old_value = models.CharField(max_length=255, blank=True)
    new_value = models.CharField(max_length=255, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at"]
        verbose_name_plural = "ticket history"

    def __str__(self):
        return f"#{self.ticket_id}: {self.field} {self.old_value} -> {self.new_value}"