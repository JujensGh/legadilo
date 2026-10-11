# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.views.decorators.http import require_POST

from legadilo.reading import constants as reading_constants
from legadilo.reading.models import Article
from legadilo.reading.templatetags import article_card_id
from legadilo.reading.views.article_actions_views import (
    get_common_template_context,
    redirect_to_reading_list,
)
from legadilo.users.user_types import AuthenticatedHttpRequest


@require_POST
@login_required
def delete_article_view(request: AuthenticatedHttpRequest, article_id: int) -> HttpResponse:
    article = get_object_or_404(
        Article.objects.get_queryset().for_deletion(), id=article_id, user=request.user
    )
    hx_target = f"#{article_card_id(article)}"

    article.delete()

    for_article_details = request.POST.get("for_article_details", "").lower() == "true"
    if for_article_details:
        return redirect_to_reading_list(request)

    return TemplateResponse(
        request,
        "reading/update_article_action.html",
        get_common_template_context(
            request, reading_constants.UpdateArticleActions.DO_NOTHING, deleting_article=True
        ),
        headers={
            "HX-Reswap": "delete swap:1s",
            "HX-Retarget": hx_target,
        },
    )
