from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    """Creates users and superusers using an email address instead of a username."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)  # hashes the password, never stores it as plain text
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "admin")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        REQUESTER = "requester", "Requester"
        AGENT = "agent", "Agent"
        MANAGER = "manager", "Manager"
        ADMIN = "admin", "Administrator"

    username = None          # we don't use usernames
    first_name = None        # we store one full_name field instead
    last_name = None

    email = models.EmailField("email address", unique=True)
    full_name = models.CharField(max_length=150)
    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.REQUESTER
    )

    USERNAME_FIELD = "email"        # log in with email
    REQUIRED_FIELDS = ["full_name"]  # asked for by createsuperuser

    objects = UserManager()

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name

    def __str__(self):
        return f"{self.full_name} ({self.email})"