#  SPDX-FileCopyrightText: 2026 Legadilo contributors
#
#  SPDX-License-Identifier: AGPL-3.0-or-later

from django.contrib.auth.decorators import login_required
from django.template.response import TemplateResponse
from django.views.decorators.http import require_http_methods

from legadilo.users.user_types import AuthenticatedHttpRequest


@login_required
@require_http_methods(["GET"])
def stats_view(request: AuthenticatedHttpRequest) -> TemplateResponse:
    return TemplateResponse(request, "users/stats.html", {"stats": request.user.stats})
