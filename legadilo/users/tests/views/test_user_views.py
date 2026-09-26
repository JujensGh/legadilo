# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from http import HTTPStatus

import pytest
from django.contrib import messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpRequest
from django.test import RequestFactory
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from legadilo.core.models import Timezone
from legadilo.core.utils.time_utils import utcnow
from legadilo.feeds.tests.factories import FeedCategoryFactory, FeedFactory
from legadilo.reading.tests.factories import (
    ArticleFactory,
    ArticleFetchErrorFactory,
    ArticlesGroupFactory,
    ReadingListFactory,
    TagFactory,
)
from legadilo.users import constants
from legadilo.users.forms import UserAdminChangeForm
from legadilo.users.models import User, UserSession, UserSettings
from legadilo.users.views.user_views import UserRedirectView, UserUpdateView


@pytest.mark.django_db
class TestUserUpdateView:
    def dummy_get_response(self, request: HttpRequest):
        return None

    def test_get_success_url(self, user: User, rf: RequestFactory):
        view = UserUpdateView()
        request = rf.get("/fake-url/")
        request.user = user

        view.request = request
        assert view.get_success_url() == "/users/~update/"

    def test_get_object(self, user: User, rf: RequestFactory):
        view = UserUpdateView()
        request = rf.get("/fake-url/")
        request.user = user

        view.request = request

        assert view.get_object() == user

    def test_form_valid(self, user: User, rf: RequestFactory):
        view = UserUpdateView()
        request = rf.get("/fake-url/")

        # Add the session/message middleware to the request
        SessionMiddleware(self.dummy_get_response).process_request(request)
        MessageMiddleware(self.dummy_get_response).process_request(request)
        request.user = user

        view.request = request

        # Initialize the form
        form = UserAdminChangeForm()
        form.cleaned_data = {}
        form.instance = user
        view.form_valid(form)

        messages_sent = [m.message for m in messages.get_messages(request)]
        assert messages_sent == [_("Information successfully updated")]


@pytest.mark.django_db
class TestUserRedirectView:
    def test_get_redirect_url(self, user: User, rf: RequestFactory):
        view = UserRedirectView()
        request = rf.get("/fake-url")
        request.user = user

        view.request = request
        assert view.get_redirect_url() == "/reading/"


@pytest.mark.django_db
class TestUserUpdateSettingsView:
    def setup_method(self):
        self.url = reverse("users:update_settings")
        self.new_tz, _ = Timezone.objects.get_or_create(name="Europe/Paris")
        self.extra_form_values = {
            "article_details_font_family": constants.UserSettingsArticleDetailsFontFamilyChoices.SYSTEM_UI,  # ruff: ignore[line-too-long]
            "article_details_font_size_desktop": constants.UserSettingsArticleDetailsFontSizeChoices.MEDIUM,  # ruff: ignore[line-too-long]
            "article_details_font_size_tablet": constants.UserSettingsArticleDetailsFontSizeChoices.MEDIUM,  # ruff: ignore[line-too-long]
            "article_details_font_size_mobile": constants.UserSettingsArticleDetailsFontSizeChoices.MEDIUM,  # ruff: ignore[line-too-long]
            "article_details_max_width_desktop": constants.UserSettingsArticleDetailsMaxWidthChoices.MEDIUM,  # ruff: ignore[line-too-long]
            "article_details_max_width_tablet": constants.UserSettingsArticleDetailsMaxWidthChoices.MEDIUM,  # ruff: ignore[line-too-long]
        }

    def test_get_for_current_user(self, logged_in_sync_client):
        response = logged_in_sync_client.get(self.url)

        assert response.status_code == HTTPStatus.OK

    def test_update(self, user, logged_in_sync_client):
        response = logged_in_sync_client.post(
            self.url,
            data={**self.extra_form_values, "default_reading_time": 0, "timezone": self.new_tz.id},
        )

        assert response.status_code == HTTPStatus.OK
        user.settings.refresh_from_db()
        assert user.settings.default_reading_time == 0
        assert user.settings.timezone.id == self.new_tz.id


@pytest.mark.django_db
class TestDeleteAccountView:
    def test_delete(self, user, logged_in_sync_client, utc_tz, reauthentication_bypass):
        assert UserSettings.objects.filter(user=user).exists()
        tag = TagFactory(user=user)
        feed = FeedFactory(user=user)
        feed.tags.add(tag)
        FeedCategoryFactory(user=user)
        article = ArticleFactory(user=user)
        ArticleFetchErrorFactory(article=article)
        article.tags.add(tag)
        reading_list = ReadingListFactory(user=user)
        reading_list.tags.add(tag)
        ArticlesGroupFactory(user=user)
        UserSession.objects.create(
            session_key="expired_session",
            user=user,
            expire_date=utcnow(),
            created_at=utcnow(),
            updated_at=utcnow(),
        )

        with reauthentication_bypass():
            response = logged_in_sync_client.post(reverse("users:delete_account"))

        assert response.status_code == HTTPStatus.FOUND
        assert response["Location"] == reverse("website:home")
        assert not User.objects.filter(id=user.id).exists()
