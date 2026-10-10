# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from functools import cached_property
from itertools import chain
from typing import TYPE_CHECKING, Self, assert_never

from dateutil.relativedelta import relativedelta
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import (
    SearchQuery,
    SearchRank,
    SearchVector,
    SearchVectorField,
)
from django.core.paginator import Paginator
from django.db import connection, models, transaction
from django.db.models.functions import Cast, Coalesce, Left
from django.utils.translation import gettext_lazy as _
from ninja.schema import Schema
from pydantic import ConfigDict
from slugify import slugify

from legadilo.core.utils.collections_utils import CustomJsonEncoder, max_or_none, min_or_none
from legadilo.core.utils.text import get_nb_words_from_html
from legadilo.core.utils.time_utils import utcnow
from legadilo.core.utils.validators import (
    CONTENT_TYPES,
    language_code_validator,
    list_of_strings_validator,
    table_of_content_validator,
)
from legadilo.reading import constants
from legadilo.reading.models.tag import ArticleTag

from ...core.utils.db import ExtractEpoch, RemoveExtraSpaces, StripHtmlTags
from .article_fetch_error import ArticleFetchError

if TYPE_CHECKING:
    from django_stubs_ext.db.models import TypedModelMeta

    from legadilo.reading.models.reading_list import ReadingList
    from legadilo.reading.models.tag import Tag
    from legadilo.reading.services.article_fetching import (
        ArticleData,
        FetchArticleResult,
    )
    from legadilo.users.models import User

    from .articles_group import ArticlesGroup
else:
    TypedModelMeta = object

logger = logging.getLogger(__name__)


# The search vector cannot be too big or it won't be indexed. It must be under 1MB with all its
# data. According to my tests, these values are fine and allow for very long articles (over 2h of
# reading time) to be indexed. If articles are cut, what's indexed should be enough to find the
# article.
SEARCH_CONTENT_MAX_LENGTH = 200_000
SEARCH_SUMMARY_MAX_LENGTH = 20_000
SEARCH_AUTHORS_MAX_LENGTH = 5_000
SEARCH_VECTOR = (
    SearchVector("title", config="english", weight="A")
    + SearchVector(
        Left(RemoveExtraSpaces(StripHtmlTags("summary")), SEARCH_SUMMARY_MAX_LENGTH),
        config="english",
        weight="B",
    )
    + SearchVector(
        Left(RemoveExtraSpaces(StripHtmlTags("content")), SEARCH_CONTENT_MAX_LENGTH),
        config="english",
        weight="C",
    )
    + SearchVector(
        Left(Cast("authors", output_field=models.TextField()), SEARCH_AUTHORS_MAX_LENGTH),
        config="english",
        weight="C",
    )
    + SearchVector("main_source_title", config="english", weight="D")
)
# Used to rank the search results when we can't use the full text search of PostgreSQL. The weights
# mirror the ones of SEARCH_VECTOR.
FALLBACK_SEARCH_WEIGHTS = (
    ("title", 1.0),
    ("summary", 0.4),
    ("authors", 0.25),
    ("content", 0.2),
    ("main_source_title", 0.1),
)
DEFAULT_INDEXES = [
    models.Index(
        fields=["user", "is_read", "is_favorite", "is_for_later"],
    )
]


@dataclass(frozen=True)
class SaveArticleResult:
    article: Article
    article_id_in_data: str
    was_updated: bool = False
    was_created: bool = False
    is_from_invalid_data: bool = False


@dataclass(frozen=True)
class ArticlesTagsSearch:
    tag_ids_to_include: frozenset[int] = frozenset()
    include_tag_operator: constants.ReadingListTagOperator = constants.ReadingListTagOperator.ALL
    tag_ids_to_exclude: frozenset[int] = frozenset()
    exclude_tag_operator: constants.ReadingListTagOperator = constants.ReadingListTagOperator.ALL
    count_tags_to_include_alias: str = "count_tags_to_include"
    count_tags_to_exclude_alias: str = "count_tags_to_exclude"


class ArticleSearchQuery(Schema):
    model_config = ConfigDict(frozen=True)

    read_status: constants.ReadStatus = constants.ReadStatus.ALL
    favorite_status: constants.FavoriteStatus = constants.FavoriteStatus.ALL
    for_later_status: constants.ForLaterStatus = constants.ForLaterStatus.ALL
    articles_max_age_value: int = 0
    articles_max_age_unit: constants.ArticlesMaxAgeUnit = constants.ArticlesMaxAgeUnit.UNSET
    articles_reading_time: int = 0
    articles_reading_time_operator: constants.ArticlesReadingTimeOperator = (
        constants.ArticlesReadingTimeOperator.UNSET
    )

    @classmethod
    def from_reading_list(cls, reading_list: ReadingList):
        return cls(
            read_status=constants.ReadStatus(reading_list.read_status),
            favorite_status=constants.FavoriteStatus(reading_list.favorite_status),
            for_later_status=constants.ForLaterStatus(reading_list.for_later_status),
            articles_max_age_unit=constants.ArticlesMaxAgeUnit(reading_list.articles_max_age_unit),
            articles_max_age_value=reading_list.articles_max_age_value,
            articles_reading_time_operator=constants.ArticlesReadingTimeOperator(
                reading_list.articles_reading_time_operator
            ),
            articles_reading_time=reading_list.articles_reading_time,
        )


class ArticleFullTextSearchQuery(ArticleSearchQuery):
    q: str = ""
    search_type: constants.ArticleSearchType = constants.ArticleSearchType.PLAIN
    order: constants.ArticleSearchOrderBy = constants.ArticleSearchOrderBy.RANK_DESC
    linked_with_feeds: frozenset[int] = frozenset()
    external_tags_to_include: frozenset[str] = frozenset()

    @property
    def order_by(self) -> str:  # ruff:ignore[too-many-return-statements]
        match self.order:
            case constants.ArticleSearchOrderBy.RANK_DESC:
                return "-rank"
            case constants.ArticleSearchOrderBy.RANK_ASC:
                return "rank"
            case constants.ArticleSearchOrderBy.ARTICLE_SAVE_DATE_DESC:
                return "-obj_created_at"
            case constants.ArticleSearchOrderBy.ARTICLE_SAVE_DATE_ASC:
                return "obj_created_at"
            case constants.ArticleSearchOrderBy.ARTICLE_DATE_DESC:
                return "-published_at"
            case constants.ArticleSearchOrderBy.ARTICLE_DATE_ASC:
                return "published_at"
            case constants.ArticleSearchOrderBy.READ_AT_DESC:
                return "-read_at"
            case constants.ArticleSearchOrderBy.READ_AT_ASC:
                return "read_at"
            case _:
                assert_never(self.order)


def _build_order_by(order_by: str) -> tuple[models.OrderBy, models.OrderBy]:
    if order_by.startswith("-"):
        return (
            models.F(order_by.removeprefix("-")).desc(nulls_last=True),
            models.F("id").desc(),
        )

    return models.F(order_by).asc(nulls_last=True), models.F("id").desc()


def _build_fallback_rank(query: str) -> models.Expression:
    cases = [
        models.When(models.Q(**{f"{field}__icontains": query}), then=models.Value(weight))
        for field, weight in FALLBACK_SEARCH_WEIGHTS
    ]
    return models.Case(
        *cases,
        default=models.Value(0.0),
        output_field=models.FloatField(),
    )


def _build_basic_filters_from_reading_list(search_query: ArticleSearchQuery) -> models.Q:  # ruff:ignore[complex-structure, too-many-branches]
    filters = models.Q()

    match search_query.read_status:
        case constants.ReadStatus.ALL:
            pass
        case constants.ReadStatus.ONLY_READ:
            filters &= models.Q(is_read=True)
        case constants.ReadStatus.ONLY_UNREAD:
            filters &= models.Q(is_read=False)
        case _:
            assert_never(search_query.read_status)

    match search_query.favorite_status:
        case constants.FavoriteStatus.ALL:
            pass
        case constants.FavoriteStatus.ONLY_FAVORITE:
            filters &= models.Q(is_favorite=True)
        case constants.FavoriteStatus.ONLY_NON_FAVORITE:
            filters &= models.Q(is_favorite=False)
        case _:
            assert_never(search_query.favorite_status)

    match search_query.for_later_status:
        case constants.ForLaterStatus.ALL:
            pass
        case constants.ForLaterStatus.ONLY_FOR_LATER:
            filters &= models.Q(is_for_later=True)
        case constants.ForLaterStatus.ONLY_NOT_FOR_LATER:
            filters &= models.Q(is_for_later=False)
        case _:
            assert_never(search_query.for_later_status)

    if search_query.articles_max_age_unit != constants.ArticlesMaxAgeUnit.UNSET:
        filters &= models.Q(
            published_at__gt=utcnow()
            - relativedelta(**{  # type: ignore[arg-type]
                search_query.articles_max_age_unit.lower(): search_query.articles_max_age_value
            })
        )

    match search_query.articles_reading_time_operator:
        case constants.ArticlesReadingTimeOperator.UNSET:
            pass
        case constants.ArticlesReadingTimeOperator.MORE_THAN:
            filters &= models.Q(reading_time__gte=search_query.articles_reading_time)
        case constants.ArticlesReadingTimeOperator.LESS_THAN:
            filters &= models.Q(reading_time__lte=search_query.articles_reading_time)
        case _:
            assert_never(search_query.articles_reading_time_operator)

    return filters


def _build_tag_search_from_reading_list(reading_list: ReadingList) -> ArticlesTagsSearch:
    tag_ids_to_include = set()
    tag_ids_to_exclude = set()
    for reading_list_tag in reading_list.reading_list_tags.all():
        filter_type = constants.ReadingListTagFilterType(reading_list_tag.filter_type)
        match filter_type:
            case constants.ReadingListTagFilterType.INCLUDE:
                tag_ids_to_include.add(reading_list_tag.tag_id)
            case constants.ReadingListTagFilterType.EXCLUDE:
                tag_ids_to_exclude.add(reading_list_tag.tag_id)
            case _:
                assert_never(filter_type)

    return ArticlesTagsSearch(
        tag_ids_to_include=frozenset(tag_ids_to_include),
        include_tag_operator=constants.ReadingListTagOperator(reading_list.include_tag_operator),
        tag_ids_to_exclude=frozenset(tag_ids_to_exclude),
        exclude_tag_operator=constants.ReadingListTagOperator(reading_list.exclude_tag_operator),
        count_tags_to_include_alias=f"{reading_list.slug}_tag_count_include",
        count_tags_to_exclude_alias=f"{reading_list.slug}_tag_count_exclude",
    )


def _build_filter_by_tag_ids(
    qs: ArticleQuerySet, tags_search: ArticlesTagsSearch
) -> tuple[ArticleQuerySet, models.Q]:
    filters = models.Q()
    # Only count tags when needed: counting requires a join on tags and a GROUP BY on articles.
    aliases = {}

    if tags_search.tag_ids_to_include:
        aliases[tags_search.count_tags_to_include_alias] = models.Count(
            "tags", filter=models.Q(tags__id__in=tags_search.tag_ids_to_include)
        )
        match tags_search.include_tag_operator:
            case constants.ReadingListTagOperator.ALL:
                filters &= models.Q(**{
                    tags_search.count_tags_to_include_alias: len(tags_search.tag_ids_to_include)
                })
            case constants.ReadingListTagOperator.ANY:
                filters &= models.Q(**{f"{tags_search.count_tags_to_include_alias}__gte": 1})
            case _:
                assert_never(tags_search.include_tag_operator)

    if tags_search.tag_ids_to_exclude:
        aliases[tags_search.count_tags_to_exclude_alias] = models.Count(
            "tags", filter=models.Q(tags__id__in=tags_search.tag_ids_to_exclude)
        )
        match tags_search.exclude_tag_operator:
            case constants.ReadingListTagOperator.ALL:
                filters &= ~models.Q(**{
                    tags_search.count_tags_to_exclude_alias: len(tags_search.tag_ids_to_exclude)
                })
            case constants.ReadingListTagOperator.ANY:
                filters &= models.Q(**{tags_search.count_tags_to_exclude_alias: 0})
            case _:
                assert_never(tags_search.exclude_tag_operator)

    if aliases:
        qs = qs.alias(**aliases)

    return qs, filters


class ArticleQuerySet(models.QuerySet["Article"]):
    def for_user(self, user: User):
        return self.filter(user=user)

    def only_unread(self):
        return self.filter(is_read=False)

    def _filter_by_reading_list_tags(self, reading_list: ReadingList) -> Self:
        tags_search = _build_tag_search_from_reading_list(reading_list)
        return self._filter_by_tag_ids(tags_search)

    def _filter_by_tag_ids(self, tags_search: ArticlesTagsSearch):
        qs, filters = _build_filter_by_tag_ids(self, tags_search)
        return qs.filter(filters)

    def for_reading_list(self, reading_list: ReadingList) -> Self:
        return (
            self
            .for_user(reading_list.user)
            .filter(
                _build_basic_filters_from_reading_list(
                    ArticleSearchQuery.from_reading_list(reading_list)
                )
            )
            ._filter_by_reading_list_tags(reading_list)
            .select_related("main_feed")
            .prefetch_related("tags")
            .default_order_by(reading_list.order_direction)
        )

    def for_tag(self, tag: Tag) -> Self:
        return (
            self
            .filter(tags__id=tag.id)
            .select_related("main_feed")
            .prefetch_related("tags")
            .default_order_by()
        )

    def for_external_tag(self, tag: str) -> Self:
        return (
            self
            .filter(external_tags__icontains=tag)
            .prefetch_related("tags")
            .select_related("main_feed")
            .default_order_by()
        )

    def for_external_tags_search(self, tags: Iterable[str]) -> Self:
        filters = models.Q()
        for tag in tags:
            filters |= models.Q(external_tags__icontains=tag)

        return self.filter(filters)

    def for_feed(self) -> Self:
        return self.prefetch_related("tags").select_related("main_feed").default_order_by()

    def for_details(self) -> Self:
        return self.prefetch_related("tags", "comments").select_related("main_feed", "group")

    def for_export(self, user: User, *, updated_since: datetime | None = None) -> Self:
        qs = (
            self
            .for_user(user)
            .select_related("main_feed", "main_feed__category", "group")
            .prefetch_related("tags", "comments", "group__tags")
            .order_by("group_order", "id")
        )
        if updated_since:
            qs = qs.filter(
                models.Q(updated_at__gte=updated_since)
                | models.Q(comments__updated_at__gte=updated_since)
            )

        return qs

    def update_articles_from_action(self, action: constants.UpdateArticleActions):  # ruff:ignore[too-many-return-statements]
        # Remove order bys to allow UPDATE to work. Otherwise, Django will fail because it can't
        # resolve the alias_date_field_order field.
        update_qs = self.order_by()

        match action:
            case constants.UpdateArticleActions.DO_NOTHING:
                return 0
            case constants.UpdateArticleActions.MARK_AS_READ:
                return update_qs.filter(read_at__isnull=True).update(read_at=utcnow())
            case constants.UpdateArticleActions.MARK_AS_UNREAD:
                return update_qs.update(read_at=None)
            case constants.UpdateArticleActions.MARK_AS_FAVORITE:
                return update_qs.update(is_favorite=True)
            case constants.UpdateArticleActions.UNMARK_AS_FAVORITE:
                return update_qs.update(is_favorite=False)
            case constants.UpdateArticleActions.MARK_AS_FOR_LATER:
                return update_qs.update(is_for_later=True)
            case constants.UpdateArticleActions.UNMARK_AS_FOR_LATER:
                return update_qs.update(is_for_later=False)
            case constants.UpdateArticleActions.MARK_AS_OPENED:
                return update_qs.filter(opened_at__isnull=True).update(opened_at=utcnow())
            case _:
                assert_never(action)

    def default_order_by(
        self,
        order_direction: constants.ReadingListOrderDirection = constants.ReadingListOrderDirection.DESC,  # ruff:ignore[line-too-long]
    ) -> Self:
        order_expression = models.F("alias_date_field_order")
        match order_direction:
            case constants.ReadingListOrderDirection.ASC:
                order = order_expression.asc(nulls_last=True)
            case constants.ReadingListOrderDirection.DESC:
                order = order_expression.desc(nulls_last=True)
            case _:
                assert_never(order_direction)

        return self.alias(
            alias_date_field_order=Coalesce(models.F("updated_at"), models.F("published_at"))
        ).order_by(order, models.F("id").desc())

    def for_deletion(self) -> Self:
        return self.prefetch_related("feed_articles", "feed_articles__feed")

    def for_cleanup(self) -> Self:
        return (
            self
            .for_deletion()
            .alias(
                min_feed_retention_time=models.Min("feeds__article_retention_time"),
                # Let's keep the article until the last feed says it's time to collect.
                feed_retention_time=models.Max("feeds__article_retention_time"),
                article_cleanup_time=models.ExpressionWrapper(
                    ExtractEpoch("read_at")
                    + (
                        # This time is stored in days in the database. Convert it to seconds to add
                        # it to the read at time stamp.
                        models.F("feed_retention_time")
                        * models.Value(
                            24,
                            output_field=models.IntegerField(),
                        )
                        * models.Value(60, output_field=models.IntegerField())
                        * models.Value(60, output_field=models.IntegerField())
                    ),
                    output_field=models.IntegerField(),
                ),
            )
            .filter(
                is_read=True,
                feed_retention_time__isnull=False,
                feed_retention_time__gt=0,
                # If the min retention time is 0, it means at least one feed requires us to keep
                # the article forever.
                min_feed_retention_time__gt=0,
                article_cleanup_time__lt=utcnow().timestamp(),
                main_source_type=constants.ArticleSourceType.FEED,
            )
        )

    def for_search(self, search_query: ArticleFullTextSearchQuery) -> Self:
        if connection.vendor == "postgresql":
            full_text_search_query = SearchQuery(
                search_query.q,
                search_type=search_query.search_type.value,
                config="english",
            )
            return self.annotate(
                rank=SearchRank(models.F("search_vector"), full_text_search_query)
            ).filter(search_vector=full_text_search_query)

        return self.annotate(rank=_build_fallback_rank(search_query.q)).filter(rank__gt=0)

    def with_placeholder_rank(self):
        return self.annotate(rank=models.Value(0.0))

    def for_url_search(self, urls: list[str]) -> Self:
        filters = models.Q()
        for url in urls:
            filters |= models.Q(url=url)

        return self.filter(filters)

    def for_api(self):
        return self.prefetch_related("tags", "group__tags").select_related("group")


class ArticleManager(models.Manager["Article"]):
    _hints: dict

    def get_queryset(self) -> ArticleQuerySet:
        qs = ArticleQuerySet(model=self.model, using=self._db, hints=self._hints)
        if connection.vendor == "postgresql":
            # The search vector is only used to search articles. Don't load it otherwise.
            qs = qs.defer("search_vector")  # type: ignore[misc]
        return qs

    @transaction.atomic()
    def save_from_list_of_data(
        self,
        user: User,
        articles_data: list[ArticleData],
        tags: Iterable[Tag],
        *,
        initial_main_feed_id: int | None = None,
        force_update: bool = False,
    ) -> list[SaveArticleResult]:
        initial_source_type = (
            constants.ArticleSourceType.FEED
            if initial_main_feed_id
            else constants.ArticleSourceType.MANUAL
        )

        if len(articles_data) == 0:
            return []

        existing_urls_to_articles = {
            article.url: article
            for article in self
            .get_queryset()
            .filter(user=user, url__in=[article_data.url for article_data in articles_data])
            .select_related("user", "user__settings")
        }
        articles_to_create: list[SaveArticleResult] = []
        articles_to_update: list[SaveArticleResult] = []
        seen_urls = set()
        for article_data in articles_data:
            if article_data.url in seen_urls:
                continue

            seen_urls.add(article_data.url)
            if article_data.url in existing_urls_to_articles:
                article_to_update = existing_urls_to_articles[article_data.url]
                was_updated = article_to_update.update_article_from_data(
                    article_data, force_update=force_update
                )
                if initial_source_type == constants.ArticleSourceType.MANUAL:
                    if article_to_update.main_source_type == constants.ArticleSourceType.FEED:
                        # We force the source type to manual if we manually add it so prevent any
                        # cleanup later one.
                        article_to_update.main_source_type = constants.ArticleSourceType.MANUAL
                    was_updated = True
                    article_to_update.obj_updated_at = utcnow()
                articles_to_update.append(
                    SaveArticleResult(
                        article=article_to_update,
                        # Current article.external_article_id can be different from the one saved
                        # in db. If the article was manually added, it may even be empty.
                        # Don't update the article just for that: too complex for very little
                        # gain. Use this mapping to preserve the id in further processing.
                        article_id_in_data=article_data.external_article_id,
                        was_updated=was_updated,
                    )
                )
            else:
                article_to_create = self.model(
                    user=user,
                    external_article_id=article_data.external_article_id,
                    title=article_data.title,
                    slug=slugify(article_data.title),
                    summary=article_data.summary,
                    content=article_data.content,
                    content_type=article_data.content_type,
                    table_of_content=article_data.table_of_content,
                    reading_time=get_nb_words_from_html(article_data.content)
                    // user.settings.default_reading_time,
                    authors=article_data.authors,
                    contributors=article_data.contributors,
                    external_tags=article_data.tags,
                    url=article_data.url,
                    preview_picture_url=article_data.preview_picture_url,
                    preview_picture_alt=article_data.preview_picture_alt,
                    published_at=article_data.published_at,
                    updated_at=article_data.updated_at,
                    main_source_type=initial_source_type,
                    main_source_title=article_data.source_title,
                    main_feed_id=initial_main_feed_id,
                    language=article_data.language,
                    annotations=article_data.annotations,
                    read_at=article_data.read_at,
                    is_favorite=article_data.is_favorite,
                )
                articles_to_create.append(
                    SaveArticleResult(
                        article=article_to_create,
                        article_id_in_data=article_data.external_article_id,
                        was_created=True,
                    )
                )

        self.bulk_create(
            [result.article for result in articles_to_create], unique_fields=["user", "url"]
        )
        ArticleTag.objects.associate_articles_with_tags(
            [result.article for result in articles_to_create], tags
        )

        self.bulk_update(
            [result.article for result in articles_to_update if result.was_updated],
            fields=[
                "title",
                "slug",
                "summary",
                "content",
                "content_type",
                "table_of_content",
                "reading_time",
                "authors",
                "preview_picture_url",
                "preview_picture_alt",
                "contributors",
                "external_tags",
                "updated_at",
                "read_at",
                "main_source_type",
                "obj_updated_at",
            ],
        )

        all_results = []
        for result in chain(articles_to_create, articles_to_update):
            all_results.append(result)

        return all_results

    @transaction.atomic()
    def save_from_fetch_results(
        self,
        user: User,
        fetch_article_results: list[FetchArticleResult],
        tags: Iterable[Tag],
        *,
        force_update: bool = False,
    ) -> list[SaveArticleResult]:
        """Save articles from a list of FetchArticleResult objects.

        The returned list[SaveArticleResult] may not match the order of the inputs.
        """
        valid_articles_data = []
        invalid_fetch_results = []
        for fetch_result in fetch_article_results:
            if fetch_result.is_success:
                valid_articles_data.append(fetch_result.article_data)
            else:
                invalid_fetch_results.append(fetch_result)

        valid_saved_results = []
        if valid_articles_data:
            valid_saved_results = self.save_from_list_of_data(
                user,
                valid_articles_data,
                tags,
                force_update=force_update,
            )

        invalid_saved_results = []
        if invalid_fetch_results:
            invalid_saved_results = self._create_invalid_articles(user, invalid_fetch_results, tags)

        return [*valid_saved_results, *invalid_saved_results]

    def _create_invalid_articles(
        self,
        user: User,
        fetch_article_results: list[FetchArticleResult],
        tags: Iterable[Tag],
    ) -> list[SaveArticleResult]:
        """Force the creation of articles with only their URLs.

        Used to save an article when data fetching failed. Data about the failure is also saved for
        debugging purposes. This debugging data is cleaned up by the clean_data command after some
        time.

        If the article already exists, its content, title and summary won't be updated. Its tags
        will and debugging data will be saved.
        """
        article_urls_to_articles = {
            article.url: article
            for article in self.get_queryset().filter(
                user=user, url__in=[fetch_result.url for fetch_result in fetch_article_results]
            )
        }
        existing_article_urls = set(article_urls_to_articles.keys())
        articles_to_create = []
        for fetch_result in fetch_article_results:
            if fetch_result.url in existing_article_urls:
                continue

            article = self.model(
                user=user,
                url=fetch_result.url,
                main_source_title=fetch_result.article_data.source_title,
                main_source_type=constants.ArticleSourceType.MANUAL,
                title=fetch_result.article_data.title,
                slug=slugify(fetch_result.article_data.title),
                content=fetch_result.article_data.content,
                content_type=fetch_result.article_data.content_type,
                summary=fetch_result.article_data.summary,
            )
            articles_to_create.append(article)
            article_urls_to_articles[fetch_result.url] = article

        self.bulk_create(articles_to_create, unique_fields=["user", "url"])
        ArticleTag.objects.associate_articles_with_tags(articles_to_create, tags)

        article_fetch_errors_to_create = [
            ArticleFetchError(
                article=article_urls_to_articles[fetch_result.url],
                message=fetch_result.error_message,
                technical_debug_data=fetch_result.technical_debug_data,
            )
            for fetch_result in fetch_article_results
        ]
        ArticleFetchError.objects.bulk_create(article_fetch_errors_to_create)

        return [
            SaveArticleResult(
                article=article,
                article_id_in_data=article.external_article_id,
                was_created=article.url not in existing_article_urls,
                was_updated=False,
                is_from_invalid_data=True,
            )
            for article in article_urls_to_articles.values()
        ]

    def get_articles_of_reading_list(self, reading_list: ReadingList) -> ArticleQuerySet:
        return self.get_queryset().for_reading_list(reading_list)

    def count_unread_articles_of_reading_lists(
        self, user: User, reading_lists: list[ReadingList]
    ) -> dict[str, int]:
        # We only count unread articles in the reading list. Not all articles. I think it's more
        # relevant.
        aggregations = {}
        qs = self.get_queryset().for_user(user).only_unread()

        for reading_list in reading_lists:
            tags_search = _build_tag_search_from_reading_list(reading_list)
            qs, filters = _build_filter_by_tag_ids(qs, tags_search)

            aggregations[reading_list.slug] = models.Count(
                "id",
                filter=_build_basic_filters_from_reading_list(
                    ArticleSearchQuery.from_reading_list(reading_list)
                )
                & filters,
            )

        return qs.aggregate(**aggregations)

    def get_articles_of_tag(self, tag: Tag) -> ArticleQuerySet:
        return self.get_queryset().for_tag(tag)

    def get_articles_with_external_tag(self, user: User, tag: str) -> ArticleQuerySet:
        return self.get_queryset().for_user(user).for_external_tag(tag)

    def export(self, user: User, *, updated_since: datetime | None = None):
        articles_qs = self.get_queryset().for_export(user, updated_since=updated_since)
        paginator = Paginator(articles_qs, constants.MAX_EXPORT_ARTICLES_PER_PAGE)
        for page_index in paginator.page_range:
            page = paginator.page(page_index)
            articles = []
            for article in page.object_list:
                articles.append({
                    "group_id": article.group.id if article.group else "",
                    "group_title": article.group.title if article.group else "",
                    "group_description": article.group.description if article.group else "",
                    "group_tags": json.dumps([tag.title for tag in article.group.tags.all()])
                    if article.group
                    else "[]",
                    "category_id": article.main_feed.category_id if article.main_feed else "",
                    "category_title": article.main_feed.category.title
                    if article.main_feed and article.main_feed.category
                    else "",
                    "feed_id": article.main_feed_id or "",
                    "feed_title": article.main_feed.title if article.main_feed else "",
                    "feed_url": article.main_feed.feed_url if article.main_feed else "",
                    "feed_site_url": article.main_feed.site_url if article.main_feed else "",
                    "article_id": article.id,
                    "article_title": article.title,
                    "article_url": article.url,
                    "article_content": article.content,
                    "article_content_type": article.content_type,
                    "article_date_published": article.published_at.isoformat()
                    if article.published_at
                    else "",
                    "article_date_updated": article.updated_at.isoformat()
                    if article.updated_at
                    else "",
                    "article_authors": json.dumps(article.authors) if article.authors else "",
                    "article_tags": json.dumps([tag.title for tag in article.tags.all()]),
                    "article_read_at": article.read_at.isoformat() if article.read_at else "",
                    "article_is_favorite": article.is_favorite,
                    "article_lang": article.language,
                    "article_comments": json.dumps([
                        comment.text for comment in article.comments.all()
                    ]),
                })

            yield articles

    def search(
        self,
        user: User,
        search_query: ArticleFullTextSearchQuery,
        tags_search: ArticlesTagsSearch | None = None,
    ) -> ArticleQuerySet:
        articles_qs = (
            self
            .get_queryset()
            .for_user(user)
            .select_related("main_feed")
            .prefetch_related("tags")
            .filter(_build_basic_filters_from_reading_list(search_query))
        )

        if tags_search:
            articles_qs = articles_qs._filter_by_tag_ids(tags_search)

        if search_query.linked_with_feeds:
            articles_qs = articles_qs.filter(feeds__id__in=search_query.linked_with_feeds)

        if search_query.external_tags_to_include:
            articles_qs = articles_qs.for_external_tags_search(
                search_query.external_tags_to_include
            )

        if search_query.search_type == constants.ArticleSearchType.URL:
            articles_qs = articles_qs.for_url_search([search_query.q]).with_placeholder_rank()
        elif search_query.q:
            articles_qs = articles_qs.for_search(search_query)
        else:
            articles_qs = articles_qs.with_placeholder_rank()

        return articles_qs.order_by(*_build_order_by(search_query.order_by))

    def cleanup_articles(self):
        return self.get_queryset().for_cleanup().delete()

    def link_articles_to_group(
        self, group: ArticlesGroup, articles: Iterable[Article]
    ) -> tuple[Article, ...]:
        """Link supplied articles to the given group.

        If any of the supplied articles are already linked to another group, they are not linked
        again and remain in their original group. These articles are returned.

        The newly linked articles have a group_order higher than the highest group_order of the
        articles in the group.
        """
        articles_already_linked_to_other_group = tuple(
            article
            for article in self
            .get_queryset()
            .filter(id__in=[article.id for article in articles], group__isnull=False)
            .exclude(group=group)
        )
        max_group_order = group.articles.aggregate(
            max_group_order=Coalesce(models.Max("group_order"), 0)
        )["max_group_order"]
        articles_to_update = []
        for order, article in enumerate(articles, start=max_group_order + 1):
            if article in articles_already_linked_to_other_group:
                continue

            article.group = group
            article.group_order = order
            articles_to_update.append(article)

        self.bulk_update(
            articles_to_update,
            fields=(
                "group",
                "group_order",
            ),
        )

        return articles_already_linked_to_other_group

    @transaction.atomic()
    def reorder_in_group(self, group: ArticlesGroup, new_order: dict[int, int]):
        articles = group.articles.all()
        max_new_order_value = max(new_order.values())
        group_order_articles_not_in_mapping = max_new_order_value + 1

        for article in articles:
            if article.id in new_order:
                article.group_order = new_order[article.id]
            else:
                article.group_order = group_order_articles_not_in_mapping
                group_order_articles_not_in_mapping += 1

        # Change order to prevent unicity conflicts on (group, group_order)
        # Just setting group_order to id can cause unicity conflicts on on sqlite because of how it
        # handles bulk_update.
        group.articles.all().update(
            group_order=models.F("id") + group_order_articles_not_in_mapping
        )

        self.bulk_update(articles, fields=["group_order"])


class Article(models.Model):
    title = models.CharField(max_length=constants.ARTICLE_TITLE_MAX_LENGTH)
    slug = models.SlugField(max_length=constants.ARTICLE_TITLE_MAX_LENGTH)
    summary = models.TextField(blank=True)
    content = models.TextField(blank=True)
    content_type = models.CharField(
        choices=[(content_type, content_type) for content_type in CONTENT_TYPES],
        max_length=50,
        default="text/html",
    )
    reading_time = models.PositiveIntegerField(
        default=0,
        help_text=_(
            "How much time in minutes is needed to read this article. If not specified, "
            "it will be calculated automatically from content length. If we don't have content, "
            "we will use 0."
        ),
    )
    authors = models.JSONField(validators=[list_of_strings_validator], blank=True, default=list)
    contributors = models.JSONField(
        validators=[list_of_strings_validator], blank=True, default=list
    )
    url = models.URLField(max_length=1_024)
    preview_picture_url = models.URLField(blank=True, max_length=1_024)
    preview_picture_alt = models.TextField(blank=True)
    external_tags = models.JSONField(
        validators=[list_of_strings_validator],
        blank=True,
        default=list,
        help_text=_("Tags of the article from its source"),
    )
    external_article_id = models.CharField(
        default="",
        blank=True,
        max_length=constants.EXTERNAL_ARTICLE_ID_MAX_LENGTH,
        help_text=_("The id of the article in its source."),
    )
    annotations = models.JSONField(
        blank=True,
        default=list,
        help_text=_(
            "Annotations made to the article. Currently only used for data imports to prevent data "
            "loss."
        ),
    )
    language = models.CharField(
        default="",
        blank=True,
        max_length=constants.LANGUAGE_CODE_MAX_LENGTH,
        help_text=_("The language code for this article"),
        validators=[language_code_validator],
    )
    table_of_content = models.JSONField(
        validators=[table_of_content_validator],
        blank=True,
        default=list,
        help_text=_("The table of content of the article."),
        encoder=CustomJsonEncoder,
    )

    read_at = models.DateTimeField(null=True, blank=True)
    is_read = models.GeneratedField(
        expression=models.Case(
            models.When(models.Q(read_at__isnull=True), then=False),
            default=True,
        ),
        output_field=models.BooleanField(),
        db_persist=True,
    )
    opened_at = models.DateTimeField(null=True, blank=True)
    was_opened = models.GeneratedField(
        expression=models.Case(
            models.When(models.Q(opened_at__isnull=True), then=False),
            default=True,
        ),
        output_field=models.BooleanField(),
        db_persist=True,
    )
    is_favorite = models.BooleanField(default=False)
    is_for_later = models.BooleanField(default=False)

    user = models.ForeignKey("users.User", related_name="articles", on_delete=models.CASCADE)

    main_source_type = models.CharField(
        default=constants.ArticleSourceType.FEED,
        choices=constants.ArticleSourceType.choices,
        max_length=100,
    )
    main_source_title = models.CharField(max_length=constants.ARTICLE_SOURCE_TITLE_MAX_LENGTH)
    main_feed = models.ForeignKey(
        "feeds.Feed",
        related_name="articles_main_feed",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    group = models.ForeignKey(
        "reading.ArticlesGroup",
        related_name="articles",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    group_order = models.PositiveIntegerField(default=0, help_text=_("Order in the group"))

    published_at = models.DateTimeField(
        null=True, blank=True, help_text=_("The date of publication of the article.")
    )
    updated_at = models.DateTimeField(
        null=True, blank=True, help_text=_("The last time the article was updated.")
    )
    obj_created_at = models.DateTimeField(
        auto_now_add=True,
        help_text=_("Technical date for the creation of the article in the database."),
    )
    obj_updated_at = models.DateTimeField(
        auto_now=True,
        help_text=_("Technical date for the last update of the article in the database."),
    )
    if connection.vendor == "postgresql":
        # Stored to avoid computing the vector of each article on each search.
        search_vector = models.GeneratedField(
            expression=SEARCH_VECTOR,
            output_field=SearchVectorField(),
            db_persist=True,
        )

    objects = ArticleManager()

    class Meta(TypedModelMeta):
        ordering = ["-updated_at", "-published_at", "id"]
        constraints = [
            models.UniqueConstraint(
                "user", "url", name="%(app_label)s_%(class)s_article_unique_for_user"
            ),
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_main_source_type_valid",
                condition=models.Q(
                    main_source_type__in=constants.ArticleSourceType.names,
                ),
            ),
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_content_type_valid",
                condition=models.Q(
                    content_type__in=["application/xhtml+xml", "text/html", "text/plain"]
                ),
            ),
            models.UniqueConstraint(
                "group", "group_order", name="%(app_label)s_%(class)s_group_order_unique"
            ),
        ]
        if connection.vendor == "postgresql":
            indexes = [
                *DEFAULT_INDEXES,
                GinIndex(
                    fields=["search_vector"],
                    name="%(app_label)s_%(class)s_search_vector",
                ),
            ]
        else:
            indexes = DEFAULT_INDEXES

    def __str__(self):
        return (
            f"Article(title={self.title}, main_source_type={self.main_source_type}, "
            f"main_source_title={self.main_source_title}, published_at={self.published_at})"
        )

    def save(self, *args, **kwargs):
        self.slug = self.slug or slugify(self.title) or str(_("no-slug"))

        return super().save(*args, **kwargs)

    def update_article_from_data(
        self, article_data: ArticleData, *, force_update: bool = False
    ) -> bool:
        is_more_recent = (
            self.updated_at is None
            or article_data.updated_at is None
            or article_data.updated_at > self.updated_at
        )
        has_content_unlike_saved = bool(article_data.content) and not bool(self.content)
        if not is_more_recent and not has_content_unlike_saved and not force_update:
            return False

        if is_more_recent or force_update:
            # We don't update the title (nor the slug) automatically since it could have been
            # updated manually. It's also useful to spot an article (and avoids weird redirection
            # on refresh).
            self.summary = article_data.summary or self.summary
            self.content = article_data.content or self.content
            self.table_of_content = article_data.table_of_content or self.table_of_content
            # Reading time could have been updated manually. Let's update it only if it's 0.
            self.reading_time = self.reading_time or (
                get_nb_words_from_html(self.content) // self.user.settings.default_reading_time
            )
            self.preview_picture_url = article_data.preview_picture_url or self.preview_picture_url
            self.preview_picture_alt = article_data.preview_picture_alt or self.preview_picture_alt
            # We create the deduplicated list with dict.fromkeys and not sets to preserve the
            # initial order. We chain the iterable since they don't have the same type.
            self.authors = list(dict.fromkeys(chain(self.authors, article_data.authors)))
            self.contributors = list(
                dict.fromkeys(chain(self.contributors, article_data.contributors))
            )
            self.external_tags = list(dict.fromkeys(chain(self.external_tags, article_data.tags)))
            self.updated_at = max_or_none([article_data.updated_at, self.updated_at])
            self.published_at = min_or_none([article_data.published_at, self.published_at])
        elif has_content_unlike_saved:
            self.content = article_data.content
            self.table_of_content = article_data.table_of_content

        self.content_type = article_data.content_type
        self.obj_updated_at = utcnow()

        return True

    def update_from_details(self, *, title: str, summary: str, reading_time: int):
        self.title = title
        self.summary = summary
        self.reading_time = reading_time

    @cached_property
    def next_article_of_group(self) -> Article | None:
        if self.group_id is None:
            return None
        return (
            self.group.articles  # type: ignore[union-attr]
            .filter(group_order__gt=self.group_order)
            .order_by("group_order")
            .first()
        )

    @cached_property
    def previous_article_of_group(self) -> Article | None:
        if self.group_id is None:
            return None
        return (
            self.group.articles  # type: ignore[union-attr]
            .filter(group_order__lt=self.group_order)
            .order_by("group_order")
            .last()
        )
