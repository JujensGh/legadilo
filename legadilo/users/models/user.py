# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import timedelta
from functools import cached_property
from typing import Self
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import models
from django.template.loader import get_template
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext_lazy as _

from legadilo.core.utils.db import CaseInsensitiveEmailField
from legadilo.core.utils.time_utils import utcnow

from ...core.utils.types import DeletionResult
from .. import constants as users_constants


class UserQuerySet(models.QuerySet):
    def with_feeds(self, user_ids: list[int] | None) -> Self:
        qs = self.filter(feeds__isnull=False)
        if user_ids:
            qs = qs.filter(id__in=user_ids)

        return qs.distinct()

    def invalid_accounts(self):
        # Users are created as active, no point in filtering on the active status here.
        return self.alias(
            nb_verified_emails=models.Count(
                "emailaddress", filter=models.Q(emailaddress__verified=True)
            )
        ).filter(
            date_joined__lt=utcnow() - users_constants.INVALID_USERS_RETENTION_DAYS,
            nb_verified_emails=0,
        )

    def inactive_accounts_to_delete(self):
        return self.alias(nb_sessions=models.Count("sessions")).filter(
            last_login__lte=utcnow() - users_constants.INACTIVE_USERS_RETENTION,
            nb_sessions=0,
        )

    def inactive_accounts_to_notify(self):
        filter_ = models.Q()
        for notification_threshold in users_constants.INACTIVE_USERS_NOTIFICATION_THRESHOLDS:
            filter_ |= models.Q(
                last_login__date=(
                    utcnow() - users_constants.INACTIVE_USERS_RETENTION + notification_threshold
                ).date()
            )

        return self.alias(nb_sessions=models.Count("sessions")).filter(filter_, nb_sessions=0)


class UserManager(DjangoUserManager["User"]):
    """Custom manager for the User model."""

    _hints: dict

    def get_queryset(self) -> UserQuerySet:
        return UserQuerySet(self.model, using=self._db, hints=self._hints)

    def _create_user(self, email: str, password: str | None, **extra_fields):
        """Create and save a user with the given email and password."""
        if not email:
            raise ValueError("The given email must be set")
        validate_email(email)
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.password = make_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields):  # type: ignore[override]
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str | None = None, **extra_fields):  # type: ignore[override]
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)

    def get(self, *args, **kwargs):
        return self.select_related("settings", "settings__timezone").get(*args, **kwargs)

    def cleanup_invalid_accounts(self) -> DeletionResult:
        return self.get_queryset().invalid_accounts().delete()

    def compute_stats(self) -> dict[str, int]:
        """Compute various statistics about total and active users."""
        return self.get_queryset().aggregate(
            total_nb_users=models.Count("id", distinct=True),
            total_nb_active_users=models.Count(
                "id", filter=models.Q(is_active=True), distinct=True
            ),
            total_nb_active_users_with_validated_emails=models.Count(
                "id", filter=models.Q(is_active=True, emailaddress__verified=True), distinct=True
            ),
            total_nb_active_users_connected_last_week=models.Count(
                "id", filter=models.Q(last_login__gt=utcnow() - timedelta(days=7)), distinct=True
            ),
            total_account_created_last_week=models.Count(
                "id", filter=models.Q(date_joined__gt=utcnow() - timedelta(days=7)), distinct=True
            ),
            nb_users_with_active_session=models.Count(
                "sessions__user_id",
                filter=models.Q(sessions__expire_date__gte=utcnow()),
                distinct=True,
            ),
        )

    def list_admin_emails(self) -> list[str]:
        return list(
            self
            .get_queryset()
            .filter(is_superuser=True, is_staff=True, is_active=True)
            .values_list("email", flat=True)
        )

    def cleanup_inactive_users(self) -> DeletionResult:
        return self.get_queryset().inactive_accounts_to_delete().delete()

    def notify_inactive_accounts(self) -> int:
        inactive_accounts = set(
            self
            .get_queryset()
            .inactive_accounts_to_notify()
            .select_related("settings")
            .order_by("last_login")
        )
        template = get_template("users/inactive_account_notification.txt")
        for user in inactive_accounts:
            days_since_last_login = (utcnow() - user.last_login).days
            with translation.override(user.settings.language):
                message = template.render({
                    "email": user.email,
                    "days_since_last_login": days_since_last_login,
                    "days_until_deletion": (
                        (user.last_login + users_constants.INACTIVE_USERS_RETENTION - utcnow()).days
                    ),
                })
                send_mail(
                    subject=_("Your Legadilo account is inactive and will be deleted soon"),
                    message=message.strip(),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                )

        return len(inactive_accounts)


class User(AbstractUser):
    """Default custom user model for Legadilo.

    If adding fields that need to be filled at user signup,
    check forms.SignupForm and forms.SocialSignupForms accordingly.
    """

    # First and last name do not cover name patterns around the globe
    name = models.CharField(_("Username"), blank=True, max_length=255)
    first_name = None  # type: ignore[assignment]
    last_name = None  # type: ignore[assignment]
    email = CaseInsensitiveEmailField(_("email address"), unique=True)
    username = None  # type: ignore[assignment]

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    # mypy false positive about overriding class variable.
    objects = UserManager()  # type: ignore[misc]

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("users:update")

    @cached_property
    def count_unread_notifications(self) -> int:
        return self.notifications.count_unread(self)

    @cached_property
    def tzinfo(self) -> ZoneInfo:
        return self.settings.timezone.zone_info

    @cached_property
    def stats(self) -> dict[str, int]:
        return {
            "nb_articles": self.articles.count(),
            "nb_opened_articles": self.articles.filter(was_opened=True).count(),
            "nb_manually_added_articles": self.articles.filter(main_feed__isnull=True).count(),
            "nb_articles_from_feeds": self.articles.filter(main_feed__isnull=False).count(),
            "nb_feeds": self.feeds.count(),
            "nb_active_feeds": self.feeds.filter(enabled=True).count(),
            "nb_articles_added_this_year": self.articles.filter(
                obj_created_at__year=utcnow().year
            ).count(),
            "nb_articles_opened_this_year": self.articles.filter(
                opened_at__year=utcnow().year
            ).count(),
            "nb_manually_added_articles_this_year": self.articles.filter(
                obj_created_at__year=utcnow().year,
                main_feed__isnull=True,
            ).count(),
            "nb_articles_from_feeds_this_year": self.articles.filter(
                obj_created_at__year=utcnow().year,
                main_feed__isnull=False,
            ).count(),
            "nb_articles_added_last_year": self.articles.filter(
                obj_created_at__year=utcnow().year - 1
            ).count(),
            "nb_articles_opened_last_year": self.articles.filter(
                opened_at__year=utcnow().year - 1
            ).count(),
            "nb_manually_added_articles_last_year": self.articles.filter(
                obj_created_at__year=utcnow().year - 1,
                main_feed__isnull=True,
            ).count(),
            "nb_articles_from_feeds_last_year": self.articles.filter(
                obj_created_at__year=utcnow().year - 1,
                main_feed__isnull=False,
            ).count(),
        }
