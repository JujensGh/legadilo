#  SPDX-FileCopyrightText: 2025 Legadilo contributors
#
#  SPDX-License-Identifier: AGPL-3.0-or-later

from http import HTTPStatus

import pytest
import time_machine
from django.urls import reverse

from legadilo.core.utils.testing import read_streamable_response, serialize_for_snapshot
from legadilo.core.utils.time_utils import utcdt
from legadilo.feeds.models import FeedArticle
from legadilo.feeds.tests.factories import FeedCategoryFactory, FeedFactory
from legadilo.reading.tests.factories import ArticleFactory


@pytest.mark.django_db
class TestExportFeedsApi:
    @pytest.fixture(autouse=True)
    def _setup_data(self, user):
        self.url = reverse("api-1.0.0:export_feeds")
        self.category = FeedCategoryFactory(id=1, user=user, title="My Category")
        FeedFactory(id=1, title="Feed other user", feed_url="https://example.com/feeds/1.xml")
        self.feed_without_category = FeedFactory(
            id=2,
            user=user,
            title="Feed without a category",
            feed_url="https://example.com/feeds/no_cat.xml",
        )
        self.feed_with_category = FeedFactory(
            id=3,
            user=user,
            category=self.category,
            title="Feed with category",
            feed_url="https://example.com/feeds/2.xml",
        )

    def test_not_logged_in(self, client):
        response = client.get(self.url)

        assert response.status_code == HTTPStatus.UNAUTHORIZED

    def test_export_as_opml(self, logged_in_sync_client, snapshot):
        with time_machine.travel("2024-06-20 22:00:00", tick=False):
            response = logged_in_sync_client.get(self.url)

        assert response.status_code == HTTPStatus.OK
        assert response.headers.get("Content-Type") == "text/x-opml"
        assert response.content == snapshot

    def test_export_as_json(self, logged_in_sync_client, snapshot):
        with time_machine.travel("2024-06-20 22:00:00", tick=False):
            response = logged_in_sync_client.get(self.url, data={"format": "json"})

        assert response.status_code == HTTPStatus.OK
        assert response.headers.get("Content-Type") == "application/json; charset=utf-8"
        assert serialize_for_snapshot(response.json()) == snapshot


@pytest.mark.django_db
class TestExportArticlesApi:
    @pytest.fixture(autouse=True)
    def _setup_data(self, user):
        self.url = reverse("api-1.0.0:export_articles")
        with time_machine.travel("2024-06-20 22:00:00", tick=False):
            feed = FeedFactory(
                user=user,
                id=1,
                title="Some feed",
                feed_url="https://example.com/feeds/1.xml",
            )
        with time_machine.travel("2025-06-20 22:00:00", tick=False):
            FeedFactory(
                user=user,
                id=2,
                title="Recently updated feed",
                feed_url="https://example.com/feeds/2.xml",
            )
        article = ArticleFactory(
            user=user,
            id=1,
            title="Some article",
            url="https://example.com/article/1",
            published_at=utcdt(2024, 6, 23, 12, 0, 0),
            updated_at=utcdt(2024, 6, 23, 12, 0, 0),
            main_feed=feed,
        )
        FeedArticle.objects.create(feed=feed, article=article)
        ArticleFactory(
            user=user,
            id=2,
            title="Recently updated article",
            url="https://example.com/article/2",
            published_at=utcdt(2024, 6, 23, 12, 0, 0),
            updated_at=utcdt(2025, 6, 23, 12, 0, 0),
        )

    def test_not_logged_in(self, client):
        response = client.get(self.url)

        assert response.status_code == HTTPStatus.UNAUTHORIZED

    def test_export_all(self, logged_in_sync_client, snapshot):
        response = logged_in_sync_client.get(self.url)

        assert read_streamable_response(response) == snapshot

    def test_dont_export_feeds(self, logged_in_sync_client, snapshot):
        response = logged_in_sync_client.get(self.url, data={"include_feeds": False})

        assert read_streamable_response(response) == snapshot

    def test_export_only_recent_articles(self, logged_in_sync_client, snapshot):
        response = logged_in_sync_client.get(self.url, data={"updated_since": utcdt(2025, 6, 1)})

        assert read_streamable_response(response) == snapshot
