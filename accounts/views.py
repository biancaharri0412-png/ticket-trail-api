from django.contrib.auth import authenticate
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from .models import User

from .permissions import IsAdminRole
from .serializers import (
    AdminUserSerializer,
    ChangePasswordSerializer,
    LoginSerializer,
    RegisterSerializer,
    UserSerializer,
)


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []          # a stale token must not block sign-up
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {"token": token.key, "user": UserSerializer(user).data}, status=201
        )


class LoginView(generics.GenericAPIView):
    serializer_class = LoginSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"             # limits brute-force password guessing

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            # Same message for "no such email" and "wrong password", so an
            # attacker can't discover which emails exist.
            return Response({"detail": "Invalid email or password."}, status=400)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "user": UserSerializer(user).data})


class LogoutView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        request.user.auth_token.delete()   # the token stops working immediately
        return Response(status=204)


class MeView(generics.RetrieveUpdateAPIView):
    """View or update your own profile."""

    serializer_class = UserSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user           # always yourself, never anyone else


class ChangePasswordView(generics.GenericAPIView):
    serializer_class = ChangePasswordSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["old_password"]):
            return Response({"old_password": ["Wrong password."]}, status=400)
        user.set_password(serializer.validated_data["new_password"])
        user.save()
        # Replace the token so any old copies stop working.
        Token.objects.filter(user=user).delete()
        token = Token.objects.create(user=user)
        return Response({"token": token.key})

class UserViewSet(viewsets.ModelViewSet):
    """Administrators list, create, view, and update accounts. No delete: deactivate instead."""

    queryset = User.objects.all().order_by("email")
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdminRole]
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = ["role", "is_active"]
    search_fields = ["email", "full_name"]