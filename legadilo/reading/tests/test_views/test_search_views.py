# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from http import HTTPStatus
from urllib.parse import urlencode

import pytest
from django.http import QueryDict
from django.urls import reverse

from legadilo.conftest import assert_redirected_to_login_page
from legadilo.core.utils.testing import AnyOfType, dict_to_query_dict
from legadilo.core.utils.time_utils import utcdt
from legadilo.feeds.models import Feed
from legadilo.feeds.tests.factories import FeedFactory
from legadilo.reading import constants
from legadilo.reading.tests.factories import ArticleFactory, TagFactory
from legadilo.reading.views.search_views import SearchForm


class TestSearchForm:
    def test_without_data(self):
        form = SearchForm(
            QueryDict(),
            tags_to_include_choices=[],
            tags_to_exclude_choices=[],
            feeds_qs=Feed.objects.none(),
        )

        assert form.is_valid()

    def test_with_only_q(self):
        form = SearchForm(
            dict_to_query_dict({"q": "Claudius"}),
            tags_to_include_choices=[],
            tags_to_exclude_choices=[],
            feeds_qs=Feed.objects.none(),
        )

        assert form.is_valid()
        assert form.cleaned_data == {
            "q": "Claudius",
            "search_type": constants.ArticleSearchType.PLAIN,
            "order": constants.ArticleSearchOrderBy.RANK_DESC,
            "read_status": constants.ReadStatus.ALL,
            "favorite_status": constants.FavoriteStatus.ALL,
            "for_later_status": constants.ForLaterStatus.ALL,
            "articles_max_age_value": None,
            "articles_max_age_unit": constants.ArticlesMaxAgeUnit.UNSET,
            "articles_reading_time": None,
            "articles_reading_time_operator": constants.ArticlesReadingTimeOperator.UNSET,
            "include_tag_operator": constants.ReadingListTagOperator.ALL,
            "tags_to_include": [],
            "exclude_tag_operator": constants.ReadingListTagOperator.ALL,
            "tags_to_exclude": [],
            "external_tags_to_include": [],
            "linked_with_feeds": AnyOfType(Feed.objects.none()),
        }

    def test_advanced_values_set_unit_and_operator_unset(self):
        form = SearchForm(
            dict_to_query_dict({
                "q": "Claudius",
                "articles_max_age_value": 12,
                "articles_reading_time": 12,
            }),
            tags_to_include_choices=[],
            tags_to_exclude_choices=[],
            feeds_qs=Feed.objects.none(),
        )

        assert not form.is_valid()
        assert form.errors == {
            "__all__": [
                "You must set the max age unit when searching by max age.",
                "You must supply a reading time operator when searching by reading time.",
            ]
        }

    def test_advanced_values_unset_unit_and_operator_set(self):
        form = SearchForm(
            dict_to_query_dict({
                "q": "Claudius",
                "articles_max_age_unit": constants.ArticlesMaxAgeUnit.WEEKS.value,
                "articles_reading_time_operator": constants.ArticlesReadingTimeOperator.LESS_THAN.value,  # ruff:ignore[line-too-long]
            }),
            tags_to_include_choices=[],
            tags_to_exclude_choices=[],
            feeds_qs=Feed.objects.none(),
        )

        assert not form.is_valid()
        assert form.errors == {
            "__all__": [
                "You must supply a max age value when searching by max age.",
                "You must supply a reading time when searching by reading time.",
            ]
        }

    def test_filled(self):
        form = SearchForm(
            dict_to_query_dict({
                "q": "Claudius",
                "search_type": constants.ArticleSearchType.PHRASE,
                "order": constants.ArticleSearchOrderBy.READ_AT_ASC,
                "read_status": constants.ReadStatus.ONLY_READ.value,
                "favorite_status": constants.FavoriteStatus.ONLY_FAVORITE.value,
                "for_later_status": constants.ForLaterStatus.ONLY_FOR_LATER.value,
                "articles_max_age_value": 12,
                "articles_max_age_unit": constants.ArticlesMaxAgeUnit.WEEKS.value,
                "articles_reading_time": 12,
                "articles_reading_time_operator": constants.ArticlesReadingTimeOperator.LESS_THAN.value,  # ruff:ignore[line-too-long]
                "include_tag_operator": constants.ReadingListTagOperator.ALL.value,
                "tags_to_include": ["some-tag"],
                "exclude_tag_operator": constants.ReadingListTagOperator.ANY.value,
                "tags_to_exclude": ["other-tag"],
                "external_tags_to_include": ["Some word"],
                "linked_with_feeds": [],
            }),
            tags_to_include_choices=[("some-tag", "Some tag"), ("other-tag", "Other tag")],
            tags_to_exclude_choices=[("some-tag", "Some tag"), ("other-tag", "Other tag")],
            feeds_qs=Feed.objects.none(),
        )

        assert form.is_valid()
        assert form.cleaned_data == {
            "q": "Claudius",
            "search_type": constants.ArticleSearchType.PHRASE,
            "order": constants.ArticleSearchOrderBy.READ_AT_ASC,
            "read_status": constants.ReadStatus.ONLY_READ,
            "favorite_status": constants.FavoriteStatus.ONLY_FAVORITE,
            "for_later_status": constants.ForLaterStatus.ONLY_FOR_LATER,
            "articles_max_age_value": 12,
            "articles_max_age_unit": constants.ArticlesMaxAgeUnit.WEEKS,
            "articles_reading_time": 12,
            "articles_reading_time_operator": constants.ArticlesReadingTimeOperator.LESS_THAN,
            "include_tag_operator": constants.ReadingListTagOperator.ALL,
            "tags_to_include": ["some-tag"],
            "exclude_tag_operator": constants.ReadingListTagOperator.ANY,
            "tags_to_exclude": ["other-tag"],
            "external_tags_to_include": ["Some word"],
            "linked_with_feeds": AnyOfType(Feed.objects.none()),
        }


@pytest.mark.django_db
class TestSearchView:
    @pytest.fixture(autouse=True)
    def _setup_data(self):
        self.url = reverse("reading:search")

    def test_not_connected(self, client):
        response = client.get(self.url)

        assert_redirected_to_login_page(response)

    def test_search(self, user, logged_in_sync_client):
        article = ArticleFactory(title="Claudius", user=user)
        ArticleFactory(user=user)

        response = logged_in_sync_client.get(self.url, data={"q": "Claudius"})

        assert response.status_code == HTTPStatus.OK
        assert response.template_name == "reading/search.html"
        assert response.context_data["search_form"].is_valid()
        assert response.context_data["articles"] == [article]
        assert response.context_data["total_results"] == 1

    def test_search_with_accents(self, user, logged_in_sync_client):
        article = ArticleFactory(title="Poésie", user=user)
        ArticleFactory(user=user)

        response = logged_in_sync_client.get(self.url, data={"q": "Poésie"})

        assert response.status_code == HTTPStatus.OK
        assert response.template_name == "reading/search.html"
        assert response.context_data["search_form"].is_valid()
        assert response.context_data["articles"] == [article]
        assert response.context_data["total_results"] == 1

    def test_search_with_url(self, user, logged_in_sync_client):
        article_url = "https://example.com/articles/1.html"
        article = ArticleFactory(title="Claudius", user=user, url=article_url)

        response = logged_in_sync_client.get(self.url, data={"q": article_url})

        assert response.status_code == HTTPStatus.OK
        assert response.template_name == "reading/search.html"
        assert response.context_data["search_form"].is_valid()
        assert response.context_data["search_form"].data == {
            "q": ["https://example.com/articles/1.html"],
            "search_type": [constants.ArticleSearchType.URL],
        }
        assert response.context_data["articles"] == [article]

    def test_search_with_tags(self, user, logged_in_sync_client):
        ArticleFactory(user=user, title="Claudius")
        tag_to_include = TagFactory(user=user)
        tag_to_exclude = TagFactory(user=user)
        article_with_tag_to_include = ArticleFactory(user=user, title="Claudius")
        article_with_tag_to_include.tags.add(tag_to_include)
        article_with_tag_to_exclude = ArticleFactory(user=user, title="Claudius")
        article_with_tag_to_exclude.tags.add(tag_to_exclude)

        response = logged_in_sync_client.get(
            self.url,
            data={
                "q": "Claudius",
                "tags_to_include": [tag_to_include.slug],
                "tags_to_exclude": [tag_to_exclude.slug],
            },
        )

        assert response.status_code == HTTPStatus.OK
        assert response.template_name == "reading/search.html"
        assert response.context_data["search_form"].is_valid()
        assert response.context_data["articles"] == [article_with_tag_to_include]
        assert response.context_data["total_results"] == 1

    def test_search_with_external_tags(self, user, logged_in_sync_client):
        article = ArticleFactory(user=user, external_tags=["poetry"])

        response = logged_in_sync_client.get(
            self.url, data={"external_tags_to_include": ["Poetry"]}
        )

        assert response.status_code == HTTPStatus.OK
        assert response.template_name == "reading/search.html"
        assert response.context_data["search_form"].is_valid()
        assert response.context_data["articles"] == [article]
        assert response.context_data["total_results"] == 1

    def test_search_with_feeds(self, user, logged_in_sync_client):
        feed = FeedFactory(user=user)
        feed_article = ArticleFactory(user=user)
        feed.articles.add(feed_article)

        response = logged_in_sync_client.get(self.url, data={"linked_with_feeds": [feed.id]})

        assert response.status_code == HTTPStatus.OK
        assert response.template_name == "reading/search.html"
        assert response.context_data["search_form"].is_valid()
        assert response.context_data["articles"] == [feed_article]
        assert response.context_data["total_results"] == 1

    def test_search_with_order(self, user, logged_in_sync_client):
        oldest_article = ArticleFactory(user=user, title="Claudius", published_at=utcdt(2024, 6, 1))
        newest_article = ArticleFactory(
            user=user, title="Claudius", published_at=utcdt(2024, 6, 30)
        )

        response_asc = logged_in_sync_client.get(
            self.url,
            data={"q": "Claudius", "order": constants.ArticleSearchOrderBy.ARTICLE_DATE_ASC},
        )
        response_desc = logged_in_sync_client.get(
            self.url,
            data={"q": "Claudius", "order": constants.ArticleSearchOrderBy.ARTICLE_DATE_DESC},
        )

        assert response_asc.status_code == HTTPStatus.OK
        assert response_asc.context_data["articles"] == [oldest_article, newest_article]
        assert response_desc.status_code == HTTPStatus.OK
        assert response_desc.context_data["articles"] == [newest_article, oldest_article]

    def test_update_search(self, user, logged_in_sync_client):
        ArticleFactory(user=user, title="Claudius")
        tag_to_include = TagFactory(user=user)
        tag_to_exclude = TagFactory(user=user)
        article_with_tag_to_include = ArticleFactory(user=user, title="Claudius")
        article_with_tag_to_include.tags.add(tag_to_include)
        article_with_tag_to_exclude = ArticleFactory(user=user, title="Claudius")
        article_with_tag_to_exclude.tags.add(tag_to_exclude)
        get_data = urlencode(
            {
                "q": "Claudius",
                "tags_to_include": [tag_to_include.slug],
                "tags_to_exclude": [tag_to_exclude.slug],
            },
            doseq=True,
        )

        response = logged_in_sync_client.post(
            f"{self.url}?{get_data}",
            data={
                "update_action": constants.UpdateArticleActions.MARK_AS_READ.value,
                "add_tags": ["New tag"],
            },
        )

        article_with_tag_to_include.refresh_from_db()
        assert article_with_tag_to_include.is_read
        assert list(
            article_with_tag_to_include.tags.order_by("slug").values_list("slug", flat=True)
        ) == [
            "new-tag",
            tag_to_include.slug,
        ]
        assert response.status_code == HTTPStatus.OK
        assert response.template_name == "reading/search.html"
        assert response.context_data["search_form"].is_valid()
        assert response.context_data["articles"] == [article_with_tag_to_include]
        assert response.context_data["total_results"] == 1
