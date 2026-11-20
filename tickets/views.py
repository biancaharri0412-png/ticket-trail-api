import os

from django.db import transaction
from django.db.models import ProtectedError
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from accounts.models import User

from . import services
from .models import Category, Ticket
from .permissions import IsAdminOrReadOnly, TicketPermission, visible_tickets
from .serializers import (
    AssignSerializer,
    AttachmentSerializer,
    CategorySerializer,
    CommentSerializer,
    HistorySerializer,
    StatusSerializer,
    TicketSerializer,
)

TRACKED_FIELDS = ["title", "priority", "category"]  # edits we record in the history


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {"detail": "This category is used by tickets and cannot be deleted."},
                status=status.HTTP_409_CONFLICT,
            )


class TicketViewSet(viewsets.ModelViewSet):
    serializer_class = TicketSerializer
    permission_classes = [TicketPermission]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    # Filtering, searching, and sorting (see settings for the backends)
    filterset_fields = ["status", "priority", "category", "assignee"]
    search_fields = ["title", "description"]
    ordering_fields = ["created_at", "updated_at", "priority", "status"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # used when building the docs
            return Ticket.objects.none()
        return visible_tickets(self.request.user).select_related(
            "requester", "assignee", "category"
        )

    def perform_create(self, serializer):
        # The requester is always the logged-in user, never taken from the request.
        serializer.save(requester=self.request.user)

    def perform_update(self, serializer):
        ticket = serializer.instance
        before = {f: str(getattr(ticket, f)) for f in TRACKED_FIELDS}
        with transaction.atomic():
            ticket = serializer.save()
            for field in TRACKED_FIELDS:
                after = str(getattr(ticket, field))
                if after != before[field]:
                    services.record_history(
                        ticket, self.request.user, field, before[field], after
                    )

    def perform_destroy(self, instance):
        # Soft delete: hide the ticket but keep it (and its history) in the database.
        with transaction.atomic():
            instance.is_deleted = True
            instance.save()
            services.record_history(instance, self.request.user, "deleted", "no", "yes")

    @extend_schema(request=AssignSerializer, responses=TicketSerializer)
    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        ticket = self.get_object()
        serializer = AssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.assign_ticket(ticket, request.user, serializer.validated_data["assignee"])
        return Response(TicketSerializer(ticket).data)

    @extend_schema(request=StatusSerializer, responses=TicketSerializer)
    @action(detail=True, methods=["post"], url_path="status")
    def change_status(self, request, pk=None):
        ticket = self.get_object()
        serializer = StatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.change_status(ticket, request.user, serializer.validated_data["status"])
        return Response(TicketSerializer(ticket).data)

    @extend_schema(methods=["GET"], responses=CommentSerializer(many=True))
    @extend_schema(methods=["POST"], request=CommentSerializer, responses=CommentSerializer)
    @action(detail=True, methods=["get", "post"])
    def comments(self, request, pk=None):
        ticket = self.get_object()
        user = request.user

        if request.method == "POST":
            serializer = CommentSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            if serializer.validated_data.get("is_internal") and user.role == User.Role.REQUESTER:
                raise PermissionDenied("Requesters cannot write internal notes.")
            serializer.save(ticket=ticket, author=user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        comments = ticket.comments.select_related("author")
        if user.role == User.Role.REQUESTER:
            comments = comments.filter(is_internal=False)  # hide staff-only notes
        return Response(CommentSerializer(comments, many=True).data)

    @extend_schema(responses=HistorySerializer(many=True))
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        ticket = self.get_object()
        if request.user.role == User.Role.REQUESTER:
            raise PermissionDenied("The history is visible to staff only.")
        entries = ticket.history.select_related("changed_by")
        return Response(HistorySerializer(entries, many=True).data)


    @extend_schema(methods=["GET"], responses=AttachmentSerializer(many=True))
    @extend_schema(
        methods=["POST"],
        request={"multipart/form-data": AttachmentSerializer},
        responses=AttachmentSerializer,
    )
    @action(detail=True, methods=["get", "post"],
            parser_classes=[MultiPartParser, FormParser])
    def attachments(self, request, pk=None):
        ticket = self.get_object()  # raises 404 if you may not see this ticket

        if request.method == "POST":
            if ticket.status == Ticket.Status.CLOSED:
                raise ValidationError("Files cannot be added to a closed ticket.")
            serializer = AttachmentSerializer(
                data=request.data, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            with transaction.atomic():
                attachment = serializer.save(ticket=ticket, uploaded_by=request.user)
                services.record_history(
                    ticket, request.user, "attachment", "",
                    os.path.basename(attachment.file.name),
                )
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        files = ticket.attachments.select_related("uploaded_by")
        return Response(
            AttachmentSerializer(files, many=True, context={"request": request}).data
        )

    @extend_schema(responses={200: bytes})
    @action(
        detail=True,
        methods=["get"],
        url_path=r"attachments/(?P<attachment_id>[0-9]+)/download",
    )
    def download_attachment(self, request, pk=None, attachment_id=None):
        ticket = self.get_object()  # same visibility rules as everything else
        attachment = get_object_or_404(ticket.attachments, pk=attachment_id)
        return FileResponse(
            attachment.file.open("rb"),
            as_attachment=True,  # tells the browser to download, never to display
            filename=os.path.basename(attachment.file.name),
        )