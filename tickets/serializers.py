import os

from django.urls import reverse
from rest_framework import serializers
from accounts.models import User
from .models import Category, Comment, Ticket, TicketHistory
from .models import Attachment, Category, Comment, Ticket, TicketHistory


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "description"]


class TicketSerializer(serializers.ModelSerializer):
    requester_name = serializers.CharField(source="requester.full_name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    assignee_name = serializers.SerializerMethodField()

    class Meta:
        model = Ticket
        fields = [
            "id", "title", "description", "category", "category_name",
            "priority", "status", "requester", "requester_name",
            "assignee", "assignee_name",
            "created_at", "updated_at", "resolved_at",
        ]
        # Status and assignee change only through their own endpoints,
        # so every change is checked and recorded in the history.
        read_only_fields = [
            "id", "status", "requester", "assignee",
            "created_at", "updated_at", "resolved_at",
        ]

    def get_assignee_name(self, obj):
        return obj.assignee.full_name if obj.assignee else None


class AssignSerializer(serializers.Serializer):
    assignee = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(
            role__in=[User.Role.AGENT, User.Role.MANAGER], is_active=True
        )
    )


class StatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Ticket.Status.choices)


class CommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.full_name", read_only=True)

    class Meta:
        model = Comment
        fields = ["id", "author", "author_name", "body", "is_internal", "created_at"]
        read_only_fields = ["id", "author", "created_at"]


class HistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(source="changed_by.full_name", read_only=True)

    class Meta:
        model = TicketHistory
        fields = ["id", "field", "old_value", "new_value", "changed_by_name", "changed_at"]


ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".txt", ".csv", ".docx", ".xlsx"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB


class AttachmentSerializer(serializers.ModelSerializer):
    filename = serializers.SerializerMethodField()
    uploaded_by_name = serializers.CharField(source="uploaded_by.full_name", read_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = ["id", "file", "filename", "download_url",
                  "uploaded_by", "uploaded_by_name", "uploaded_at"]
        read_only_fields = ["id", "uploaded_by", "uploaded_at"]
        # The raw file path is never shown; clients use download_url instead.
        extra_kwargs = {"file": {"write_only": True}}

    def get_filename(self, obj):
        return os.path.basename(obj.file.name)

    def get_download_url(self, obj):
        path = reverse(
            "ticket-download-attachment",
            kwargs={"pk": obj.ticket_id, "attachment_id": obj.pk},
        )
        request = self.context.get("request")
        return request.build_absolute_uri(path) if request else path

    def validate_file(self, uploaded):
        extension = os.path.splitext(uploaded.name)[1].lower()
        if extension not in ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
            raise serializers.ValidationError(
                f"'{extension or 'no extension'}' files are not allowed. Allowed types: {allowed}"
            )
        if uploaded.size > MAX_UPLOAD_BYTES:
            raise serializers.ValidationError("The file is too large. The limit is 5 MB.")
        return uploaded