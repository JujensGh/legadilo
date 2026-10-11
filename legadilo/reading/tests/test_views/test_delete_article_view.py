# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from http import HTTPStatus

import pytest
from django.urls import reverse

from legadilo.conftest import assert_redirected_to_login_page
from legadilo.feeds.models import FeedArticle
from legadilo.feeds.tests.factories import FeedArticleFactory, FeedFactory
from legadilo.reading.models import Article
from legadilo.reading.tests.factories import ArticleFactory, ReadingListFactory


@pytest.mark.django_db
class TestDeleteArticleView:
    @pytest.fixture(autouse=True)
    def _setup_data(self, user):
        self.reading_list = ReadingListFactory(user=user)
        self.reading_list_url = reverse(
            "reading:reading_list", kwargs={"reading_list_slug": self.reading_list.slug}
        )
        self.article = ArticleFactory(user=user)
        self.url = reverse(
            "reading:delete_article",
            kwargs={
                "article_id": self.article.id,
            },
        )

    def test_cannot_access_if_not_logged_in(self, client):
        response = client.post(self.url)

        assert_redirected_to_login_page(response)

    def test_cannot_delete_article_as_other_user(self, logged_in_other_user_sync_client):
        response = logged_in_other_user_sync_client.post(self.url)

        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_delete_with_from_url(self, logged_in_sync_client, django_assert_num_queries):
        with django_assert_num_queries(15):
            response = logged_in_sync_client.post(self.url, {"from_url": self.reading_list_url})

        assert response.status_code == HTTPStatus.OK
        assert response["HX-Reswap"] == "delete swap:1s"
        assert response["HX-Retarget"] == f"#article-card-{self.article.id}"
        assert Article.objects.count() == 0

    def test_delete(self, logged_in_sync_client, django_assert_num_queries):
        with django_assert_num_queries(18):
            response = logged_in_sync_client.post(
                self.url,
                {
                    "from_url": self.reading_list_url,
                    "displayed_reading_list_id": str(self.reading_list.id),
                },
            )

        assert response.status_code == HTTPStatus.OK
        assert response.context_data["reading_lists"] == [self.reading_list]
        assert response.context_data["count_unread_articles_of_reading_lists"] == {
            self.reading_list.slug: 0
        }
        assert response.context_data["displayed_reading_list"] == self.reading_list
        assert response.context_data["js_cfg"] == {
            "is_reading_on_scroll_enabled": False,
            "auto_refresh_interval": 0,
        }
        assert response["HX-Reswap"] == "delete swap:1s"
        assert response["HX-Retarget"] == f"#article-card-{self.article.id}"
        assert Article.objects.count() == 0
        assert b"<article" not in response.content

    def test_delete_article_for_article_details(
        self, logged_in_sync_client, django_assert_num_queries
    ):
        with django_assert_num_queries(12):
            response = logged_in_sync_client.post(
                self.url, {"from_url": self.reading_list_url, "for_article_details": "True"}
            )

        assert response.status_code == HTTPStatus.OK
        assert response["HX-Redirect"] == self.reading_list_url
        assert response["HX-Push-Url"] == "true"
        assert Article.objects.count() == 0

    def test_delete_article_linked_with_feed(
        self, logged_in_sync_client, django_assert_num_queries, user
    ):
        feed = FeedFactory(user=user)
        feed_article = FeedArticleFactory(feed=feed, article=self.article)

        with django_assert_num_queries(13):
            response = logged_in_sync_client.post(
                self.url, {"from_url": self.reading_list_url, "for_article_details": "True"}
            )

        assert response.status_code == HTTPStatus.OK
        assert Article.objects.count() == 0
        assert FeedArticle.objects.count() == 1
        feed_article.refresh_from_db()
        assert feed_article.feed == feed
        assert feed_article.article is None
