# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later


from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from slugify import slugify

from legadilo.reading import constants
from legadilo.users.models import User

if TYPE_CHECKING:
    from django_stubs_ext.db.models import TypedModelMeta
else:
    TypedModelMeta = object


class ReadingListManager(models.Manager["ReadingList"]):
    @transaction.atomic()
    def create_default_lists(self, user: User):
        self.update_or_create(
            slug=slugify(str(_("All articles"))),
            user=user,
            defaults={
                "title": str(_("All articles")),
                "order": 0,
            },
        )
        base_default_list_values = {
            "title": str(_("Unread")),
            "read_status": constants.ReadStatus.ONLY_UNREAD,
            "for_later_status": constants.ForLaterStatus.ONLY_NOT_FOR_LATER,
            "order": 10,
        }
        self.update_or_create(
            slug=slugify(str(_("Unread"))),
            user=user,
            create_defaults={
                **base_default_list_values,
                "is_default": True,
                "auto_refresh_interval": 1,
            },
            defaults=base_default_list_values,
        )
        self.update_or_create(
            slug=slugify(str(_("Recent"))),
            user=user,
            defaults={
                "title": str(_("Recent")),
                "articles_max_age_value": 2,
                "articles_max_age_unit": constants.ArticlesMaxAgeUnit.DAYS,
                "order": 20,
            },
        )
        self.update_or_create(
            slug=slugify(str(_("Favorite"))),
            user=user,
            defaults={
                "title": str(_("Favorite")),
                "favorite_status": constants.FavoriteStatus.ONLY_FAVORITE,
                "order": 30,
                "user": user,
            },
        )
        self.update_or_create(
            slug=slugify(str(_("For later"))),
            user=user,
            defaults={
                "title": str(_("For later")),
                "read_status": constants.ReadStatus.ONLY_UNREAD,
                "for_later_status": constants.ForLaterStatus.ONLY_FOR_LATER,
                "order": 35,
            },
        )

    def get_reading_list(self, user: User, reading_list_slug: str | None) -> ReadingList:
        qs = self.get_queryset().select_related("user")
        if reading_list_slug is None:
            return qs.get(user=user, is_default=True)

        return qs.get(user=user, slug=reading_list_slug)

    def get_all_for_user(self, user: User) -> list[ReadingList]:
        return list(
            self.filter(user=user).select_related("user").prefetch_related("reading_list_tags")
        )

    @transaction.atomic()
    def make_default(self, reading_list: ReadingList):
        current_default_reading_list = self.get_reading_list(
            reading_list.user, reading_list_slug=None
        )
        current_default_reading_list.is_default = False
        current_default_reading_list.save()
        reading_list.is_default = True
        reading_list.save()

    @transaction.atomic()
    def reorder(self, user: User, new_order: dict[int, int]):
        reading_lists = {
            reading_list.id: reading_list for reading_list in self.get_all_for_user(user)
        }
        for reading_list_id, new_order_value in new_order.items():
            if reading_list_id not in reading_lists:
                continue
            reading_lists[reading_list_id].order = new_order_value

        self.bulk_update(reading_lists.values(), ["order"])


class ReadingList(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(blank=True, max_length=255)
    is_default = models.BooleanField(default=False)
    enable_reading_on_scroll = models.BooleanField(default=False)
    auto_refresh_interval = models.PositiveIntegerField(
        default=0,
        help_text=_(
            "Number of hours after which to refresh reading lists automatically. "
            "0 will disable the feature."
        ),
    )
    show_unread_count = models.CharField(
        choices=constants.ReadingListShowUnreadCount,
        default=constants.ReadingListShowUnreadCount.COUNT,
        help_text=_(
            "How to show the count of unread articles in the reading list: either the count, an "
            "indicator or nothing."
        ),
    )
    order = models.IntegerField(default=0)

    read_status = models.CharField(
        choices=constants.ReadStatus.choices,
        default=constants.ReadStatus.ALL,
        max_length=100,
    )
    favorite_status = models.CharField(
        choices=constants.FavoriteStatus.choices,
        default=constants.FavoriteStatus.ALL,
        max_length=100,
    )
    for_later_status = models.CharField(
        choices=constants.ForLaterStatus.choices,
        default=constants.ForLaterStatus.ALL,
        max_length=100,
    )
    articles_max_age_value = models.PositiveIntegerField(
        default=0,
        help_text=_(
            "Articles published before today minus this number will be excluded from the reading list."  # ruff:ignore[line-too-long]
        ),
    )
    articles_max_age_unit = models.CharField(
        choices=constants.ArticlesMaxAgeUnit.choices,
        default=constants.ArticlesMaxAgeUnit.UNSET,
        max_length=100,
        help_text=_(
            "Define the unit for the previous number. Leave to unset to not use this feature."
        ),
    )
    articles_reading_time = models.PositiveIntegerField(
        default=0,
        help_text=_("Include only articles that take more or less than this time to read."),
    )
    articles_reading_time_operator = models.CharField(
        choices=constants.ArticlesReadingTimeOperator.choices,
        default=constants.ArticlesReadingTimeOperator.UNSET,
        max_length=100,
        help_text=_("Whether the reading time must be more or less that the supplied value."),
    )
    include_tag_operator = models.CharField(
        choices=constants.ReadingListTagOperator.choices,
        default=constants.ReadingListTagOperator.ALL,
        max_length=100,
        help_text=_(
            "Defines whether the articles must have all or any of the tags to be included in the reading list."  # ruff:ignore[line-too-long]
        ),
    )
    exclude_tag_operator = models.CharField(
        choices=constants.ReadingListTagOperator.choices,
        default=constants.ReadingListTagOperator.ALL,
        max_length=100,
        help_text=_(
            "Defines whether the articles must have all or any of the tags to be excluded from the reading list."  # ruff:ignore[line-too-long]
        ),
    )
    order_direction = models.CharField(
        choices=constants.ReadingListOrderDirection.choices,
        default=constants.ReadingListOrderDirection.DESC,
        max_length=10,
        help_text=_(
            "How to sort the article. ASC will put the most recent articles first. DECS will put the least recent articles first."  # ruff:ignore[line-too-long]
        ),
    )

    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="reading_lists")

    objects = ReadingListManager()

    class Meta(TypedModelMeta):
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                "is_default",
                "user",
                name="%(app_label)s_%(class)s_enforce_one_default_reading_list",
                condition=models.Q(is_default=True),
            ),
            models.UniqueConstraint(
                "slug", "user", name="%(app_label)s_%(class)s_enforce_slug_unicity"
            ),
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_articles_max_age_unit_valid",
                condition=models.Q(
                    articles_max_age_unit__in=constants.ArticlesMaxAgeUnit.names,
                ),
            ),
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_articles_reading_time_operator_valid",
                condition=models.Q(
                    articles_reading_time_operator__in=constants.ArticlesReadingTimeOperator.names
                ),
            ),
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_favorite_status_valid",
                condition=models.Q(favorite_status__in=constants.FavoriteStatus.names),
            ),
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_read_status_valid",
                condition=models.Q(read_status__in=constants.ReadStatus.names),
            ),
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_for_later_status_valid",
                condition=models.Q(for_later_status__in=constants.ForLaterStatus.names),
            ),
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_exclude_tag_operator_valid",
                condition=models.Q(exclude_tag_operator__in=constants.ReadingListTagOperator.names),
            ),
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_include_tag_operator_valid",
                condition=models.Q(include_tag_operator__in=constants.ReadingListTagOperator.names),
            ),
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_order_direction_valid",
                condition=models.Q(order_direction__in=constants.ReadingListOrderDirection.names),
            ),
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_show_unread_count_valid",
                condition=models.Q(show_unread_count__in=["COUNT", "INDICATOR", "NOTHING"]),
            ),
        ]

    def __str__(self):
        return (
            f"ReadingList(id={self.id}, title={self.title}, user={self.user}, order={self.order})"
        )

    def save(self, *args, **kwargs):
        self.slug = slugify(self.title)
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.is_default:
            raise ValidationError("Cannot delete default list")

        return super().delete(*args, **kwargs)
