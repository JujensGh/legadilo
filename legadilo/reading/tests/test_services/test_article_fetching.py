# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from collections.abc import Callable
from typing import Any

import httpx2
import pytest

from legadilo.core.utils.testing import serialize_for_snapshot
from legadilo.reading.services.article_fetching import ArticleData, fetch_article_data
from legadilo.reading.tests.fixtures import get_article_fixture_content


def test_fetch_article_data(httpx2_mock, snapshot):
    url = "https://www.example.com/posts/en/1-super-article/"
    httpx2_mock.add_response(url=url, html=get_article_fixture_content("sample_blog_article.html"))

    fetch_article_result = fetch_article_data(url)

    assert serialize_for_snapshot(fetch_article_result.article_data) == snapshot


def test_get_text_article_from_url(httpx2_mock, snapshot):
    url = "https://www.example.com/posts/en/1-super-article/"
    httpx2_mock.add_response(url=url, text="Just some raw text!")

    fetch_article_result = fetch_article_data(url)

    assert serialize_for_snapshot(fetch_article_result.article_data) == snapshot


def test_fetch_article_data_with_http_errors(httpx2_mock, snapshot):
    url = "https://www.example.com/posts/en/1-super-article/"
    httpx2_mock.add_exception(httpx2.HTTPError("Error"))

    fetch_article_result = fetch_article_data(url)

    assert not fetch_article_result.is_success
    assert serialize_for_snapshot(fetch_article_result.article_data) == snapshot


@pytest.mark.parametrize(
    "fixture_file",
    ["htm_redirection_invalid_http_equiv.html", "html_redirection.html"],
)
def test_fetch_article_data_with_http_equiv(fixture_file, httpx2_mock):
    url = "https://newsletter.com/article/1"
    httpx2_mock.add_response(url=url, html=get_article_fixture_content(fixture_file))
    article_url = "https://example.com/article/redirected-article/"
    httpx2_mock.add_response(
        url=article_url, html=get_article_fixture_content("sample_blog_article.html")
    )

    fetch_article_result = fetch_article_data(url)

    assert fetch_article_result.is_success
    assert (
        fetch_article_result.article_data.url == "https://www.example.com/posts/en/1-super-article/"
    )
    assert fetch_article_result.article_data.title == "On the 3 musketeers"


@pytest.mark.parametrize(
    ("fixture_file", "expected_starts_with"),
    [
        (
            "multiple_articles_tags.html",
            "<article>",
        ),
        ("multiple_articles_tags_identify_class.html", "<article>"),
        ("multiple_articles_tags_identify_section_by_class.html", "\n<div>\n<p>\n"),
    ],
)
def test_fetch_article_data_weird_content(fixture_file, expected_starts_with, httpx2_mock):
    url = "https://www.example.com/posts/en/1-super-article/"
    httpx2_mock.add_response(url=url, html=get_article_fixture_content(fixture_file))

    fetch_article_result = fetch_article_data(url)

    assert fetch_article_result.is_success
    assert fetch_article_result.article_data.title == "On the 3 musketeers"
    assert fetch_article_result.article_data.content.startswith(expected_starts_with)
    assert "Lorem ipsum dolor sit amet" in fetch_article_result.article_data.content


@pytest.mark.parametrize(
    "process_fn",
    [
        pytest.param(
            lambda content: content.replace("<article>", "").replace("</article>", ""),
            id="no-article-tag",
        ),
    ],
)
def test_fetch_article_data_process_fixture(
    process_fn: Callable[[str], str], httpx2_mock, snapshot
):
    url = "https://www.example.com/posts/en/1-super-article/"
    httpx2_mock.add_response(
        url=url, html=process_fn(get_article_fixture_content("sample_blog_article.html"))
    )

    fetch_article_result = fetch_article_data(url)

    assert serialize_for_snapshot(fetch_article_result.article_data) == snapshot


@pytest.mark.parametrize(
    "parameters",
    [
        pytest.param(
            {
                "external_article_id": "<p>external article id",
                "source_title": "<p>source article title</p>",
                "title": "<p>Title</p>",
                "summary": """<p>Summary <span>?</span> <img src="/toto" /> </p>""",
                "content": """<p>C <span>?</span> <img src="/t" /> <script>alert()</script></p>""",
                "content_type": "text/html",
                "authors": ["<span>me</span>"],
                "contributors": ["<span>me</span>"],
                "tags": ["<span>tag</span>"],
                "url": "https://example.com/articles/1",
                "preview_picture_url": "https://example.com/articles/1.png",
                "preview_picture_alt": "<p>Hi there!</p>",
                "published_at": None,
                "updated_at": None,
                "language": "<span>en</span>",
                "read_at": None,
                "is_favorite": False,
            },
            id="full-with-required-escaping",
        ),
        pytest.param(
            {
                "external_article_id": "<p>external article id",
                "source_title": "",
                "title": "",
                "summary": """<p>Summary <span>?</span> <img src="/toto" /> </p>""",
                "content": """<p>C <span>?</span> <img src="/t" /> <script>alert()</script></p>""",
                "content_type": "text/html",
                "authors": ["<span>me</span>"],
                "contributors": ["<span>me</span>"],
                "tags": ["<span>tag</span>"],
                "url": "https://example.com/articles/1",
                "preview_picture_url": "https://example.com/articles/1.png",
                "preview_picture_alt": "<p>Hi there!</p>",
                "published_at": None,
                "updated_at": None,
                "language": "<span>en</span>",
                "read_at": None,
                "is_favorite": False,
            },
            id="title-missing",
        ),
        pytest.param(
            {
                "external_article_id": "<p>external article id",
                "source_title": "<p>source article title</p>",
                "title": "<p>Title</p>",
                "summary": "",
                "content": """<p>C <span>?</span> <img src="/t" /> <script>alert()</script></p>""",
                "content_type": "text/html",
                "authors": ["<span>me</span>"],
                "contributors": ["<span>me</span>"],
                "tags": ["<span>tag</span>"],
                "url": "https://example.com/articles/1",
                "preview_picture_url": "https://example.com/articles/1.png",
                "preview_picture_alt": "<p>Hi there!</p>",
                "published_at": None,
                "updated_at": None,
                "language": "<span>en</span>",
                "read_at": None,
                "is_favorite": False,
            },
            id="summary-missing",
        ),
        pytest.param(
            {
                "external_article_id": "<p>external article id",
                "source_title": "<p>source article title</p>",
                "title": "<p>Title</p>",
                "summary": """<p><a href="/relative">Link 1</a><a href="https://example.com/abs">Link 1</a></p>""",  # ruff:ignore[line-too-long]
                "content": """<p><a href="/relative">Link 1</a><a href="https://example.com/abs">Link 1</a><img src="/relative.png" /><img src="https://example.com/image.png" /></p>""",  # ruff:ignore[line-too-long]
                "content_type": "text/html",
                "authors": ["<span>me</span>"],
                "contributors": ["<span>me</span>"],
                "tags": ["<span>tag</span>"],
                "url": "https://example.com/articles/1",
                "preview_picture_url": "https://example.com/articles/1.png",
                "preview_picture_alt": "<p>Hi there!</p>",
                "published_at": None,
                "updated_at": None,
                "language": "<span>en</span>",
                "read_at": None,
                "is_favorite": False,
            },
            id="link-correction",
        ),
        pytest.param(
            {
                "external_article_id": "<p>external article id",
                "source_title": "<p>source article title</p>",
                "title": "<p>Title</p>",
                "summary": """<p><a href="/relative">Link 1</a><a href="https://example.com/abs">Link 1</a></p>""",  # ruff:ignore[line-too-long]
                "content": """
                <h1>Some header</h1>
                <h2 id="test">This one has an id</h2>
                <p>Some text</p>
                <h2>This one <em>has HTML</em> in <script>it</script></h2>
                <h1>Another root title</h1>
                """,
                "content_type": "text/html",
                "authors": ["<span>me</span>"],
                "contributors": ["<span>me</span>"],
                "tags": ["<span>tag</span>"],
                "url": "https://example.com/articles/1",
                "preview_picture_url": "https://example.com/articles/1.png",
                "preview_picture_alt": "<p>Hi there!</p>",
                "published_at": None,
                "updated_at": None,
                "language": "<span>en</span>",
                "read_at": None,
                "is_favorite": False,
            },
            id="with-headers",
        ),
        pytest.param(
            {
                "external_article_id": "<p>external article id",
                "source_title": "<p>source article title</p>",
                "title": "<p>Title</p>",
                "summary": """<p><a href="/relative">Link 1</a><a href="https://example.com/abs">Link 1</a></p>""",  # ruff:ignore[line-too-long]
                "content": """
                <img src="data:image/png;base64" />
                """,
                "content_type": "text/html",
                "authors": ["<span>me</span>"],
                "contributors": ["<span>me</span>"],
                "tags": ["<span>tag</span>"],
                "url": "https://example.com/articles/1",
                "preview_picture_url": "https://example.com/articles/1.png",
                "preview_picture_alt": "<p>Hi there!</p>",
                "published_at": None,
                "updated_at": None,
                "language": "<span>en</span>",
                "read_at": None,
                "is_favorite": False,
            },
            id="with-base64-image",
        ),
        pytest.param(
            {
                "external_article_id": "<p>external article id",
                "source_title": "<p>source article title</p>",
                "title": "<p>Title</p>",
                "summary": """<p><a href="/relative">Link 1</a><a href="https://example.com/abs">Link 1</a></p>""",  # ruff:ignore[line-too-long]
                "content": """
                <h1>1st h1</h1>
                <h1>2nd h1</h1>
                """,
                "content_type": "text/html",
                "authors": ["<span>me</span>"],
                "contributors": ["<span>me</span>"],
                "tags": ["<span>tag</span>"],
                "url": "https://example.com/articles/1",
                "preview_picture_url": "https://example.com/articles/1.png",
                "preview_picture_alt": "<p>Hi there!</p>",
                "published_at": None,
                "updated_at": None,
                "language": "<span>en</span>",
                "read_at": None,
                "is_favorite": False,
            },
            id="multiple-h1",
        ),
        pytest.param(
            {
                "external_article_id": "external article id",
                "source_title": "source article title",
                "title": "<p>Title</p>",
                "summary": "",
                "content": """
                <p><img  src="invalid.png" data-src="profile.png" decoding="async" /></p>
                """,
                "content_type": "text/html",
                "authors": ["<span>me</span>"],
                "contributors": ["<span>me</span>"],
                "tags": ["<span>tag</span>"],
                "url": "https://example.com/articles/1",
                "preview_picture_url": "https://example.com/articles/1.png",
                "preview_picture_alt": "<p>Hi there!</p>",
                "published_at": None,
                "updated_at": None,
                "language": "<span>en</span>",
                "read_at": None,
                "is_favorite": False,
            },
            id="async-images",
        ),
        pytest.param(
            {
                "external_article_id": "<p>external article id",
                "source_title": "",
                "title": "Title",
                "summary": """Summary""",
                "content": """Some content""",
                "content_type": "text/plain",
                "authors": [],
                "contributors": [],
                "tags": [],
                "url": "https://example.com/articles/1",
                "preview_picture_url": "https://example.com/articles/1.png",
                "preview_picture_alt": "",
                "published_at": None,
                "updated_at": None,
                "language": None,
                "read_at": None,
                "is_favorite": False,
            },
            id="plain-text",
        ),
        pytest.param(
            {
                "external_article_id": "<p>external article id",
                "source_title": "<p>source article title</p>",
                "title": "Title",
                "summary": """Summary""",
                "content": """Some <p>content</p> <script>alert()</script>""",
                "content_type": "text/plain",
                "authors": [],
                "contributors": [],
                "tags": [],
                "url": "https://example.com/articles/1",
                "preview_picture_url": "https://example.com/articles/1.png",
                "preview_picture_alt": "",
                "published_at": None,
                "updated_at": None,
                "language": None,
                "read_at": None,
                "is_favorite": False,
            },
            id="plain-text-with-html",
        ),
        pytest.param(
            {
                "external_article_id": "<p>external article id",
                "source_title": "<p>source article title</p>",
                "title": "Title",
                "summary": """Summary""",
                "content": """Some <p>content</p> <script>alert()</script>""",
                "content_type": "text/plain",
                "authors": [],
                "contributors": [],
                "tags": [],
                "url": "https://example.com/articles/1#anchor",
                "preview_picture_url": "https://example.com/articles/1.png",
                "preview_picture_alt": "",
                "published_at": None,
                "updated_at": None,
                "language": None,
                "read_at": None,
                "is_favorite": False,
            },
            id="with-fragment-after-path",
        ),
        pytest.param(
            {
                "external_article_id": "<p>external article id",
                "source_title": "<p>source article title</p>",
                "title": "Title",
                "summary": """Summary""",
                "content": """Some <p>content</p> <script>alert()</script>""",
                "content_type": "text/plain",
                "authors": [],
                "contributors": [],
                "tags": [],
                "url": "https://example.com/articles/1?toto=1#anchor",
                "preview_picture_url": "https://example.com/articles/1.png",
                "preview_picture_alt": "",
                "published_at": None,
                "updated_at": None,
                "language": None,
                "read_at": None,
                "is_favorite": False,
            },
            id="with-fragment-after-qs",
        ),
        pytest.param(
            {
                "external_article_id": "<p>external article id",
                "source_title": "<p>source article title</p>",
                "title": "   ",
                "summary": """Summary""",
                "content": """Some <p>content</p> <script>alert()</script>""",
                "content_type": "text/plain",
                "authors": [],
                "contributors": [],
                "tags": [],
                "url": "https://example.com/articles/1?toto=1#anchor",
                "preview_picture_url": "https://example.com/articles/1.png",
                "preview_picture_alt": "",
                "published_at": None,
                "updated_at": None,
                "language": None,
                "read_at": None,
                "is_favorite": False,
            },
            id="unslugifiable-title",
        ),
    ],
)
def test_build_article_data(parameters: dict[str, Any], snapshot):
    article_data = ArticleData(**parameters)

    assert serialize_for_snapshot(article_data) == snapshot
