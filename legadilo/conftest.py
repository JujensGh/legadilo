# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later
from contextlib import contextmanager
from http import HTTPStatus
from unittest.mock import patch

import pytest
from django.urls import reverse

from legadilo.core.models import Timezone
from legadilo.users.models import User
from legadilo.users.tests.factories import UserFactory, UserSettingsFactory


@pytest.fixture
def reauthentication_bypass():
    """Copied from https://codeberg.org/allauth/django-allauth/src/commit/9bbcca14665b787d20284125c610986f55d86eec/tests/conftest.py#L134"""

    @contextmanager
    def f():
        with patch(
            "allauth.account.internal.flows.reauthentication.did_recently_reauthenticate"
        ) as m:
            m.return_value = True
            yield

    return f


@pytest.fixture(autouse=True)
def _setup_settings(settings, tmpdir):
    settings.IS_PRODUCTION = True
    # https://docs.djangoproject.com/en/dev/ref/settings/#media-url
    settings.MEDIA_URL = "http://media.testserver"
    settings.MEDIA_ROOT = tmpdir.strpath
    settings.STORAGES["staticfiles"]["BACKEND"] = (
        "django.contrib.staticfiles.storage.StaticFilesStorage"
    )
    # https://docs.djangoproject.com/en/dev/ref/settings/#password-hashers
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    # https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
    settings.MAILERS["default"]["BACKEND"] = "django.core.mail.backends.locmem.EmailBackend"
    settings.TEMPLATES[0]["OPTIONS"]["debug"] = True


@pytest.fixture
def user(db) -> User:
    return UserFactory()


@pytest.fixture
def other_user(db) -> User:
    return UserFactory()


@pytest.fixture
def utc_tz(db) -> Timezone:
    # The Timezone table will be filled when the db is created from migrations and deleted at the
    # end of the test suite. So we have to use get_or_create here.
    return Timezone.objects.get(name="UTC")


@pytest.fixture
def admin_user(admin_user, utc_tz) -> User:
    admin_user.settings = UserSettingsFactory(user=admin_user, timezone=utc_tz)
    admin_user.save()
    return admin_user


@pytest.fixture
def logged_in_sync_client(user, client):
    client.force_login(user)
    return client


@pytest.fixture
def logged_in_other_user_sync_client(other_user, client):
    client.force_login(other_user)
    return client


def assert_redirected_to_login_page(response):
    assert response.status_code == HTTPStatus.FOUND  # ruff:ignore[assert]
    assert reverse("account_login") in response["Location"]  # ruff:ignore[assert]
