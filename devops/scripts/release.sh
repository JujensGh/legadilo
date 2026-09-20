#!/usr/bin/env bash

#
# SPDX-FileCopyrightText: 2026 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#


set -eu
set -o pipefail

if [[ $(git branch --show-current) != "main" ]]; then
    echo "You must run the release script on the main branch" >&2
    exit 1
fi

docker login rg.fr-par.scw.cloud/legadilo -u nologin --password-stdin < ~/.private/scw-registry-password

release_tag=$(git tag --list  | sort -r | head -n 1)
git checkout "${release_tag}"
echo "Releasing version ${release_tag} Press enter to accept."
read -r

docker image tag legadilo_production_django:latest "rg.fr-par.scw.cloud/legadilo/legadilo-django:${release_tag}"
docker image tag legadilo_production_django:latest rg.fr-par.scw.cloud/legadilo/legadilo-django:latest
docker image push "rg.fr-par.scw.cloud/legadilo/legadilo-django:${release_tag}"
docker image push rg.fr-par.scw.cloud/legadilo/legadilo-django:latest

git checkout main
