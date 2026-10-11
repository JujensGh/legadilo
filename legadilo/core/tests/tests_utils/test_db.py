#  SPDX-FileCopyrightText: 2026 Legadilo contributors
#
#  SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from django.db import connection, models
from django.db.models.sql import Query

from legadilo.core.utils.db import RemoveExtraSpaces, StripHtmlTags


def _evaluate(expression: models.Func) -> str:
    query = Query(None)
    compiler = query.get_compiler(connection=connection)
    sql, params = compiler.compile(expression.resolve_expression(query))
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {sql}", params)
        return cursor.fetchone()[0]


@pytest.mark.django_db
def test_evaluate():
    assert _evaluate(models.Value("Hello, World!")) == "Hello, World!"


@pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL specific test")
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("Hello world", "Hello world", id="no-html"),
        pytest.param("<p>Hello</p>", " Hello ", id="simple-tag"),
        pytest.param("<P>Hello</P>", " Hello ", id="uppercase-tag"),
        pytest.param('<p class="text" id="a">Hello</p>', " Hello ", id="tag-with-attributes"),
        pytest.param('<a\n  href="https://example.com">link</a>', " link ", id="multiline-tag"),
        pytest.param("a<br/>b<br />c", "a b c", id="self-closing-tags"),
        pytest.param("foo</p><p>bar", "foo  bar", id="adjacent-tags-dont-merge-words"),
        pytest.param("<h1>Title</h1>", " Title ", id="tag-with-digit"),
        pytest.param("a < b and c > d", "a < b and c > d", id="not-a-tag"),
    ],
)
def test_strip_html_tags(user, text: str, expected: str):
    assert _evaluate(StripHtmlTags(models.Value(text))) == expected


@pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL specific test")
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("Hello world", "Hello world", id="nothing-to-do"),
        pytest.param("Hello  \n\t world", "Hello world", id="mixed-whitespaces"),
    ],
)
def test_remove_extra_spaces(user, text: str, expected: str):
    assert _evaluate(RemoveExtraSpaces(models.Value(text))) == expected


@pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL specific test")
def test_strip_html_tags_then_remove_extra_spaces(user):
    result = _evaluate(RemoveExtraSpaces(StripHtmlTags(models.Value("<p>Hello</p>\n<p>world</p>"))))
    assert result == " Hello world "
