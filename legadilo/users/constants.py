# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from datetime import timedelta
from types import MappingProxyType

from django.conf import settings
from django.db.models import TextChoices
from django.utils.translation import gettext_lazy as _

INVALID_USERS_RETENTION_DAYS = timedelta(days=30)
INACTIVE_USERS_RETENTION = timedelta(days=365 * 2)
INACTIVE_USERS_NOTIFICATION_THRESHOLDS = (timedelta(days=30), timedelta(days=14), timedelta(days=7))
USER_SETTINGS_PAGES = MappingProxyType({
    "users:update_settings": _("My settings"),
    "users:update": _("My Infos"),
    "account_email": _("E-Mail"),
    "account_change_password": _("Change password"),
    "mfa_index": _("Two-Factor Authentication"),
    "users:manage_tokens": _("Manage application tokens"),
    "import_export:import_export_articles": _("Import/Export Articles"),
})
LANGUAGE_CHOICES = (("", ""), *tuple(settings.LANGUAGES))


class UserSettingsArticleDetailsFontFamilyChoices(TextChoices):
    SYSTEM_UI = ("system-ui", _("System UI"))
    BROWSER_SERIF = ("serif", _("Browser Serif"))
    BROWSER_SANS_SERIF = ("sans-serif", _("Browser Sans Serif"))


class UserSettingsArticleDetailsFontSizeChoices(TextChoices):
    SMALL = ("small", _("Small"))
    MEDIUM = ("medium", _("Medium"))
    LARGE = ("large", _("Large"))
    LARGER = ("larger", _("Larger"))


class UserSettingsArticleDetailsMaxWidthChoices(TextChoices):
    SMALL = ("small", _("Small"))
    MEDIUM = ("medium", _("Medium"))
    LARGE = ("large", _("Large"))


# To keep in sync with the JS constant in user_settings.js.
USER_SETTINGS_ARTICLE_DETAILS_MAX_WIDTHS_CHOICES_TO_CSS_VALUES = MappingProxyType({
    UserSettingsArticleDetailsMaxWidthChoices.SMALL: "700px",
    UserSettingsArticleDetailsMaxWidthChoices.MEDIUM: "900px",
    UserSettingsArticleDetailsMaxWidthChoices.LARGE: "1100px",
})
