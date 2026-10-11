# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from datetime import datetime
from http import HTTPStatus
from typing import Annotated, Self
from urllib.parse import urlparse

from django.conf import settings
from django.db import connection, transaction
from django.shortcuts import get_object_or_404
from django.urls import reverse
from ninja import Field, ModelSchema, Query, Router, Schema, Status
from ninja.errors import ValidationError as NinjaValidationError
from ninja.pagination import paginate
from pydantic import field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

from legadilo.core.utils.api import ApiError, NotSet, update_model_from_schema
from legadilo.core.utils.validators import (
    CleanedString,
    ContentType,
    ValidUrlValidator,
    remove_falsy_items,
)
from legadilo.reading.models import Article, ArticlesGroup, ArticleTag, Comment, ReadingList, Tag
from legadilo.reading.models.article import ArticleFullTextSearchQuery
from legadilo.reading.services.article_fetching import (
    FetchArticleResult,
    Language,
    build_article_data_from_content,
    fetch_article_data,
)
from legadilo.reading.services.articles_groups import update_article_group
from legadilo.users.models import User
from legadilo.users.user_types import AuthenticatedApiRequest

reading_api_router = Router(tags=["reading"])


class OutTagSchema(ModelSchema):
    class Meta:
        model = Tag
        fields = ("title", "slug")


class OutCommentSchema(ModelSchema):
    class Meta:
        model = Comment
        fields = ("text", "created_at", "updated_at")


class OutArticlesGroupSchema(ModelSchema):
    details_url: str
    tags: list[OutTagSchema]

    @staticmethod
    def resolve_details_url(obj, context) -> str:
        if obj is None:
            return ""

        url = reverse(
            "reading:articles_group_details", kwargs={"group_id": obj.id, "group_slug": obj.slug}
        )
        return context["request"].build_absolute_uri(url)

    class Meta:
        model = ArticlesGroup
        exclude = ("user", "created_at", "updated_at")


class OutArticleSchema(ModelSchema):
    tags: list[OutTagSchema]
    comments: list[OutCommentSchema]
    details_url: str
    group: OutArticlesGroupSchema | None

    @staticmethod
    def resolve_details_url(obj, context) -> str:
        url = reverse(
            "reading:article_details", kwargs={"article_id": obj.id, "article_slug": obj.slug}
        )
        return context["request"].build_absolute_uri(url)

    class Meta:
        model = Article
        exclude = (
            "user",
            "obj_created_at",
            "obj_updated_at",
            # Only exists on PostgreSQL and is only used to search articles.
            *(("search_vector",) if connection.vendor == "postgresql" else ()),
        )


class ArticleCreation(Schema):
    url: Annotated[str, ValidUrlValidator]
    title: CleanedString = ""
    # We must not sanitize this yet: we need the raw content when building the article to fetch some
    # data (like authors, canonicals…). It will be sanitized later when we extract the actual
    # content of the article.
    content: str = ""
    language: Language = ""
    content_type: ContentType = "text/html"
    tags: Annotated[tuple[CleanedString, ...], remove_falsy_items(tuple)] = ()
    group_id: int | CleanedString | None = Field(
        default=None,
        description="Id (int) or slug (str) of the group. Leave empty or set to null to not link "
        "the article to any group",
    )
    must_extract_content: bool = Field(
        default=True,
        description="Whether to extract content. It must be true if content is the full HTML of "
        "the page to let the backend extract the content of the article. It must be false if "
        "content is the extracted content of the article and must be saved directly.",
    )

    @field_validator("url", mode="after")
    @classmethod
    def check_url_is_not_from_instance(cls, value: str) -> str:
        domain = urlparse(value).netloc
        if domain in settings.ALLOWED_HOSTS:
            raise ValueError("The URL cannot be from the instance.")

        return value

    @model_validator(mode="after")
    def check_title_and_content(self) -> Self:
        if len(self.title) == 0 and len(self.content) > 0:
            raise ValueError("Title is mandatory when content is provided.")

        return self

    @property
    def has_data(self) -> bool:
        return bool(self.title)


@reading_api_router.post(
    "/articles/",
    response={
        HTTPStatus.CREATED: OutArticleSchema,
        HTTPStatus.OK: OutArticleSchema,
        HTTPStatus.BAD_REQUEST: ApiError,
    },
    url_name="create_article",
    summary="Create a new article",
)
def create_article_view(request: AuthenticatedApiRequest, payload: ArticleCreation):
    """Create an article either just with a link or with a link, a title and some content."""
    fetch_article_result = _get_article_data(payload)
    if not fetch_article_result.is_success:
        return Status(
            HTTPStatus.BAD_REQUEST,
            {"detail": f"Failed to fetch article data: {fetch_article_result.error_message}"},
        )

    with transaction.atomic():
        tags = Tag.objects.get_or_create_from_list(request.auth, payload.tags)
        save_results = Article.objects.save_from_fetch_results(
            request.auth,
            [fetch_article_result],
            tags,
        )
        if group := _get_group(request.auth, payload.group_id):
            Article.objects.link_articles_to_group(group, [save_results[0].article])

    save_result = save_results[0]
    article = Article.objects.get_queryset().for_api().get(id=save_result.article.id)

    if save_result.was_created:
        return Status(HTTPStatus.CREATED, article)

    return Status(HTTPStatus.OK, article)


def _get_group(user: User, group_id: int | str | None) -> ArticlesGroup | None:
    # If the group id is None or an empty slug, the group must not be created.
    if not group_id:
        return None

    if isinstance(group_id, str):
        return ArticlesGroup.objects.get_or_create_from_slug(user, group_id)

    try:
        return ArticlesGroup.objects.get(id=group_id, user=user)
    except ArticlesGroup.DoesNotExist as e:
        raise NinjaValidationError([
            {"group_id": f"Failed to find the group with id: {group_id}"}
        ]) from e


def _get_article_data(payload: ArticleCreation) -> FetchArticleResult:
    if payload.has_data:
        article_data = build_article_data_from_content(
            url=payload.url,
            title=payload.title,
            content=payload.content,
            content_type=payload.content_type,
            content_language=payload.language,
            must_extract_content=payload.must_extract_content,
        )
        return FetchArticleResult(article_data=article_data)
    return fetch_article_data(payload.url)


@reading_api_router.get(
    "/articles/",
    response={HTTPStatus.OK: list[OutArticleSchema]},
    url_name="list_articles",
    summary="List articles",
)
@paginate
def list_articles_view(request: AuthenticatedApiRequest, query: Query[ArticleFullTextSearchQuery]):
    return Article.objects.search(request.auth, query)


@reading_api_router.get(
    "/articles/{int:article_id}/",
    url_name="get_article",
    response=OutArticleSchema,
    summary="View the details of a specific article",
)
def get_article_view(request: AuthenticatedApiRequest, article_id: int) -> Article:
    return get_object_or_404(
        Article.objects.get_queryset().for_api(), id=article_id, user=request.auth
    )


class ArticleUpdate(Schema):
    title: CleanedString | SkipJsonSchema[NotSet] = NotSet(str)
    tags: (
        Annotated[tuple[CleanedString, ...], remove_falsy_items(tuple)] | SkipJsonSchema[NotSet]
    ) = NotSet(tuple)
    group_id: int | str | NotSet | None = Field(
        default=NotSet(int),
        description="Id (int) or slug (str) of the group. Leave empty or set to null to not link "
        "the article to any group",
    )
    read_at: datetime | SkipJsonSchema[NotSet] | None = NotSet(datetime.now)
    is_favorite: bool | SkipJsonSchema[NotSet] = NotSet(bool)
    is_for_later: bool | SkipJsonSchema[NotSet] = NotSet(bool)
    reading_time: int | SkipJsonSchema[NotSet] = NotSet(int)


@reading_api_router.patch(
    "/articles/{int:article_id}/",
    response=OutArticleSchema,
    url_name="update_article",
    summary="Update an article",
)
@transaction.atomic()
def update_article_view(
    request: AuthenticatedApiRequest,
    article_id: int,
    payload: ArticleUpdate,
) -> Article:
    article = get_object_or_404(Article, id=article_id, user=request.auth)

    if not isinstance(payload.tags, NotSet):
        _update_article_tags(request.auth, article, payload.tags)

    excluded_fields = {"tags"}
    if not isinstance(payload.group_id, NotSet):
        excluded_fields.add("group_id")
        # Use get group to check if the group exists and return the proper error message if not.
        group = _get_group(request.auth, payload.group_id)
        update_article_group(article, group.slug if group else None)

    update_model_from_schema(article, payload, excluded_fields=excluded_fields)

    return Article.objects.get_queryset().for_api().get(id=article_id)


def _update_article_tags(user: User, article: Article, new_tags: tuple[str, ...]):
    tags = Tag.objects.get_or_create_from_list(user, new_tags)
    ArticleTag.objects.associate_articles_with_tags([article], tags)
    ArticleTag.objects.dissociate_article_with_tags_not_in_list(article, tags)


@reading_api_router.delete(
    "/articles/{int:article_id}/",
    url_name="delete_article",
    response={HTTPStatus.NO_CONTENT: None},
    summary="Delete an article",
)
def delete_article_view(request: AuthenticatedApiRequest, article_id: int):
    article = get_object_or_404(Article, id=article_id, user=request.auth)

    article.delete()

    return Status(HTTPStatus.NO_CONTENT, None)


class OutTagWithHierarchySchema(OutTagSchema):
    sub_tags: list[OutTagSchema]


@reading_api_router.get(
    "/tags/",
    url_name="list_tags",
    summary="List tags",
    response={HTTPStatus.OK: list[OutTagWithHierarchySchema]},
)
@paginate
def list_tags_view(request: AuthenticatedApiRequest):
    return Tag.objects.get_queryset().for_user(request.auth).for_api()


@reading_api_router.get(
    "/articles-groups/",
    url_name="list_articles_groups",
    summary="List articles groups",
    response={HTTPStatus.OK: list[OutArticlesGroupSchema]},
)
@paginate
def list_articles_groups_view(request: AuthenticatedApiRequest):
    return ArticlesGroup.objects.get_queryset().for_user(request.auth).for_api()


class ReadingListReorderPayload(Schema):
    order: dict[int, int]


@reading_api_router.post(
    "/lists/reorder/",
    url_name="reorder_reading_lists",
    summary="Reorder reading lists. Provide a mapping of reading list id to new order.",
    response={HTTPStatus.NO_CONTENT: None},
)
def reorder_reading_lists_view(
    request: AuthenticatedApiRequest, payload: ReadingListReorderPayload
):
    ReadingList.objects.reorder(request.auth, payload.order)

    return Status(HTTPStatus.NO_CONTENT, None)
