# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Any

import httpx2
import pytest

from legadilo.core.utils.testing import serialize_for_snapshot
from legadilo.feeds.constants import SupportedFeedType
from legadilo.feeds.services.feed_parsing import (
    FeedData,
    FeedFileTooBigError,
    MultipleFeedFoundError,
    NoFeedUrlFoundError,
    _find_feed_page_content,
    _find_youtube_rss_feed_url,
    _get_feed_site_url,
    _parse_articles_in_feed,
    get_feed_data,
    parse_feed,
)

from ... import constants
from ..fixtures import (
    get_feed_fixture_content,
    get_page_for_feed_subscription_content,
)


class TestFindFeedUrl:
    @pytest.mark.parametrize(
        ("content", "expected_url"),
        [
            pytest.param(
                get_page_for_feed_subscription_content({
                    "feed_urls": """<link href="https://www.jujens.eu/feeds/all.rss.xml" type="application/rss+xml" rel="alternate" title="Jujens' blog RSS">""",  # ruff:ignore[line-too-long]
                }),
                "https://www.jujens.eu/feeds/all.rss.xml",
                id="single-rss-link",
            ),
            pytest.param(
                get_page_for_feed_subscription_content({
                    "feed_urls": """<link href="https://www.jujens.eu/feeds/all.atom.xml" type="application/atom+xml" rel="alternate" title="Jujens' blog Atom">""",  # ruff:ignore[line-too-long]
                }),
                "https://www.jujens.eu/feeds/all.atom.xml",
                id="single-atom-link",
            ),
            pytest.param(
                get_page_for_feed_subscription_content({
                    "feed_urls": """<link href="https://www.jujens.eu/feeds/all.atom.xml" type="application/atom+xml" rel="alternate" title="Jujens' blog Atom">
                    <link href="//www.jujens.eu/feeds/all.atom.xml" type="application/atom+xml" rel="alternate" title="Jujens' blog Atom">""",  # ruff:ignore[line-too-long]
                }),
                "https://www.jujens.eu/feeds/all.atom.xml",
                id="duplicate-link",
            ),
            pytest.param(
                get_page_for_feed_subscription_content({
                    "feed_urls": """<link href="//www.jujens.eu/feeds/all.atom.xml" type="application/atom+xml" rel="alternate" title="Jujens' blog Atom">>""",  # ruff:ignore[line-too-long]
                }),
                "https://www.jujens.eu/feeds/all.atom.xml",
                id="link-no-scheme",
            ),
        ],
    )
    def test_find_one_url(self, content: str, expected_url: str):
        url = _find_feed_page_content(content)

        assert url == expected_url

    @pytest.mark.parametrize(
        "content",
        [
            pytest.param("", id="empty-string"),
            pytest.param("<head></head", id="bad-html"),
            pytest.param(get_page_for_feed_subscription_content({"feed_urls": ""}), id="no-links"),
            pytest.param(
                get_page_for_feed_subscription_content({"feed_urls": "invalid data"}),
                id="invalid-data-in-head",
            ),
            pytest.param(
                get_page_for_feed_subscription_content({
                    "feed_urls": """<link type="application/rss+xml" rel="alternate" title="Jujens' blog RSS">""",  # ruff:ignore[line-too-long]
                }),
                id="no-href",
            ),
            pytest.param(
                get_page_for_feed_subscription_content({
                    "feed_urls": """<link href="" type="application/rss+xml" rel="alternate" title="Jujens' blog RSS">""",  # ruff:ignore[line-too-long]
                }),
                id="empty-href",
            ),
        ],
    )
    def test_cannot_find_feed_url(self, content):
        with pytest.raises(NoFeedUrlFoundError):
            _find_feed_page_content(content)

    @pytest.mark.parametrize(
        ("content", "expected_urls"),
        [
            pytest.param(
                get_page_for_feed_subscription_content({
                    "feed_urls": """<link href="//www.jujens.eu/feeds/all.rss.xml" type="application/rss+xml" rel="alternate" title="Full feed">
                    <link href="//www.jujens.eu/feeds/cat1.rss.xml" type="application/rss+xml" rel="alternate" title="Cat 1 feed">""",  # ruff:ignore[line-too-long]
                }),
                [
                    ("https://www.jujens.eu/feeds/all.rss.xml", "Full feed"),
                    ("https://www.jujens.eu/feeds/cat1.rss.xml", "Cat 1 feed"),
                ],
                id="multiple-rss-links",
            ),
            pytest.param(
                get_page_for_feed_subscription_content({
                    "feed_urls": """<link href="//www.jujens.eu/feeds/all.atom.xml" type="application/atom+xml" rel="alternate" title="Full feed">
                    <link href="//www.jujens.eu/feeds/cat1.atom.xml" type="application/atom+xml" rel="alternate" title="Cat 1 feed">""",  # ruff:ignore[line-too-long]
                }),
                [
                    ("https://www.jujens.eu/feeds/all.atom.xml", "Full feed"),
                    ("https://www.jujens.eu/feeds/cat1.atom.xml", "Cat 1 feed"),
                ],
                id="multiple-atom-links",
            ),
            pytest.param(
                get_page_for_feed_subscription_content({
                    "feed_urls": """<link href="//www.jujens.eu/feeds/all.rss.xml" type="application/rss+xml" rel="alternate" title="Full feed">
                    <link href="//www.jujens.eu/feeds/cat1.atom.xml" type="application/atom+xml" rel="alternate" title="Cat 1 feed">""",  # ruff:ignore[line-too-long]
                }),
                [
                    ("https://www.jujens.eu/feeds/cat1.atom.xml", "Cat 1 feed"),
                    ("https://www.jujens.eu/feeds/all.rss.xml", "Full feed"),
                ],
                id="various-types",
            ),
            pytest.param(
                get_page_for_feed_subscription_content({
                    "feed_urls": """<link href="//www.jujens.eu/feeds/all.rss.xml" type="application/rss+xml" rel="alternate">
                    <link href="//www.jujens.eu/feeds/cat1.atom.xml" type="application/atom+xml" rel="alternate" title="">""",  # ruff:ignore[line-too-long]
                }),
                [
                    (
                        "https://www.jujens.eu/feeds/cat1.atom.xml",
                        "https://www.jujens.eu/feeds/cat1.atom.xml",
                    ),
                    (
                        "https://www.jujens.eu/feeds/all.rss.xml",
                        "https://www.jujens.eu/feeds/all.rss.xml",
                    ),
                ],
                id="missing-titles",
            ),
        ],
    )
    def test_find_multiple_url(self, content, expected_urls):
        with pytest.raises(MultipleFeedFoundError) as excinfo:
            _find_feed_page_content(content)

        assert excinfo.value.feed_urls == expected_urls


class TestGetFeedData:
    @pytest.mark.parametrize(
        ("feed_url", "feed_content", "feed_type"),
        [
            pytest.param(
                "https://www.jujens.eu/feed/rss.xml",
                get_feed_fixture_content("sample_rss.xml"),
                SupportedFeedType.rss20,
                id="sample-rss-feed",
            ),
            pytest.param(
                "https://www.jujens.eu/feed/atom.xml",
                get_feed_fixture_content("sample_atom.xml"),
                SupportedFeedType.atom10,
                id="sample-atom-feed",
            ),
        ],
    )
    def test_get_feed_data_from_feed_url(
        self, feed_url: str, feed_content: str, feed_type: SupportedFeedType, httpx2_mock, snapshot
    ):
        httpx2_mock.add_response(text=feed_content, url=feed_url)

        with httpx2.Client() as client:
            feed_data = get_feed_data(feed_url, client=client)

        assert feed_data.feed_url == feed_url
        assert feed_data.feed_type == feed_type
        assert serialize_for_snapshot(feed_data) == snapshot

    @pytest.mark.parametrize(
        ("user_entered_url", "expected_url"),
        [
            pytest.param(
                "https://www.youtube.com/feeds/videos.xml?channel_id=toto",
                "https://www.youtube.com/feeds/videos.xml?channel_id=toto",
                id="already-is-channel-feed-link",
            ),
            pytest.param(
                "https://www.youtube.com/feeds/videos.xml?playlist_id=toto",
                "https://www.youtube.com/feeds/videos.xml?playlist_id=toto",
                id="already-is-playlist-feed-link",
            ),
            pytest.param(
                "https://www.youtube.com/channel/toto",
                "https://www.youtube.com/feeds/videos.xml?channel_id=toto",
                id="is-channel-with-id",
            ),
            pytest.param(
                "https://www.youtube.com/watch?v=video_id&list=toto",
                "https://www.youtube.com/feeds/videos.xml?playlist_id=toto",
                id="is-playlist-url",
            ),
            pytest.param(
                "https://www.youtube.com/watch?v=someVideo",
                "https://www.youtube.com/watch?v=someVideo",
                id="some-other-youtube-url",
            ),
        ],
    )
    def test_find_youtube_rss_feed_url(self, user_entered_url: str, expected_url: str):
        youtube_feed_url = _find_youtube_rss_feed_url(user_entered_url)

        assert youtube_feed_url == expected_url

    def test_get_feed_data_from_page_url(self, httpx2_mock, snapshot):
        page_content = get_page_for_feed_subscription_content({
            "feed_urls": """<link href="//www.jujens.eu/feeds/all.atom.xml" type="application/atom+xml" rel="alternate" title="Jujens' blog Atom">""",  # ruff:ignore[line-too-long]
        })
        page_url = "https://www.jujens.eu"
        feed_url = "https://www.jujens.eu/feeds/all.atom.xml"
        httpx2_mock.add_response(text=page_content, url=page_url)
        httpx2_mock.add_response(text=get_feed_fixture_content("sample_atom.xml"), url=feed_url)

        with httpx2.Client() as client:
            feed_data = get_feed_data(page_url, client=client)

        assert feed_data.feed_type == SupportedFeedType.atom10
        assert serialize_for_snapshot(feed_data) == snapshot

    def test_feed_file_too_big(self, httpx2_mock, mocker):
        mocker.patch(
            "legadilo.feeds.services.feed_parsing.sys.getsizeof", return_value=11 * 1024 * 1024
        )
        httpx2_mock.add_response(
            text=get_feed_fixture_content("sample_atom.xml"),
            url="https://www.jujens.eu/feed/rss.xml",
        )

        with pytest.raises(FeedFileTooBigError), httpx2.Client() as client:
            get_feed_data("https://www.jujens.eu/feed/rss.xml", client=client)

    def test_feed_file_is_an_attack(self, httpx2_mock, snapshot):
        feed_url = "https://example.com/feed.xml"
        httpx2_mock.add_response(text=get_feed_fixture_content("attack_feed.xml"), url=feed_url)

        with httpx2.Client() as client:
            feed_data = get_feed_data(feed_url, client=client)

        assert serialize_for_snapshot(feed_data) == snapshot


class TestParseArticlesInFeed:
    @pytest.mark.parametrize(
        "feed_content",
        [
            pytest.param(
                get_feed_fixture_content("sample_rss.xml"),
                id="sample-rss-feed",
            ),
            pytest.param(
                get_feed_fixture_content("sample_atom.xml"),
                id="sample-atom-feed",
            ),
            pytest.param(
                get_feed_fixture_content(
                    "sample_atom.xml",
                    {"media_content_variant": "media_content_description"},  # type: ignore[arg-type]
                ),
                id="atom-with-media-description",
            ),
            pytest.param(
                get_feed_fixture_content(
                    "sample_atom.xml",
                    {"media_content_variant": "media_content_title"},  # type: ignore[arg-type]
                ),
                id="atom-with-media-title",
            ),
            pytest.param(
                get_feed_fixture_content("sample_youtube_atom.xml"),
                id="atom-from-youtube",
            ),
            pytest.param(
                get_feed_fixture_content("with_text_plain_articles.xml"),
                id="plain-text",
            ),
        ],
    )
    def test_parse_articles(self, feed_content, snapshot):
        feed_data = parse_feed(feed_content)

        articles = _parse_articles_in_feed(
            "https://example.com/feeds/feed.xml", "Some feed", feed_data
        )

        assert serialize_for_snapshot(articles) == snapshot


class TestGetFeedSiteUrl:
    @pytest.mark.parametrize(
        ("found_site_url", "feed_url", "expected_site_url"),
        [
            pytest.param(
                None,
                "https://example.com/feed.xml",
                "https://example.com",
                id="failed-to-find-feed",
            ),
            pytest.param(
                "https://example.fr/the-site/",
                "https://example.com/feed.xml",
                "https://example.fr/the-site/",
                id="found-in-full",
            ),
            pytest.param(
                "//example.com",
                "https://example.com/feed.xml",
                "https://example.com",
                id="found-without-scheme-full",
            ),
            pytest.param(
                "/", "https://example.com/feed.xml", "https://example.com", id="not-full-url"
            ),
        ],
    )
    def test_get_feed_site_url(
        self, found_site_url: str | None, feed_url: str, expected_site_url: str
    ):
        build_site_url = _get_feed_site_url(found_site_url, feed_url)

        assert build_site_url == expected_site_url


@pytest.mark.parametrize(
    "parameters",
    [
        pytest.param(
            {
                "feed_url": "https://example.com/rss",
                "site_url": "https://example.com",
                "title": "",
                "description": "",
                "feed_type": constants.SupportedFeedType.rss,
                "etag": "",
                "last_modified": None,
                "articles": [],
            },
            id="empty-title",
        ),
    ],
)
def test_build_feed_data(parameters: dict[str, Any], snapshot):
    feed_data = FeedData(**parameters)

    assert serialize_for_snapshot(feed_data) == snapshot


@pytest.mark.parametrize(
    ("parameters", "error"),
    [
        pytest.param(
            {
                "feed_url": "https://example.com/rss",
                "site_url": "https://example.com",
                "title": "   ",
                "description": "",
                "feed_type": constants.SupportedFeedType.rss,
                "etag": "",
                "last_modified": None,
                "articles": [],
            },
            "'' cannot be slugified",
            id="unslugifiable-title",
        ),
    ],
)
def test_build_feed_data_with_invalid_data(parameters: dict[str, Any], error: str):
    with pytest.raises(ValueError, match=error):
        FeedData(**parameters)
