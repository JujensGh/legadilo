#  SPDX-FileCopyrightText: 2025 Legadilo contributors
#
#  SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from legadilo.core.utils.time_utils import utcnow
from legadilo.reading.models import ArticlesGroup
from legadilo.reading.tests.factories import ArticleFactory, ArticlesGroupFactory, TagFactory


@pytest.mark.django_db
class TestArticlesGroupQuerySet:
    def test_for_user(self, user, other_user):
        group = ArticlesGroupFactory(user=user)
        ArticlesGroupFactory(user=other_user)

        groups = ArticlesGroup.objects.get_queryset().for_user(user)

        assert list(groups) == [group]

    def test_for_search(self, user):
        group = ArticlesGroupFactory(user=user, title="About Groups")
        other_group = ArticlesGroupFactory(user=user, title="Some group")
        ArticleFactory(user=user, title="Article about groups", group=other_group)
        tagged_group = ArticlesGroupFactory(user=user, title="Tagged group")
        tagged_group.tags.add(TagFactory(title="Groups"))

        groups = list(ArticlesGroup.objects.get_queryset().for_search("groups"))

        assert groups == [group, other_group, tagged_group]

    def test_with_metadata(self, user):
        group = ArticlesGroupFactory(user=user)
        ArticleFactory(
            title="Read article",
            user=user,
            group=group,
            group_order=1,
            read_at=utcnow(),
            reading_time=10,
        )
        ArticleFactory(
            title="Unread article",
            user=user,
            group=group,
            group_order=2,
            read_at=None,
            reading_time=5,
        )

        group = ArticlesGroup.objects.get_queryset().with_metadata().get()

        assert group.annot_nb_articles_in_group == 2
        assert group.annot_unread_articles_count == 1
        assert group.annot_has_unread_articles is True
        assert group.annot_total_reading_time == 15
        assert group.annot_remaining_reading_time == 5

    def test_with_articles(self, user):
        group = ArticlesGroupFactory(user=user)
        second_article = ArticleFactory(user=user, group=group, group_order=2)
        first_article = ArticleFactory(user=user, group=group, group_order=1)
        third_article = ArticleFactory(user=user, group=group, group_order=3)

        group = ArticlesGroup.objects.get_queryset().with_articles().get()

        assert group.sorted_articles == [first_article, second_article, third_article]


@pytest.mark.django_db
class TestArticlesGroupManager:
    def test_get_choices(self, user):
        group1 = ArticlesGroupFactory(user=user, title="My group")
        ArticlesGroupFactory(user=user, title="Testing")

        choices = ArticlesGroup.objects.get_choices(user, query="Group")

        assert choices == [(group1.slug, group1.title)]

    def test_get_or_create_from_slug(self, user, django_assert_num_queries):
        group = ArticlesGroupFactory(user=user, title="My group")

        with django_assert_num_queries(3):
            group_from_slug = ArticlesGroup.objects.get_or_create_from_slug(user, group.slug)

        assert group_from_slug == group

    def test_get_or_create_from_slug_creates_new_group_if_not_found(
        self, user, other_user, django_assert_num_queries
    ):
        ArticlesGroupFactory(user=other_user, title="New group")

        with django_assert_num_queries(9):
            group = ArticlesGroup.objects.get_or_create_from_slug(user, "New group")

        assert group.title == "New group"
        assert group.slug == "new-group"
        assert group.user == user

    def test_create_with_tags(self, user, django_assert_num_queries):
        tag = TagFactory(title="existing-tag")

        with django_assert_num_queries(7):
            group = ArticlesGroup.objects.create_with_tags(
                user, title="New group", description="Description", tags=[tag]
            )

        assert set(group.tags.values_list("title", flat=True)) == {"existing-tag"}
        assert group.user == user
        assert group.title == "New group"
        assert group.slug == "new-group"
        assert group.description == "Description"

    def test_list_for_admin(self, user, other_user):
        ArticlesGroupFactory(user=other_user, title="Other user group")
        group = ArticlesGroupFactory(user=user, title="My group")
        ArticleFactory(user=user, title="Article in group", group=group, read_at=utcnow())
        other_group = ArticlesGroupFactory(user=user, title="Other group")
        ArticleFactory(user=user, title="Article in other group", group=other_group, read_at=None)

        groups = list(ArticlesGroup.objects.list_for_admin(user))

        assert groups == [other_group, group]

    def test_list_for_admin_with_search_text(self, user):
        group = ArticlesGroupFactory(user=user, title="About groups")
        ArticlesGroupFactory(user=user, title="Other group")

        groups = list(ArticlesGroup.objects.list_for_admin(user, "groups"))

        assert groups == [group]

    def test_list_for_admin_with_search_text_and_tags(self, user):
        group = ArticlesGroupFactory(user=user, title="About groups")
        tag = TagFactory(user=user, title="Groups")
        group.tags.add(tag)
        ArticlesGroupFactory(user=user, title="Other groups")

        groups = list(ArticlesGroup.objects.list_for_admin(user, "groups", tag_slugs=[tag.slug]))

        assert groups == [group]
