# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later
from functools import lru_cache

from django.template.defaultfilters import stringfilter
from django.template.defaulttags import register
from django.urls import reverse
from django.utils.safestring import mark_safe
from markdown_it import MarkdownIt

from legadilo.core.utils.security import sanitize_keep_safe_tags
from legadilo.reading import constants
from legadilo.reading.models import Article, ArticlesGroup, ReadingList


@register.filter
def read_action_url(article: Article) -> str:
    action = (
        constants.UpdateArticleActions.MARK_AS_UNREAD
        if article.is_read
        else constants.UpdateArticleActions.MARK_AS_READ
    )
    return reverse(
        "reading:update_article", kwargs={"article_id": article.id, "update_action": action}
    )


@register.filter
def favorite_action_url(article: Article) -> str:
    action = (
        constants.UpdateArticleActions.UNMARK_AS_FAVORITE
        if article.is_favorite
        else constants.UpdateArticleActions.MARK_AS_FAVORITE
    )
    return reverse(
        "reading:update_article", kwargs={"article_id": article.id, "update_action": action}
    )


@register.filter
def for_later_action_url(article: Article) -> str:
    action = (
        constants.UpdateArticleActions.UNMARK_AS_FOR_LATER
        if article.is_for_later
        else constants.UpdateArticleActions.MARK_AS_FOR_LATER
    )

    return reverse(
        "reading:update_article", kwargs={"article_id": article.id, "update_action": action}
    )


@register.filter
def opened_action_url(article: Article) -> str:
    return reverse(
        "reading:update_article",
        kwargs={
            "article_id": article.id,
            "update_action": constants.UpdateArticleActions.MARK_AS_OPENED,
        },
    )


@register.filter
def article_details_url(article: Article) -> str:
    return reverse(
        "reading:article_details", kwargs={"article_id": article.id, "article_slug": article.slug}
    )


@register.filter
def articles_group_details_url(group: ArticlesGroup) -> str:
    return reverse(
        "reading:articles_group_details", kwargs={"group_id": group.id, "group_slug": group.slug}
    )


@register.filter
def reading_list_url(reading_list: ReadingList) -> str:
    if reading_list.is_default:
        return reverse("reading:default_reading_list")

    return reverse("reading:reading_list", kwargs={"reading_list_slug": reading_list.slug})


@register.filter
def article_action_indicator(article: Article) -> str:
    return f"icon-indicator-{article.id}"


@register.filter
def article_card_id(article: Article) -> str:
    return f"article-card-{article.id}"


@register.filter
def delete_article_form_id(article: Article) -> str:
    return f"delete-article-{article.id}"


@register.filter
def update_article_form_id(article: Article) -> str:
    return f"update-article-actions-form-{article.id}"


@register.filter
@stringfilter
def markdown(value: str) -> str:
    md = _get_markdown_it_instance()
    rendered_value = md.render(value)
    cleaned_value = sanitize_keep_safe_tags(rendered_value)
    cleaned_value = cleaned_value.strip()
    return mark_safe(cleaned_value)  # ruff:ignore[suspicious-mark-safe-usage]


@lru_cache(maxsize=1)
def _get_markdown_it_instance():
    """Get markdown-it instance.

    It's cached because it's slow to create and it's called in a loop when rendering lists of
    articles.
    """
    return MarkdownIt("gfm-like")


@register.filter
def open_original_with_link(article: Article) -> bool:
    return not article.content or bool(
        article.main_feed and article.main_feed.open_original_url_by_default
    )


@register.filter
def article_title_anchor_id(article: Article) -> str:
    return f"legadilo-article-{article.id}"


@register.filter
def article_title_anchor(article: Article) -> str:
    anchor_id = article_title_anchor_id(article)
    return f"#{anchor_id}"


@register.simple_tag(name="append_qs_params", takes_context=True)
def append_qs_params(context, **kwargs):
    params = context.request.GET.copy()
    for key, value in kwargs.items():
        existing_values = params.getlist(key)
        params.setlist(key, list({*existing_values, value}))

    qs = params.urlencode()
    return f"?{qs}"
