# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from http import HTTPStatus
from io import BytesIO
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.messages import DEFAULT_LEVELS, get_messages
from django.contrib.messages.storage.base import Message
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile
from django.urls import reverse

from legadilo.conftest import assert_redirected_to_login_page
from legadilo.core.utils.testing import (
    all_model_fields_except,
    read_streamable_response,
    serialize_for_snapshot,
)
from legadilo.core.utils.time_utils import utcdt
from legadilo.feeds.models import Feed
from legadilo.feeds.tests.factories import FeedCategoryFactory, FeedFactory
from legadilo.feeds.tests.fixtures import get_feed_fixture_content
from legadilo.reading.models import Article
from legadilo.reading.tests.factories import ArticleFactory, CommentFactory


class TestExportArticlesView:
    @pytest.fixture(autouse=True)
    def _setup_data(self):
        self.url = reverse("import_export:export_articles")

    def test_not_logged_in(self, client):
        response = client.get(self.url)

        assert_redirected_to_login_page(response)

    def test_export_no_data(self, logged_in_sync_client, snapshot):
        response = logged_in_sync_client.get(self.url)

        assert response.status_code == HTTPStatus.OK
        assert response.headers["Content-Type"] == "text/csv"
        assert read_streamable_response(response) == snapshot

    def test_export_some_content(self, logged_in_sync_client, user, snapshot):
        FeedCategoryFactory(user=user, id=1, title="Some category")
        FeedFactory(user=user, id=1, title="Some feed", feed_url="https://example.com/feeds/0.xml")
        article = ArticleFactory(
            user=user,
            id=1,
            title="Some article",
            url="https://example.com/article/0",
            published_at=utcdt(2024, 6, 23, 12, 0, 0),
            updated_at=utcdt(2024, 6, 23, 12, 0, 0),
        )
        CommentFactory(article=article, text="Some comment")

        response = logged_in_sync_client.get(self.url)

        assert response.status_code == HTTPStatus.OK
        assert response.headers["Content-Type"] == "text/csv"
        assert read_streamable_response(response) == snapshot


class TestImportExportArticlesView:
    @pytest.fixture(autouse=True)
    def _setup_data(self):
        self.url = reverse("import_export:import_export_articles")

    def test_not_logged_in(self, client):
        response = client.get(self.url)

        assert_redirected_to_login_page(response)

    def test_import_unsupported_file(self, logged_in_sync_client):
        buffer = BytesIO(b"stuff")
        with InMemoryUploadedFile(
            buffer,
            "some_file",
            "file.png",
            content_type="application/xml",
            size=100,
            charset="utf-8",
        ) as file:
            response = logged_in_sync_client.post(self.url, {"invalid_file": file})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        messages = list(get_messages(response.wsgi_request))
        assert messages == [
            Message(
                level=DEFAULT_LEVELS["ERROR"],
                message="This file type is not supported for imports.",
            )
        ]


class TestImportCustomCSV:
    @pytest.fixture(autouse=True)
    def _setup_data(self):
        self.url = reverse("import_export:import_export_articles")

    def test_import_invalid_file(self, logged_in_sync_client):
        buffer = BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01")
        with InMemoryUploadedFile(
            buffer,
            "some_file",
            "file.png",
            content_type="application/xml",
            size=100,
            charset="utf-8",
        ) as file:
            response = logged_in_sync_client.post(
                self.url,
                {
                    "csv_file": file,
                },
            )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.template_name == "import_export/import_export_articles.html"
        assert response.context_data["import_custom_csv_form"].errors == {}
        assert Feed.objects.count() == 0
        assert Article.objects.count() == 0
        messages = list(get_messages(response.wsgi_request))
        assert messages == [
            Message(
                level=DEFAULT_LEVELS["ERROR"],
                message="The file you supplied is not valid.",
            )
        ]

    def test_import_in_memory_file(self, logged_in_sync_client, httpx2_mock):
        httpx2_mock.add_response(
            url="https://example.com/rss2.xml",
            content=get_feed_fixture_content("sample_rss.xml"),
        )
        httpx2_mock.add_response(
            url="https://example.com/rss4.xml",
            content=get_feed_fixture_content("sample_atom.xml"),
        )
        httpx2_mock.add_response(url="https://example.com/rss8.xml", content="")
        httpx2_mock.add_response(url="https://example.com/existing.xml", content="")

        with (
            Path(settings.APPS_DIR / "import_export/tests/fixtures/custom_csv/custom_csv.csv").open(
                "r", encoding="utf-8"
            ) as f,
            InMemoryUploadedFile(
                f,
                "some_file",
                "file.png",
                content_type="application/xml",
                size=100,
                charset="utf-8",
            ) as file,
        ):
            response = logged_in_sync_client.post(
                self.url,
                {
                    "csv_file": file,
                },
            )

        assert response.status_code == HTTPStatus.OK
        assert response.template_name == "import_export/import_export_articles.html"
        assert response.context_data["import_custom_csv_form"].errors == {}
        assert Feed.objects.count() > 0
        assert Article.objects.count() > 0
        messages = list(get_messages(response.wsgi_request))
        assert messages == [
            Message(
                level=DEFAULT_LEVELS["SUCCESS"],
                message="Successfully imported 4 feeds, 3 feed categories and 8 articles.",
            )
        ]

    def test_import_temporary_file(self, logged_in_sync_client, httpx2_mock, settings):
        settings.FILE_UPLOAD_MAX_MEMORY_SIZE = 0
        httpx2_mock.add_response(
            url="https://example.com/rss2.xml",
            content=get_feed_fixture_content("sample_rss.xml"),
        )
        httpx2_mock.add_response(
            url="https://example.com/rss4.xml",
            content=get_feed_fixture_content("sample_atom.xml"),
        )
        httpx2_mock.add_response(url="https://example.com/rss8.xml", content="")
        httpx2_mock.add_response(url="https://example.com/existing.xml", content="")
        with TemporaryUploadedFile(
            settings.APPS_DIR / "import_export/tests/fixtures/custom_csv/custom_csv.csv",  # type: ignore[arg-type]
            "text/csv",
            size=100,
            charset="utf-8",
        ) as temp_file:
            input_csv = Path(
                settings.APPS_DIR / "import_export/tests/fixtures/custom_csv/custom_csv.csv"
            ).read_text(encoding="utf-8")
            Path(temp_file.file.name).write_text(input_csv, encoding="utf-8")

            response = logged_in_sync_client.post(
                self.url,
                {
                    "csv_file": temp_file,
                },
            )

        assert response.status_code == HTTPStatus.OK
        assert response.template_name == "import_export/import_export_articles.html"
        assert response.context_data["import_custom_csv_form"].errors == {}
        assert Feed.objects.count() > 0
        assert Article.objects.count() > 0
        messages = list(get_messages(response.wsgi_request))
        assert messages == [
            Message(
                level=DEFAULT_LEVELS["SUCCESS"],
                message="Successfully imported 4 feeds, 3 feed categories and 8 articles.",
            )
        ]


class TestImportWallabag:
    @pytest.fixture(autouse=True)
    def _setup_data(self):
        self.url = reverse("import_export:import_export_articles")

    def test_import_invalid_data(self, logged_in_sync_client):
        buffer = BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01")
        with InMemoryUploadedFile(
            buffer,
            "some_file",
            "file.png",
            content_type="application/xml",
            size=100,
            charset="utf-8",
        ) as file:
            response = logged_in_sync_client.post(
                self.url,
                {
                    "wallabag_file": file,
                },
            )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.template_name == "import_export/import_export_articles.html"
        assert response.context_data["import_wallabag_form"].errors == {}
        assert Feed.objects.count() == 0
        assert Article.objects.count() == 0
        messages = list(get_messages(response.wsgi_request))
        assert messages == [
            Message(
                level=DEFAULT_LEVELS["ERROR"],
                message="The file you supplied is not valid.",
            )
        ]

    def test_import_invalid_file(self, logged_in_sync_client):
        with (
            Path(
                settings.APPS_DIR / "import_export/tests/fixtures/wallabag/invalid_wallabag.json"
            ).open("r", encoding="utf-8") as f,
            InMemoryUploadedFile(
                f,
                "some_file",
                "file.png",
                content_type="application/json",
                size=100,
                charset="utf-8",
            ) as file,
        ):
            response = logged_in_sync_client.post(
                self.url,
                {
                    "wallabag_file": file,
                },
            )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.template_name == "import_export/import_export_articles.html"
        assert response.context_data["import_wallabag_form"].errors == {}
        assert Feed.objects.count() == 0
        assert Article.objects.count() == 0
        messages = list(get_messages(response.wsgi_request))
        assert messages == [
            Message(
                level=DEFAULT_LEVELS["ERROR"],
                message="The file you supplied is not valid.",
            )
        ]

    def test_import_valid_file(self, logged_in_sync_client, snapshot):
        with (
            Path(
                settings.APPS_DIR / "import_export/tests/fixtures/wallabag/valid_wallabag.json"
            ).open("r", encoding="utf-8") as f,
            InMemoryUploadedFile(
                f,
                "some_file",
                "file.png",
                content_type="application/json",
                size=100,
                charset="utf-8",
            ) as file,
        ):
            response = logged_in_sync_client.post(
                self.url,
                {
                    "wallabag_file": file,
                },
            )

        assert response.status_code == HTTPStatus.OK
        assert response.template_name == "import_export/import_export_articles.html"
        assert response.context_data["import_wallabag_form"].errors == {}
        assert Feed.objects.count() == 0
        assert Article.objects.count() > 0
        messages = list(get_messages(response.wsgi_request))
        assert messages == [
            Message(
                level=DEFAULT_LEVELS["SUCCESS"],
                message="Successfully imported 1 articles",
            )
        ]
        assert (
            serialize_for_snapshot(
                list(
                    Article.objects.order_by("url").values(
                        *all_model_fields_except(
                            Article, {"id", "user", "obj_created_at", "obj_updated_at"}
                        )
                    )
                )
            )
            == snapshot
        )
