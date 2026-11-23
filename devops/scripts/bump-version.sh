#!/usr/bin/env bash

#
# SPDX-FileCopyrightText: 2026 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#


set -eu
set -o pipefail

if [[ $(git branch --show-current) != "main" ]]; then
    echo "You must run this script on the main branch" >&2
    exit 1
fi

base_date_tag=$(date +%y.%m)
last_tag=$(git tag --list "${base_date_tag}.*" | sort -r | head -n 1)
last_tag_revision=$(echo "${last_tag}" | cut -d . -f 3 -)
new_tag_revision=$((last_tag_revision+1))
new_tag="${base_date_tag}.${new_tag_revision}"

sed -Ei "s/^version = \"[1-9]{2}\.[0-9]{2}\.[0-9]\"$/version = \"${new_tag}\"/g" pyproject.toml
sed -i "s/## Unreleased$/## Unreleased\n\n## ${new_tag}/g" CHANGELOG.md
uv lock
echo "Creating version ${new_tag} Press enter to accept."
read -r

git commit -am "chore: releasing ${new_tag}"
git tag "${new_tag}"
git push --follow-tags --no-verify
git push --follow-tags --no-verify github
