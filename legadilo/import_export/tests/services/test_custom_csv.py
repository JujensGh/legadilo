# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import httpx2
import pytest
import time_machine

from config import settings
from legadilo.core.utils.testing import all_model_fields_except, serialize_for_snapshot
from legadilo.feeds.models import Feed, FeedArticle, FeedCategory
from legadilo.feeds.tests.factories import FeedCategoryFactory, FeedFactory
from legadilo.feeds.tests.fixtures import get_feed_fixture_content
from legadilo.import_export.services.custom_csv import import_custom_csv_file
from legadilo.import_export.services.exceptions import DataImportError
from legadilo.reading.models import Article, ArticlesGroup
from legadilo.reading.tests.factories import ArticleFactory, ArticlesGroupFactory


def test_import_invalid_custom_csv(user):
    with pytest.raises(DataImportError):
        import_custom_csv_file(
            user, settings.APPS_DIR / "import_export/tests/fixtures/custom_csv/invalid_file.csv"
        )


@pytest.mark.django_db
def test_import_empty_file(user):
    nb_imported_articles, nb_imported_feeds, nb_imported_categories = import_custom_csv_file(
        user, settings.APPS_DIR / "import_export/tests/fixtures/custom_csv/empty_file.csv"
    )

    assert nb_imported_articles == 0
    assert nb_imported_feeds == 0
    assert nb_imported_categories == 0
    assert Article.objects.count() == 0
    assert Feed.objects.count() == 0
    assert FeedCategory.objects.count() == 0


@pytest.mark.django_db
@time_machine.travel("2024-05-17 13:00:00", tick=False)
def test_import_custom_csv(user, httpx2_mock, snapshot):
    feed_category = FeedCategoryFactory(
        user=user, title="Existing category", slug="existing-category"
    )
    FeedFactory(
        user=user,
        feed_url="https://example.com/existing.xml",
        category=feed_category,
        title="Existing feed",
    )
    ArticleFactory(
        user=user,
        title="Existing article",
        external_article_id="",
        url="https://example.com/article/existing",
        published_at="2024-05-17T13:00:00+00:00",
        updated_at="2024-05-17T13:00:00+00:00",
    )
    articles_group = ArticlesGroupFactory(
        user=user, title="Existing group", description="Existing group description"
    )

    httpx2_mock.add_response(url="https://example.com/existing.xml", content="")
    httpx2_mock.add_response(
        url="https://example.com/rss2.xml",
        content=get_feed_fixture_content("sample_rss.xml"),
    )
    httpx2_mock.add_response(
        url="https://example.com/rss4.xml",
        content=get_feed_fixture_content("sample_atom.xml"),
    )
    httpx2_mock.add_exception(
        httpx2.HTTPError("Failed to fetch"),
        url="https://example.com/rss8.xml",
    )

    nb_imported_articles, nb_imported_feeds, nb_imported_categories = import_custom_csv_file(
        user, settings.APPS_DIR / "import_export/tests/fixtures/custom_csv/custom_csv.csv"
    )

    assert nb_imported_articles == 8
    assert nb_imported_feeds == 3
    assert nb_imported_categories == 2
    assert Article.objects.count() == 10
    assert ArticlesGroup.objects.count() == 2
    assert articles_group.articles.all().count() == 1
    assert Article.objects.filter(group__isnull=False).count() == 2
    assert set(Article.objects.filter(main_feed__isnull=False).values_list("url", flat=True)) == {
        "https://example.com/articles/with-tags",  # From a feed file.
        "http://example.org/entry/3",  # From a feed file.
        "https://example.com/article/4",
    }
    assert Feed.objects.count() == 4
    assert FeedCategory.objects.count() == 3
    assert FeedArticle.objects.count() == 5

    assert serialize_for_snapshot(
        list(
            Article.objects.order_by("id").values(
                *all_model_fields_except(
                    Article,
                    {"id", "user", "obj_created_at", "obj_updated_at", "main_feed", "group"},
                )
            )
        )
    ) == snapshot(name="articles")
    assert serialize_for_snapshot(
        list(
            Feed.objects.order_by("id").values(
                *all_model_fields_except(
                    Feed, {"id", "user", "category", "created_at", "updated_at"}
                ),
                "category__title",
            )
        )
    ) == snapshot(name="feeds")
    assert serialize_for_snapshot(
        list(
            FeedCategory.objects.order_by("id").values(
                *all_model_fields_except(FeedCategory, {"id", "user", "created_at", "updated_at"})
            )
        )
    ) == snapshot(name="feed_categories")
