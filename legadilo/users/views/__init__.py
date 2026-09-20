# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from .manage_tokens_views import delete_token_view, manage_tokens_view
from .notifications_views import list_notifications_view
from .stats_views import stats_view
from .user_views import (
    delete_account_view,
    logout_view,
    signup_view,
    user_login_view,
    user_redirect_view,
    user_update_settings_view,
    user_update_view,
)

__all__ = [
    "delete_account_view",
    "delete_token_view",
    "list_notifications_view",
    "logout_view",
    "manage_tokens_view",
    "signup_view",
    "stats_view",
    "user_login_view",
    "user_redirect_view",
    "user_update_settings_view",
    "user_update_view",
]
