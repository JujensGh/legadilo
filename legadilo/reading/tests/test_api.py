# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from http import HTTPStatus
from typing import Any

import pytest
import time_machine
from django.urls import reverse

from legadilo.core.utils.testing import serialize_for_snapshot
from legadilo.core.utils.time_utils import utcdt, utcnow
from legadilo.reading import constants
from legadilo.reading.models import Article, ArticlesGroup
from legadilo.reading.tests.factories import (
    ArticleDataFactory,
    ArticleFactory,
    ArticlesGroupFactory,
    CommentFactory,
    FetchArticleResultFactory,
    ReadingListFactory,
    TagFactory,
)
from legadilo.reading.tests.fixtures import get_article_fixture_content


def _prepare_article_for_serialization(data: dict[str, Any], article: Article) -> dict[str, Any]:
    data = data.copy()
    assert data["id"] == article.id
    assert data["title"] == article.title
    assert data["slug"] == article.slug
    assert data["external_article_id"] == article.external_article_id
    assert data["url"] == article.url
    assert data["details_url"] == f"http://testserver/reading/articles/{article.id}-{article.slug}/"

    data["id"] = 1
    data["title"] = "Article title"
    data["slug"] = "article-slug"
    data["external_article_id"] = "external-article-id"
    data["url"] = "https://example.com/articles/article.html"
    data["details_url"] = "http://testserver/reading/articles/1-article-slug/"

    return data


@pytest.mark.django_db
class TestCreateArticleView:
    @pytest.fixture(autouse=True)
    def _setup_data(self):
        self.url = reverse("api-1.0.0:create_article")
        self.article_url = "https://example.com/articles/legadilo.html"

    def test_not_logged_in(self, client):
        response = client.post(self.url)

        assert response.status_code == HTTPStatus.UNAUTHORIZED

    def test_create_article_empty_payload(self, user, logged_in_sync_client):
        response = logged_in_sync_client.post(self.url, {}, content_type="application/json")

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert response.json() == {
            "detail": [
                {"type": "missing", "loc": ["body", "payload", "url"], "msg": "Field required"}
            ]
        }

    def test_create_article_invalid_data(self, user, logged_in_sync_client):
        response = logged_in_sync_client.post(
            self.url,
            {"url": self.article_url, "content": "Some content"},
            content_type="application/json",
        )

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert response.json() == {
            "detail": [
                {
                    "ctx": {"error": "Title is mandatory when content is provided."},
                    "loc": ["body", "payload"],
                    "msg": "Value error, Title is mandatory when content is provided.",
                    "type": "value_error",
                }
            ]
        }

    def test_create_article_with_title_and_no_content(self, user, logged_in_sync_client):
        response = logged_in_sync_client.post(
            self.url,
            {"url": self.article_url, "title": "Some title"},
            content_type="application/json",
        )

        assert response.status_code == HTTPStatus.CREATED
        assert Article.objects.count() == 1
        article = Article.objects.get()
        assert article.url == self.article_url

    def test_url_from_instance(self, logged_in_sync_client):
        response = logged_in_sync_client.post(
            self.url, {"url": "https://testserver/some/url"}, content_type="application/json"
        )

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert (
            response.json()
            == {
                "detail": [
                    {
                        "ctx": {"error": "https://testserver/some/url is not a valid url"},
                        "loc": ["body", "payload", "url"],
                        "msg": "Value error, https://testserver/some/url is not a valid url",
                        "type": "value_error",
                    }
                ]
            }
            != {"detail": "Invalid URL: https://example.com/"}
        )

    def test_create_article_from_url_only_http_failure(self, logged_in_sync_client, mocker):
        mocked_fetch_article_data = mocker.patch(
            "legadilo.reading.api.fetch_article_data",
            return_value=FetchArticleResultFactory(error_message="ArticleTooBigError"),
        )

        response = logged_in_sync_client.post(
            self.url, {"url": self.article_url}, content_type="application/json"
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.json() == {"detail": "Failed to fetch article data: ArticleTooBigError"}
        assert Article.objects.count() == 0
        mocked_fetch_article_data.assert_called_once_with(self.article_url)

    def test_create_article_from_url_only(
        self, django_assert_num_queries, logged_in_sync_client, mocker, snapshot
    ):
        mocked_fetch_article_data = mocker.patch(
            "legadilo.reading.api.fetch_article_data",
            return_value=FetchArticleResultFactory(
                article_data=ArticleDataFactory(url=self.article_url, source_title="Source 0")
            ),
        )

        with django_assert_num_queries(18):
            response = logged_in_sync_client.post(
                self.url, {"url": self.article_url}, content_type="application/json"
            )

        assert response.status_code == HTTPStatus.CREATED
        assert Article.objects.count() == 1
        article = Article.objects.get()
        assert article.url == self.article_url
        mocked_fetch_article_data.assert_called_once_with(self.article_url)
        assert (
            serialize_for_snapshot(_prepare_article_for_serialization(response.json(), article))
            == snapshot
        )

    def test_create_article_with_tags(
        self, django_assert_num_queries, logged_in_sync_client, mocker, snapshot
    ):
        mocked_fetch_article_data = mocker.patch(
            "legadilo.reading.api.fetch_article_data",
            return_value=FetchArticleResultFactory(
                article_data=ArticleDataFactory(url=self.article_url, source_title="Source 0")
            ),
        )

        with django_assert_num_queries(22):
            response = logged_in_sync_client.post(
                self.url,
                {"url": self.article_url, "tags": ["Some tag"]},
                content_type="application/json",
            )

        assert response.status_code == HTTPStatus.CREATED
        assert Article.objects.count() == 1
        article = Article.objects.get()
        assert article.url == self.article_url
        assert list(article.tags.all().values_list("title", flat=True)) == ["Some tag"]
        mocked_fetch_article_data.assert_called_once_with(self.article_url)
        assert (
            serialize_for_snapshot(_prepare_article_for_serialization(response.json(), article))
            == snapshot
        )

    def test_create_article_from_data(
        self, django_assert_num_queries, logged_in_sync_client, mocker, snapshot
    ):
        mocked_fetch_article_data = mocker.patch("legadilo.reading.api.fetch_article_data")

        with django_assert_num_queries(18):
            response = logged_in_sync_client.post(
                self.url,
                {
                    "url": self.article_url,
                    "content": get_article_fixture_content("sample_blog_article.html"),
                    "title": "My article",
                    "language": "en",
                },
                content_type="application/json",
            )

        assert response.status_code == HTTPStatus.CREATED
        assert Article.objects.count() == 1
        article = Article.objects.get()
        assert article.url == "https://www.example.com/posts/en/1-super-article/"
        assert article.table_of_content == []
        assert not mocked_fetch_article_data.called
        assert article.content_type == "text/html"
        assert (
            serialize_for_snapshot(_prepare_article_for_serialization(response.json(), article))
            == snapshot
        )

    def test_create_article_from_data_without_content_extraction(
        self, logged_in_sync_client, snapshot
    ):
        response = logged_in_sync_client.post(
            self.url,
            {
                "url": self.article_url,
                "content": "<p>My content</p>",
                "title": "My article",
                "must_extract_content": False,
            },
            content_type="application/json",
        )

        assert response.status_code == HTTPStatus.CREATED
        assert Article.objects.count() == 1
        article = Article.objects.get()
        assert article.url == self.article_url
        assert article.content_type == "text/html"
        assert (
            serialize_for_snapshot(_prepare_article_for_serialization(response.json(), article))
            == snapshot
        )

    def test_create_article_from_data_with_content_extraction_and_partial_payload(
        self, logged_in_sync_client
    ):
        response = logged_in_sync_client.post(
            self.url,
            {
                "url": self.article_url,
                "content": "<p>My content</p>",
                "title": "My article",
                "must_extract_content": True,
            },
            content_type="application/json",
        )

        assert response.status_code == HTTPStatus.CREATED
        assert Article.objects.count() == 1
        article = Article.objects.get()
        assert article.url == self.article_url
        assert article.content_type == "text/html"
        assert not article.content

    def test_create_article_from_text_data(
        self, django_assert_num_queries, logged_in_sync_client, mocker, snapshot
    ):
        mocked_fetch_article_data = mocker.patch("legadilo.reading.api.fetch_article_data")

        with django_assert_num_queries(18):
            response = logged_in_sync_client.post(
                self.url,
                {
                    "url": self.article_url,
                    "content": "Just some text",
                    "content_type": "text/plain",
                    "title": "My article",
                },
                content_type="application/json",
            )

        assert response.status_code == HTTPStatus.CREATED
        assert Article.objects.count() == 1
        article = Article.objects.get()
        assert article.url == self.article_url
        assert article.table_of_content == []
        assert not mocked_fetch_article_data.called
        assert article.content_type == "text/plain"
        data = response.json()
        # Keep other fields since they shouldn't change for text data.
        data["id"] = 1
        data["details_url"] = "http://testserver/reading/articles/1-my-article/"
        assert serialize_for_snapshot(data) == snapshot

    def test_try_to_create_existing_article(
        self, user, django_assert_num_queries, logged_in_sync_client, mocker
    ):
        existing_article = ArticleFactory(
            user=user, title="Existing", reading_time=14, url=self.article_url, read_at=utcnow()
        )
        mocker.patch(
            "legadilo.reading.api.fetch_article_data",
            return_value=FetchArticleResultFactory(
                article_data=ArticleDataFactory(
                    title="Fetched article",
                    url=self.article_url,
                    content="Blabla for reading time " * 50,
                )
            ),
        )

        with django_assert_num_queries(18):
            response = logged_in_sync_client.post(
                self.url, {"url": self.article_url}, content_type="application/json"
            )

        assert response.status_code == HTTPStatus.OK
        assert Article.objects.count() == 1
        article = Article.objects.get()
        assert article.url == self.article_url
        assert article.table_of_content == []
        assert article.title == existing_article.title
        assert article.slug == existing_article.slug
        assert article.reading_time == existing_article.reading_time
        assert article.read_at == existing_article.read_at

    @pytest.mark.parametrize(
        ("group_id_attr", "nb_requests"),
        [
            pytest.param("id", 23, id="group_id"),
            pytest.param("slug", 25, id="group_slug"),
        ],
    )
    def test_create_link_with_group(
        self, user, django_assert_num_queries, logged_in_sync_client, group_id_attr, nb_requests
    ):
        group = ArticlesGroupFactory(user=user, title="Some group")

        with django_assert_num_queries(nb_requests):
            response = logged_in_sync_client.post(
                self.url,
                {
                    "url": "https://example.com/some-link",
                    "group_id": getattr(group, group_id_attr),
                    "content": "Just some text",
                    "content_type": "text/plain",
                    "title": "My article",
                },
                content_type="application/json",
            )

        assert response.status_code == HTTPStatus.CREATED
        assert Article.objects.count() == 1
        article = Article.objects.get()
        assert article.url == "https://example.com/some-link"
        assert article.group == group

    def test_create_link_with_new_group(
        self, user, django_assert_num_queries, logged_in_sync_client
    ):
        with django_assert_num_queries(31):
            response = logged_in_sync_client.post(
                self.url,
                {
                    "url": "https://example.com/some-link",
                    "group_id": "Some group",
                    "content": "Just some text",
                    "content_type": "text/plain",
                    "title": "My article",
                },
                content_type="application/json",
            )

        assert response.status_code == HTTPStatus.CREATED
        assert Article.objects.count() == 1
        article = Article.objects.get()
        assert article.url == "https://example.com/some-link"
        assert article.group is not None
        group = ArticlesGroup.objects.get()
        assert group.title == "Some group"

    def test_create_link_with_group_invalid_id(
        self, user, django_assert_num_queries, logged_in_sync_client
    ):
        with django_assert_num_queries(17):
            response = logged_in_sync_client.post(
                self.url,
                {
                    "url": "https://example.com/some-link",
                    "group_id": 1,
                    "content": "Just some text",
                    "content_type": "text/plain",
                    "title": "My article",
                },
                content_type="application/json",
            )

        assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
        assert Article.objects.count() == 0

    def test_create_link_with_empty_group_id(self, user, logged_in_sync_client):
        response = logged_in_sync_client.post(
            self.url,
            {
                "url": "https://example.com/some-link",
                "group_id": "",
                "content": "Just some text",
                "content_type": "text/plain",
                "title": "My article",
            },
            content_type="application/json",
        )

        assert response.status_code == HTTPStatus.CREATED
        assert Article.objects.count() == 1
        article = Article.objects.get()
        assert article.group is None
        assert ArticlesGroup.objects.count() == 0


@pytest.mark.django_db
class TestListArticleView:
    @pytest.fixture(autouse=True)
    def _setup_data(self, user):
        self.article = ArticleFactory(
            user=user,
            published_at=utcdt(2024, 11, 24, 17, 57, 0),
            updated_at=utcdt(2024, 11, 24, 17, 57, 0),
        )
        ArticleFactory(
            user=user,
        )
        self.url = reverse("api-1.0.0:list_articles")

    def test_not_logged_in(self, client):
        response = client.get(self.url)

        assert response.status_code == HTTPStatus.UNAUTHORIZED

    def test_list_other_user(self, logged_in_other_user_sync_client):
        response = logged_in_other_user_sync_client.get(self.url)

        assert response.status_code == HTTPStatus.OK
        assert response.json()["count"] == 0

    def test_list(self, logged_in_sync_client, snapshot):
        response = logged_in_sync_client.get(self.url)

        assert response.status_code == HTTPStatus.OK
        assert response.json()["count"] == 2

    def test_search(self, logged_in_sync_client, snapshot):
        response = logged_in_sync_client.get(
            self.url, {"q": self.article.url, "search_type": constants.ArticleSearchType.URL.value}
        )

        assert response.status_code == HTTPStatus.OK
        assert response.json()["count"] == 1


@pytest.mark.django_db
class TestGetArticleView:
    @pytest.fixture(autouse=True)
    def _setup_data(self, user):
        self.article = ArticleFactory(
            user=user,
            id=1,
            title="Article title",
            url="https://example.com/articles/article.html",
            external_article_id="external-article-id",
            published_at=utcdt(2024, 11, 24, 17, 57, 0),
            updated_at=utcdt(2024, 11, 24, 17, 57, 0),
        )
        self.url = reverse("api-1.0.0:get_article", kwargs={"article_id": self.article.id})

    def test_not_logged_in(self, client):
        response = client.get(self.url)

        assert response.status_code == HTTPStatus.UNAUTHORIZED

    def test_get_other_user(self, logged_in_other_user_sync_client):
        response = logged_in_other_user_sync_client.get(self.url)

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert Article.objects.count() == 1

    def test_get(self, user, logged_in_sync_client, snapshot, django_assert_num_queries):
        tag = TagFactory(user=user, title="Some tag")
        self.article.tags.add(tag)
        with time_machine.travel("2025-07-01"):
            CommentFactory(article=self.article, text="Some comment")

        with django_assert_num_queries(8):
            response = logged_in_sync_client.get(self.url)

        assert response.status_code == HTTPStatus.OK
        assert serialize_for_snapshot(response.json()) == snapshot


@pytest.mark.django_db
class TestUpdateArticleView:
    @pytest.fixture(autouse=True)
    def _setup_data(self, user):
        self.article = ArticleFactory(
            user=user,
            id=1,
            title="Article title",
            url="https://example.com/articles/article.html",
            external_article_id="external-article-id",
            published_at=utcdt(2024, 11, 24, 17, 57, 0),
            updated_at=utcdt(2024, 11, 24, 17, 57, 0),
        )
        self.url = reverse("api-1.0.0:update_article", kwargs={"article_id": self.article.id})

    def test_not_logged_in(self, client):
        response = client.patch(self.url, {}, content_type="application/json")

        assert response.status_code == HTTPStatus.UNAUTHORIZED

    def test_update_other_user(self, logged_in_other_user_sync_client):
        response = logged_in_other_user_sync_client.patch(
            self.url, {}, content_type="application/json"
        )

        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_no_update(self, logged_in_sync_client, django_assert_num_queries, snapshot):
        with django_assert_num_queries(11):
            response = logged_in_sync_client.patch(self.url, {}, content_type="application/json")

        assert response.status_code == HTTPStatus.OK
        assert serialize_for_snapshot(response.json()) == snapshot

    def test_update(self, logged_in_sync_client, django_assert_num_queries, snapshot):
        with django_assert_num_queries(12):
            response = logged_in_sync_client.patch(
                self.url,
                {
                    "title": "<p>New title</p>",
                    "read_at": "2024-11-24 18:00:00Z",
                    "reading_time": 10,
                },
                content_type="application/json",
            )

        self.article.refresh_from_db()
        assert self.article.title == "New title"
        assert self.article.read_at == utcdt(2024, 11, 24, 18)
        assert self.article.reading_time == 10
        assert serialize_for_snapshot(response.json()) == snapshot

    def test_update_tags(self, logged_in_sync_client, user, django_assert_num_queries, snapshot):
        existing_tag = TagFactory(user=user, title="Tag to keep")
        tag_to_delete = TagFactory(user=user, title="Tag to delete")
        self.article.tags.add(existing_tag, tag_to_delete)

        with django_assert_num_queries(19):
            response = logged_in_sync_client.patch(
                self.url,
                {
                    "tags": [existing_tag.slug, "", "<p>New tag</p>"],
                },
                content_type="application/json",
            )

        self.article.refresh_from_db()
        assert list(self.article.article_tags.all().values_list("tag__title", flat=True)) == [
            "New tag",
            "Tag to keep",
        ]
        assert serialize_for_snapshot(response.json()) == snapshot

    @pytest.mark.parametrize(
        ("group_id_attr", "nb_requests"),
        [
            pytest.param("id", 23, id="group_id"),
            pytest.param("slug", 25, id="group_slug"),
        ],
    )
    def test_update_with_group(
        self, logged_in_sync_client, django_assert_num_queries, group_id_attr, nb_requests
    ):
        group = ArticlesGroupFactory(user=self.article.user, title="Some group")

        with django_assert_num_queries(nb_requests):
            response = logged_in_sync_client.patch(
                self.url,
                {
                    "group_id": getattr(group, group_id_attr),
                },
                content_type="application/json",
            )

        assert response.status_code == HTTPStatus.OK
        self.article.refresh_from_db()
        assert self.article.group == group

    def test_update_with_group_invalid_id(self, logged_in_sync_client, django_assert_num_queries):
        response = logged_in_sync_client.patch(
            self.url,
            {
                "group_id": 1,
            },
            content_type="application/json",
        )

        assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT

    def test_update_unlink_from_group(self, logged_in_sync_client, django_assert_num_queries):
        group = ArticlesGroupFactory(user=self.article.user, title="Some group")
        self.article.group = group
        self.article.save()

        with django_assert_num_queries(15):
            response = logged_in_sync_client.patch(
                self.url,
                {
                    "group_id": None,
                },
                content_type="application/json",
            )

        assert response.status_code == HTTPStatus.OK
        self.article.refresh_from_db()
        assert self.article.group is None

    def test_update_with_empty_group_id(self, logged_in_sync_client):
        initial_group_count = ArticlesGroup.objects.count()

        response = logged_in_sync_client.patch(
            self.url,
            {
                "group_id": "",
            },
            content_type="application/json",
        )

        assert response.status_code == HTTPStatus.OK
        self.article.refresh_from_db()
        assert self.article.group is None
        assert ArticlesGroup.objects.count() == initial_group_count


@pytest.mark.django_db
class TestDeleteArticleView:
    @pytest.fixture(autouse=True)
    def _setup_data(self, user):
        self.article = ArticleFactory(user=user)
        self.url = reverse("api-1.0.0:delete_article", kwargs={"article_id": self.article.id})

    def test_not_logged_in(self, client):
        response = client.delete(self.url)

        assert response.status_code == HTTPStatus.UNAUTHORIZED
        assert Article.objects.count() == 1

    def test_delete_other_user(self, logged_in_other_user_sync_client):
        response = logged_in_other_user_sync_client.delete(self.url)

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert Article.objects.count() == 1

    def test_delete(self, logged_in_sync_client):
        response = logged_in_sync_client.delete(self.url)

        assert response.status_code == HTTPStatus.NO_CONTENT
        assert Article.objects.count() == 0


@pytest.mark.django_db
class TestListTagsView:
    @pytest.fixture(autouse=True)
    def _setup_data(self, user):
        self.tag = TagFactory(
            user=user,
            title="Some tag",
        )
        self.url = reverse("api-1.0.0:list_tags")

    def test_not_logged_in(self, client):
        response = client.get(self.url, {}, content_type="application/json")

        assert response.status_code == HTTPStatus.UNAUTHORIZED

    def test_list(
        self, user, other_user, logged_in_sync_client, django_assert_num_queries, snapshot
    ):
        TagFactory(user=other_user, title="Some tag")
        tag_with_sub_tag = TagFactory(user=user, title="With sub tags")
        tag_with_sub_tag.sub_tags.add(self.tag)

        with django_assert_num_queries(8):
            response = logged_in_sync_client.get(self.url)

        assert response.status_code == HTTPStatus.OK
        assert serialize_for_snapshot(response.json()) == snapshot


@pytest.mark.django_db
class TestListArticlesGroup:
    @pytest.fixture(autouse=True)
    def _setup_data(self, user):
        self.group = ArticlesGroupFactory(id=1, user=user, title="Some group", slug="some-group")
        tag = TagFactory(user=user, title="Some tag")
        self.group.tags.add(tag)
        self.url = reverse("api-1.0.0:list_articles_groups")

    def test_not_logged_in(self, client):
        response = client.get(self.url, {}, content_type="application/json")

        assert response.status_code == HTTPStatus.UNAUTHORIZED

    def test_list(self, logged_in_sync_client, django_assert_num_queries, snapshot):
        ArticlesGroupFactory()

        with django_assert_num_queries(8):
            response = logged_in_sync_client.get(self.url)

        assert response.status_code == HTTPStatus.OK
        assert serialize_for_snapshot(response.json()) == snapshot


@pytest.mark.django_db
class TestReadingListsReorderView:
    @pytest.fixture(autouse=True)
    def _setup_data(self, user, other_user):
        self.reading_list = ReadingListFactory(user=user, order=0)
        self.reading_list_other_user = ReadingListFactory(user=other_user, order=10)
        self.url = reverse("api-1.0.0:reorder_reading_lists")

    def test_not_logged_in(self, client):
        response = client.post(self.url, {}, content_type="application/json")

        assert response.status_code == HTTPStatus.UNAUTHORIZED

    def test_reorder(self, logged_in_sync_client):
        response = logged_in_sync_client.post(
            self.url,
            {"order": {self.reading_list.id: 100, self.reading_list_other_user.id: 110, -1: 0}},
            content_type="application/json",
        )

        assert response.status_code == HTTPStatus.NO_CONTENT
        self.reading_list.refresh_from_db()
        self.reading_list_other_user.refresh_from_db()
        assert self.reading_list.order == 100
        assert self.reading_list_other_user.order == 10
