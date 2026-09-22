# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from http import HTTPStatus
from typing import Any

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from legadilo.core.forms.fields import ListField, MultipleTagsField, SlugifiableCharField
from legadilo.core.utils.types import FormChoices
from legadilo.reading import constants
from legadilo.reading.models import ReadingList, ReadingListTag, Tag
from legadilo.users.models import User
from legadilo.users.user_types import AuthenticatedHttpRequest


class ReorderReadingListsForm(forms.Form):
    reading_list_order = ListField(field=forms.IntegerField())


@require_http_methods(["GET", "POST"])
@login_required
def reading_list_admin_view(request: AuthenticatedHttpRequest) -> TemplateResponse:
    form = ReorderReadingListsForm()
    status = HTTPStatus.OK
    if request.method == "POST":
        form = ReorderReadingListsForm(request.POST)
        if form.is_valid():
            new_order = {
                reading_list_id: index
                for index, reading_list_id in enumerate(form.cleaned_data["reading_list_order"])
            }
            ReadingList.objects.reorder(request.user, new_order)
        else:
            status = HTTPStatus.BAD_REQUEST

    return TemplateResponse(
        request,
        "reading/reading_lists_admin.html",
        {
            "reading_lists": ReadingList.objects.get_all_for_user(request.user),
            "form": form,
            "breadcrumbs": [
                (reverse("reading:reading_lists_admin"), _("Reading lists admin")),
            ],
        },
        status=status,
    )


class ReadingListForm(forms.ModelForm):
    title = SlugifiableCharField(label=_("Title"), required=True)
    tags_to_include = MultipleTagsField(
        label=_("Tags to include"),
        required=False,
        choices=[],
        help_text=_("Articles with these tags will be included in the reading list."),
    )
    tags_to_exclude = MultipleTagsField(
        label=_("Tags to exclude"),
        required=False,
        choices=[],
        help_text=_("Articles with these tags will be excluded from the reading list."),
    )

    def __init__(
        self,
        *,
        data=None,
        instance: ReadingList | None = None,
        initial: dict[str, Any],
        tag_choices: FormChoices,
        user: User,
    ):
        super().__init__(data=data, instance=instance, initial=initial)
        self._user = user
        self.fields["tags_to_include"].choices = tag_choices  # type: ignore[attr-defined]
        self.fields["tags_to_exclude"].choices = tag_choices  # type: ignore[attr-defined]

    class Meta:
        model = ReadingList
        fields = (
            "title",
            "enable_reading_on_scroll",
            "auto_refresh_interval",
            "show_unread_count",
            "read_status",
            "favorite_status",
            "for_later_status",
            "articles_max_age_value",
            "articles_max_age_unit",
            "articles_reading_time",
            "articles_reading_time_operator",
            "tags_to_include",
            "include_tag_operator",
            "tags_to_exclude",
            "exclude_tag_operator",
            "order_direction",
        )
        labels = {
            "enable_reading_on_scroll": _("Enable reading on scroll"),
            "auto_refresh_interval": _("Auto refresh interval"),
            "show_unread_count": _("How to show unread count?"),
            "read_status": _("Read status"),
            "favorite_status": _("Favorite status"),
            "for_later_status": _("For later status"),
            "articles_max_age_value": _("Articles max age value"),
            "articles_max_age_unit": _("Articles max age unit"),
            "articles_reading_time": _("Articles reading time"),
            "articles_reading_time_operator": _("Articles reading time operator"),
            "include_tag_operator": _("Include tag operator"),
            "exclude_tag_operator": _("Exclude tag operator"),
            "order_direction": _("Order direction"),
        }

    @transaction.atomic()
    def save(self, commit: bool = True):  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]
        if self.instance.id is None:
            return self._create()

        self._update_tags()
        self.instance.user = self._user
        return super().save(commit=commit)

    @transaction.atomic()
    def _create(self):
        create_data = self.cleaned_data.copy()
        # Tags are managed with a many-to-many relationship and thus must be created independently
        # and cannot be passed to .create
        create_data.pop("tags_to_include")
        create_data.pop("tags_to_exclude")
        reading_list = ReadingList.objects.create(**create_data, user=self._user)
        self.instance = reading_list

        self._update_tags()

        return reading_list

    def _update_tags(self):
        tags_to_include = self.cleaned_data.pop("tags_to_include")
        if tags_to_include != self.initial["tags_to_include"]:
            tags = Tag.objects.get_or_create_from_list(self.instance.user, tags_to_include)
            ReadingListTag.objects.associate_reading_list_with_tags(
                self.instance,
                tags,
                filter_type=constants.ReadingListTagFilterType.INCLUDE,
            )

        tags_to_exclude = self.cleaned_data.pop("tags_to_exclude")
        if tags_to_exclude != self.initial["tags_to_exclude"]:
            tags = Tag.objects.get_or_create_from_list(self.instance.user, tags_to_exclude)
            ReadingListTag.objects.associate_reading_list_with_tags(
                self.instance,
                tags,
                filter_type=constants.ReadingListTagFilterType.EXCLUDE,
            )


@require_http_methods(["GET", "POST"])
@login_required
def reading_list_edit_view(
    request: AuthenticatedHttpRequest, reading_list_id: int | None = None
) -> TemplateResponse | HttpResponseRedirect:
    reading_list = None
    if reading_list_id is not None:
        reading_list = get_object_or_404(ReadingList, id=reading_list_id, user=request.user)

    form = _build_form_from_reading_list_instance(request.user, reading_list=reading_list)
    status = HTTPStatus.OK

    if reading_list and request.method == "POST" and "delete" in request.POST:
        reading_list.delete()
        return HttpResponseRedirect(reverse("reading:reading_lists_admin"))

    if reading_list and request.method == "POST" and "make-default" in request.POST:
        ReadingList.objects.make_default(reading_list)
        return HttpResponseRedirect(reverse("reading:reading_lists_admin"))

    if request.method == "POST":
        status, form, reading_list = _handle_reading_list_edition(request, reading_list)
        if status == HTTPStatus.OK and "save" in request.POST:
            return HttpResponseRedirect(reverse("reading:reading_lists_admin"))
        if status == HTTPStatus.OK and "save-add-new" in request.POST:
            return HttpResponseRedirect(reverse("reading:create_reading_list"))
        if reading_list and status == HTTPStatus.OK:
            return HttpResponseRedirect(
                reverse("reading:edit_reading_list", kwargs={"reading_list_id": reading_list.id})
            )

    last_crumb = (
        (
            reverse("reading:edit_reading_list", kwargs={"reading_list_id": reading_list.id}),
            _("Edit reading list"),
        )
        if reading_list
        else (reverse("reading:create_reading_list"), _("Create reading list"))
    )
    return TemplateResponse(
        request,
        "reading/edit_reading_list.html",
        {
            "reading_list": reading_list,
            "form": form,
            "breadcrumbs": [
                (reverse("reading:reading_lists_admin"), _("Reading lists admin")),
                last_crumb,
            ],
        },
        status=status,
    )


def _build_form_from_reading_list_instance(
    user: User,
    reading_list: ReadingList | None = None,
    data=None,
):
    return ReadingListForm(
        data=data,
        instance=reading_list,
        tag_choices=reading_list.reading_list_tags.get_selected_choices() if reading_list else [],
        user=user,
        initial={
            "tags_to_include": reading_list.reading_list_tags.get_selected_values(
                constants.ReadingListTagFilterType.INCLUDE
            )
            if reading_list
            else [],
            "tags_to_exclude": reading_list.reading_list_tags.get_selected_values(
                constants.ReadingListTagFilterType.EXCLUDE
            )
            if reading_list
            else [],
        },
    )


def _handle_reading_list_edition(
    request: AuthenticatedHttpRequest, reading_list: ReadingList | None
) -> tuple[HTTPStatus, ReadingListForm, ReadingList | None]:
    form = _build_form_from_reading_list_instance(
        request.user, data=request.POST, reading_list=reading_list
    )
    if not form.is_valid():
        return HTTPStatus.BAD_REQUEST, form, reading_list

    try:
        reading_list = form.save()
    except IntegrityError:
        messages.error(
            request,
            _("A reading list with title '%s' already exists.") % form.cleaned_data["title"],
        )
        return HTTPStatus.CONFLICT, form, reading_list

    return HTTPStatus.OK, form, reading_list
