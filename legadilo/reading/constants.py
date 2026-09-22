# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later


from django.db.models import TextChoices
from django.utils.translation import gettext_lazy as _


class ReadStatus(TextChoices):
    ALL = "ALL", _("All")
    ONLY_UNREAD = "ONLY_UNREAD", _("Only unread")
    ONLY_READ = "ONLY_READ", _("Only read")


class FavoriteStatus(TextChoices):
    ALL = "ALL", _("All")
    ONLY_FAVORITE = "ONLY_FAVORITE", _("Only favorite")
    ONLY_NON_FAVORITE = "ONLY_NON_FAVORITE", _("Only non favorite")


class ForLaterStatus(TextChoices):
    ALL = "ALL", _("All")
    ONLY_FOR_LATER = "ONLY_FOR_LATER", _("Only for later")
    ONLY_NOT_FOR_LATER = "ONLY_NOT_FOR_LATER", _("Only for not later")


class ArticlesMaxAgeUnit(TextChoices):
    UNSET = "UNSET", _("Unset")
    HOURS = "HOURS", _("Hour(s)")
    DAYS = "DAYS", _("Day(s)")
    WEEKS = "WEEKS", _("Week(s)")
    MONTHS = "MONTHS", _("Month(s)")


class ArticlesReadingTimeOperator(TextChoices):
    UNSET = "UNSET", _("Unset")
    MORE_THAN = "MORE_THAN", _("More than than")
    LESS_THAN = "LESS_THAN", _("Less than than")


class ReadingListShowUnreadCount(TextChoices):
    COUNT = "COUNT", _("Count")
    INDICATOR = "INDICATOR", _("Indicator")
    NOTHING = "NOTHING", _("Nothing")


class ReadingListTagFilterType(TextChoices):
    INCLUDE = "INCLUDE", _("Include")
    EXCLUDE = "EXCLUDE", _("Exclude")


class ReadingListTagOperator(TextChoices):
    ALL = "ALL", _("All")
    ANY = "ANY", _("Any")


class ReadingListOrderDirection(TextChoices):
    ASC = "ASC", _("Ascendant")
    DESC = "DESC", _("Descendant")


class UpdateArticleActions(TextChoices):
    DO_NOTHING = "DO_NOTHING", _("Do nothing")
    MARK_AS_FAVORITE = "MARK_AS_FAVORITE", _("Mark as favorite")
    UNMARK_AS_FAVORITE = "UNMARK_AS_FAVORITE", _("Unmark as favorite")
    MARK_AS_READ = "MARK_AS_READ", _("Mark as read")
    MARK_AS_UNREAD = "MARK_AS_UNREAD", _("Mark as unread")
    MARK_AS_OPENED = "MARK_AS_OPENED", _("Mark as opened")
    MARK_AS_FOR_LATER = "MARK_AS_FOR_LATER", _("Mark as for later")
    UNMARK_AS_FOR_LATER = "UNMARK_AS_FOR_LATER", _("Unmark as for later")

    @classmethod
    def is_read_status_update(cls, update_action: UpdateArticleActions) -> bool:
        return update_action in {
            cls.MARK_AS_READ,
            cls.MARK_AS_UNREAD,
        }


class ArticleSourceType(TextChoices):
    FEED = "FEED", _("Feed")
    MANUAL = "MANUAL", _("Manual")


class ArticleSearchType(TextChoices):
    PLAIN = "plain", _("Words")
    PHRASE = "phrase", _("Phrase")
    URL = "url", _("URL")


class ArticleSearchOrderBy(TextChoices):
    RANK_DESC = "RANK_DESC", _("Rank desc")
    RANK_ASC = "RANK_ASC", _("Rank asc")
    ARTICLE_SAVE_DATE_DESC = "ARTICLE_SAVE_DATE_DESC", _("Article save date desc")
    ARTICLE_SAVE_DATE_ASC = "ARTICLE_SAVE_DATE_ASC", _("Article save date asc")
    ARTICLE_DATE_DESC = "ARTICLE_DATE_DESC", _("Article date desc")
    ARTICLE_DATE_ASC = "ARTICLE_DATE_ASC", _("Article date asc")
    READ_AT_DESC = "READ_AT_DESC", _("Read at desc")
    READ_AT_ASC = "READ_AT_ASC", _("Read at asc")


MAX_ARTICLE_FILE_SIZE = 5 * 1024 * 1024  # 5MiB in bytes.
MAX_OBJECTS_PER_PAGE = 100
MAX_ARTICLES_PER_PAGE_WITH_READ_ON_SCROLL = 5 * MAX_OBJECTS_PER_PAGE
PAGINATION_ORPHANS_PERCENTAGE = 0.1  # 10%
ARTICLE_TITLE_MAX_LENGTH = 300
ARTICLES_GROUP_TITLE_MAX_LENGTH = 300
ARTICLE_SOURCE_TITLE_MAX_LENGTH = 300
MAX_SUMMARY_LENGTH = 255  # In words
EXTRA_TAGS_TO_REMOVE_FROM_SUMMARY = frozenset({"img", "pre"})
KEEP_ARTICLE_FETCH_ERROR_FOR = 60  # In days
LANGUAGE_CODE_MAX_LENGTH = 5
EXTERNAL_ARTICLE_ID_MAX_LENGTH = 512
MAX_EXPORT_ARTICLES_PER_PAGE = 100
