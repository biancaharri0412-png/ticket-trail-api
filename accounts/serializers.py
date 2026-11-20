from multiprocessing.managers import Token

from django.contrib.auth import password_validation
from rest_framework import serializers

from .models import User
from rest_framework.authtoken.models import Token


class UserSerializer(serializers.ModelSerializer):
    """What we show about a user. Role and email can't be changed from here."""

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "role", "date_joined"]
        read_only_fields = ["id", "email", "role", "date_joined"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["email", "full_name", "password"]

    def validate_password(self, value):
        password_validation.validate_password(value)  # Django's strength rules
        return value

    def create(self, validated_data):
        # The role is NOT accepted from the client. New accounts are always
        # Requesters, so nobody can register themselves as an admin.
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        password_validation.validate_password(value)
        return value


class AdminUserSerializer(serializers.ModelSerializer):
    """Used only by administrators to manage accounts."""

    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "role", "is_active", "date_joined", "password"]
        read_only_fields = ["id", "date_joined"]

    def validate_email(self, value):
        if self.instance and value.lower() != self.instance.email.lower():
            raise serializers.ValidationError("An email address cannot be changed.")
        return value

    def validate_password(self, value):
        password_validation.validate_password(value)
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        if self.instance is None:
            if not attrs.get("password"):
                raise serializers.ValidationError({"password": "This field is required."})
        elif request and self.instance.pk == request.user.pk:
            if attrs.get("role", self.instance.role) != User.Role.ADMIN:
                raise serializers.ValidationError(
                    {"role": "You cannot remove your own administrator role."}
                )
            if attrs.get("is_active", True) is False:
                raise serializers.ValidationError(
                    {"is_active": "You cannot deactivate your own account."}
                )
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, **validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        instance = super().update(instance, validated_data)
        if password:
            instance.set_password(password)
            instance.save()
            Token.objects.filter(user=instance).delete()  # force a fresh login
        return instance