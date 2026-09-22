# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from http import HTTPStatus
from typing import Any

import pytest
from django.contrib.messages import DEFAULT_LEVELS, get_messages
from django.contrib.messages.storage.base import Message
from django.urls import reverse
from slugify import slugify

from legadilo.reading import constants
from legadilo.reading.models import ReadingList, ReadingListTag
from legadilo.reading.tests.factories import ReadingListFactory, TagFactory


@pytest.mark.django_db
class TestReadingListsAdminView:
    @pytest.fixture(autouse=True)
    def _setup_data(self, user):
        self.url = reverse("reading:reading_lists_admin")
        self.reading_list = ReadingListFactory(user=user, order=0)

    def test_not_logged_in(self, client):
        response = client.get(self.url)

        assert response.status_code == HTTPStatus.FOUND
        assert response["Location"] == f"/~login/?next={self.url}"

    def test_get_page(self, logged_in_sync_client, other_user):
        ReadingListFactory(user=other_user)

        response = logged_in_sync_client.get(self.url)

        assert response.status_code == HTTPStatus.OK
        assert response.template_name == "reading/reading_lists_admin.html"
        assert list(response.context_data["reading_lists"]) == [self.reading_list]

    def test_reorder_invalid_data(self, logged_in_sync_client):
        response = logged_in_sync_client.post(self.url, data={"reading_list_order": ["a", "b"]})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.context_data["form"].errors == {
            "reading_list_order": ["Enter a whole number."]
        }

    def test_reorder(self, user, logged_in_sync_client):
        other_reading_list = ReadingListFactory(user=user, order=10)

        response = logged_in_sync_client.post(
            self.url, data={"reading_list_order": [other_reading_list.id, self.reading_list.id]}
        )

        assert response.status_code == HTTPStatus.OK
        self.reading_list.refresh_from_db()
        other_reading_list.refresh_from_db()
        assert self.reading_list.order == 1
        assert other_reading_list.order == 0


@pytest.mark.django_db
class TestCreateReadingListView:
    @pytest.fixture(autouse=True)
    def _setup_data(self):
        self.url = reverse("reading:create_reading_list")
        self.tag_to_include = TagFactory(slug="tag-to-include")
        self.tag_to_exclude = TagFactory(slug="tag-to-exclude")
        self.sample_data: dict[str, Any] = {
            "title": "Sample Reading List",
            "enable_reading_on_scroll": True,
            "auto_refresh_interval": 0,
            "show_unread_count": constants.ReadingListShowUnreadCount.COUNT,
            "read_status": constants.ReadStatus.ONLY_READ,
            "favorite_status": constants.FavoriteStatus.ONLY_FAVORITE,
            "for_later_status": constants.ForLaterStatus.ONLY_NOT_FOR_LATER,
            "articles_max_age_value": 0,
            "articles_max_age_unit": constants.ArticlesMaxAgeUnit.WEEKS,
            "articles_reading_time": 15,
            "articles_reading_time_operator": constants.ArticlesReadingTimeOperator.LESS_THAN,
            "tags_to_include": ["New tag", self.tag_to_include.slug],
            "include_tag_operator": constants.ReadingListTagOperator.ANY,
            "tags_to_exclude": [self.tag_to_exclude.slug],
            "exclude_tag_operator": constants.ReadingListTagOperator.ANY,
            "order_direction": constants.ReadingListOrderDirection.ASC,
        }

    def test_not_logged_in(self, client):
        response = client.post(self.url)

        assert response.status_code == HTTPStatus.FOUND
        assert response["Location"] == f"/~login/?next={self.url}"

    def test_invalid_form(self, logged_in_sync_client):
        response = logged_in_sync_client.post(self.url, data={})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.template_name == "reading/edit_reading_list.html"
        assert response.context_data["form"].errors == {
            "articles_max_age_unit": ["This field is required."],
            "articles_max_age_value": ["This field is required."],
            "articles_reading_time": ["This field is required."],
            "articles_reading_time_operator": ["This field is required."],
            "auto_refresh_interval": ["This field is required."],
            "exclude_tag_operator": ["This field is required."],
            "favorite_status": ["This field is required."],
            "for_later_status": ["This field is required."],
            "include_tag_operator": ["This field is required."],
            "order_direction": ["This field is required."],
            "read_status": ["This field is required."],
            "title": ["Cannot contain only spaces or special characters."],
        }

    def test_create_reading_list(self, logged_in_sync_client, user, django_assert_num_queries):
        with django_assert_num_queries(53):
            response = logged_in_sync_client.post(self.url, data=self.sample_data)

        reading_list = ReadingList.objects.get()
        assert response.status_code == HTTPStatus.FOUND
        assert response["Location"] == reverse(
            "reading:edit_reading_list", kwargs={"reading_list_id": reading_list.id}
        )
        assert reading_list.title == "Sample Reading List"
        assert reading_list.user == user
        assert list(reading_list.reading_list_tags.values_list("tag__slug", "filter_type")) == [
            ("new-tag", constants.ReadingListTagFilterType.INCLUDE),
            (self.tag_to_include.slug, constants.ReadingListTagFilterType.INCLUDE),
            (self.tag_to_exclude.slug, constants.ReadingListTagFilterType.EXCLUDE),
        ]
        for field, value in self.sample_data.items():
            if field in {"tags_to_include", "tags_to_exclude"}:
                continue

            assert getattr(reading_list, field) == value

    def test_create_duplicated_reading_list(
        self, logged_in_sync_client, user, django_assert_num_queries
    ):
        self.sample_data.pop("tags_to_include")
        self.sample_data.pop("tags_to_exclude")
        reading_list = ReadingListFactory(
            **self.sample_data, slug=slugify(self.sample_data["title"]), user=user
        )

        with django_assert_num_queries(40):
            response = logged_in_sync_client.post(self.url, data=self.sample_data)

        assert response.status_code == HTTPStatus.CONFLICT
        assert ReadingList.objects.count() == 1
        messages = list(get_messages(response.wsgi_request))
        assert messages == [
            Message(
                level=DEFAULT_LEVELS["ERROR"],
                message=f"A reading list with title '{reading_list.title}' already exists.",
            )
        ]


@pytest.mark.django_db
class TestReadingListEditView:
    @pytest.fixture(autouse=True)
    def _setup_data(self, user):
        self.reading_list = ReadingListFactory(user=user)
        self.include_tag = TagFactory(user=user, slug="include-tag")
        ReadingListTag.objects.create(
            tag=self.include_tag,
            reading_list=self.reading_list,
            filter_type=constants.ReadingListTagFilterType.INCLUDE,
        )
        self.exclude_tag = TagFactory(user=user, slug="exclude-tag")
        ReadingListTag.objects.create(
            tag=self.exclude_tag,
            reading_list=self.reading_list,
            filter_type=constants.ReadingListTagFilterType.INCLUDE,
        )
        self.url = reverse(
            "reading:edit_reading_list", kwargs={"reading_list_id": self.reading_list.id}
        )
        self.sample_data = {
            "title": "Sample Reading List",
            "enable_reading_on_scroll": True,
            "auto_refresh_interval": 0,
            "show_unread_count": constants.ReadingListShowUnreadCount.COUNT,
            "read_status": constants.ReadStatus.ONLY_READ,
            "favorite_status": constants.FavoriteStatus.ONLY_FAVORITE,
            "for_later_status": constants.ForLaterStatus.ONLY_NOT_FOR_LATER,
            "articles_max_age_value": 0,
            "articles_max_age_unit": constants.ArticlesMaxAgeUnit.WEEKS,
            "articles_reading_time": 15,
            "articles_reading_time_operator": constants.ArticlesReadingTimeOperator.LESS_THAN,
            "tags_to_include": ["New tag", self.include_tag.slug],
            "include_tag_operator": constants.ReadingListTagOperator.ANY,
            "tags_to_exclude": [self.exclude_tag.slug],
            "exclude_tag_operator": constants.ReadingListTagOperator.ANY,
            "order_direction": constants.ReadingListOrderDirection.ASC,
        }

    def test_not_logged_in(self, client):
        response = client.post(self.url)

        assert response.status_code == HTTPStatus.FOUND
        assert response["Location"] == f"/~login/?next={self.url}"

    def test_edit_other_user(self, logged_in_other_user_sync_client):
        response = logged_in_other_user_sync_client.post(self.url, data=self.sample_data)

        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_invalid_form(self, logged_in_sync_client):
        response = logged_in_sync_client.post(self.url, data={})

        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_update(self, logged_in_sync_client, django_assert_num_queries):
        with django_assert_num_queries(58):
            response = logged_in_sync_client.post(self.url, data={**self.sample_data, "save": ""})

        assert response.status_code == HTTPStatus.FOUND
        assert response["Location"] == reverse("reading:reading_lists_admin")
        assert list(
            self.reading_list.reading_list_tags.values_list("tag__slug", "filter_type")
        ) == [
            ("new-tag", "INCLUDE"),
            (self.include_tag.slug, "INCLUDE"),
            (self.exclude_tag.slug, "EXCLUDE"),
        ]
        self.reading_list.refresh_from_db()
        for field, value in self.sample_data.items():
            if field in {"tags_to_include", "tags_to_exclude"}:
                continue

            assert getattr(self.reading_list, field) == value

    def test_update_add_new(self, logged_in_sync_client, django_assert_num_queries):
        with django_assert_num_queries(58):
            response = logged_in_sync_client.post(
                self.url, data={**self.sample_data, "save-add-new": ""}
            )

        assert response.status_code == HTTPStatus.FOUND
        assert response["Location"] == reverse("reading:create_reading_list")

    def test_update_add_continue_edition(self, logged_in_sync_client, django_assert_num_queries):
        with django_assert_num_queries(58):
            response = logged_in_sync_client.post(
                self.url, data={**self.sample_data, "save-continue-edition": ""}
            )

        assert response.status_code == HTTPStatus.FOUND
        assert response["Location"] == self.url
