# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from datetime import UTC, datetime
from random import choice
from typing import Any
from unittest.mock import patch

import pytest
import time_machine
from django.db import connection, models

from legadilo.core.utils.testing import serialize_for_snapshot
from legadilo.core.utils.time_utils import utcdt, utcnow
from legadilo.core.utils.validators import TableOfContentTopItem
from legadilo.feeds.tests.factories import FeedArticleFactory, FeedCategoryFactory, FeedFactory
from legadilo.reading import constants
from legadilo.reading.models import (
    Article,
    ArticleFetchError,
    ReadingList,
    ReadingListTag,
)
from legadilo.reading.models.article import (
    ArticleFullTextSearchQuery,
    _build_basic_filters_from_reading_list,
)
from legadilo.reading.services.article_fetching import ArticleData
from legadilo.reading.tests.factories import (
    ArticleDataFactory,
    ArticleFactory,
    ArticlesGroupFactory,
    CommentFactory,
    FetchArticleResultFactory,
    ReadingListFactory,
    TagFactory,
)


@pytest.mark.parametrize(
    ("search_query_kwargs", "expected_filter"),
    [
        pytest.param(
            {"read_status": constants.ReadStatus.ONLY_UNREAD},
            models.Q(is_read=False),
            id="unread_only",
        ),
        pytest.param(
            {"read_status": constants.ReadStatus.ONLY_READ},
            models.Q(is_read=True),
            id="read_only",
        ),
        pytest.param(
            {"favorite_status": constants.FavoriteStatus.ONLY_NON_FAVORITE},
            models.Q(is_favorite=False),
            id="non_favorite_only",
        ),
        pytest.param(
            {"favorite_status": constants.FavoriteStatus.ONLY_FAVORITE},
            models.Q(is_favorite=True),
            id="favorite_only",
        ),
        pytest.param(
            {"for_later_status": constants.ForLaterStatus.ONLY_FOR_LATER},
            models.Q(is_for_later=True),
            id="for_later_only",
        ),
        pytest.param(
            {"for_later_status": constants.ForLaterStatus.ONLY_NOT_FOR_LATER},
            models.Q(is_for_later=False),
            id="not_for_later_only",
        ),
        pytest.param(
            {
                "articles_max_age_unit": constants.ArticlesMaxAgeUnit.HOURS,
                "articles_max_age_value": 1,
            },
            models.Q(published_at__gt=datetime(2024, 3, 19, 20, 8, 0, tzinfo=UTC)),
            id="max_age_hours",
        ),
        pytest.param(
            {
                "articles_max_age_unit": constants.ArticlesMaxAgeUnit.DAYS,
                "articles_max_age_value": 1,
            },
            models.Q(published_at__gt=datetime(2024, 3, 18, 21, 8, 0, tzinfo=UTC)),
            id="max_age_days",
        ),
        pytest.param(
            {
                "articles_max_age_unit": constants.ArticlesMaxAgeUnit.WEEKS,
                "articles_max_age_value": 1,
            },
            models.Q(published_at__gt=datetime(2024, 3, 12, 21, 8, 0, tzinfo=UTC)),
            id="max_age_weeks",
        ),
        pytest.param(
            {
                "articles_max_age_unit": constants.ArticlesMaxAgeUnit.MONTHS,
                "articles_max_age_value": 1,
            },
            models.Q(published_at__gt=datetime(2024, 2, 19, 21, 8, 0, tzinfo=UTC)),
            id="max_age_months",
        ),
        pytest.param(
            {
                "articles_reading_time": 5,
                "articles_reading_time_operator": constants.ArticlesReadingTimeOperator.MORE_THAN,
            },
            models.Q(reading_time__gte=5),
            id="more-than-5-minutes-reading-time",
        ),
        pytest.param(
            {
                "articles_reading_time": 5,
                "articles_reading_time_operator": constants.ArticlesReadingTimeOperator.LESS_THAN,
            },
            models.Q(reading_time__lte=5),
            id="less-than-5-minutes-reading-time",
        ),
        pytest.param(
            {
                "read_status": constants.ReadStatus.ONLY_UNREAD,
                "favorite_status": constants.FavoriteStatus.ONLY_FAVORITE,
            },
            models.Q(is_read=False) & models.Q(is_favorite=True),
            id="simple-combination",
        ),
        pytest.param(
            {
                "read_status": constants.ReadStatus.ONLY_UNREAD,
                "favorite_status": constants.FavoriteStatus.ONLY_FAVORITE,
                "articles_max_age_unit": constants.ArticlesMaxAgeUnit.MONTHS,
                "articles_max_age_value": 1,
                "articles_reading_time_operator": constants.ArticlesReadingTimeOperator.MORE_THAN,
                "articles_reading_time": 5,
            },
            models.Q(is_read=False)
            & models.Q(is_favorite=True)
            & models.Q(
                published_at__gt=datetime(2024, 2, 19, 21, 8, 0, tzinfo=UTC),
            )
            & models.Q(reading_time__gte=5),
            id="full-combination",
        ),
    ],
)
def test_build_filters_from_reading_list(
    user, search_query_kwargs: dict[str, Any], expected_filter: models.Q
):
    search_query = ArticleFullTextSearchQuery(**search_query_kwargs)

    with time_machine.travel("2024-03-19 21:08:00"):
        filters = _build_basic_filters_from_reading_list(search_query)

    assert filters == expected_filter


@pytest.mark.django_db
class TestArticleQuerySet:
    def test_for_user(self, user, other_user):
        article = ArticleFactory(user=user)
        ArticleFactory(user=other_user)

        articles = Article.objects.get_queryset().for_user(user)

        assert list(articles) == [article]

    def test_only_unread(self, user):
        ArticleFactory(user=user, read_at=utcnow())
        unread_article = ArticleFactory(user=user, read_at=None)

        articles = Article.objects.get_queryset().only_unread()

        assert list(articles) == [unread_article]

    def test_for_reading_list_with_tags_basic_include(self, user, django_assert_num_queries):
        reading_list = ReadingListFactory(user=user)
        tag_to_include = TagFactory(user=user)
        other_tag = TagFactory(user=user)
        ReadingListTag.objects.create(
            reading_list=reading_list,
            tag=tag_to_include,
            filter_type=constants.ReadingListTagFilterType.INCLUDE,
        )
        article_to_include_linked_many_tags = ArticleFactory(
            title="Article to include linked many tags",
            user=user,
            published_at=utcdt(2024, 5, 1),
            updated_at=None,
        )
        article_to_include_linked_many_tags.tags.add(tag_to_include, other_tag)
        article_to_include_one_tag = ArticleFactory(
            title="Article to include linked to one tag",
            user=user,
            published_at=utcdt(2024, 5, 2),
            updated_at=None,
        )
        article_to_include_one_tag.tags.add(tag_to_include)
        ArticleFactory(
            title="Article linked to no tag",
            user=user,
            published_at=utcdt(2024, 5, 3),
            updated_at=None,
        )
        article_linked_only_to_other_tag = ArticleFactory(
            title="Article linked to other tag",
            user=user,
            published_at=utcdt(2024, 5, 4),
            updated_at=None,
        )
        article_linked_only_to_other_tag.tags.add(other_tag)

        with django_assert_num_queries(3):
            articles = list(Article.objects.get_articles_of_reading_list(reading_list))

        assert articles == [
            article_to_include_one_tag,
            article_to_include_linked_many_tags,
        ]

    def test_for_reading_list_include_all_tags(self, user, django_assert_num_queries):
        reading_list = ReadingListFactory(
            user=user, include_tag_operator=constants.ReadingListTagOperator.ALL
        )
        tag1 = TagFactory(user=user)
        tag2 = TagFactory(user=user)
        ReadingListTag.objects.create(
            reading_list=reading_list,
            tag=tag1,
            filter_type=constants.ReadingListTagFilterType.INCLUDE,
        )
        ReadingListTag.objects.create(
            reading_list=reading_list,
            tag=tag2,
            filter_type=constants.ReadingListTagFilterType.INCLUDE,
        )
        article_linked_to_all_tags = ArticleFactory(
            user=user,
            published_at=utcdt(2024, 5, 1),
            updated_at=None,
        )
        article_linked_to_all_tags.tags.add(tag1, tag2)
        article_linked_to_one_tag = ArticleFactory(
            user=user,
            published_at=utcdt(2024, 5, 2),
            updated_at=None,
        )
        article_linked_to_one_tag.tags.add(tag1)

        with django_assert_num_queries(3):
            articles = list(Article.objects.get_articles_of_reading_list(reading_list))

        assert list(articles) == [
            article_linked_to_all_tags,
        ]

    def test_for_reading_list_include_any_tags(self, user, django_assert_num_queries):
        reading_list = ReadingListFactory(
            user=user, include_tag_operator=constants.ReadingListTagOperator.ANY
        )
        tag1 = TagFactory(user=user)
        tag2 = TagFactory(user=user)
        ReadingListTag.objects.create(
            reading_list=reading_list,
            tag=tag1,
            filter_type=constants.ReadingListTagFilterType.INCLUDE,
        )
        ReadingListTag.objects.create(
            reading_list=reading_list,
            tag=tag2,
            filter_type=constants.ReadingListTagFilterType.INCLUDE,
        )
        article_linked_to_all_tags = ArticleFactory(
            user=user,
            published_at=utcdt(2024, 5, 1),
            updated_at=None,
        )
        article_linked_to_all_tags.tags.add(tag1, tag2)
        article_to_include_one_tag = ArticleFactory(
            user=user,
            published_at=utcdt(2024, 5, 2),
            updated_at=None,
        )
        article_to_include_one_tag.tags.add(tag1)
        ArticleFactory(user=user, title="Article linked to no tag")

        with django_assert_num_queries(3):
            articles = list(Article.objects.get_articles_of_reading_list(reading_list))

        assert articles == [
            article_to_include_one_tag,
            article_linked_to_all_tags,
        ]

    def test_for_reading_list_with_tags_basic_exclude(self, user, django_assert_num_queries):
        reading_list = ReadingListFactory(user=user)
        tag_to_exclude = TagFactory(user=user)
        other_tag = TagFactory(user=user)
        ReadingListTag.objects.create(
            reading_list=reading_list,
            tag=tag_to_exclude,
            filter_type=constants.ReadingListTagFilterType.EXCLUDE,
        )
        article_to_exclude_linked_many_tags = ArticleFactory(
            title="Article to exclude linked to many tags",
            user=user,
            published_at=utcdt(2024, 5, 1),
            updated_at=None,
        )
        article_to_exclude_linked_many_tags.tags.add(tag_to_exclude, other_tag)
        article_to_exclude_one_tag = ArticleFactory(
            title="Article to exclude linked to one tag",
            user=user,
            published_at=utcdt(2024, 5, 2),
            updated_at=None,
        )
        article_to_exclude_one_tag.tags.add(tag_to_exclude)
        article_linked_only_to_other_tag = ArticleFactory(
            title="Article linked to only one other tag",
            user=user,
            published_at=utcdt(2024, 5, 3),
            updated_at=None,
        )
        article_linked_only_to_other_tag.tags.add(other_tag)
        article_linked_to_no_tag = ArticleFactory(
            title="Article linked to no tag",
            user=user,
            published_at=utcdt(2024, 5, 4),
            updated_at=None,
        )

        with django_assert_num_queries(3):
            articles = list(Article.objects.get_articles_of_reading_list(reading_list))

        assert articles == [article_linked_to_no_tag, article_linked_only_to_other_tag]

    def test_for_reading_list_exclude_any_tags(self, user, django_assert_num_queries):
        reading_list = ReadingListFactory(
            user=user, exclude_tag_operator=constants.ReadingListTagOperator.ANY
        )
        tag1 = TagFactory(user=user)
        tag2 = TagFactory(user=user)
        other_tag = TagFactory(user=user)
        ReadingListTag.objects.create(
            reading_list=reading_list,
            tag=tag1,
            filter_type=constants.ReadingListTagFilterType.EXCLUDE,
        )
        ReadingListTag.objects.create(
            reading_list=reading_list,
            tag=tag2,
            filter_type=constants.ReadingListTagFilterType.EXCLUDE,
        )
        article_to_exclude_linked_many_tags = ArticleFactory(
            title="Article to exclude linked to many tags",
            user=user,
            published_at=utcdt(2024, 5, 1),
            updated_at=None,
        )
        article_to_exclude_linked_many_tags.tags.add(tag1, tag2, other_tag)
        article_to_exclude_one_tag = ArticleFactory(
            title="Article to exclude linked to one tag",
            user=user,
            published_at=utcdt(2024, 5, 2),
            updated_at=None,
        )
        article_to_exclude_one_tag.tags.add(tag1)
        article_linked_to_no_tag = ArticleFactory(
            title="Article linked to no tag",
            user=user,
            published_at=utcdt(2024, 5, 4),
            updated_at=None,
        )

        with django_assert_num_queries(3):
            articles = list(Article.objects.get_articles_of_reading_list(reading_list))

        assert list(articles) == [article_linked_to_no_tag]

    def test_for_reading_list_exclude_all_tags(self, user, django_assert_num_queries):
        reading_list = ReadingListFactory(
            user=user, exclude_tag_operator=constants.ReadingListTagOperator.ALL
        )
        tag1 = TagFactory(user=user)
        tag2 = TagFactory(user=user)
        ReadingListTag.objects.create(
            reading_list=reading_list,
            tag=tag1,
            filter_type=constants.ReadingListTagFilterType.EXCLUDE,
        )
        ReadingListTag.objects.create(
            reading_list=reading_list,
            tag=tag2,
            filter_type=constants.ReadingListTagFilterType.EXCLUDE,
        )
        article_to_exclude_linked_to_all_tags = ArticleFactory(
            title="Article to exclude linked to many tags",
            user=user,
            published_at=utcdt(2024, 5, 1),
            updated_at=None,
        )
        article_to_exclude_linked_to_all_tags.tags.add(tag1, tag2)
        article_linked_to_one_tag = ArticleFactory(
            title="Article to exclude linked to one tag",
            user=user,
            published_at=utcdt(2024, 5, 2),
            updated_at=None,
        )
        article_linked_to_one_tag.tags.add(tag1)
        article_linked_to_no_tag = ArticleFactory(
            title="Article linked to no tag",
            user=user,
            published_at=utcdt(2024, 5, 4),
            updated_at=None,
        )

        with django_assert_num_queries(3):
            articles = list(Article.objects.get_articles_of_reading_list(reading_list))

        assert articles == [article_linked_to_no_tag, article_linked_to_one_tag]

    def test_for_reading_list_with_tags(self, user, django_assert_num_queries):
        reading_list = ReadingListFactory(
            user=user,
            include_tag_operator=constants.ReadingListTagOperator.ALL,
            exclude_tag_operator=constants.ReadingListTagOperator.ANY,
        )
        tag1_to_include = TagFactory(user=user)
        tag2_to_include = TagFactory(user=user)
        other_tag = TagFactory(user=user)
        tag1_to_exclude = TagFactory(user=user)
        tag2_to_exclude = TagFactory(user=user)
        ReadingListTag.objects.create(
            reading_list=reading_list,
            tag=tag1_to_include,
            filter_type=constants.ReadingListTagFilterType.INCLUDE,
        )
        ReadingListTag.objects.create(
            reading_list=reading_list,
            tag=tag2_to_include,
            filter_type=constants.ReadingListTagFilterType.INCLUDE,
        )
        ReadingListTag.objects.create(
            reading_list=reading_list,
            tag=tag1_to_exclude,
            filter_type=constants.ReadingListTagFilterType.EXCLUDE,
        )
        ReadingListTag.objects.create(
            reading_list=reading_list,
            tag=tag2_to_exclude,
            filter_type=constants.ReadingListTagFilterType.EXCLUDE,
        )
        article_to_include_linked_to_all_tags = ArticleFactory(
            title="Article cannot be included",
            user=user,
            published_at=utcdt(2024, 5, 1),
            updated_at=None,
        )
        article_to_include_linked_to_all_tags.tags.add(tag1_to_include, tag2_to_include, other_tag)
        article_cannot_be_included_linked_to_tag_to_exclude = ArticleFactory(
            title="Article cannot be included linked to tag to exclude",
            user=user,
            published_at=utcdt(2024, 5, 2),
            updated_at=None,
        )
        article_cannot_be_included_linked_to_tag_to_exclude.tags.add(
            tag1_to_include, tag2_to_include, tag1_to_exclude
        )
        article_cannot_be_included_linked_to_one_tag = ArticleFactory(
            title="Article to include one tag",
            user=user,
            published_at=utcdt(2024, 5, 3),
            updated_at=None,
        )
        article_cannot_be_included_linked_to_one_tag.tags.add(tag1_to_include)
        article_cannot_be_included_linked_to_deleted_tag_to_include = ArticleFactory(
            title="Article to include linked many tags",
            user=user,
            published_at=utcdt(2024, 5, 3),
            updated_at=None,
        )
        article_cannot_be_included_linked_to_deleted_tag_to_include.tags.add(tag2_to_include)

        with django_assert_num_queries(3):
            articles = list(Article.objects.get_articles_of_reading_list(reading_list))

        assert articles == [article_to_include_linked_to_all_tags]

    @pytest.mark.parametrize(
        ("action", "attrs"),
        [
            pytest.param(
                constants.UpdateArticleActions.MARK_AS_READ,
                {"read_at": datetime(2024, 4, 20, 12, 0, tzinfo=UTC), "is_read": True},
                id="mark-as-read",
            ),
            pytest.param(
                constants.UpdateArticleActions.MARK_AS_UNREAD,
                {"read_at": None, "is_read": False},
                id="mark-as-unread",
            ),
            pytest.param(
                constants.UpdateArticleActions.MARK_AS_FAVORITE,
                {"is_favorite": True},
                id="mark-as-favorite",
            ),
            pytest.param(
                constants.UpdateArticleActions.UNMARK_AS_FAVORITE,
                {"is_favorite": False},
                id="unmark-as-favorite",
            ),
            pytest.param(
                constants.UpdateArticleActions.MARK_AS_FOR_LATER,
                {"is_for_later": True},
                id="mark-as-for-later",
            ),
            pytest.param(
                constants.UpdateArticleActions.UNMARK_AS_FOR_LATER,
                {"is_for_later": False},
                id="unmark-as-for-later",
            ),
            pytest.param(
                constants.UpdateArticleActions.MARK_AS_OPENED,
                {"opened_at": datetime(2024, 4, 20, 12, 0, tzinfo=UTC), "was_opened": True},
                id="mark-as-opened",
            ),
        ],
    )
    def test_update_articles_from_action(
        self, action: constants.UpdateArticleActions, attrs: dict[str, bool | str]
    ):
        article = ArticleFactory(
            read_at=choice([datetime(2024, 4, 20, 12, 0, tzinfo=UTC), None]),
            is_favorite=choice([True, False]),
            is_for_later=choice([True, False]),
            opened_at=choice([datetime(2024, 4, 20, 12, 0, tzinfo=UTC), None]),
        )

        with time_machine.travel("2024-04-20 12:00:00"):
            Article.objects.get_queryset().filter(id=article.id).update_articles_from_action(action)

        article.refresh_from_db()
        for attr_name, attr_value in attrs.items():
            assert getattr(article, attr_name) == attr_value

    def test_default_order_by(self):
        article_only_published_at = ArticleFactory(
            title="Only published at", published_at=utcdt(2024, 5, 28), updated_at=None
        )
        article_only_updated_at = ArticleFactory(
            title="Only updated at", published_at=None, updated_at=utcdt(2024, 5, 31)
        )
        article_both_dates = ArticleFactory(
            title="Both dates",
            published_at=utcdt(2024, 5, 29),
            updated_at=utcdt(2024, 5, 30),
        )
        article_no_dates = ArticleFactory(title="No date", published_at=None, updated_at=None)

        articles_order_desc = Article.objects.get_queryset().default_order_by()
        articles_order_asc = Article.objects.get_queryset().default_order_by(
            constants.ReadingListOrderDirection.ASC
        )

        assert list(articles_order_desc) == [
            article_only_updated_at,
            article_both_dates,
            article_only_published_at,
            article_no_dates,
        ]
        assert list(articles_order_asc) == [
            article_only_published_at,
            article_both_dates,
            article_only_updated_at,
            article_no_dates,
        ]

    def test_for_cleanup(self, user, other_user):
        ArticleFactory(
            title="Unread not linked to a feed (to keep)",
            user=user,
            read_at=None,
            main_source_type=constants.ArticleSourceType.MANUAL,
        )
        ArticleFactory(
            title="Read not linked to a feed (to keep)",
            user=user,
            read_at=utcdt(2024, 6, 1),
            main_source_type=constants.ArticleSourceType.MANUAL,
        )
        feed_forever_retention = FeedFactory(user=user, article_retention_time=0)
        feed_one_day_retention = FeedFactory(user=user, article_retention_time=1)
        feed_seven_day_retention = FeedFactory(user=user, article_retention_time=7)

        unread_1_day_retention_to_keep = ArticleFactory(
            title="Unread, linked to 1 day retention (to keep)",
            user=user,
            main_source_type=constants.ArticleSourceType.FEED,
        )
        FeedArticleFactory(feed=feed_one_day_retention, article=unread_1_day_retention_to_keep)

        read_1_day_retention_to_cleanup = ArticleFactory(
            title="Read, 1 day retention (to cleanup)",
            user=user,
            read_at=utcdt(2024, 6, 1),
            main_source_type=constants.ArticleSourceType.FEED,
        )
        FeedArticleFactory(feed=feed_one_day_retention, article=read_1_day_retention_to_cleanup)

        read_1_day_retention_to_cleanup_but_was_manually_added_too = ArticleFactory(
            title="Read, 1 day retention but was manually added too (to keep)!",
            user=user,
            read_at=utcdt(2024, 6, 1),
            main_source_type=constants.ArticleSourceType.MANUAL,
        )
        FeedArticleFactory(
            feed=feed_one_day_retention,
            article=read_1_day_retention_to_cleanup_but_was_manually_added_too,
        )

        read_1_day_retention_to_keep = ArticleFactory(
            title="Read, 1 day retention (to keep)",
            user=user,
            read_at=utcdt(2024, 6, 6, hour=12),
            main_source_type=constants.ArticleSourceType.FEED,
        )
        FeedArticleFactory(feed=feed_one_day_retention, article=read_1_day_retention_to_keep)

        read_seven_day_retention_to_keep = ArticleFactory(
            title="Read, 7 days retention (to keep)",
            user=user,
            read_at=utcdt(2024, 6, 1),
            main_source_type=constants.ArticleSourceType.FEED,
        )
        FeedArticleFactory(feed=feed_seven_day_retention, article=read_seven_day_retention_to_keep)

        read_keep_forever_retention_to_keep = ArticleFactory(
            title="Read keep forever (to keep)",
            user=user,
            read_at=utcdt(2024, 6, 1),
            main_source_type=constants.ArticleSourceType.FEED,
        )
        FeedArticleFactory(feed=feed_forever_retention, article=read_keep_forever_retention_to_keep)

        read_keep_forever_and_one_day_retention_to_keep = ArticleFactory(
            title="Read keep forever and 1 day (to keep)",
            user=user,
            read_at=utcdt(2024, 6, 1),
            main_source_type=constants.ArticleSourceType.FEED,
        )
        FeedArticleFactory(
            feed=feed_forever_retention, article=read_keep_forever_and_one_day_retention_to_keep
        )
        FeedArticleFactory(
            feed=feed_one_day_retention, article=read_keep_forever_and_one_day_retention_to_keep
        )

        read_keep_one_and_seven_days_retention_to_keep = ArticleFactory(
            title="Read keep 1 and 7 days (to keep)",
            user=user,
            read_at=utcdt(2024, 6, 1),
            main_source_type=constants.ArticleSourceType.FEED,
        )
        FeedArticleFactory(
            feed=feed_forever_retention, article=read_keep_one_and_seven_days_retention_to_keep
        )
        FeedArticleFactory(
            feed=feed_one_day_retention, article=read_keep_one_and_seven_days_retention_to_keep
        )

        with time_machine.travel("2024-06-07 00:00:00"):
            articles_to_cleanup = Article.objects.get_queryset().for_cleanup()

        assert list(articles_to_cleanup) == [read_1_day_retention_to_cleanup]

    def test_for_search(self, user):
        search_in_title = ArticleFactory(title="Claudius", user=user)
        ArticleFactory(title="Does not match search", user=user)
        search_in_authors = ArticleFactory(
            title="Search in authors", user=user, authors=["Claudius"]
        )
        search_in_main_source_title = ArticleFactory(
            title="Search in main source title", user=user, main_source_title="Claudius"
        )
        search_in_content = ArticleFactory(title="Search in content", user=user, content="Claudius")
        search_in_summary = ArticleFactory(title="Search in summary", user=user, summary="Claudius")

        searched_articles = list(
            Article.objects
            .get_queryset()
            .for_search(
                ArticleFullTextSearchQuery(
                    q="Claudius", search_type=constants.ArticleSearchType.PLAIN
                )
            )
            .order_by("-rank")
        )

        expected_searched_articles = [
            search_in_title,
            search_in_summary,
            search_in_authors,
            search_in_content,
            search_in_main_source_title,
        ]
        if connection.vendor == "postgresql":
            assert searched_articles == expected_searched_articles
        else:
            assert {article.id for article in searched_articles} == {
                article.id for article in expected_searched_articles
            }

    def test_for_tags_search(self, user):
        ArticleFactory(title="Claudius", user=user)
        article = ArticleFactory(title="Correctly tagged", user=user)
        tag_that_matches = TagFactory(title="Claudius", user=user)
        article.tags.add(tag_that_matches)
        other_article = ArticleFactory(title="Other article", user=user)
        other_tag = TagFactory(title="Other tag", user=user)
        other_article.tags.add(other_tag)
        article.tags.add(other_tag)

        searched_articles = list(
            Article.objects.get_queryset().for_tags_search(ArticleFullTextSearchQuery(q="claudius"))
        )

        assert searched_articles == [article]

    def test_for_url_search(self, user):
        searched_url = "https://example.com/articles/1"
        ArticleFactory(title="Full url", user=user, url=f"{searched_url}.html")
        article_with_exact_url = ArticleFactory(title="Exact url", user=user, url=searched_url)
        ArticleFactory(title="Other URL", user=user)

        articles = list(
            Article.objects.get_queryset().for_url_search([searched_url]).order_by("id")
        )

        assert articles == [article_with_exact_url]


@pytest.mark.django_db
class TestArticleManager:
    @time_machine.travel("2024-06-01 12:00:00", tick=False)
    def test_save_from_list_of_data(self, user, django_assert_num_queries):
        tag1 = TagFactory(user=user)
        tag2 = TagFactory(user=user)
        existing_article_no_tag = ArticleFactory(
            title="Old title",
            content="Old content",
            content_type="text/html",
            user=user,
            external_article_id="existing-article-feed",
            updated_at=utcdt(2023, 4, 20),
            read_at=utcnow(),
            main_source_type=constants.ArticleSourceType.FEED,
        )
        existing_article_with_tag = ArticleFactory(
            title="Title to keep",
            content="Content to keep",
            user=user,
            updated_at=utcdt(2024, 4, 20),
        )
        existing_article_with_tag.tags.add(tag1)
        now_dt = utcnow()

        with django_assert_num_queries(7), time_machine.travel("2024-06-02 12:00:00", tick=False):
            Article.objects.save_from_list_of_data(
                user,
                [
                    ArticleData(
                        external_article_id="some-article-1",
                        title="Article 1",
                        summary="Summary 1",
                        content="""<h2 id="section-title">My title</h2> <h3 id="sub-section">Sub-section</h3>Description 1"""  # ruff:ignore[line-too-long]
                        + " word " * user.settings.default_reading_time * 3,
                        content_type="text/html",
                        table_of_content=(),
                        authors=("Author",),
                        contributors=(),
                        tags=(),
                        url="https://example.com/article/some-new-article-1",
                        preview_picture_url="https://example.com/preview.png",
                        preview_picture_alt="Some image alt",
                        published_at=now_dt,
                        updated_at=now_dt,
                        source_title="Some site",
                        language="fr",
                    ),
                    ArticleData(
                        external_article_id=existing_article_no_tag.external_article_id,
                        url=existing_article_no_tag.url,
                        title="Article updated",
                        summary="Summary updated",
                        content="Description updated",
                        content_type="text/plain",
                        table_of_content=(),
                        authors=("Author",),
                        contributors=(),
                        tags=(),
                        preview_picture_url="",
                        preview_picture_alt="",
                        published_at=now_dt,
                        updated_at=now_dt,
                        source_title="Some site",
                        language="fr",
                    ),
                    ArticleData(
                        external_article_id=existing_article_with_tag.external_article_id,
                        url=existing_article_with_tag.url,
                        title="Updated article",
                        summary="Summary updated",
                        content="Description updated",
                        content_type="text/plain",
                        table_of_content=(),
                        authors=("Author",),
                        contributors=(),
                        tags=(),
                        preview_picture_url="",
                        preview_picture_alt="",
                        published_at=utcdt(2024, 4, 19),
                        updated_at=utcdt(2024, 4, 19),
                        source_title="Some site",
                        language="fr",
                    ),
                    ArticleData(
                        external_article_id="article-3",
                        title="Article 3",
                        summary="Summary 3",
                        content="Description 3",
                        content_type="text/plain",
                        table_of_content=(),
                        authors=("Author",),
                        contributors=("Contributor",),
                        tags=("Some tag",),
                        url="https://example.com/article/new-article-3",
                        preview_picture_url="",
                        preview_picture_alt="",
                        published_at=now_dt,
                        updated_at=now_dt,
                        source_title="Some site",
                        language="fr",
                    ),
                ],
                [tag1, tag2],
            )

        assert Article.objects.count() == 4
        existing_article_no_tag.refresh_from_db()
        assert existing_article_no_tag.title == "Old title"
        assert existing_article_no_tag.content == "Description updated"
        assert existing_article_no_tag.content_type == "text/plain"
        assert existing_article_no_tag.slug == "old-title"
        assert existing_article_no_tag.updated_at == now_dt
        assert existing_article_no_tag.read_at is not None
        assert existing_article_no_tag.main_source_type == constants.ArticleSourceType.MANUAL
        assert existing_article_no_tag.obj_created_at == utcdt(2024, 6, 1, 12, 0)
        assert existing_article_no_tag.obj_updated_at == utcdt(2024, 6, 2, 12, 0)
        existing_article_with_tag.refresh_from_db()
        assert existing_article_with_tag.title == "Title to keep"
        assert existing_article_with_tag.slug == "title-to-keep"
        assert existing_article_with_tag.content == "Content to keep"
        assert existing_article_with_tag.updated_at == utcdt(2024, 4, 20)
        assert existing_article_with_tag.obj_created_at == utcdt(2024, 6, 1, 12, 0)
        assert existing_article_with_tag.obj_updated_at == utcdt(2024, 6, 2, 12, 0)
        other_article = Article.objects.get(external_article_id="some-article-1")
        assert other_article.title == "Article 1"
        assert other_article.slug == "article-1"
        assert other_article.reading_time == 3
        assert other_article.obj_created_at == utcdt(2024, 6, 2, 12, 0)
        assert other_article.obj_updated_at == utcdt(2024, 6, 2, 12, 0)
        assert other_article.table_of_content == [
            {
                "children": [{"id": "sub-section", "level": 3, "text": "Sub-section"}],
                "id": "section-title",
                "level": 2,
                "text": "My title",
            }
        ]
        tag_slugs = list(
            Article.objects
            .annotate(tag_slugs=models.StringAgg("tags__slug", delimiter=models.Value("|")))
            .values_list("url", "tag_slugs")
            .order_by("url")
        )
        assert tag_slugs == [
            (existing_article_no_tag.url, None),
            (existing_article_with_tag.url, tag1.slug),
            ("https://example.com/article/new-article-3", f"{tag1.slug}|{tag2.slug}"),
            ("https://example.com/article/some-new-article-1", f"{tag1.slug}|{tag2.slug}"),
        ]

    def test_same_urlmultiple_times(self, user, django_assert_num_queries):
        now_dt = utcnow()

        with django_assert_num_queries(4):
            Article.objects.save_from_list_of_data(
                user,
                [
                    ArticleData(
                        external_article_id="some-article-1",
                        title="Article 1",
                        summary="Summary 1",
                        content="Description 1" + " word " * user.settings.default_reading_time * 3,
                        content_type="text/plain",
                        table_of_content=(),
                        authors=("Author",),
                        contributors=(),
                        tags=(),
                        url="https://example.com/article/1",
                        preview_picture_url="https://example.com/preview.png",
                        preview_picture_alt="Some image alt",
                        published_at=now_dt,
                        updated_at=now_dt,
                        source_title="Some site",
                        language="fr",
                    ),
                    ArticleData(
                        external_article_id="some-article-1",
                        url="https://example.com/article/1",
                        title="Article updated",
                        summary="Summary updated",
                        content="Description updated",
                        content_type="text/plain",
                        table_of_content=(),
                        authors=("Author",),
                        contributors=(),
                        tags=(),
                        preview_picture_url="",
                        preview_picture_alt="",
                        published_at=now_dt,
                        updated_at=now_dt,
                        source_title="Some site",
                        language="fr",
                    ),
                ],
                tags=[],
            )

        assert Article.objects.count() == 1
        other_article = Article.objects.get()
        assert other_article.title == "Article 1"
        assert other_article.slug == "article-1"
        assert other_article.reading_time == 3

    def test_manually_readd_read_article(self, user, django_assert_num_queries):
        now_dt = utcnow()
        existing_article = ArticleFactory(
            title="Old title",
            content="Old content",
            content_type="text/plain",
            user=user,
            external_article_id="existing-article-feed",
            updated_at=utcdt(2023, 4, 20),
            read_at=now_dt,
        )
        article_data = ArticleData(
            external_article_id=existing_article.external_article_id,
            url=existing_article.url,
            title=existing_article.title,
            summary=existing_article.summary,
            content=existing_article.content,
            content_type="text/plain",
            table_of_content=(),
            authors=tuple(existing_article.authors),
            contributors=tuple(existing_article.contributors),
            tags=tuple(existing_article.external_tags),
            published_at=now_dt,
            updated_at=now_dt,
            source_title="Some site",
            preview_picture_url="https://example.com/preview.png",
            preview_picture_alt="Some image alt",
            language="fr",
        )

        with django_assert_num_queries(4):
            Article.objects.save_from_list_of_data(user, [article_data], tags=[])

        existing_article.refresh_from_db()
        assert existing_article.read_at is not None
        assert existing_article.title == "Old title"

    def test_readd_read_article_from_a_feed(self, user, django_assert_num_queries):
        now_dt = utcnow()
        feed = FeedFactory(user=user)
        existing_article = ArticleFactory(
            title="Old title",
            content="Old content",
            content_type="text/plain",
            user=user,
            external_article_id="existing-article-feed",
            updated_at=utcdt(2023, 4, 20),
            read_at=now_dt,
            main_feed=feed,
        )
        article_data = ArticleData(
            external_article_id=existing_article.external_article_id,
            url=existing_article.url,
            title=existing_article.title,
            summary=existing_article.summary,
            content=existing_article.content,
            content_type="text/plain",
            table_of_content=(),
            authors=tuple(existing_article.authors),
            contributors=tuple(existing_article.contributors),
            tags=tuple(existing_article.external_tags),
            published_at=now_dt,
            updated_at=now_dt,
            source_title="Some site",
            preview_picture_url="https://example.com/preview.png",
            preview_picture_alt="Some image alt",
            language="fr",
        )

        with django_assert_num_queries(4):
            Article.objects.save_from_list_of_data(
                user,
                [article_data],
                tags=[],
                initial_main_feed_id=feed.id,
            )

        existing_article.refresh_from_db()
        assert existing_article.read_at == now_dt

    def test_count_unread_articles_of_reading_lists(self, user, django_assert_num_queries):
        reading_list1 = ReadingListFactory(user=user)
        reading_list2 = ReadingListFactory(user=user, read_status=constants.ReadStatus.ONLY_READ)
        reading_list3 = ReadingListFactory(
            user=user, favorite_status=constants.FavoriteStatus.ONLY_FAVORITE
        )
        tag = TagFactory(user=user)
        reading_list4 = ReadingListFactory(user=user)
        ReadingListTag.objects.create(
            reading_list=reading_list4,
            tag=tag,
            filter_type=constants.ReadingListTagFilterType.INCLUDE,
        )
        article = ArticleFactory(user=user)
        article.tags.add(tag)
        ArticleFactory(user=user, read_at=utcnow())
        reading_lists = ReadingList.objects.get_all_for_user(user)

        with django_assert_num_queries(1):
            counts = Article.objects.count_unread_articles_of_reading_lists(user, reading_lists)

        assert counts == {
            reading_list1.slug: 1,
            reading_list2.slug: 0,
            reading_list3.slug: 0,
            reading_list4.slug: 1,
        }

    def test_get_articles_of_tag(self, user, django_assert_num_queries):
        tag_to_display = TagFactory(user=user)
        other_tag = TagFactory(user=user)
        article_linked_only_to_tag_to_display = ArticleFactory(
            title="Article linked only to tag to display", user=user
        )
        article_linked_only_to_tag_to_display.tags.add(tag_to_display)
        article_linked_to_all_tags = ArticleFactory(title="Article linked to all tags", user=user)
        article_linked_to_all_tags.tags.add(tag_to_display, other_tag)
        ArticleFactory(title="Article linked to not tag to display", user=user)
        article_linked_to_other_tag = ArticleFactory(title="Article linked to other tag", user=user)
        article_linked_to_other_tag.tags.add(other_tag)

        with django_assert_num_queries(2):
            articles = list(Article.objects.get_articles_of_tag(tag_to_display).order_by("id"))

        assert list(articles) == [article_linked_only_to_tag_to_display, article_linked_to_all_tags]

    def test_get_articles_with_external_tag(self, user, django_assert_num_queries):
        tag = TagFactory(user=user, title="Test")
        article = ArticleFactory(user=user, external_tags=["Test"])
        article.tags.add(tag)
        ArticleFactory(user=user, external_tags=["Other tag"])
        properly_tagged_article = ArticleFactory(user=user)
        properly_tagged_article.tags.add(tag)
        ArticleFactory(external_tags=["Just", "Some", "Test"])

        with django_assert_num_queries(2):
            articles = list(Article.objects.get_articles_with_external_tag(user, "Test"))

        assert articles == [article]

    def test_create_invalid_articles(self, user, django_assert_num_queries):
        tag = TagFactory(user=user, title="Test")
        link = "http://toto.com/"
        fetch_result = FetchArticleResultFactory(
            error_message="Error",
            article_data=ArticleDataFactory(
                url=link,
                title="toto.com",
                source_title="toto.com",
            ),
        )

        with django_assert_num_queries(7):
            save_results = Article.objects.save_from_fetch_results(
                user,
                [fetch_result],
                [tag],
            )

        assert len(save_results) == 1
        save_result = save_results[0]
        assert save_result.was_created
        assert save_result.article.url == link
        assert save_result.article.title == "toto.com"
        assert save_result.article.slug == "toto-com"
        assert save_result.article.updated_at is None
        assert save_result.article.main_source_type == constants.ArticleSourceType.MANUAL
        assert save_result.article.main_source_title == "toto.com"
        assert list(save_result.article.tags.all()) == [tag]
        assert save_result.article.article_fetch_errors.count() == 1

    def test_create_article_title_cannot_be_slugified(self, user):
        article = Article.objects.create(url="https://toto.com/article", title="??", user=user)

        assert article.title == "??"
        assert article.slug == "no-slug"

    def test_create_invalid_article_articles_already_saved(self, user, django_assert_num_queries):
        initial_article = ArticleFactory(user=user)
        tag = TagFactory(user=user, title="Test")
        fetch_result = FetchArticleResultFactory(
            error_message="Error",
            article_data=ArticleDataFactory(
                url=initial_article.url,
                title="New article title",
                source_title="toto.com",
            ),
        )

        with django_assert_num_queries(4):
            save_results = Article.objects.save_from_fetch_results(
                user,
                [fetch_result],
                [tag],
            )

        assert len(save_results) == 1
        save_result = save_results[0]
        assert not save_result.was_created
        assert save_result.article.url == initial_article.url
        assert save_result.article.title != initial_article.url
        assert save_result.article.title == initial_article.title
        assert save_result.article.tags.count() == 0
        assert save_result.article.article_fetch_errors.count() == 1

    def test_save_from_fetch_results(self, user, django_assert_num_queries):
        tag = TagFactory(user=user, title="Test")
        link = "http://toto.com/"
        invalid_fetch_result = FetchArticleResultFactory(
            error_message="Error",
            article_data=ArticleDataFactory(
                url=link,
                title="toto.com",
                source_title="toto.com",
            ),
        )
        valid_fetch_result = FetchArticleResultFactory()

        with django_assert_num_queries(13):
            save_results = Article.objects.save_from_fetch_results(
                user,
                [valid_fetch_result, invalid_fetch_result],
                [tag],
            )

        assert len(save_results) == 2
        assert all(result.was_created for result in save_results)
        assert Article.objects.count() == 2
        assert ArticleFetchError.objects.count() == 1

    @patch.object(constants, "MAX_EXPORT_ARTICLES_PER_PAGE", 2)
    def test_export(self, user, other_user, snapshot, django_assert_num_queries):
        ArticleFactory(id=10, user=other_user)
        feed_category = FeedCategoryFactory(id=1, user=user, title="Feed category")
        feed_with_category = FeedFactory(
            id=1,
            user=user,
            title="Feed with category",
            category=feed_category,
            feed_url="https://example.com/feeds/with_cat.xml",
        )
        feed_without_category = FeedFactory(
            id=2,
            user=user,
            title="Feed without category",
            feed_url="https://example.com/feeds/without_cat.xml",
        )
        article_from_feed = ArticleFactory(
            id=1,
            user=user,
            title="Article from feed",
            url="https://example.com/article/feed-article/",
            published_at=utcdt(2024, 6, 23, 12, 0, 0),
            updated_at=utcdt(2024, 6, 23, 12, 0, 0),
            authors=["Author 1", "Author 2"],
            contributors=["Contributor 1", "Contributor 2"],
            external_tags=["Tag 1", "Tag 2"],
            read_at=utcdt(2024, 6, 25, 12, 0, 0),
            opened_at=utcdt(2024, 6, 25, 12, 0, 0),
            is_favorite=True,
            is_for_later=True,
            main_feed=feed_without_category,
        )
        FeedArticleFactory(feed=feed_without_category, article=article_from_feed)
        article_two_feeds = ArticleFactory(
            id=2,
            user=user,
            title="Article with 2 feeds",
            url="https://example.com/article/multiple-feeds-article/",
            published_at=utcdt(2024, 6, 23, 12, 0, 0),
            updated_at=utcdt(2024, 6, 23, 12, 0, 0),
            main_feed=feed_with_category,
        )
        FeedArticleFactory(feed=feed_with_category, article=article_two_feeds)
        FeedArticleFactory(feed=feed_without_category, article=article_two_feeds)
        article_no_feed = ArticleFactory(
            id=3,
            user=user,
            is_favorite=True,
            title="Article",
            url="https://example.com/article/independant-article/",
            published_at=utcdt(2024, 6, 23, 12, 0, 0),
            updated_at=utcdt(2024, 6, 23, 12, 0, 0),
        )
        CommentFactory(id=1, article=article_from_feed, text="A comment")
        group = ArticlesGroupFactory(id=1, user=user, title="Group", description="A group")
        second_article_of_group = ArticleFactory(
            id=4,
            user=user,
            group=group,
            group_order=2,
            title="2nd article in group",
            content="Content",
            content_type="text/plain",
            url="https://example.com/article/in-group2/",
            published_at=utcdt(2024, 6, 23, 12, 0, 0),
            updated_at=utcdt(2024, 6, 23, 12, 0, 0),
        )
        first_article_of_group = ArticleFactory(
            id=5,
            user=user,
            group=group,
            group_order=1,
            title="1st article in group",
            content="Content",
            content_type="text/plain",
            url="https://example.com/article/in-group/",
            published_at=utcdt(2024, 6, 23, 12, 0, 0),
            updated_at=utcdt(2024, 6, 23, 12, 0, 0),
        )

        with django_assert_num_queries(12):
            articles = self._export_all_articles(user)

        assert len(articles) == 3
        assert len(articles[0]) == 2
        assert len(articles[1]) == 2
        assert len(articles[2]) == 1
        assert articles[0][0]["article_id"] == article_from_feed.id
        assert articles[0][0]["feed_id"] == feed_without_category.id
        assert articles[0][1]["article_id"] == article_two_feeds.id
        assert articles[0][1]["feed_id"] == feed_with_category.id
        assert articles[0][1]["category_id"] == feed_category.id
        assert articles[1][0]["article_id"] == article_no_feed.id
        assert articles[1][1]["article_id"] == first_article_of_group.id
        assert articles[2][0]["article_id"] == second_article_of_group.id
        assert serialize_for_snapshot(articles) == snapshot

    @patch.object(constants, "MAX_EXPORT_ARTICLES_PER_PAGE", 2)
    def test_export_updated_since(self, user, other_user):
        ArticleFactory(
            id=1,
            user=user,
            title="Old article",
            url="https://example.com/article/1/",
            published_at=utcdt(2024, 6, 23, 12, 0, 0),
            updated_at=utcdt(2024, 6, 23, 12, 0, 0),
            authors=["Author 1", "Author 2"],
            contributors=["Contributor 1", "Contributor 2"],
            external_tags=["Tag 1", "Tag 2"],
            read_at=utcdt(2024, 6, 25, 12, 0, 0),
            opened_at=utcdt(2024, 6, 25, 12, 0, 0),
            is_favorite=True,
            is_for_later=True,
        )
        recent_article = ArticleFactory(
            id=2,
            user=user,
            title="Recently updated article",
            url="https://example.com/article/2/",
            published_at=utcdt(2024, 6, 23, 12, 0, 0),
            updated_at=utcdt(2025, 6, 23, 12, 0, 0),
        )
        article_with_recent_comment = ArticleFactory(
            id=3,
            user=user,
            title="Article with recent comment",
            url="https://example.com/article/3/",
            published_at=utcdt(2024, 6, 23, 12, 0, 0),
            updated_at=utcdt(2024, 6, 23, 12, 0, 0),
        )
        with time_machine.travel("2025-06-04"):
            CommentFactory(article=article_with_recent_comment, text="A comment")

        articles = self._export_all_articles(user, utcdt(2025, 6, 1))

        assert len(articles) == 1
        assert len(articles[0]) == 2
        assert articles[0][0]["article_id"] == recent_article.id
        assert articles[0][1]["article_id"] == article_with_recent_comment.id

    def _export_all_articles(self, user, updated_since=None):
        all_articles = []
        for articles in Article.objects.export(user, updated_since=updated_since):
            all_articles.append(articles)

        return all_articles

    def test_search(self, user, other_user):
        ArticleFactory(title="Claudius other user", user=other_user)
        search_in_title = ArticleFactory(user=user, title="Claudius")
        search_query = ArticleFullTextSearchQuery(q="Claudius")

        found_articles = list(Article.objects.search(user, search_query))

        assert found_articles == [search_in_title]

    def test_search_url(self, user):
        article = ArticleFactory(title="Test", user=user)
        search_query = ArticleFullTextSearchQuery(
            q=article.url, search_type=constants.ArticleSearchType.URL
        )

        found_articles = list(Article.objects.search(user, search_query))

        assert found_articles == [article]

    @pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL specific test")
    def test_search_with_tags_results(self, user, other_user):
        ArticleFactory(title="Claudius other user", user=other_user)
        search_in_title = ArticleFactory(user=user, title="Claudius")
        search_query = ArticleFullTextSearchQuery(q="Claudius")
        tagged_article = ArticleFactory(title="Tagged article", user=user)
        tag = TagFactory(title="claudius", user=user)
        tagged_article.tags.add(tag)

        found_articles = list(Article.objects.search(user, search_query))

        assert found_articles == [search_in_title, tagged_article]

    def test_search_with_advanced_filters(self, user, other_user):
        ArticleFactory(user=user, title="Claudius read", read_at=utcnow())
        ArticleFactory(user=user, title="Claudius", read_at=None)
        search_in_multiple_fields = ArticleFactory(
            user=user, title="Claudius", read_at=None, external_tags=["Claudius", "Maximus"]
        )
        feed = FeedFactory(user=user, title="Claudius feed")
        feed.articles.add(search_in_multiple_fields)
        search_query = ArticleFullTextSearchQuery(
            q="Claudius",
            read_status=constants.ReadStatus.ONLY_UNREAD,
            linked_with_feeds=frozenset([feed.id]),
            external_tags_to_include=frozenset(["Maximus", "Not there!"]),
        )

        found_articles = list(Article.objects.search(user, search_query))

        assert found_articles == [search_in_multiple_fields]

    def test_search_order_by(self, user):
        article_1 = ArticleFactory(title="Read at", user=user, read_at=utcdt(2024, 6, 1))
        article_2 = ArticleFactory(title="Read at", user=user, read_at=utcdt(2024, 6, 30))
        search_query = ArticleFullTextSearchQuery(
            q="Read at", order=constants.ArticleSearchOrderBy.READ_AT_ASC
        )

        articles = list(Article.objects.search(user, search_query))

        assert articles == [article_1, article_2]

    def test_cleanup_articles(self, user):
        ArticleFactory(
            title="Read not linked to a feed (to keep)",
            user=user,
            read_at=utcdt(2024, 6, 1),
            main_source_type=constants.ArticleSourceType.MANUAL,
        )
        read_keep_one_and_seven_days_retention_to_keep = ArticleFactory(
            title="Read keep 1 and 7 days (to keep)",
            user=user,
            read_at=utcdt(2024, 6, 1),
            main_source_type=constants.ArticleSourceType.FEED,
        )
        feed_forever_retention = FeedFactory(user=user, article_retention_time=0)
        feed_article_to_keep = FeedArticleFactory(
            feed=feed_forever_retention, article=read_keep_one_and_seven_days_retention_to_keep
        )
        read_1_day_retention_to_cleanup = ArticleFactory(
            title="Read, 1 day retention (to cleanup)",
            user=user,
            read_at=utcdt(2024, 6, 1),
            main_source_type=constants.ArticleSourceType.FEED,
        )
        feed_one_day_retention = FeedFactory(user=user, article_retention_time=1)
        feed_article_to_deleted = FeedArticleFactory(
            feed=feed_one_day_retention, article=read_1_day_retention_to_cleanup
        )

        with time_machine.travel("2024-06-07 00:00:00"):
            deletion_result = Article.objects.cleanup_articles()

        assert deletion_result == (1, {"reading.Article": 1})
        feed_article_to_keep.refresh_from_db()
        assert feed_article_to_keep.article == read_keep_one_and_seven_days_retention_to_keep
        feed_article_to_deleted.refresh_from_db()
        assert feed_article_to_deleted.article is None
        assert Article.objects.count() == 2

    def test_link_articles_to_group(self, user):
        group = ArticlesGroupFactory(user=user)
        article = ArticleFactory(user=user)
        article_already_linked_to_group = ArticleFactory(user=user, group=group, group_order=1)
        other_group = ArticlesGroupFactory(user=user)
        article_already_linked_to_other_group = ArticleFactory(user=user, group=other_group)
        other_group.articles.add(article_already_linked_to_other_group)

        articles_already_linked = Article.objects.link_articles_to_group(
            group,
            [article, article_already_linked_to_group, article_already_linked_to_other_group],
        )

        assert articles_already_linked == (article_already_linked_to_other_group,)
        assert list(Article.objects.filter(group=group).values_list("id", "group_order")) == [
            (article.id, 2),
            (article_already_linked_to_group.id, 3),
        ]
        assert list(Article.objects.filter(group=other_group).values_list("id", flat=True)) == [
            article_already_linked_to_other_group.id
        ]

    def test_link_new_article_to_group(self, user):
        group = ArticlesGroupFactory(user=user)
        ArticleFactory(user=user, group=group, group_order=1)
        article = ArticleFactory(user=user)

        articles_already_linked = Article.objects.link_articles_to_group(group, [article])

        assert articles_already_linked == ()
        article.refresh_from_db()
        assert article.group == group
        assert article.group_order == 2

    def test_reorder_in_group(self, user):
        group = ArticlesGroupFactory(user=user)
        article = ArticleFactory(user=user, group=group, group_order=1)
        article2 = ArticleFactory(user=user, group=group, group_order=2)
        other_group = ArticlesGroupFactory(user=user)
        article_other_group = ArticleFactory(user=user, group=other_group, group_order=1)
        independent_article = ArticleFactory(user=user)
        other_independent_article = ArticleFactory(user=user)

        Article.objects.reorder_in_group(
            group,
            {
                article2.id: 1,
                article.id: 2,
                article_other_group.id: 3,
                other_independent_article.id: 4,
            },
        )

        article.refresh_from_db()
        assert article.group == group
        assert article.group_order == 2
        article2.refresh_from_db()
        assert article2.group == group
        assert article2.group_order == 1
        article_other_group.refresh_from_db()
        assert article_other_group.group == other_group
        assert article_other_group.group_order == 1
        independent_article.refresh_from_db()
        assert independent_article.group is None
        assert independent_article.group_order == 0
        other_independent_article.refresh_from_db()
        assert other_independent_article.group is None
        assert other_independent_article.group_order == 0


class TestArticleModel:
    @pytest.mark.django_db
    def test_generated_fields(self):
        article = ArticleFactory(opened_at=None, read_at=None)
        assert not article.is_read
        assert not article.was_opened

        article = ArticleFactory(opened_at=utcnow(), read_at=utcnow())
        assert article.is_read
        assert article.was_opened

    @pytest.mark.parametrize(
        ("initial_data", "force_update", "expected_data", "expected_was_updated"),
        [
            pytest.param(
                {
                    "title": "Initial title",
                    "content": "Initial content",
                    "content_type": "text/html",
                    "updated_at": utcdt(2024, 4, 21),
                },
                False,
                {
                    "title": "Initial title",
                    "content": "Initial content",
                    "content_type": "text/html",
                    "updated_at": utcdt(2024, 4, 21),
                },
                False,
                id="initial-data-more-recent-than-update-proposal",
            ),
            pytest.param(
                {
                    "title": "Initial title",
                    "content": "Initial content",
                    "content_type": "text/html",
                    "updated_at": utcdt(2024, 4, 21),
                },
                True,
                {
                    "title": "Initial title",
                    "content": """<h2 id="my-title">My title</h2> Updated content""",
                    "content_type": "text/html",
                    "updated_at": utcdt(2024, 4, 21),
                },
                True,
                id="initial-data-more-recent-than-update-proposal-but-ask-for-force-update",
            ),
            pytest.param(
                {
                    "title": "Initial title",
                    "content": "",
                    "content_type": "text/html",
                    "updated_at": utcdt(2024, 4, 21),
                },
                False,
                {
                    "title": "Initial title",
                    "content": """<h2 id="my-title">My title</h2> Updated content""",
                    "content_type": "text/html",
                    "updated_at": utcdt(2024, 4, 21),
                },
                True,
                id="initial-data-more-recent-than-update-proposal-but-update-has-content",
            ),
            pytest.param(
                {
                    "title": "Initial title",
                    "summary": "Initial summary",
                    "content": "Initial content",
                    "content_type": "text/html",
                    "table_of_content": [],
                    "updated_at": utcdt(2024, 4, 19),
                    "external_tags": ["Initial tag", "Some tag"],
                    "authors": ["Author 1", "Author 2"],
                    "contributors": ["Contributor 1", "Contributor 2"],
                },
                False,
                {
                    "title": "Initial title",
                    "summary": "Updated summary",
                    "content": """<h2 id="my-title">My title</h2> Updated content""",
                    "content_type": "text/html",
                    "table_of_content": (
                        TableOfContentTopItem(id="my-title", text="My title", level=2, children=[]),
                    ),
                    "updated_at": utcdt(2024, 4, 20),
                    "external_tags": ["Initial tag", "Some tag", "Updated tag"],
                    "authors": ["Author 1", "Author 2", "Author 3"],
                    "contributors": ["Contributor 1", "Contributor 2", "Contributor 3"],
                },
                True,
                id="initial-data-less-recent-than-update-proposal",
            ),
        ],
    )
    def test_update_article_from_data(
        self,
        user,
        initial_data: dict,
        force_update: bool,
        expected_data: dict,
        expected_was_updated: bool,
    ):
        article = ArticleFactory.build(**initial_data, user=user)

        was_updated = article.update_article_from_data(
            ArticleData(
                external_article_id="some-article-1",
                title="Updated title",
                summary="Updated summary",
                content="<h2>My title</h2> Updated content",
                content_type="text/html",
                table_of_content=(
                    TableOfContentTopItem(id="header", text="My title", level=2, children=[]),
                ),
                authors=("Author 2", "Author 3"),
                contributors=("Contributor 2", "Contributor 3"),
                tags=("Some tag", "Updated tag"),
                url="https://example.com/article/1",
                preview_picture_url="https://example.com/preview.png",
                preview_picture_alt="Some image alt",
                published_at=utcdt(2024, 4, 20),
                updated_at=utcdt(2024, 4, 20),
                source_title="Some site",
                language="fr",
            ),
            force_update=force_update,
        )

        assert was_updated == expected_was_updated
        for attr, value in expected_data.items():
            assert getattr(article, attr) == value

    def test_update_article_from_data_article_data_is_missing_some_data(self, user):
        initial_data = {
            "title": "Initial title",
            "summary": "Initial summary",
            "content": "Initial content",
            "content_type": "text/plain",
            "updated_at": utcdt(2024, 4, 19),
            "reading_time": 13,
        }
        expected_data = {
            "title": "Initial title",
            "summary": "Initial summary",
            "content": "Initial content",
            "content_type": "text/plain",
            "updated_at": utcdt(2024, 4, 20),
            "reading_time": 13,
        }
        article = ArticleFactory.build(**initial_data, user=user)

        was_updated = article.update_article_from_data(
            ArticleData(
                external_article_id="some-article-1",
                title="Updated title",
                summary="",
                content="",
                content_type="text/plain",
                table_of_content=(),
                authors=("Author",),
                contributors=(),
                tags=(),
                url="https://example.com/article/1",
                preview_picture_url="",
                preview_picture_alt="",
                published_at=utcdt(2024, 4, 20),
                updated_at=utcdt(2024, 4, 20),
                source_title="Some site",
                language="fr",
            )
        )

        assert was_updated
        for attr, value in expected_data.items():
            assert getattr(article, attr) == value

    def test_update_content_type(self, user):
        article = ArticleFactory.build(content_type="text/plain", user=user)

        was_updated = article.update_article_from_data(ArticleDataFactory(content_type="text/html"))

        assert was_updated
        assert article.content_type == "text/html"

    @pytest.mark.django_db
    def test_adjoining_articles_of_group_no_group(self, django_assert_num_queries):
        article = ArticleFactory(group=None)

        with django_assert_num_queries(0):
            assert article.next_article_of_group is None
            assert article.previous_article_of_group is None

    @pytest.mark.django_db
    def test_adjoining_articles_of_group_with_group_no_other_article(
        self, django_assert_num_queries
    ):
        article = ArticleFactory.build(group=ArticlesGroupFactory())

        with django_assert_num_queries(2):
            assert article.next_article_of_group is None
            assert article.previous_article_of_group is None

    @pytest.mark.django_db
    def test_adjoining_articles_of_group(self):
        group = ArticlesGroupFactory()
        article_1 = ArticleFactory(group=group, group_order=1)
        article_3 = ArticleFactory(group=group, group_order=3)
        article_2 = ArticleFactory(group=group, group_order=2)

        assert article_1.next_article_of_group == article_2
        assert article_1.previous_article_of_group is None
        assert article_2.next_article_of_group == article_3
        assert article_2.previous_article_of_group == article_1
        assert article_3.next_article_of_group is None
        assert article_3.previous_article_of_group == article_2

    def test_update_from_details(self):
        article = ArticleFactory.build()

        article.update_from_details(title="Test title", summary="Test summary", reading_time=10)

        assert article.title == "Test title"
        assert article.summary == "Test summary"
        assert article.reading_time == 10
