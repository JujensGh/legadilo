# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from http import HTTPStatus
from pathlib import Path

import pytest
import time_machine
from django.conf import settings
from django.contrib.messages import DEFAULT_LEVELS, get_messages
from django.contrib.messages.storage.base import Message
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile
from django.urls import reverse

from legadilo.conftest import assert_redirected_to_login_page
from legadilo.feeds.models import Feed, FeedCategory
from legadilo.feeds.tests.factories import FeedCategoryFactory, FeedFactory
from legadilo.feeds.tests.fixtures import get_feed_fixture_content


@pytest.mark.django_db
class TestExportFeeds:
    @pytest.fixture(autouse=True)
    def _setup_data(self):
        self.url = reverse("import_export:export_feeds")

    def test_not_logged_in(self, client):
        response = client.get(self.url)

        assert_redirected_to_login_page(response)

    def test_export_no_feed(self, snapshot, logged_in_sync_client):
        with time_machine.travel("2024-06-20 22:00:00", tick=False):
            response = logged_in_sync_client.get(self.url)

        assert response.status_code == HTTPStatus.OK
        assert response.headers.get("Content-Type") == "text/x-opml"
        assert response.text == snapshot

    def test_export(self, snapshot, logged_in_sync_client, user):
        category = FeedCategoryFactory(user=user, title="My Category")
        FeedFactory(title="Feed other user", feed_url="https://example.com/feeds/1.xml")
        FeedFactory(
            user=user,
            title="Feed without a category",
            feed_url="https://example.com/feeds/no_cat.xml",
        )
        FeedFactory(
            user=user,
            category=category,
            title="Feed with category",
            feed_url="https://example.com/feeds/2.xml",
        )

        with time_machine.travel("2024-06-20 22:00:00", tick=False):
            response = logged_in_sync_client.get(self.url)

        assert response.status_code == HTTPStatus.OK
        assert response.headers.get("Content-Type") == "text/x-opml"
        assert response.text == snapshot


@pytest.mark.django_db
class TestImportFeeds:
    @pytest.fixture(autouse=True)
    def _setup_data(self):
        self.url = reverse("import_export:import_feeds")

    def test_not_logged_in(self, client):
        response = client.get(self.url)

        assert_redirected_to_login_page(response)

    def test_import_empty_file(self, logged_in_sync_client):
        with TemporaryUploadedFile(
            settings.APPS_DIR / "import_export/tests/fixtures/opml/valid.opml",  # type: ignore[arg-type]
            "application/xml",
            size=100,
            charset="utf-8",
        ) as temp_file:
            response = logged_in_sync_client.post(
                self.url,
                {
                    "opml_file": temp_file,
                },
            )

        assert response.status_code == HTTPStatus.OK
        assert response.template_name == "import_export/import_feeds.html"
        assert response.context_data["form"].errors == {
            "opml_file": ["The submitted file is empty."]
        }
        assert Feed.objects.count() == 0

    def test_import_too_big(self, logged_in_sync_client):
        with TemporaryUploadedFile(
            settings.APPS_DIR / "import_export/tests/fixtures/opml/valid.opml",  # type: ignore[arg-type]
            "application/xml",
            size=0,
            charset="utf-8",
        ) as temp_file:
            Path(temp_file.file.name).write_text("stuff" * 2048 * 2048, encoding="utf-8")

            response = logged_in_sync_client.post(
                self.url,
                {
                    "opml_file": temp_file,
                },
            )

        assert response.status_code == HTTPStatus.OK
        assert response.template_name == "import_export/import_feeds.html"
        assert response.context_data["form"].errors == {
            "opml_file": ["The supplied file is too big to be imported."]
        }
        assert Feed.objects.count() == 0

    def test_import_invalid_file(self, logged_in_sync_client):
        with TemporaryUploadedFile(
            settings.APPS_DIR / "import_export/tests/fixtures/opml/valid.opml",  # type: ignore[arg-type]
            "application/xml",
            size=100,
            charset="utf-8",
        ) as temp_file:
            Path(temp_file.file.name).write_text("stuff", encoding="utf-8")  # type: ignore[union-attr]

            response = logged_in_sync_client.post(
                self.url,
                {
                    "opml_file": temp_file,
                },
            )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.template_name == "import_export/import_feeds.html"
        assert response.context_data["form"].errors == {}
        assert Feed.objects.count() == 0
        messages = list(get_messages(response.wsgi_request))
        assert messages == [
            Message(
                level=DEFAULT_LEVELS["ERROR"],
                message="The file you supplied is not valid.",
            )
        ]

    def test_import_in_memory_file(self, logged_in_sync_client, httpx2_mock):
        httpx2_mock.add_response(
            url="https://www.example.com/feeds/all.rss.xml",
            content=get_feed_fixture_content("sample_rss.xml"),
        )
        httpx2_mock.add_response(
            url="https://www.example.eu/feeds/all.atom.xml",
            content=get_feed_fixture_content("sample_atom.xml"),
        )

        with (
            Path(settings.APPS_DIR / "import_export/tests/fixtures/opml/valid.opml").open(
                "r", encoding="utf-8"
            ) as f,
            InMemoryUploadedFile(
                f,
                "opml_file",
                "valid.opml",
                content_type="application/xml",
                size=100,
                charset="utf-8",
            ) as in_memory_file,
        ):
            response = logged_in_sync_client.post(
                self.url,
                {
                    "opml_file": in_memory_file,
                },
            )

        assert response.status_code == HTTPStatus.OK
        assert response.template_name == "import_export/import_feeds.html"
        assert Feed.objects.count() > 0
        assert FeedCategory.objects.count() > 0
        messages = list(get_messages(response.wsgi_request))
        assert messages == [
            Message(
                level=DEFAULT_LEVELS["SUCCESS"],
                message="Successfully imported 2 feeds into 1 categories.",
            )
        ]

    def test_import_temporary_file(self, logged_in_sync_client, httpx2_mock, settings):
        settings.FILE_UPLOAD_MAX_MEMORY_SIZE = 0
        httpx2_mock.add_response(
            url="https://www.example.com/feeds/all.rss.xml",
            content=get_feed_fixture_content("sample_rss.xml"),
        )
        httpx2_mock.add_response(
            url="https://www.example.eu/feeds/all.atom.xml",
            content=get_feed_fixture_content("sample_atom.xml"),
        )
        with TemporaryUploadedFile(
            settings.APPS_DIR / "import_export/tests/fixtures/opml/valid.opml",  # type: ignore[arg-type]
            "application/xml",
            size=100,
            charset="utf-8",
        ) as temp_file:
            input_csv = Path(
                settings.APPS_DIR / "import_export/tests/fixtures/opml/valid.opml"
            ).read_text(encoding="utf-8")
            Path(temp_file.file.name).write_text(input_csv, encoding="utf-8")

            response = logged_in_sync_client.post(
                self.url,
                {
                    "opml_file": temp_file,
                },
            )

        assert response.status_code == HTTPStatus.OK
        assert response.template_name == "import_export/import_feeds.html"
        assert Feed.objects.count() > 0
        assert FeedCategory.objects.count() > 0
        messages = list(get_messages(response.wsgi_request))
        assert messages == [
            Message(
                level=DEFAULT_LEVELS["SUCCESS"],
                message="Successfully imported 2 feeds into 1 categories.",
            )
        ]
