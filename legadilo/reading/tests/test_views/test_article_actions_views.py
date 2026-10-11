# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from http import HTTPStatus

import pytest
from django.urls import reverse

from legadilo.conftest import assert_redirected_to_login_page
from legadilo.reading import constants
from legadilo.reading.tests.factories import (
    ArticleFactory,
    ArticlesGroupFactory,
    ReadingListFactory,
)


@pytest.mark.django_db
class TestUpdateArticleView:
    @pytest.fixture(autouse=True)
    def _setup_data(self, user):
        self.reading_list = ReadingListFactory(user=user)
        self.article = ArticleFactory(read_at=None, user=user)
        self.other_article = ArticleFactory(read_at=None, user=user)
        self.mark_as_read_url = reverse(
            "reading:update_article",
            kwargs={
                "article_id": self.article.id,
                "update_action": constants.UpdateArticleActions.MARK_AS_READ.name,
            },
        )
        self.mark_as_favorite_url = reverse(
            "reading:update_article",
            kwargs={
                "article_id": self.article.id,
                "update_action": constants.UpdateArticleActions.MARK_AS_FAVORITE.name,
            },
        )

    def test_cannot_access_if_not_logged_in(self, client):
        response = client.post(self.mark_as_read_url)

        assert_redirected_to_login_page(response)

    def test_cannot_update_article_as_other_user(self, logged_in_other_user_sync_client):
        response = logged_in_other_user_sync_client.post(self.mark_as_read_url)

        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_update_article_view(self, logged_in_sync_client, django_assert_num_queries):
        with django_assert_num_queries(17):
            response = logged_in_sync_client.post(
                self.mark_as_read_url,
                data={"displayed_reading_list_id": str(self.reading_list.id)},
                HTTP_REFERER="http://testserver/reading/",
            )

        assert response.status_code == HTTPStatus.OK
        assert response.template_name == "reading/update_article_action.html"
        assert response.context_data["articles"] == [self.article]
        assert response.context_data["reading_lists"] == [self.reading_list]
        assert response.context_data["count_unread_articles_of_reading_lists"] == {
            self.reading_list.slug: 1
        }
        assert response.context_data["displayed_reading_list"] == self.reading_list
        assert response.context_data["js_cfg"] == {
            "is_reading_on_scroll_enabled": False,
            "auto_refresh_interval": 0,
        }
        assert response["HX-Reswap"] == "none show:none"
        assert "HX-Retarget" not in response.headers
        self.article.refresh_from_db()
        assert self.article.is_read
        assert b"<article" in response.content

    def test_update_article_view_with_htmx_mark_for_later_reading_list_dont_include_for_later(
        self, user, logged_in_sync_client, django_assert_num_queries
    ):
        reading_list_hide_for_later = ReadingListFactory(
            user=user, for_later_status=constants.ForLaterStatus.ONLY_NOT_FOR_LATER
        )

        with django_assert_num_queries(17):
            response = logged_in_sync_client.post(
                reverse(
                    "reading:update_article",
                    kwargs={
                        "article_id": self.article.id,
                        "update_action": constants.UpdateArticleActions.MARK_AS_FOR_LATER.name,
                    },
                ),
                data={"displayed_reading_list_id": str(reading_list_hide_for_later.id)},
                HTTP_REFERER="http://testserver/reading/",
            )

        assert response.status_code == HTTPStatus.OK
        assert response.template_name == "reading/update_article_action.html"
        assert response.context_data["articles"] == [self.article]
        assert response.context_data["delete_article_card"]
        assert response["HX-Reswap"] == "delete swap:1s"
        assert response["HX-Retarget"] == f"#article-card-{self.article.id}"
        self.article.refresh_from_db()
        assert self.article.is_for_later
        assert b"<article" not in response.content

    def test_update_article_view_with_htmx_mark_not_for_later_reading_list_include_only_for_later(
        self, user, logged_in_sync_client, django_assert_num_queries
    ):
        reading_list_hide_for_later = ReadingListFactory(
            user=user, for_later_status=constants.ForLaterStatus.ONLY_FOR_LATER
        )

        with django_assert_num_queries(17):
            response = logged_in_sync_client.post(
                reverse(
                    "reading:update_article",
                    kwargs={
                        "article_id": self.article.id,
                        "update_action": constants.UpdateArticleActions.UNMARK_AS_FOR_LATER.name,
                    },
                ),
                data={"displayed_reading_list_id": str(reading_list_hide_for_later.id)},
                HTTP_REFERER="http://testserver/reading/",
            )

        assert response.status_code == HTTPStatus.OK
        assert response.template_name == "reading/update_article_action.html"
        assert response.context_data["articles"] == [self.article]
        assert response.context_data["delete_article_card"]
        assert response["HX-Reswap"] == "delete swap:1s"
        assert response["HX-Retarget"] == f"#article-card-{self.article.id}"
        self.article.refresh_from_db()
        assert not self.article.is_for_later
        assert b"<article" not in response.content

    def test_update_article_view_with_htmx_mark_for_later_reading_list_include_all(
        self, user, logged_in_sync_client, django_assert_num_queries
    ):
        with django_assert_num_queries(17):
            response = logged_in_sync_client.post(
                reverse(
                    "reading:update_article",
                    kwargs={
                        "article_id": self.article.id,
                        "update_action": constants.UpdateArticleActions.MARK_AS_FOR_LATER.name,
                    },
                ),
                data={"displayed_reading_list_id": str(self.reading_list.id)},
                HTTP_REFERER="http://testserver/reading/",
            )

        assert response.status_code == HTTPStatus.OK
        assert response.template_name == "reading/update_article_action.html"
        assert response.context_data["articles"] == [self.article]
        assert not response.context_data["delete_article_card"]
        assert response["HX-Reswap"] == "none show:none"
        assert "HX-Retarget" not in response.headers
        self.article.refresh_from_db()
        assert self.article.is_for_later
        assert b"<article" in response.content

    def test_update_article_view_for_article_details_read_status_action(
        self, logged_in_sync_client, django_assert_num_queries
    ):
        with django_assert_num_queries(11):
            response = logged_in_sync_client.post(
                self.mark_as_read_url,
                data={"for_article_details": "True"},
                HTTP_REFERER="http://example.com/reading/",
            )

        assert response.status_code == HTTPStatus.OK
        assert response["HX-Redirect"] == reverse("reading:default_reading_list")
        assert response["HX-Push-Url"] == "true"

    def test_update_article_view_for_article_details_read_and_go_next_status_action_no_next(
        self, logged_in_sync_client, django_assert_num_queries
    ):
        with django_assert_num_queries(11):
            response = logged_in_sync_client.post(
                self.mark_as_read_url,
                data={"for_article_details": "True", "read_and_go_to_next": ""},
                HTTP_REFERER="http://example.com/reading/",
            )

        assert response.status_code == HTTPStatus.OK
        assert response["HX-Redirect"] == reverse("reading:default_reading_list")
        assert response["HX-Push-Url"] == "true"

    def test_update_article_view_for_article_details_read_and_go_next_status_action(
        self, user, logged_in_sync_client, django_assert_num_queries
    ):
        group = ArticlesGroupFactory(user=user)
        self.article.group = group
        self.article.save()
        next_article = ArticleFactory(user=user, group=group, group_order=2)

        with django_assert_num_queries(12):
            response = logged_in_sync_client.post(
                self.mark_as_read_url,
                data={"for_article_details": "True", "read_and_go_to_next": ""},
                HTTP_REFERER="http://example.com/reading/",
            )

        next_article_url = reverse(
            "reading:article_details",
            kwargs={"article_id": next_article.id, "article_slug": next_article.slug},
        )
        assert response.status_code == HTTPStatus.OK
        assert response["HX-Redirect"] == f"{next_article_url}?from_url=%2Freading%2F"
        assert response["HX-Push-Url"] == "true"

    def test_update_article_view_for_article_details_favorite_status_action(
        self, logged_in_sync_client, django_assert_num_queries
    ):
        with django_assert_num_queries(11):
            response = logged_in_sync_client.post(
                self.mark_as_favorite_url,
                data={"for_article_details": "True"},
                HTTP_REFERER="http://testserver/reading/articles/1",
            )

        assert response.status_code == HTTPStatus.OK
        assert response.template_name == "reading/update_article_details_actions.html"
        assert response.headers["HX-Reswap"] == "none show:none"


@pytest.mark.django_db
class TestMarkArticlesAsReadInBulkView:
    @pytest.fixture(autouse=True)
    def _setup_data(self, user):
        self.url = reverse("reading:mark_articles_as_read_in_bulk")
        self.article = ArticleFactory(user=user, read_at=None)
        self.reading_list = ReadingListFactory(user=user)

    def test_with_no_article_ids(self, logged_in_sync_client):
        response = logged_in_sync_client.post(self.url)

        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_with_empty_article_ids(self, logged_in_sync_client):
        response = logged_in_sync_client.post(self.url, {"article_ids": ""})

        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_with_invalid_article_ids(self, logged_in_sync_client):
        response = logged_in_sync_client.post(self.url, {"article_ids": "toto"})

        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_mark_one_article_as_read(self, logged_in_sync_client, django_assert_num_queries):
        with django_assert_num_queries(17):
            response = logged_in_sync_client.post(
                self.url,
                {
                    "article_ids": self.article.id,
                    "displayed_reading_list_id": str(self.reading_list.id),
                },
            )

        assert response.status_code == HTTPStatus.OK
        assert response.template_name == "reading/update_article_action.html"
        assert response.context_data["articles"] == [self.article]
        assert response.context_data["reading_lists"] == [self.reading_list]
        assert response.context_data["count_unread_articles_of_reading_lists"] == {
            self.reading_list.slug: 0
        }
        assert response.context_data["displayed_reading_list"] == self.reading_list
        assert response.context_data["js_cfg"] == {
            "is_reading_on_scroll_enabled": False,
            "auto_refresh_interval": 0,
        }
        assert "HX-Reswap" not in response.headers
        assert "HX-Retarget" not in response.headers
        self.article.refresh_from_db()
        assert self.article.is_read
        assert b"<article" in response.content

    def test_mark_multiple_articles_as_read(
        self, logged_in_sync_client, django_assert_num_queries, user, other_user
    ):
        other_article = ArticleFactory(user=user, read_at=None)
        article_other_user = ArticleFactory(user=other_user, read_at=None)

        with django_assert_num_queries(17):
            response = logged_in_sync_client.post(
                self.url,
                {
                    "article_ids": f"{self.article.id},{other_article.id},{article_other_user.id}",
                    "displayed_reading_list_id": self.reading_list.id,
                },
            )

        assert response.status_code == HTTPStatus.OK
        assert response.template_name == "reading/update_article_action.html"
        assert response.context_data["articles"] == [self.article, other_article]
        assert response.context_data["reading_lists"] == [self.reading_list]
        assert response.context_data["count_unread_articles_of_reading_lists"] == {
            self.reading_list.slug: 0
        }
        assert response.context_data["displayed_reading_list"] == self.reading_list
        assert response.context_data["js_cfg"] == {
            "is_reading_on_scroll_enabled": False,
            "auto_refresh_interval": 0,
        }
        assert "HX-Reswap" not in response.headers
        assert "HX-Retarget" not in response.headers
        self.article.refresh_from_db()
        assert self.article.is_read
        other_article.refresh_from_db()
        assert other_article.is_read
        article_other_user.refresh_from_db()
        assert not article_other_user.is_read
