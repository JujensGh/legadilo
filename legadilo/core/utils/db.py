#  SPDX-FileCopyrightText: 2026 Legadilo contributors
#
#  SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import models


class CaseInsensitiveEmailField(models.EmailField):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db_collation = "nocase"


class ExtractEpoch(models.Func):
    def as_postgresql(self, compiler, connection, **extra_context):
        return self.as_sql(
            compiler,
            connection,
            function="EXTRACT",
            template="%(function)s(EPOCH FROM %(expressions)s)",
            **extra_context,
        )

    def as_sqlite(self, compiler, connection, **extra_context):
        extra_context.setdefault("output_field", models.IntegerField())
        return self.as_sql(
            compiler,
            connection,
            function="STRFTIME",
            # The string will be formatted with % twice!
            template=r"%(function)s('%%%%s', %(expressions)s)",
            **extra_context,
        )


class StripHtmlTags(models.Func):
    function = "REGEXP_REPLACE"
    output_field = models.TextField()

    def __init__(self, expression, *args, **kwargs):
        super().__init__(
            expression,
            models.Value(r"</?[a-zA-Z0-9]+[^>]*>"),
            models.Value(" "),
            models.Value("g"),
            **kwargs,
        )


class RemoveExtraSpaces(models.Func):
    function = "REGEXP_REPLACE"
    output_field = models.TextField()

    def __init__(self, expression, *args, **kwargs):
        super().__init__(
            expression,
            models.Value(r"\s+"),
            models.Value(" "),
            models.Value("g"),
            **kwargs,
        )
