# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import re
from datetime import UTC, datetime

import pytest
import time_machine

from legadilo.core.models import Timezone
from legadilo.core.utils.testing import serialize_for_snapshot
from legadilo.core.utils.time_utils import utcdt, utcnow
from legadilo.feeds.models import FeedArticle, FeedUpdate
from legadilo.feeds.services.feed_parsing import ArticleData, FeedData
from legadilo.feeds.tests.factories import (
    FeedArticleFactory,
    FeedCategoryFactory,
    FeedFactory,
    FeedUpdateFactory,
)
from legadilo.reading import constants as reading_constants
from legadilo.reading.models import Article
from legadilo.reading.tests.factories import ArticleDataFactory, ArticleFactory, TagFactory
from legadilo.users.models import Notification
from legadilo.users.tests.factories import UserFactory

from ... import constants as feeds_constants
from ...models import Feed

ONE_ARTICLE_FEED_DATA = FeedData(
    feed_url="https://example.com/feeds/atom.xml",
    site_url="https://example.com",
    title="Awesome website",
    description="A description",
    feed_type=feeds_constants.SupportedFeedType.atom,
    etag="W/etag",
    last_modified=None,
    articles=[
        ArticleData(
            external_article_id="some-article-1",
            title="Article 1",
            summary="Summary 1",
            content="Description 1",
            content_type="text/plain",
            table_of_content=(),
            authors=("Author",),
            contributors=(),
            tags=(),
            url="https://example.com/article/1",
            preview_picture_url="https://example.com/preview.png",
            preview_picture_alt="Some image alt",
            published_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
            source_title="Awesome website",
            language="fr",
        )
    ],
)


@pytest.mark.django_db
class TestFeedQuerySet:
    def test_for_user(self, user, other_user):
        feed = FeedFactory(user=user)
        FeedFactory(user=other_user)

        feeds = Feed.objects.get_queryset().for_user(user)

        assert list(feeds) == [feed]

    @time_machine.travel("2024-05-08 10:00:00")
    def test_for_update(self, user):
        feed_updated_more_than_one_hour_ago = FeedFactory(
            title="Updated more than one hour ago",
            user=user,
            refresh_delay=feeds_constants.FeedRefreshDelays.HOURLY,
        )
        with time_machine.travel("2024-05-08 09:00:00"):
            FeedUpdateFactory(feed=feed_updated_more_than_one_hour_ago)
        disabled_feed_updated_more_than_one_hour_ago = FeedFactory(
            title="Disabled feed",
            user=user,
            refresh_delay=feeds_constants.FeedRefreshDelays.HOURLY,
            disabled_at=utcnow(),
        )
        with time_machine.travel("2024-05-08 09:00:00"):
            FeedUpdateFactory(feed=disabled_feed_updated_more_than_one_hour_ago)
        feed_updated_less_than_one_hour_ago = FeedFactory(
            title="Updated less than one hour ago",
            user=user,
            refresh_delay=feeds_constants.FeedRefreshDelays.HOURLY,
        )
        with time_machine.travel("2024-05-08 07:30:00"):
            FeedUpdateFactory(feed=feed_updated_less_than_one_hour_ago)
        with time_machine.travel("2024-05-08 09:30:00"):
            FeedUpdateFactory(feed=feed_updated_less_than_one_hour_ago)
        feed_updated_this_morning = FeedFactory(
            title="Updated this morning",
            user=user,
            refresh_delay=feeds_constants.FeedRefreshDelays.EVERY_MORNING,
        )
        with time_machine.travel("2024-05-07 09:00:00"):
            FeedUpdateFactory(feed=feed_updated_this_morning)
        with time_machine.travel("2024-05-08 09:00:00"):
            FeedUpdateFactory(feed=feed_updated_this_morning)
        feed_not_yet_updated_this_morning = FeedFactory(
            title="Not yet updated this morning",
            user=user,
            refresh_delay=feeds_constants.FeedRefreshDelays.EVERY_MORNING,
        )
        with time_machine.travel("2024-05-07 09:00:00"):
            FeedUpdateFactory(feed=feed_not_yet_updated_this_morning)

        feed_no_feed_update_object = FeedFactory(
            title="Not yet updated this morning",
            user=user,
            refresh_delay=feeds_constants.FeedRefreshDelays.EVERY_MORNING,
        )

        feeds_to_update = Feed.objects.get_queryset().for_update(user)

        assert list(feeds_to_update) == [
            feed_updated_more_than_one_hour_ago,
            feed_not_yet_updated_this_morning,
            feed_no_feed_update_object,
        ]

    @time_machine.travel("2024-05-08 10:00:00")
    def test_for_update_non_utc_user_nothing_to_update(self, user):
        user.settings.timezone = Timezone.objects.get(name="Europe/Paris")
        user.settings.save()

        feed_updated_more_than_one_hour_ago = FeedFactory(
            title="Updated more than one hour ago",
            user=user,
            refresh_delay=feeds_constants.FeedRefreshDelays.HOURLY,
        )
        with time_machine.travel("2024-05-08 09:00:00"):
            FeedUpdateFactory(feed=feed_updated_more_than_one_hour_ago)
        feed_not_yet_updated_this_morning = FeedFactory(
            title="Not yet updated this morning",
            user=user,
            refresh_delay=feeds_constants.FeedRefreshDelays.EVERY_MORNING,
        )
        with time_machine.travel("2024-05-07 09:00:00"):
            FeedUpdateFactory(feed=feed_not_yet_updated_this_morning)

        # Morning feed update time passed in user TZ (but not in UTC).
        feeds_to_update = Feed.objects.get_queryset().for_update(user)

        assert list(feeds_to_update) == [
            feed_updated_more_than_one_hour_ago,
        ]

    @time_machine.travel("2024-05-08 08:00:00")
    def test_for_update_non_utc_user(self, user):
        user.settings.timezone = Timezone.objects.get(name="Europe/Paris")
        user.settings.save()

        feed_not_yet_updated_this_morning = FeedFactory(
            title="Not yet updated this morning",
            user=user,
            refresh_delay=feeds_constants.FeedRefreshDelays.EVERY_MORNING,
        )
        with time_machine.travel("2024-05-07 09:00:00"):
            FeedUpdateFactory(feed=feed_not_yet_updated_this_morning)

        # Morning feed can be updated in user TZ (although not yet in UTC).
        feeds_to_update = Feed.objects.get_queryset().for_update(user)

        assert list(feeds_to_update) == [
            feed_not_yet_updated_this_morning,
        ]

    @time_machine.travel("2024-05-08 13:00:00")
    def test_for_update_not_morning(self, user):
        feed_updated_this_morning = FeedFactory(
            user=user, refresh_delay=feeds_constants.FeedRefreshDelays.EVERY_MORNING
        )
        with time_machine.travel("2024-05-08 10:00:00"):
            FeedUpdateFactory(feed=feed_updated_this_morning)
        feed_not_yet_updated_this_morning = FeedFactory(
            user=user, refresh_delay=feeds_constants.FeedRefreshDelays.EVERY_MORNING
        )
        with time_machine.travel("2024-05-07 10:00:00"):
            FeedUpdateFactory(feed=feed_not_yet_updated_this_morning)

        feeds_to_update = Feed.objects.get_queryset().for_update(user)

        assert list(feeds_to_update) == []

    def test_update_feed_once_a_month(self, user):
        feed_to_update_on_first_day_of_month = FeedFactory(
            user=user, refresh_delay=feeds_constants.FeedRefreshDelays.FIRST_DAY_OF_THE_MONTH
        )
        with time_machine.travel("2024-01-01 00:00:00"):
            FeedUpdateFactory(feed=feed_to_update_on_first_day_of_month)

        with time_machine.travel("2024-02-01 00:00:00"):
            feeds_to_update = Feed.objects.get_queryset().for_update(user)

        assert list(feeds_to_update) == [feed_to_update_on_first_day_of_month]

    def test_only_with_ids(self):
        feed1 = FeedFactory(disabled_at=None)
        FeedFactory(disabled_at=None)

        feeds = list(Feed.objects.get_queryset().only_with_ids([feed1.id]))

        assert feeds == [feed1]

    def test_only_enabled(self):
        feed1 = FeedFactory(disabled_at=None)
        FeedFactory(disabled_at=utcnow())

        feeds = list(Feed.objects.get_queryset().only_enabled())

        assert feeds == [feed1]

    def test_for_url_search(self):
        feed1 = FeedFactory()
        FeedFactory()

        feeds = list(
            Feed.objects.get_queryset().for_feed_urls_search([
                "https://example.com/toto",
                feed1.feed_url,
            ])
        )

        assert feeds == [feed1]

    def test_for_status_search(self):
        feed1 = FeedFactory(disabled_at=None)
        feed2 = FeedFactory(disabled_at=utcnow())

        assert list(Feed.objects.get_queryset().for_status_search(enabled=True)) == [feed1]
        assert list(Feed.objects.get_queryset().for_status_search(enabled=False)) == [feed2]


@pytest.mark.django_db
class TestFeedManager:
    @pytest.fixture(autouse=True)
    def _setup_data(self, user):
        self.default_feed_url = "https://example.com/feeds/atom.exsiting.xml"
        self.feed = FeedFactory(
            id=1, feed_url=self.default_feed_url, user=user, title="Default feed"
        )
        self.initial_feed_count = 1

    def test_get_feeds_by_categories_no_categories(self, other_user):
        feeds_by_categories = Feed.objects.get_by_categories(other_user)

        assert feeds_by_categories == {}

    def test_get_feeds_by_categories(self, user, other_user):
        feed_1_without_category = FeedFactory(user=user)
        feed_2_without_category = FeedFactory(user=user)
        feed_category = FeedCategoryFactory(user=user)
        feed_1_with_category = FeedFactory(
            user=user, title="Feed 1 with category", category=feed_category
        )
        feed_2_with_category = FeedFactory(
            user=user, title="Feed 2 with category", slug="", category=feed_category
        )
        other_feed_category = FeedCategoryFactory(user=user)
        feed_other_category = FeedFactory(user=user, category=other_feed_category)
        feed_category_other_user = FeedCategoryFactory(user=other_user)
        FeedFactory(user=other_user, category=feed_category_other_user, title="Feed other user")

        feeds_by_categories = Feed.objects.get_by_categories(user)

        assert feeds_by_categories == {
            None: [self.feed, feed_1_without_category, feed_2_without_category],
            feed_category.title: [feed_1_with_category, feed_2_with_category],
            other_feed_category.title: [feed_other_category],
        }

    def test_get_feeds_by_categories_with_search(self, user, other_user):
        FeedFactory(user=user)

        feeds_by_categories = Feed.objects.get_by_categories(
            user, searched_text=self.feed.title.upper()
        )

        assert feeds_by_categories == {
            None: [self.feed],
        }

    def test_get_articles(self, user):
        article_of_feed = ArticleFactory(user=user)
        FeedArticle.objects.create(feed=self.feed, article=article_of_feed)
        other_feed = FeedFactory(user=user)
        article_of_other_feed = ArticleFactory(user=user)
        FeedArticle.objects.create(feed=other_feed, article=article_of_other_feed)

        articles_qs = Feed.objects.get_articles(self.feed)

        assert list(articles_qs) == [article_of_feed]

    def test_recreate_feed_from_data_on_active_feed(self, user, django_assert_num_queries):
        existing_feed = FeedFactory(user=user, disabled_at=None)

        with django_assert_num_queries(3):
            feed, created = Feed.objects.create_from_metadata(
                FeedData(
                    feed_url=existing_feed.feed_url,
                    site_url="https://example.com",
                    title="Awesome website",
                    description="A description",
                    feed_type=feeds_constants.SupportedFeedType.atom,
                    etag="W/etag",
                    last_modified=None,
                    articles=[],
                ),
                user,
                feeds_constants.FeedRefreshDelays.DAILY_AT_NOON,
                0,
                [],
            )

        assert feed == existing_feed
        assert not created
        assert feed.disabled_at is None
        assert feed.articles.count() == 0
        assert feed.feed_updates.count() == 0

    def test_recreate_feed_from_data_on_disabled_feed(self, user, django_assert_num_queries):
        existing_feed = FeedFactory(
            feed_url=ONE_ARTICLE_FEED_DATA.feed_url, user=user, disabled_at=utcnow()
        )

        with django_assert_num_queries(20):
            feed, created = Feed.objects.create_from_metadata(
                ONE_ARTICLE_FEED_DATA,
                user,
                feeds_constants.FeedRefreshDelays.DAILY_AT_NOON,
                0,
                [],
            )

        assert feed.id == existing_feed.id
        assert not created
        assert feed.disabled_at is None
        assert feed.articles.count() > 0
        assert feed.feed_updates.count() == 1

    def test_create_from_feed_data(self, user, django_assert_num_queries):
        with django_assert_num_queries(20):
            feed, created = Feed.objects.create_from_metadata(
                FeedData(
                    feed_url="https://example.com/feeds/atom.xml",
                    site_url="https://example.com",
                    title="Awesome website",
                    description="A description",
                    feed_type=feeds_constants.SupportedFeedType.atom,
                    etag="W/etag",
                    last_modified=None,
                    articles=[
                        ArticleData(
                            external_article_id="some-article-1",
                            title="Article 1",
                            summary="Summary 1",
                            content="Description 1",
                            content_type="text/plain",
                            table_of_content=(),
                            authors=("Author",),
                            contributors=(),
                            tags=(),
                            url="https://example.com/article/1",
                            preview_picture_url="https://example.com/preview.png",
                            preview_picture_alt="Some image alt",
                            published_at=datetime.now(tz=UTC),
                            updated_at=datetime.now(tz=UTC),
                            source_title="Awesome website",
                            language="fr",
                        )
                    ],
                ),
                user,
                feeds_constants.FeedRefreshDelays.DAILY_AT_NOON,
                7,
                [],
            )

        assert created
        assert Feed.objects.all().count() == self.initial_feed_count + 1
        assert feed.id > 0
        assert feed.tags.count() == 0
        assert feed.feed_url == "https://example.com/feeds/atom.xml"
        assert feed.site_url == "https://example.com"
        assert feed.title == "Awesome website"
        assert feed.slug == "awesome-website"
        assert feed.description == "A description"
        assert feed.feed_type == feeds_constants.SupportedFeedType.atom
        assert feed.refresh_delay == feeds_constants.FeedRefreshDelays.DAILY_AT_NOON
        assert feed.article_retention_time == 7
        assert feed.articles.count() > 0
        feed_update = FeedUpdate.objects.get_latest_success_for_feed_id(feed.id)
        assert feed_update.status == feeds_constants.FeedUpdateStatus.SUCCESS
        assert not feed_update.error_message
        assert feed_update.feed_etag == "W/etag"
        assert feed_update.feed_last_modified is None
        assert Article.objects.count() > 0
        article = Article.objects.first()
        assert article is not None
        assert article.tags.count() == 0

    def test_create_from_metadata_with_tags(self, user, django_assert_num_queries):
        tag = TagFactory()

        with django_assert_num_queries(23):
            feed, _ = Feed.objects.create_from_metadata(
                ONE_ARTICLE_FEED_DATA,
                user,
                feeds_constants.FeedRefreshDelays.DAILY_AT_NOON,
                0,
                [tag],
            )

        assert Feed.objects.all().count() == self.initial_feed_count + 1
        assert feed.id > 0
        assert list(feed.tags.all()) == [tag]
        assert feed.feed_url == "https://example.com/feeds/atom.xml"
        assert feed.site_url == "https://example.com"
        assert feed.title == "Awesome website"
        assert feed.description == "A description"
        assert feed.feed_type == feeds_constants.SupportedFeedType.atom
        assert feed.articles.count() > 0
        feed_update = FeedUpdate.objects.get_latest_success_for_feed_id(feed.id)
        assert feed_update.status == feeds_constants.FeedUpdateStatus.SUCCESS
        assert not feed_update.error_message
        assert feed_update.feed_etag == "W/etag"
        assert feed_update.feed_last_modified is None
        assert Article.objects.count() > 0
        article = Article.objects.first()
        assert article is not None
        assert list(article.tags.all()) == [tag]

    def test_can_create_duplicated_feed_for_different_user(self, user):
        other_user = UserFactory()

        Feed.objects.create_from_metadata(
            FeedData(
                feed_url=self.default_feed_url,
                site_url="https://example.com",
                title="Awesome website",
                description="A description",
                feed_type=feeds_constants.SupportedFeedType.atom,
                etag="W/etag",
                last_modified=None,
                articles=[],
            ),
            other_user,
            feeds_constants.FeedRefreshDelays.DAILY_AT_NOON,
            0,
            [],
        )

        assert list(Feed.objects.values_list("feed_url", flat=True)) == [
            self.default_feed_url,
            self.default_feed_url,
        ]

    def test_disabled(self):
        with time_machine.travel(utcdt(2024, 5, 28, 21), tick=False):
            Feed.objects.log_error(self.feed, "Something went wrong")

        self.feed.refresh_from_db()
        assert not self.feed.enabled
        assert self.feed.disabled_reason == "The server failed too many times to fetch the feed."
        assert self.feed.disabled_at == utcdt(2024, 5, 28, 21)
        feed_update = self.feed.feed_updates.last()
        assert feed_update.status == feeds_constants.FeedUpdateStatus.FAILURE
        assert feed_update.error_message == "Something went wrong"
        notification = Notification.objects.get()
        assert not notification.is_read
        assert notification.title == f"Feed '{self.feed.title}' was disabled"
        assert notification.content == "The server failed too many times to fetch the feed."
        assert re.match(r"/feeds/\d+/", notification.info_link)
        assert notification.info_link_text == "Edit feed"

    def test_update_feed(self, django_assert_num_queries):
        existing_article = ArticleFactory(
            url="https://example.com/article/existing",
            main_source_type=reading_constants.ArticleSourceType.MANUAL,
            main_source_title="Not a feed",
            user=self.feed.user,
            external_article_id="",
        )
        with time_machine.travel("2025-01-01"):
            FeedArticle.objects.create(feed=self.feed, article=existing_article)

        with django_assert_num_queries(15), time_machine.travel("2025-07-01", tick=False):
            Feed.objects.update_feed(
                self.feed,
                FeedData(
                    feed_url="https://example.com/feeds/atom.xml",
                    site_url="https://example.com",
                    title="Awesome website",
                    description="A description",
                    feed_type=feeds_constants.SupportedFeedType.atom,
                    etag="W/etag",
                    last_modified=None,
                    articles=[
                        ArticleData(
                            external_article_id="some-article-1",
                            title="Article 1",
                            summary="Summary 1",
                            content="Description 1",
                            content_type="text/plain",
                            table_of_content=(),
                            authors=("Author",),
                            contributors=(),
                            tags=(),
                            url="https://example.com/article/1",
                            preview_picture_url="https://example.com/preview.png",
                            preview_picture_alt="Some image alt",
                            published_at=datetime.now(tz=UTC),
                            updated_at=datetime.now(tz=UTC),
                            source_title=self.feed.title,
                            language="fr",
                        ),
                        ArticleData(
                            external_article_id="some-article-existing",
                            title="Article 2",
                            summary="Summary 2",
                            content="Description existing updated",
                            content_type="text/plain",
                            table_of_content=(),
                            authors=("Author",),
                            contributors=(),
                            tags=(),
                            url=existing_article.url,
                            preview_picture_url="",
                            preview_picture_alt="",
                            published_at=datetime.now(tz=UTC),
                            updated_at=datetime.now(tz=UTC),
                            source_title=self.feed.title,
                            language="fr",
                        ),
                    ],
                ),
            )

        assert self.feed.articles.count() == 2
        assert self.feed.feed_updates.count() == 1
        new_article = self.feed.articles.exclude(id=existing_article.id).get()
        assert new_article.title == "Article 1"
        assert new_article.main_source_type == reading_constants.ArticleSourceType.FEED
        assert new_article.main_source_title == self.feed.title
        assert new_article.main_feed == self.feed
        assert new_article.external_article_id == "some-article-1"
        new_article_feed_article = FeedArticle.objects.get(feed=self.feed, article=new_article)
        assert new_article_feed_article.feed_article_id == "some-article-1"
        assert new_article_feed_article.last_seen_at == utcdt(2025, 7, 1)
        existing_article.refresh_from_db()
        assert existing_article.main_source_type == reading_constants.ArticleSourceType.MANUAL
        assert existing_article.main_source_title != self.feed.title
        assert existing_article.main_feed is None
        assert not existing_article.external_article_id
        existing_article_feed_article = FeedArticle.objects.get(
            feed=self.feed, article=existing_article
        )
        assert existing_article_feed_article.feed_article_id == "some-article-existing"
        assert existing_article_feed_article.last_seen_at == utcdt(2025, 7, 1)

    def test_update_feed_some_articles_changed_url(self, django_assert_num_queries):
        existing_article = ArticleFactory(
            url="https://example.com/article/existing",
            main_source_type=reading_constants.ArticleSourceType.FEED,
            main_source_title="Some feed",
            user=self.feed.user,
        )
        with time_machine.travel("2025-01-01"):
            feed_article = FeedArticle.objects.create(
                feed=self.feed, article=existing_article, feed_article_id="some-article-existing"
            )

        with django_assert_num_queries(16), time_machine.travel("2025-07-01", tick=False):
            Feed.objects.update_feed(
                self.feed,
                FeedData(
                    feed_url="https://example.com/feeds/atom.xml",
                    site_url="https://example.com",
                    title="Awesome website",
                    description="A description",
                    feed_type=feeds_constants.SupportedFeedType.atom,
                    etag="W/etag",
                    last_modified=None,
                    articles=[
                        ArticleData(
                            external_article_id=feed_article.feed_article_id,
                            title="Article 2",
                            summary="Summary 2",
                            content="Description existing updated",
                            content_type="text/plain",
                            table_of_content=(),
                            authors=("Author",),
                            contributors=(),
                            tags=(),
                            url="http://example.com/new-url",
                            preview_picture_url="",
                            preview_picture_alt="",
                            published_at=datetime.now(tz=UTC),
                            updated_at=datetime.now(tz=UTC),
                            source_title=self.feed.title,
                            language="fr",
                        ),
                    ],
                ),
            )

        assert self.feed.articles.count() == 1
        assert self.feed.feed_updates.count() == 1
        existing_article.refresh_from_db()
        assert existing_article.url == "http://example.com/new-url"
        existing_article_feed_article = FeedArticle.objects.get(
            feed=self.feed, article=existing_article
        )
        assert existing_article_feed_article.feed_article_id == "some-article-existing"
        assert existing_article_feed_article.last_seen_at == utcdt(2025, 7, 1)

    def test_update_feed_some_articles_changed_url_already_exist(self, django_assert_num_queries):
        existing_article_with_good_url = ArticleFactory(
            url="https://example.com/article/the-true-url",
            main_source_type=reading_constants.ArticleSourceType.FEED,
            main_source_title="Some feed",
            user=self.feed.user,
        )
        existing_article_with_old_url = ArticleFactory(
            url="https://example.com/article/old-url",
            main_source_type=reading_constants.ArticleSourceType.FEED,
            main_source_title="Some feed",
            user=self.feed.user,
        )
        with time_machine.travel("2025-01-01"):
            feed_article_old_url = FeedArticle.objects.create(
                feed=self.feed,
                article=existing_article_with_old_url,
                feed_article_id="some-article-existing-id",
            )

        with django_assert_num_queries(15), time_machine.travel("2025-07-01", tick=False):
            Feed.objects.update_feed(
                self.feed,
                FeedData(
                    feed_url="https://example.com/feeds/atom.xml",
                    site_url="https://example.com",
                    title="Awesome website",
                    description="A description",
                    feed_type=feeds_constants.SupportedFeedType.atom,
                    etag="W/etag",
                    last_modified=None,
                    articles=[
                        ArticleData(
                            external_article_id=feed_article_old_url.feed_article_id,
                            title="Article 2",
                            summary="Summary 2",
                            content="Description existing updated",
                            content_type="text/plain",
                            table_of_content=(),
                            authors=("Author",),
                            contributors=(),
                            tags=(),
                            url=existing_article_with_good_url.url,
                            preview_picture_url="",
                            preview_picture_alt="",
                            published_at=datetime.now(tz=UTC),
                            updated_at=datetime.now(tz=UTC),
                            source_title=self.feed.title,
                            language="fr",
                        ),
                    ],
                ),
            )

        assert self.feed.articles.count() == 1
        existing_article_with_good_url.refresh_from_db()
        assert existing_article_with_good_url.feed_articles.count() == 1
        existing_article_with_old_url.refresh_from_db()
        assert existing_article_with_old_url.feed_articles.count() == 0
        existing_article_feed_article = FeedArticle.objects.get(
            feed=self.feed, article=existing_article_with_good_url
        )
        assert existing_article_feed_article.feed_article_id == "some-article-existing-id"
        assert existing_article_feed_article.last_seen_at == utcdt(2025, 7, 1)

    def test_update_feed_with_republication(self, django_assert_num_queries):
        existing_article_seen_recently = ArticleFactory(
            url="https://example.com/article/seen-recently",
            main_source_type=reading_constants.ArticleSourceType.FEED,
            main_source_title="Some feed",
            user=self.feed.user,
            read_at=utcdt(2024, 6, 1),
        )
        FeedArticle.objects.create(
            feed=self.feed,
            article=existing_article_seen_recently,
            feed_article_id="some-article-existing-seen-recently",
            last_seen_at=utcdt(2025, 6, 1),
        )
        existing_article_read_recently = ArticleFactory(
            url="https://example.com/article/read-recently",
            main_source_type=reading_constants.ArticleSourceType.FEED,
            main_source_title="Some feed",
            user=self.feed.user,
            read_at=utcdt(2025, 6, 1),
        )
        FeedArticle.objects.create(
            feed=self.feed,
            article=existing_article_read_recently,
            feed_article_id="some-article-existing-read-recently",
            last_seen_at=utcdt(2024, 6, 1),
        )
        existing_article_to_republish = ArticleFactory(
            url="https://example.com/article/to-republish",
            main_source_type=reading_constants.ArticleSourceType.FEED,
            main_source_title="Some feed",
            user=self.feed.user,
            read_at=utcdt(2024, 6, 1),
        )
        FeedArticle.objects.create(
            feed=self.feed,
            article=existing_article_to_republish,
            feed_article_id="some-article-existing-to-republish",
            last_seen_at=utcdt(2024, 6, 1),
        )

        with django_assert_num_queries(16), time_machine.travel("2025-07-01", tick=False):
            Feed.objects.update_feed(
                self.feed,
                FeedData(
                    feed_url="https://example.com/feeds/atom.xml",
                    site_url="https://example.com",
                    title="Awesome website",
                    description="A description",
                    feed_type=feeds_constants.SupportedFeedType.atom,
                    etag="W/etag",
                    last_modified=None,
                    articles=[
                        ArticleDataFactory(
                            external_article_id="some-article-existing-seen-recently"
                        ),
                        ArticleDataFactory(
                            external_article_id="some-article-existing-read-recently"
                        ),
                        ArticleDataFactory(
                            external_article_id="some-article-existing-to-republish"
                        ),
                    ],
                ),
            )

        assert self.feed.articles.count() == 3
        assert self.feed.feed_updates.count() == 1
        existing_article_seen_recently.refresh_from_db()
        assert existing_article_seen_recently.is_read
        existing_article_read_recently.refresh_from_db()
        assert existing_article_read_recently.is_read
        existing_article_to_republish.refresh_from_db()
        assert not existing_article_to_republish.is_read

    def test_update_feed_with_deleted_articles(self, django_assert_num_queries):
        deleted_url = "https://example.com/deleted/"
        deleted_feed_article_id = "some-article-deleted"
        FeedArticleFactory(feed=self.feed, feed_article_id=deleted_feed_article_id, article=None)

        with django_assert_num_queries(14):
            Feed.objects.update_feed(
                self.feed,
                FeedData(
                    feed_url="https://example.com/feeds/atom.xml",
                    site_url="https://example.com",
                    title="Awesome website",
                    description="A description",
                    feed_type=feeds_constants.SupportedFeedType.atom,
                    etag="W/etag",
                    last_modified=None,
                    articles=[
                        ArticleData(
                            external_article_id="some-article-1",
                            title="Article 1",
                            summary="Summary 1",
                            content="Description 1",
                            content_type="text/plain",
                            table_of_content=(),
                            authors=("Author",),
                            contributors=(),
                            tags=(),
                            url="https://example.com/article/1",
                            preview_picture_url="https://example.com/preview.png",
                            preview_picture_alt="Some image alt",
                            published_at=datetime.now(tz=UTC),
                            updated_at=datetime.now(tz=UTC),
                            source_title=self.feed.title,
                            language="fr",
                        ),
                        ArticleData(
                            external_article_id=deleted_feed_article_id,
                            title="Article 2",
                            summary="Summary 2",
                            content="Description",
                            content_type="text/plain",
                            table_of_content=(),
                            authors=("Author",),
                            contributors=(),
                            tags=(),
                            url=deleted_url,
                            preview_picture_url="",
                            preview_picture_alt="",
                            published_at=datetime.now(tz=UTC),
                            updated_at=datetime.now(tz=UTC),
                            source_title=self.feed.title,
                            language="fr",
                        ),
                    ],
                ),
            )

        assert self.feed.articles.count() == 1
        article = self.feed.articles.get()
        assert article.url != deleted_url
        assert self.feed.feed_updates.count() == 1
        feed_update = self.feed.feed_updates.get()
        assert feed_update.status == feeds_constants.FeedUpdateStatus.SUCCESS
        assert feed_update.ignored_article_ids == [deleted_feed_article_id]

    def test_export(self, user, other_user, snapshot, django_assert_num_queries):
        feed_category = FeedCategoryFactory(user=user, id=1, title="Some category")
        feed_with_category = FeedFactory(
            user=user,
            id=2,
            category=feed_category,
            title="Feed with category",
            feed_url="https://example.com/feeds/with_category.xml",
        )
        Feed(user=other_user, title="Feed other user")

        with django_assert_num_queries(1):
            feeds = Feed.objects.export(user)

        assert len(feeds) == 2
        assert not feeds[0]["category_id"]
        assert feeds[0]["feed_id"] == self.feed.id
        assert feeds[1]["category_id"] == feed_category.id
        assert feeds[1]["feed_id"] == feed_with_category.id
        assert serialize_for_snapshot(feeds) == snapshot

    def test_export_updated_since(self, user, other_user):
        with time_machine.travel("2024-05-01 12:00:00"):
            FeedFactory(
                user=user,
                id=2,
                title="Old feed",
                feed_url="https://example.com/feeds/with_category.xml",
            )

        feeds = Feed.objects.export(user, updated_since=utcdt(2025, 6, 1))

        assert len(feeds) == 1
        assert feeds[0]["feed_id"] == self.feed.id


class TestFeedModel:
    def test_disable(self):
        feed = FeedFactory.build(disabled_at=None, disabled_reason="")

        feed.disable()

        assert not feed.enabled
        assert feed.disabled_at is not None
        assert not feed.disabled_reason

    def test_disable_with_reason(self):
        feed = FeedFactory.build(disabled_at=None, disabled_reason="")

        feed.disable(reason="Some reason")

        assert not feed.enabled
        assert feed.disabled_at is not None
        assert feed.disabled_reason == "Some reason"

    def test_enable(self):
        feed = FeedFactory.build(disabled_at=utcnow(), disabled_reason="Test")

        feed.enable()

        assert feed.enabled
        assert feed.disabled_at is None
        assert not feed.disabled_reason
