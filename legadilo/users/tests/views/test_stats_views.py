# SPDX-FileCopyrightText: 2026 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from http import HTTPStatus

import pytest
from django.urls import reverse

from legadilo.conftest import assert_redirected_to_login_page
from legadilo.feeds.tests.factories import FeedFactory
from legadilo.reading.tests.factories import ArticleFactory


@pytest.mark.django_db
class TestStatsView:
    @pytest.fixture(autouse=True)
    def _setup_data(self, user):
        self.url = reverse("users:stats")

    def test_stats_view_not_logged_in(self, client):
        response = client.get(self.url)

        assert_redirected_to_login_page(response)

    def test_stats_view(self, user, other_user, logged_in_sync_client):
        FeedFactory(user=other_user, enabled=True)
        ArticleFactory(user=other_user, main_feed=None)
        FeedFactory(user=user, enabled=True)
        FeedFactory(user=user, enabled=False)
        ArticleFactory(user=user, main_feed=None)
        ArticleFactory(user=user, main_feed=FeedFactory(user=user))

        response = logged_in_sync_client.get(self.url)

        assert response.status_code == HTTPStatus.OK
        assert response.template_name == "users/stats.html"
        assert "stats" in response.context_data
        assert response.context_data["stats"] == {
            "nb_active_feeds": 3,
            "nb_articles": 2,
            "nb_articles_added_last_year": 0,
            "nb_articles_added_this_year": 2,
            "nb_articles_from_feeds": 1,
            "nb_articles_from_feeds_last_year": 0,
            "nb_articles_from_feeds_this_year": 1,
            "nb_articles_opened_last_year": 0,
            "nb_articles_opened_this_year": 0,
            "nb_feeds": 3,
            "nb_manually_added_articles": 1,
            "nb_manually_added_articles_last_year": 0,
            "nb_manually_added_articles_this_year": 1,
            "nb_opened_articles": 0,
        }
