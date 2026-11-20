from django.contrib import admin

from .models import Attachment, Category, Comment, Ticket, TicketHistory


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)


class CommentInline(admin.TabularInline):
    model = Comment
    extra = 0


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "requester", "assignee", "category",
                    "priority", "status", "created_at", "is_deleted")
    list_filter = ("status", "priority", "category", "is_deleted")
    search_fields = ("title", "description", "requester__email")
    list_select_related = ("requester", "assignee", "category")
    inlines = [CommentInline]


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ("file", "ticket", "uploaded_by", "uploaded_at")


@admin.register(TicketHistory)
class TicketHistoryAdmin(admin.ModelAdmin):
    list_display = ("ticket", "field", "old_value", "new_value",
                    "changed_by", "changed_at")
    list_filter = ("field",)

    # Make the audit trail read-only, even for administrators.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False