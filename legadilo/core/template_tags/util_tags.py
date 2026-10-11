# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
from functools import lru_cache

from django.template.defaulttags import register
from django.templatetags.static import static
from django.utils.safestring import mark_safe


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def format_json(value: dict):
    return json.dumps(value, indent=4, sort_keys=True)


@register.simple_tag(name="bs_icon")
def bs_icon(icon_name: str) -> str:
    sprite_url = _cached_static("images/bs-sprite.svg")
    return mark_safe(  # ruff: ignore[suspicious-mark-safe-usage]
        f"""<svg class="bi" aria-hidden="true"><use href="{sprite_url}#{icon_name}"></use></svg>"""
    )


@lru_cache(maxsize=1024)
def _cached_static(path: str):
    """Cache wrapper around static

    Since it's called in a loop, it can help save up to 40ms in rendering big lists of articles
    according to my local tests.
    """
    return static(path)
