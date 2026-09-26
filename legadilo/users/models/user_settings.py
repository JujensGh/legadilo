# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from typing import TYPE_CHECKING

from django.db import models
from django.utils.translation import gettext_lazy as _

from .. import constants
from .user import User

if TYPE_CHECKING:
    from django_stubs_ext.db.models import TypedModelMeta
else:
    TypedModelMeta = object


class UserSettings(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="settings")

    default_reading_time = models.PositiveIntegerField(
        default=200,
        help_text=_(
            "Number of words you read in minutes. Used to calculate the reading time of articles."
        ),
    )
    timezone = models.ForeignKey(
        "core.Timezone",
        on_delete=models.PROTECT,
        related_name="user_settings",
        help_text=_("Used to display times and updated feeds at a convenient time."),
    )
    language = models.CharField(
        max_length=10, default="", choices=constants.LANGUAGE_CHOICES, blank=True
    )
    article_details_font_family = models.CharField(
        default=constants.UserSettingsArticleDetailsFontFamilyChoices.SYSTEM_UI,
        choices=constants.UserSettingsArticleDetailsFontFamilyChoices.choices,
        help_text=_(
            "'System UI' is the font used by your desktop environment, 'browser serif' and "
            "'browser sans-serif' are the default fonts defined in your browser settings."
        ),
    )
    article_details_font_size_desktop = models.CharField(
        default=constants.UserSettingsArticleDetailsFontSizeChoices.MEDIUM,
        choices=constants.UserSettingsArticleDetailsFontSizeChoices.choices,
        help_text=_("Font size in pixels for desktop devices (>= 992px wide)."),
    )
    article_details_font_size_tablet = models.CharField(
        default=constants.UserSettingsArticleDetailsFontSizeChoices.MEDIUM,
        choices=constants.UserSettingsArticleDetailsFontSizeChoices.choices,
        help_text=_("Font size in pixels for tablet devices (>= 768px wide and < 992px wide)."),
    )
    article_details_font_size_mobile = models.CharField(
        default=constants.UserSettingsArticleDetailsFontSizeChoices.MEDIUM,
        choices=constants.UserSettingsArticleDetailsFontSizeChoices.choices,
        help_text=_("Font size in pixels for mobile devices (< 768px wide)."),
    )
    article_details_max_width_desktop = models.CharField(
        default=constants.UserSettingsArticleDetailsMaxWidthChoices.MEDIUM,
        choices=constants.UserSettingsArticleDetailsMaxWidthChoices.choices,
        help_text=_("Maximum width of article details for desktop devices (>= 992px wide)."),
    )
    article_details_max_width_tablet = models.CharField(
        default=constants.UserSettingsArticleDetailsMaxWidthChoices.MEDIUM,
        choices=constants.UserSettingsArticleDetailsMaxWidthChoices.choices,
        help_text=_(
            "Maximum width of article details for tablet devices (>= 768px wide and < 992px wide)."
        ),
    )

    class Meta(TypedModelMeta):
        constraints = [
            models.UniqueConstraint("user", name="%(app_label)s_%(class)s_unique_per_user"),
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_language_valid",
                condition=models.Q(
                    language__in=[lang_code for lang_code, _ in constants.LANGUAGE_CHOICES]
                ),
            ),
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_article_details_font_family_valid",
                condition=models.Q(
                    article_details_font_family__in=[
                        "system-ui",
                        "serif",
                        "sans-serif",
                    ]
                ),
            ),
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_article_details_font_size_desktop_valid",
                condition=models.Q(
                    article_details_font_size_desktop__in=["small", "medium", "large", "larger"]
                ),
            ),
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_article_details_font_size_mobile_valid",
                condition=models.Q(
                    article_details_font_size_mobile__in=["small", "medium", "large", "larger"]
                ),
            ),
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_article_details_font_size_tablet_valid",
                condition=models.Q(
                    article_details_font_size_tablet__in=["small", "medium", "large", "larger"]
                ),
            ),
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_article_details_max_width_desktop_valid",
                condition=models.Q(
                    article_details_max_width_desktop__in=["small", "medium", "large"]
                ),
            ),
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_article_details_max_width_tablet_valid",
                condition=models.Q(
                    article_details_max_width_tablet__in=["small", "medium", "large"]
                ),
            ),
        ]

    def __str__(self):
        return f"UserSettings(user={self.user})"

    @property
    def article_details_max_width_desktop_px(self):
        return constants.USER_SETTINGS_ARTICLE_DETAILS_MAX_WIDTHS_CHOICES_TO_CSS_VALUES[
            constants.UserSettingsArticleDetailsMaxWidthChoices(
                self.article_details_max_width_desktop
            )
        ]

    @property
    def article_details_max_width_tablet_px(self):
        return constants.USER_SETTINGS_ARTICLE_DETAILS_MAX_WIDTHS_CHOICES_TO_CSS_VALUES[
            constants.UserSettingsArticleDetailsMaxWidthChoices(
                self.article_details_max_width_tablet
            )
        ]
