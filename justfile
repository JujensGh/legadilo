# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

postgres_url := "postgres://django:django_passwd@localhost:5432/legadilo"

default:
    just --list

update-deps:
    npm update
    npm --prefix browser-extension update
    uv sync --upgrade --all-groups
    just check
    git commit -am "chore: update deps"

dev:
    docker compose -f local.yml up

dev-local-python:
    docker compose -f local.yml --profile mail up -d
    python manage.py runserver

dev-local-python-pg:
    docker compose -f local.yml --profile postgres --profile mail up -d postgres mailpit
    DATABASE_URL="{{ postgres_url }}" python manage.py runserver

update-feeds:
    uv run python manage.py update_feeds

setup-dev-database:
    uv run python manage.py migrate
    uv run python manage.py setup_test_db

setup-python-ci:
    sudo apt-get update
    sudo apt-get install -y gettext
    uv sync --dev --locked

setup-ci: setup-python-ci
    npm ci
    npm ci --prefix browser-extension

test:
    uv run pytest

test-coverage:
    uv run pytest --cov --cov-report term:skip-covered --cov-fail-under=95

lint:
    uv run pre-commit run -a

makemigrations:
    uv run python manage.py makemigrations

migrate:
    uv run python manage.py createcachetable
    uv run python manage.py migrate

migrate-pg:
    DATABASE_URL="{{ postgres_url }}" uv run python manage.py migrate

clean-dev-container:
    docker compose -f local.yml down

update-po:
    uv run python manage.py makemessages --all --no-location

compile-po:
    uv run python manage.py compilemessages --verbosity 0

build-production-images:
    docker compose -f production.yml build django --pull

test-production-images: build-production-images
    docker run --rm \
      --env-file ./devops/envs/local/django \
      --env IS_PRODUCTION=true \
      --env DJANGO_SECRET_KEY=ci \
      --env DJANGO_ADMIN_URL=/admin/ \
      --env DATABASE_URL="sqlite://:memory:" \
      legadilo_production_django:latest \
      python manage.py check

[working-directory('browser-extension')]
test-browser-extension:
    npm test

[working-directory('browser-extension')]
watch-test-browser-extension:
    npm run test:watch

[working-directory('browser-extension')]
build-browser-extension:
    npm run build

check: lint test-coverage test-browser-extension

ci:
    docker compose -f ci.yml up --build --detach --force-recreate
    docker compose -f ci.yml exec django just ci-run
    docker compose -f ci.yml down
    just test-production-images

ci-run:
    bash ./devops/scripts/local-ci.sh

bump-version: ci-run
    bash ./devops/scripts/bumb-version.sh

release: build-production-images
    bash ./devops/scripts/release.sh
