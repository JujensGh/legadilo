# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import logging
from http import HTTPStatus

from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import models
from django.http import QueryDict
from django.template.response import TemplateResponse
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from legadilo.core.forms.fields import MultipleTagsField
from legadilo.core.forms.widgets import SelectMultipleAutocompleteWidget
from legadilo.core.utils.types import FormChoices
from legadilo.core.utils.validators import is_url_valid
from legadilo.reading import constants
from legadilo.reading.models import Article, Tag
from legadilo.reading.models.article import (
    ArticleFullTextSearchQuery,
    ArticleQuerySet,
    ArticlesTagsSearch,
)
from legadilo.users.user_types import AuthenticatedHttpRequest

from ...users.models import User
from .list_of_articles_views import UpdateArticlesForm, update_list_of_articles

logger = logging.getLogger(__name__)


class FeedMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return obj.title


class SearchForm(forms.Form):
    # Main fields.
    q = forms.CharField(required=False, min_length=0, label=_("Search query"))
    search_type = forms.ChoiceField(
        required=False,
        choices=constants.ArticleSearchType.choices,
        initial=constants.ArticleSearchType.PLAIN,
    )
    # Dates
    order = forms.ChoiceField(
        required=False,
        choices=constants.ArticleSearchOrderBy.choices,
        initial=constants.ArticleSearchOrderBy.RANK_DESC,
    )
    # Search refinement fields
    read_status = forms.ChoiceField(
        required=False,
        choices=constants.ReadStatus.choices,
        initial=constants.ReadStatus.ALL,
    )
    favorite_status = forms.ChoiceField(
        required=False,
        choices=constants.FavoriteStatus.choices,
        initial=constants.FavoriteStatus.ALL,
    )
    for_later_status = forms.ChoiceField(
        required=False,
        choices=constants.ForLaterStatus.choices,
        initial=constants.ForLaterStatus.ALL,
    )
    articles_max_age_value = forms.IntegerField(required=False, min_value=0)
    articles_max_age_unit = forms.ChoiceField(
        required=False,
        choices=constants.ArticlesMaxAgeUnit.choices,
        initial=constants.ArticlesMaxAgeUnit.UNSET,
    )
    articles_reading_time = forms.IntegerField(required=False, min_value=0)
    articles_reading_time_operator = forms.ChoiceField(
        required=False,
        choices=constants.ArticlesReadingTimeOperator.choices,
        initial=constants.ArticlesReadingTimeOperator.UNSET,
    )
    # Tags
    include_tag_operator = forms.ChoiceField(
        required=False,
        choices=constants.ReadingListTagOperator.choices,
        initial=constants.ReadingListTagOperator.ALL,
        help_text=_("Articles to include must have all or any of the supplied tags."),
    )
    tags_to_include = MultipleTagsField(
        required=False,
        choices=[],
        help_text=_("Articles with these tags will be included in the search."),
        widget=SelectMultipleAutocompleteWidget(
            allow_new=False,
            empty_label=_("Choose tags"),
            server_url=reverse_lazy("reading:tags_autocomplete"),
        ),
    )
    exclude_tag_operator = forms.ChoiceField(
        required=False,
        choices=constants.ReadingListTagOperator.choices,
        initial=constants.ReadingListTagOperator.ALL,
        help_text=_("Articles to exclude must have all or any of the supplied tags."),
    )
    tags_to_exclude = MultipleTagsField(
        required=False,
        choices=[],
        help_text=_("Articles with these tags will be excluded from the search."),
        widget=SelectMultipleAutocompleteWidget(
            allow_new=False,
            empty_label=_("Choose tags"),
            server_url=reverse_lazy("reading:tags_autocomplete"),
        ),
    )
    external_tags_to_include = forms.MultipleChoiceField(
        required=False,
        help_text=_(
            "Articles with these external tags will be included in the search. "
            "Any tag you type will be searched as typed."
        ),
        widget=SelectMultipleAutocompleteWidget(
            allow_new=True, empty_label=_("Choose external tags")
        ),
    )
    # Feeds
    linked_with_feeds = FeedMultipleChoiceField(
        required=False,
        queryset=None,
        widget=SelectMultipleAutocompleteWidget(allow_new=False, empty_label=_("Choose feeds")),
    )

    def __init__(
        self,
        data: QueryDict,
        *,
        tags_to_include_choices: FormChoices,
        tags_to_exclude_choices: FormChoices,
        feeds_qs: models.QuerySet,
    ):
        super().__init__(data.copy())
        # The goal is to spot invalid params when coming from "Advanced search" links.
        if data and (extra_fields := set(data.keys()) - set(self.fields.keys())):
            logger.warning(
                "SearchForm received extra fields: %s. These will be ignored.",
                ", ".join(extra_fields),
            )

        self.fields["tags_to_include"].choices = tags_to_include_choices  # type: ignore[attr-defined]
        self.fields["tags_to_exclude"].choices = tags_to_exclude_choices  # type: ignore[attr-defined]
        self.fields["external_tags_to_include"].choices = [  # type: ignore[attr-defined]
            (tag, tag) for tag in data.getlist("external_tags_to_include", [])
        ]
        self.fields["linked_with_feeds"].queryset = feeds_qs  # type: ignore[attr-defined]

        # Make sure we set the proper search type is correct when we do a URL search. By default,
        # it's a word search.
        search_type = self.data.get("search_type")
        if is_url_valid(self.data.get("q")) and not search_type:
            self.data["search_type"] = constants.ArticleSearchType.URL  # type: ignore[index]

    def clean_q(self):
        q = self.cleaned_data["q"]
        return q.strip()

    def clean_search_type(self):
        if not self.cleaned_data.get("search_type"):
            return constants.ArticleSearchType.PLAIN
        return constants.ArticleSearchType(self.cleaned_data["search_type"])

    def clean_order(self):
        if not self.cleaned_data.get("order"):
            return constants.ArticleSearchOrderBy.RANK_DESC
        return constants.ArticleSearchOrderBy(self.cleaned_data["order"])

    def clean_read_status(self):
        if not self.cleaned_data.get("read_status"):
            return constants.ReadStatus.ALL

        return constants.ReadStatus(self.cleaned_data["read_status"])

    def clean_favorite_status(self):
        if not self.cleaned_data.get("favorite_status"):
            return constants.FavoriteStatus.ALL

        return constants.FavoriteStatus(self.cleaned_data["favorite_status"])

    def clean_for_later_status(self):
        if not self.cleaned_data.get("for_later_status"):
            return constants.ForLaterStatus.ALL

        return constants.ForLaterStatus(self.cleaned_data["for_later_status"])

    def clean_articles_max_age_unit(self):
        if not self.cleaned_data.get("articles_max_age_unit"):
            return constants.ArticlesMaxAgeUnit.UNSET

        return constants.ArticlesMaxAgeUnit(self.cleaned_data["articles_max_age_unit"])

    def clean_articles_reading_time_operator(self):
        if not self.cleaned_data.get("articles_reading_time_operator"):
            return constants.ArticlesReadingTimeOperator.UNSET

        return constants.ArticlesReadingTimeOperator(
            self.cleaned_data["articles_reading_time_operator"]
        )

    def clean_include_tag_operator(self):
        if not self.cleaned_data.get("include_tag_operator"):
            return constants.ReadingListTagOperator.ALL

        return constants.ReadingListTagOperator(self.cleaned_data["include_tag_operator"])

    def clean_exclude_tag_operator(self):
        if not self.cleaned_data.get("exclude_tag_operator"):
            return constants.ReadingListTagOperator.ALL

        return constants.ReadingListTagOperator(self.cleaned_data["exclude_tag_operator"])

    def clean(self):
        super().clean()
        errors = []

        is_articles_max_age_unit_set = (
            articles_max_age_unit := self.cleaned_data.get("articles_max_age_unit")
        ) and articles_max_age_unit != constants.ArticlesMaxAgeUnit.UNSET
        is_articles_max_age_value_set = bool(self.cleaned_data.get("articles_max_age_value"))
        if is_articles_max_age_unit_set and not is_articles_max_age_value_set:
            errors.append(
                ValidationError(
                    _("You must supply a max age value when searching by max age."),
                    code="max-age-value-unset-but-unit-is",
                )
            )
        elif not is_articles_max_age_unit_set and is_articles_max_age_value_set:
            errors.append(
                ValidationError(
                    _("You must set the max age unit when searching by max age."),
                    code="max-age-unit-unset-but-value-is",
                ),
            )

        is_articles_reading_time_operator_set = (
            articles_reading_time_operator := self.cleaned_data.get(
                "articles_reading_time_operator"
            )
        ) and articles_reading_time_operator != constants.ArticlesReadingTimeOperator.UNSET
        is_articles_reading_time_set = bool(self.cleaned_data.get("articles_reading_time"))
        if is_articles_reading_time_operator_set and not is_articles_reading_time_set:
            errors.append(
                ValidationError(
                    _("You must supply a reading time when searching by reading time."),
                    code="reading-time-unset-but-operator-is",
                )
            )
        elif not is_articles_reading_time_operator_set and is_articles_reading_time_set:
            errors.append(
                ValidationError(
                    _("You must supply a reading time operator when searching by reading time."),
                    code="reading-operator-unset-but-value-is",
                )
            )

        if errors:
            raise ValidationError(errors)


@require_http_methods(["GET", "POST"])
@login_required
def search_view(request: AuthenticatedHttpRequest) -> TemplateResponse:
    status = HTTPStatus.OK
    tags_to_include_choices = Tag.objects.get_putative_choices(
        request.user, request.GET.getlist("tags_to_include", [])
    )
    tags_to_exclude_choices = Tag.objects.get_putative_choices(
        request.user, request.GET.getlist("tags_to_exclude", [])
    )
    search_form = SearchForm(
        request.GET,
        tags_to_include_choices=tags_to_include_choices,
        tags_to_exclude_choices=tags_to_exclude_choices,
        feeds_qs=request.user.feeds.all(),
    )
    update_articles_form = UpdateArticlesForm(request.POST)
    # We don't do anything unless we have a valid search.
    if not search_form.is_valid():
        return TemplateResponse(
            request,
            "reading/search.html",
            {
                "search_form": search_form,
                "update_articles_form": update_articles_form,
                "articles": [],
                "total_results": 0,
            },
            status=HTTPStatus.BAD_REQUEST,
        )

    if request.method == "POST":
        # We update the articles of the current search.
        articles_qs = _search(request.user, search_form)
        # articles_qs has annotations (like the rank) we can't use with update. Since we need
        # these features, we extract the ids of the articles to update and build a new QS.
        article_ids_to_update = set(articles_qs.values_list("id", flat=True))
        status, update_articles_form = update_list_of_articles(
            request, Article.objects.get_queryset().filter(id__in=article_ids_to_update)
        )

    # Articles have been updated. Some may not be part of the search anymore. Rerun it.
    articles_qs = _search(request.user, search_form)
    articles = list(articles_qs[: constants.MAX_OBJECTS_PER_PAGE])
    total_results = articles_qs.count()

    return TemplateResponse(
        request,
        "reading/search.html",
        {
            "search_form": search_form,
            "update_articles_form": update_articles_form,
            "articles": articles,
            "total_results": total_results,
        },
        status=status,
    )


def _search(user: User, search_form: SearchForm) -> ArticleQuerySet:
    tags_to_include = search_form.cleaned_data.get("tags_to_include", [])
    tags_to_exclude = search_form.cleaned_data.get("tags_to_exclude", [])
    all_slugs = {
        *(tag_slug for tag_slug in tags_to_include),
        *(tag_slug for tag_slug in tags_to_exclude),
    }
    tag_slugs_to_ids = Tag.objects.get_slugs_to_ids(user, all_slugs)
    form_data = {
        key: value
        for key, value in search_form.cleaned_data.items()
        if key
        not in {
            "tags_to_include",
            "tags_to_exclude",
            "include_tag_operator",
            "exclude_tag_operator",
        }
    }
    form_data["linked_with_feeds"] = frozenset(feed.id for feed in form_data["linked_with_feeds"])
    form_data["articles_max_age_value"] = form_data["articles_max_age_value"] or 0
    form_data["articles_reading_time"] = form_data["articles_reading_time"] or 0
    query = ArticleFullTextSearchQuery(**form_data)
    articles_tags_search = ArticlesTagsSearch(
        tag_ids_to_include=frozenset(
            tag_slugs_to_ids[tag_slug]
            for tag_slug in tags_to_include
            if tag_slug in tag_slugs_to_ids
        ),
        include_tag_operator=search_form.cleaned_data.get(
            "include_tag_operator", constants.ReadingListTagOperator.ALL
        ),
        tag_ids_to_exclude=frozenset(
            tag_slugs_to_ids[tag_slug]
            for tag_slug in tags_to_exclude
            if tag_slug in tag_slugs_to_ids
        ),
        exclude_tag_operator=search_form.cleaned_data.get(
            "exclude_tag_operator", constants.ReadingListTagOperator.ALL
        ),
    )
    return Article.objects.search(user, query, articles_tags_search)
