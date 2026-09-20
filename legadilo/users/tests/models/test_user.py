# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import datetime, timedelta
from io import StringIO

import pytest
import time_machine
from allauth.account.models import EmailAddress
from dateutil.tz import UTC
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection
from slugify import slugify

from legadilo.core.utils.testing import AnyOfType
from legadilo.core.utils.time_utils import utcnow
from legadilo.feeds.tests.factories import FeedFactory
from legadilo.reading.tests.factories import ArticleFactory
from legadilo.users import constants
from legadilo.users.models import User, UserSession
from legadilo.users.tests.factories import UserFactory


@pytest.mark.django_db
class TestUserQuerySet:
    def test_with_feeds(self, user, other_user):
        FeedFactory(user=user)

        users = list(User.objects.get_queryset().with_feeds(None))

        assert users == [user]

    def test_with_feeds_and_user_ids_limits(self, user, other_user):
        FeedFactory(user=user)
        FeedFactory(user=other_user)

        users = list(User.objects.get_queryset().with_feeds([user.id]))

        assert users == [user]

    def test_invalid_accounts(self):
        with time_machine.travel("2023-01-01"):
            user_to_delete_no_email_address = UserFactory(
                email="user_to_delete_no_email_address@example.com", is_active=False
            )
            user_to_delete_inactive_and_no_verified_email = UserFactory(
                email="user_to_delete_inactive_and_no_verified_email@example.com", is_active=False
            )
            EmailAddress.objects.create(
                user=user_to_delete_inactive_and_no_verified_email,
                email=user_to_delete_inactive_and_no_verified_email.email,
                verified=False,
            )
            user_to_delete_active_and_no_verified_email = UserFactory(
                email="user_to_delete_active_and_no_verified_email@example.com", is_active=True
            )
            EmailAddress.objects.create(
                user=user_to_delete_active_and_no_verified_email,
                email=user_to_delete_active_and_no_verified_email.email,
                verified=False,
            )
            user_to_keep_active_and_verified_email = UserFactory(
                email="user_to_keep_active_and_verified_email@example.com", is_active=True
            )
            EmailAddress.objects.create(
                user=user_to_keep_active_and_verified_email,
                email=user_to_keep_active_and_verified_email.email,
                verified=True,
            )
            user_to_keep_inactive_but_verified_email = UserFactory(
                email="user_to_keep_inactive_but_verified_email@example.com", is_active=False
            )
            EmailAddress.objects.create(
                user=user_to_keep_inactive_but_verified_email,
                email=user_to_keep_inactive_but_verified_email.email,
                verified=True,
            )
        user_to_keep_inactive_no_verified_email_too_recent_for_deletion = UserFactory(
            email="user_to_keep_inactive_no_verified_email_too_recent_for_deletion@example.com",
            is_active=False,
        )
        EmailAddress.objects.create(
            user=user_to_keep_inactive_no_verified_email_too_recent_for_deletion,
            email=user_to_keep_inactive_no_verified_email_too_recent_for_deletion.email,
            verified=False,
        )

        invalid_users = list(User.objects.get_queryset().invalid_accounts().order_by("id"))

        assert invalid_users == [
            user_to_delete_no_email_address,
            user_to_delete_inactive_and_no_verified_email,
            user_to_delete_active_and_no_verified_email,
        ]

    def test_inactive_accounts_to_delete(self):
        UserFactory(email="active@example.com", last_login=utcnow())
        user_to_delete = UserFactory(
            email="to_delete@example.com", last_login=utcnow() - constants.INACTIVE_USERS_RETENTION
        )
        UserFactory(
            email="to_notify@example.com",
            last_login=utcnow()
            - constants.INACTIVE_USERS_RETENTION
            + constants.INACTIVE_USERS_NOTIFICATION_THRESHOLDS[0],
        )

        inactive_accounts = User.objects.get_queryset().inactive_accounts_to_delete()

        assert list(inactive_accounts) == [user_to_delete]

    def test_inactive_accounts_to_notify(self):
        UserFactory(email="active@example.com", last_login=utcnow())
        UserFactory(
            email="to_delete@example.com", last_login=utcnow() - constants.INACTIVE_USERS_RETENTION
        )
        user_to_notify_30_days = UserFactory(
            email="user_to_notify_30_days@example.com",
            last_login=utcnow()
            - constants.INACTIVE_USERS_RETENTION
            + constants.INACTIVE_USERS_NOTIFICATION_THRESHOLDS[0],
        )
        user_to_notify_14_days = UserFactory(
            email="user_to_notify_14_days@example.com",
            last_login=utcnow()
            - constants.INACTIVE_USERS_RETENTION
            + constants.INACTIVE_USERS_NOTIFICATION_THRESHOLDS[1],
        )
        user_to_notify_7_days = UserFactory(
            email="user_to_notify_7_days@example.com",
            last_login=utcnow()
            - constants.INACTIVE_USERS_RETENTION
            + constants.INACTIVE_USERS_NOTIFICATION_THRESHOLDS[2],
        )
        UserFactory(
            email="almost_to_notify@example.com",
            last_login=utcnow()
            - constants.INACTIVE_USERS_RETENTION
            + constants.INACTIVE_USERS_NOTIFICATION_THRESHOLDS[0]
            + timedelta(days=1),
        )

        inactive_account_ids = (
            User.objects.get_queryset().inactive_accounts_to_notify().values_list("id", flat=True)
        )

        assert set(inactive_account_ids) == {
            user_to_notify_30_days.id,
            user_to_notify_14_days.id,
            user_to_notify_7_days.id,
        }


@pytest.mark.django_db
class TestUserManager:
    def test_create_user(self):
        user = User.objects.create_user(
            email="john@example.com",
            password="something-r@nd0m!",
        )
        assert user.email == "john@example.com"
        assert not user.is_staff
        assert not user.is_superuser
        assert user.check_password("something-r@nd0m!")
        assert user.username is None

    def test_create_superuser(self):
        user = User.objects.create_superuser(
            email="admin@example.com",
            password="something-r@nd0m!",
        )
        assert user.email == "admin@example.com"
        assert user.is_staff
        assert user.is_superuser
        assert user.username is None

    def test_create_superuser_username_ignored(self):
        user = User.objects.create_superuser(
            email="test@example.com",
            password="something-r@nd0m!",
        )
        assert user.username is None

    def test_create_user_invalid_email(self):
        with pytest.raises(ValidationError):
            User.objects.create_user(email="test", password="something-R@nd0m!")

    def test_email_case_insensitive_search(self):
        user = User.objects.create(email="Hacker@example.com")
        user2 = User.objects.get(email="hacker@example.com")
        assert user == user2

    def test_email_case_insensitive_unique(self):
        User.objects.create(email="Hacker@example.com")
        if connection.vendor == "postgresql":
            msg = 'duplicate key value violates unique constraint "users_user_email_key"'
        else:
            msg = "UNIQUE constraint failed: users_user.email"

        with pytest.raises(IntegrityError, match=msg):
            User.objects.create(email="hacker@example.com")

    def test_cleanup_invalid_users(self):
        with time_machine.travel("2023-01-01"):
            user_to_deleted = UserFactory(email="hacker@example.com", is_active=True)
            EmailAddress.objects.create(
                user=user_to_deleted, email=user_to_deleted.email, verified=False
            )
            user_to_keep = UserFactory(email="other-hacker@example.com", is_active=True)
            EmailAddress.objects.create(user=user_to_keep, email=user_to_keep.email, verified=True)

        deletion_result = User.objects.cleanup_invalid_accounts()

        assert deletion_result == (
            3,
            {"users.UserSettings": 1, "account.EmailAddress": 1, "users.User": 1},
        )
        assert list(User.objects.all()) == [user_to_keep]

    def test_compute_stats(self):
        with time_machine.travel("2023-01-01"):
            UserFactory(is_active=True)

        UserFactory(is_active=False)
        active_user_with_unverified_email = UserFactory(is_active=True)
        EmailAddress.objects.create(
            user=active_user_with_unverified_email,
            email=active_user_with_unverified_email.email,
            verified=False,
        )
        active_user_with_validated_email = UserFactory(is_active=True)
        EmailAddress.objects.create(
            user=active_user_with_validated_email,
            email=active_user_with_validated_email.email,
            verified=True,
        )
        active_user_who_logged_in = UserFactory(is_active=True, last_login=utcnow())
        EmailAddress.objects.create(
            user=active_user_who_logged_in,
            email=active_user_who_logged_in.email,
            verified=True,
        )
        UserSession.objects.create(
            session_key="unverified_email_expired_session",
            user=active_user_with_unverified_email,
            expire_date=utcnow() - timedelta(days=100),
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        UserSession.objects.create(
            session_key="unverified_email_valid_session",
            user=active_user_with_unverified_email,
            expire_date=utcnow() + timedelta(days=7),
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        UserSession.objects.create(
            session_key="expired_session",
            user=active_user_who_logged_in,
            expire_date=utcnow() - timedelta(days=100),
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        UserSession.objects.create(
            session_key="valid_session",
            user=active_user_who_logged_in,
            expire_date=utcnow() + timedelta(days=7),
            created_at=utcnow(),
            updated_at=utcnow(),
        )

        stats = User.objects.compute_stats()

        assert stats == {
            "total_account_created_last_week": 4,
            "total_nb_active_users": 4,
            "total_nb_active_users_connected_last_week": 1,
            "total_nb_active_users_with_validated_emails": 2,
            "total_nb_users": 5,
            "nb_users_with_active_session": 2,
        }

    def test_list_admin_emails(self):
        admin_user = UserFactory(is_superuser=True, is_staff=True, is_active=True)
        UserFactory(is_superuser=True, is_staff=True, is_active=False)
        UserFactory(is_superuser=False, is_staff=False, is_active=True)

        admin_emails = User.objects.list_admin_emails()

        assert admin_emails == [admin_user.email]

    def test_notify_inactive_accounts(self, mocker, snapshot):
        send_mail_mock = mocker.patch("legadilo.users.models.user.send_mail")
        user_to_notify_14_days = UserFactory(
            email="user_to_notify_14_days@example.com",
            last_login=utcnow()
            - constants.INACTIVE_USERS_RETENTION
            + constants.INACTIVE_USERS_NOTIFICATION_THRESHOLDS[1],
        )
        user_to_notify_7_days = UserFactory(
            email="user_to_notify_7_days@example.com",
            last_login=utcnow()
            - constants.INACTIVE_USERS_RETENTION
            + constants.INACTIVE_USERS_NOTIFICATION_THRESHOLDS[2],
        )
        UserFactory(
            email="almost_to_notify@example.com",
            last_login=utcnow()
            - constants.INACTIVE_USERS_RETENTION
            + constants.INACTIVE_USERS_NOTIFICATION_THRESHOLDS[0]
            + timedelta(days=1),
        )

        nb_notified_accounts = User.objects.notify_inactive_accounts()

        assert nb_notified_accounts == 2
        send_mail_mock.assert_has_calls(
            [
                mocker.call(
                    subject="Your Legadilo account is inactive and will be deleted soon",
                    message=AnyOfType(str),
                    from_email="Legadilo <noreply@legadilo.eu>",
                    recipient_list=[user_to_notify_7_days.email],
                ),
                mocker.call(
                    subject="Your Legadilo account is inactive and will be deleted soon",
                    message=AnyOfType(str),
                    from_email="Legadilo <noreply@legadilo.eu>",
                    recipient_list=[user_to_notify_14_days.email],
                ),
            ],
            any_order=True,
        )
        for call in send_mail_mock.call_args_list:
            email = call.kwargs["recipient_list"][0]
            assert call.kwargs["message"] == snapshot(name=f"message_body_{slugify(email)}")

    def test_cleanup_inactive_users(self):
        user_active = UserFactory(email="active@example.com", last_login=utcnow())
        UserFactory(
            email="to_delete@example.com", last_login=utcnow() - constants.INACTIVE_USERS_RETENTION
        )
        user_to_notify_14_days = UserFactory(
            email="user_to_notify_14_days@example.com",
            last_login=utcnow()
            - constants.INACTIVE_USERS_RETENTION
            + constants.INACTIVE_USERS_NOTIFICATION_THRESHOLDS[1],
        )

        nb_deleted = User.objects.cleanup_inactive_users()

        assert nb_deleted == (2, {"users.UserSettings": 1, "users.User": 1})
        user_ids = set(User.objects.values_list("id", flat=True))
        assert user_ids == {user_active.id, user_to_notify_14_days.id}


@pytest.mark.django_db
def test_createsuperuser_command():
    """Ensure createsuperuser command works with our custom manager."""
    out = StringIO()
    command_result = call_command(
        "createsuperuser",
        "--email",
        "henry@example.com",
        interactive=False,
        stdout=out,
    )

    assert command_result is None
    assert out.getvalue() == "Superuser created successfully.\n"
    user = User.objects.get(email="henry@example.com")
    assert not user.has_usable_password()


def test_user_get_absolute_url(user: User):
    assert user.get_absolute_url() == "/users/~update/"


@pytest.mark.django_db
class TestUser:
    def test_stats_property_all_values(self):
        user = UserFactory()

        # Create feeds: 5 total, 4 active (enabled=True, i.e., disabled_at=None)
        # Need 4 active feeds to avoid duplicate with other counts
        with time_machine.travel("2025-01-15"):
            active_feed1 = FeedFactory(user=user, disabled_at=None)
            active_feed2 = FeedFactory(user=user, disabled_at=None)
            active_feed3 = FeedFactory(user=user, disabled_at=None)
            active_feed4 = FeedFactory(user=user, disabled_at=None)
            FeedFactory(user=user, disabled_at=utcnow())

        # Create articles for this year (2025)
        # 6 articles added this year
        # 4 opened this year
        # 3 manually added this year (main_feed=None)
        # 3 from feeds this year (main_feed != None)
        with time_machine.travel("2025-01-15"):
            ArticleFactory(
                user=user,
                title="Manually added this year, opened this year",
                main_feed=None,
                obj_created_at=datetime(2025, 1, 10, tzinfo=UTC),
                opened_at=datetime(2025, 1, 12, tzinfo=UTC),
            )
            ArticleFactory(
                user=user,
                title="Manually added this year, opened this year",
                main_feed=None,
                obj_created_at=datetime(2025, 1, 11, tzinfo=UTC),
                opened_at=datetime(2025, 1, 13, tzinfo=UTC),
            )
            ArticleFactory(
                user=user,
                title="Manually added this year, not opened",
                main_feed=None,
                obj_created_at=datetime(2025, 1, 12, tzinfo=UTC),
                opened_at=None,
            )

            ArticleFactory(
                user=user,
                title="From feed this year, opened this year",
                main_feed=active_feed1,
                obj_created_at=datetime(2025, 1, 10, tzinfo=UTC),
                opened_at=datetime(2025, 1, 12, tzinfo=UTC),
            )
            ArticleFactory(
                user=user,
                title="From feed this year, opened this year",
                main_feed=active_feed2,
                obj_created_at=datetime(2025, 1, 11, tzinfo=UTC),
                opened_at=datetime(2025, 1, 13, tzinfo=UTC),
            )

            ArticleFactory(
                user=user,
                title="From feed this year, not opened",
                main_feed=active_feed3,
                obj_created_at=datetime(2025, 1, 10, tzinfo=UTC),
                opened_at=None,
            )

        # Create articles for last year (2024)
        # 5 articles added last year
        with time_machine.travel("2024-12-01"):
            ArticleFactory(
                user=user,
                title="Manually added last year, opened last year",
                main_feed=None,
                obj_created_at=datetime(2024, 12, 1, tzinfo=UTC),
                opened_at=datetime(2024, 12, 2, tzinfo=UTC),
            )

            ArticleFactory(
                user=user,
                title="From feed last year, opened last year",
                main_feed=active_feed1,
                obj_created_at=datetime(2024, 12, 1, tzinfo=UTC),
                opened_at=datetime(2024, 12, 2, tzinfo=UTC),
            )
            ArticleFactory(
                user=user,
                title="From feed last year, opened last year",
                main_feed=active_feed2,
                obj_created_at=datetime(2024, 12, 3, tzinfo=UTC),
                opened_at=datetime(2024, 12, 4, tzinfo=UTC),
            )
            ArticleFactory(
                user=user,
                title="From feed last year, not opened",
                main_feed=active_feed3,
                obj_created_at=datetime(2024, 12, 5, tzinfo=UTC),
                opened_at=None,
            )
            ArticleFactory(
                user=user,
                title="From feed last year, opened last year",
                main_feed=active_feed4,
                obj_created_at=datetime(2024, 12, 6, tzinfo=UTC),
                opened_at=datetime(2024, 12, 7, tzinfo=UTC),
            )

        with time_machine.travel("2025-01-15"):
            stats = user.stats

        assert stats == {
            "nb_articles": 11,
            "nb_opened_articles": 8,
            "nb_manually_added_articles": 4,
            "nb_articles_from_feeds": 7,
            "nb_feeds": 5,
            "nb_active_feeds": 4,
            "nb_articles_added_this_year": 6,
            "nb_articles_opened_this_year": 4,
            "nb_manually_added_articles_this_year": 3,
            "nb_articles_from_feeds_this_year": 3,
            "nb_articles_added_last_year": 5,
            "nb_articles_opened_last_year": 4,
            "nb_manually_added_articles_last_year": 1,
            "nb_articles_from_feeds_last_year": 4,
        }
