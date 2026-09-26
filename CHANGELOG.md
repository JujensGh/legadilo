<!--
SPDX-FileCopyrightText: 2023-2025 Legadilo contributors

SPDX-License-Identifier: CC-BY-SA-4.0
-->

# Changelog

Summary of main functional changes.

## Unreleased

- Can select the font family, font size and max width of article details.
- Can hide the unread count on reading lists.
- Add a statistics page that displays stats about the number of articles and feeds.
- Display the remaining reading of articles groups.
- Update deps.

## 26.07.1

- Update deps.

## 26.06.2

- Update deps.

## 26.06.1

- Prevent article aside to be above dropdown menu.
- Skip invalid articles in feeds.
- Use article URL as a fallback title if slugify fails.

## 26.05.3

- Update deps.

## 26.05.2

- Update deps.
- Revert HTMX update to prevent URL change on boosted actions.

## 26.05.1

- Update deps.

## 26.04.2

Extension:
- Restore the possibility to save articles from reading view.

## 26.04.1

- Prevent saving links from the instance. It’s always a mistake.

## 26.03.5

- Disable autocomplete for URLs. They will be unique anyway, and it’s confusing on mobile.
- Prevent horizontal scrolling on mobile on article details with long `code` elements.

## 26.03.4

- Allow Markdown in all editable articles groups descriptions and articles summaries.
- Correct preview picture URLs fallback when editing an article.
- Make secure HSTS seconds configurable with the `DJANGO_SECURE_HSTS_SECONDS` environment variable. It still defaults to 60 seconds (the previously hardcoded value).
- Allow the `cron` command to exit cleanly on `SIGINT` and `SIGTERM`.

## 26.03.3

Browser extension:
- Remove the unused Bootstrap JS from the extension.
- Correct the order of the fields on the article form so it makes more sense.
- Correct a bug that would create empty groups when updating an article.

## 26.03.2

- Prevent 500 errors on 404 pages.
- Make sure all feeds always have a title and a slugifiable title.
- Browser extension:
  - Prevent request duplication.
  - Avoid errors on some failures.

## 26.03.1

- Can create groups from the add article and the edit article details forms.
- Can list groups in the API.
- Autocomplete tags and groups from the server in form fields.
- Rework browser extension.
  - Improve its technical state.
  - Add support for groups.

## 26.02.5

- Add sqlite support and switch to sqlite for production and development.
- Fix the `cron` command.
- Fix import of CSV.

## 26.02.4

- Correct migration reset.

## 26.02.3

- Ends the preparation for sqlite by squashing existing migrations.

## 26.02.2

- Prepare the arrival of sqlite as a supported database. This involves technical only changes.
- Correct once again how language is enforced at login.

## 26.02.1

- Update Django for security.
- Clean up how language is forced on login based on user settings.

## 26.01.2

- Prevent errors on login when enforcing language.

## 26.01.1

- Add a `.well-known/security.txt` view to ease reporting vulnerabilities.
- List all articles of a group in the list. Some could be hidden due to a max-height applying to all cards’ main contents.
- Remove the fragment from the URL. They are almost never used for navigation in SPAs these days and could lead to duplicated URLs.
- Use lang attribute where possible.
- Improve the display of reading lists selector.
- Cleanup navigation in user settings.
- Improve save actions in admin.
- Rework how user sessions are managed to link them to the user.
  - Sessions are now cleaned as part of the `clean_users` command. `clearsessions` cannot be used anymore.
- Enable account deletion in the account parameters.
- Inactive accounts are deleted after several notification emails. Both the deletion and the notification are done by the `clean_users` command.
- Allow user to specify their language. Use the browser one by default and English as fallback.

## 25.12.5

- Correct tags admin display on mobile.
- Display active nav item it top bar.
- Show the number of displayed articles on search if not all articles are displayed.
- Adds articles groups:
    - Can create articles groups on the new articles page.
        - Can link multiple articles to a group at group creation.
    - Can list groups and view their details.
        - View articles of a group.
        - Read all articles of a group.
        - Reorder articles in a group.
        - Can search groups.
        - Can export/import groups.
        - Can reorder the articles of a group.
    - Can import and export articles groups.

## 25.12.4

- Fix how to open articles by default.

## 25.12.3

Dev changes:

- Simplify many-to-many relations. The end goal is to be able to support multiple database backends.

## 25.12.2

Dev changes:

- Improve CSS files.
- Correct installation of dependencies in dev container.
- Enable brotli as a compression algorithm for static files.
- Update Django to 6.0
- Update Python to 3.14

## 25.12.1

- Update Python dependencies.

## 25.12.1

- Display a message for articles without content.
- Remove the possibility to add a custom script.

## 25.11.2

- Simplify messages displayed when saving an article.
- Correctly refetch the list of tags after creating an article.
- Display a proper 404 page when a reading list is not found by slug. It used to be an empty page
  with a 404 status code.
- Don’t display empty tags on article details when an article doesn’t have a content.
- Remove last usages of `format_html`. Messages are now always formatted in HTML templates.
- Correct count of users with active sessions

## 25.11.1

- Update the article content type when content is updated.
- Reduce the probability of invalid horizontal scroll.
- Use lazy loaded images if any.
- Browser extension:
    - Prepare Firefox extension for data collection permissions.
- Important technical changes:
    - Cleanup Python deps.
    - Update deps.
    - Reduce Docker image size.
    - Version is now part of the package and not supplied as an environment variable.
        - The release script will now update the version in the changelog and in `pyproject.toml`

## 25.10.2

- Can reorder reading lists with drag and drop.
- Can add plain text articles in addition to HTML articles.

## 25.10.1

- Prevent horizontal scrolling on mobile because of long links.
- Make JS required for some actions.
    - Supporting non-JS users made the code a bit complex with no clear advantages since JS is
      required to use some parts of the app anyway.
    - Most (if not all) users will have JS enabled.
    - This could be reverted in the future if the justification to use the app without JS is
      stronger.

## 25.09.2

- Technical release to update deps and clean up the code.

## 25.09.1

- Update Python deps to fix a vulnerability in Django.

## 25.08.3

- Improve the order of actions depending on the situation.
- Prevent horizontal scrolling on mobile because of overflowing `code` element.
- Add French translations.
    - It’s still a work in progress. All strings should be translated, but they may contain errors
      or evolve to be more precise or concise.
    - This led to the corrections of many English strings.

## 25.08.2

- Improve `user_stats` command to list users with verified emails.

## 25.08.1

- Can send stats about users with the `user_stats` command.
- Add honeypot field to help reduce spam accounts.
- Make sure a db error occurring while updating a feed won’t prevent other feeds from being updated.
- Prevent import error on a weird edge case in which a feed would require a link article to change
  its URL but this cannot be done since an article already exists with this URL.
- Improve article deletion to allow republication of the article from a feed after a certain amount
  of time.

## 25.07.4

- Correct a migration.

## 25.07.3

- Improve article title edition.
- Improve behavior when adding new comments.
- Improve data sanitization.
- Improve tracking of article id used in feeds.
    - This should prevent article duplication when an article is republished in a feed under a
      different URL.
- Use the article URL as feed article id when the feed doesn’t specify an article id.
- Mark articles that are republished as unread.
    - Articles not seen for one year in the feed are considered as republished articles.

## 25.07.2

Browser extension:

- Correct already saved links detection.

## 25.07.1

API Changes:

- Can export feeds and articles. This was already possible through a view in the user profile.
- Include article comments in API endpoints.
- Can search articles with all options, just like in the search view.

Other changes:

- Include article comments in exports. This includes the new API exports.

## 25.06.1

- Refresh the reading list near HH:00 The goal is to refresh the reading list closer to when the
  feeds where updated.
- Hide the "Make default" button when creating a reading list.
- Search improvements:
    - Can search without a search text. This enables the usage of other fields without the need to
      find a text to search for.
    - Can search for articles linked to specific feeds.
    - Can search articles with some external tags.
    - Can go to the advanced search page from all lists of articles pages. This allows users to
      start a search from a reading list, a feed page…
- Correct access to automatically generated API documentation.
- Change the URL of the external tag with the articles view.
    - It’s required to simplify the code.
    - Switch from a pseudo-slug in the path to a query parameter.
- Hide the raw select element when updating the page with HTMX boost.
    - The issue was visible on the article details page when updating tags. You could view the tag
      selector and the raw HTML select.
- Update the tag selector when creating new tags.
    - This was visible when creating new tags on one of these pages:
        - article details,
        - reading list edition page,
    - The feed edition page already behaved as expected.

## 25.05.2

- Correct search of `EmailAddress` in the Django admin.
- Browser extension:
    - Correct refresh of the access token.

## 25.05.1

- Can configure how `gunicorn` is run.
- Correctly refresh feeds configured to run on a precise day of the month.
- Delete accounts without any verified emails after a default retention period.
- Try to improve action buttons order to make order more consistent and the buttons easier to find
  and use.
- Can edit "open original URL by default" checkbox in admin.
- Browser extension:
    - Can save YouTube videos.
    - Can save any big HTML pages without triggering an error in the API.
    - Can save a page even when the reader mode is enabled in Firefox. It already worked correctly
      in Chromium-based browsers.

## 25.04.3

- Fix bugs in browser extension:
    - Correctly build more relative URLs.
    - Handle errors when listing enabled feeds and articles.

## 25.04.2

- Show reading list title and reading list actions when scrolling up.
- Improve browser extension:
    - Display site title instead of nothing for feed links without a title attribute.
    - Can go back to list of actions from error, article & feed.
    - Can delete article from extension.
    - Display on actions chooser whether the sure is subscribed feeds.
    - Display on actions chooser whether the article is already saved.
    - Can delete and disable/enable a feed from the extension.
- API changes:
    - Switch from `link` to `url` to save articles. This is done to have a consistent naming in the
      codebase.
    - Can list articles and filter them by URLs.
    - Can list feeds and filter them by feed URLs and enabled status.
- Correct Django admin styling.
    - This was caused by the update to `django-csp` 4.0 which changed how CSP rules are computed. It
      caused the admin to be unable to load its script files and stylesheets.
- Allow base64 encoded images.
- Keep h1 titles when we have more than 1.
    - Some invalid articles may have multiple h1, keep them in this case since they are "normal"
      article titles and thus must be kept.

## 25.04.1

- Remove async functions to simplify the code.
    - We now run with `gunicorn` instead of `daphne` in production. We use 4 `gunicorn` workers.
- Switch to Python 3.13
- Correct title for feeds without sections in feeds admin.

## 25.03.2

- Improve user Django admin page.
- Prevent errors with empty slugs.

## 25.03.1

- Can filter tags in tags admin.
- Enable tags hierarchy when updating an article on the details page.

## 25.01.1

- Correct footer background on dark mode.
- Prevent articles to be read on scroll before initial scroll to top on page load.
- Force re-authentication before managing tokens.
- Allow users to change their passwords.
- Browser extension:
    - Ask before resetting options.
    - Can open articles and feeds details.
    - Prevent extension popup to become too wide.
    - Can test the options on the settings page.
    - Support tag hierarchy.

## 24.12.6

- Can change CSP for tracking script

## 24.12.5

- Add link to changelog in footer.
- Improve existing links in footer.
- Allow you to add a custom script.
- Can fetch feed without an explicit full site URL.
- Can force feeds to refresh in the admin.
- Can refresh a reading list no mobile easily, without going to the top of the page or opening the
  reading list selector.
- Switch to [`uv`](docs.astral.sh/uv/) to manage dependencies.

## 24.12.4

- Use the theme (light or dark) that matches the system theme.
- Add a theme selector.
- Use a switch to enable/disable read on scroll. This is more visible and is clearer than what we
  had before.
- Don’t disable feeds when saving modifications with enter.
- Prevent a display issue when linking new email addresses.

## 24.12.3

- Small adjustments for extensions.
- Add a privacy policy page.

## 24.12.2

- Add a privacy policy to release the extension on Chrome webstore.
- Improve extensions to publish on Chrome & Mozilla webstore.

## 24.12.1

- Reduced allow times in which daily updates are run. We still support bi-hourly cron runs.
- Display a contact email to all authenticated users.
- Add an API:
    - The documentation is available at `/api/docs/`.
    - You can manage application tokens in your profile.
    - You can get auth tokens from these applications tokens to use the API.
- Prevent 500 errors on duplicated tags (in tag admin), feed categories and reading lists.
- Add debug information to feed admin.
- Add link to feed admin on feed articles list.
- Can search for feeds in feed admin.
- Add a browser extension.

## 24.10.3

- Correct display of titles with HTML entities when adding an article.
- Build a tag hierarchy to automatically add other tags when we select a tag.
    - The hierarchy can be edited in the tag admin.
    - Tag can also be renamed now.
- Correct the modal used when deleting feeds, feed categories and reading lists.
- Create a `cron` command run by a `cron` container by default.
    - This should ease running the CRON commands requires to update feeds (and run some cleanups)
      more easily within docker compose.
- Use the feed as page title when editing a feed.
- Can update feeds on saturdays and on sundays.
    - It’s to have articles updated at the start of the weekend!
- Can sort search results by relevancy & various dates.
- Can add comments on articles.
    - Text supports Markdown markup.

## 24.10.2

- Increase session lifetime to 2 weeks: it seems like a better compromise to only be disconnected if
  we haven’t used legadilo in a while.
- Update table of content when re-fetching an artile.
- Improve display of notifications:
    - Put unread first.
    - Hide read notifications after 3 months.
- Can delete articles linked to feeds.
- Always reload the page when going back to the reading list from article details.
    - This is to make read on scroll work. Otherwise, we will have a HTMX page change and the JS
      script won’t even be loaded on the page.
- Group updates for read on scroll.
    - Instead of updating articles one by one, we now mark all scrolled articles as read in one go.
      This should make read on scroll feel easier to use.
- Allow to use all version of PG above 16.
    - We still rely on 16 but don’t block users who would want to use 17 or above.
        - We keep 16 in our container and don’t have a way to upgrade yet anyway.
          See https://github.com/Jenselme/legadilo/issues/276
    - We don’t support versions below that: we developed and tested against 16 and don’t want to
      test other ones.
        - Future versions should work fine directly from our experience.
        - Older ones probably too given the feature set we use. But we don’t want to have any weird
          surprises.

## 24.10.1

- Correct `theme_color` in `manifest.json`.
- Set main source on invalid articles.
- Correct default timeout when fetching articles and RSS data.
    - They are now configurable.
    - We have a shorter timeout when fetching an article to hit the code timeout before hitting the
      nginx timeout configured on the default instance.

## 24.09.3

- Can subscribe with channel or playlist link.
    - For channels, it must be a link of the form `/channel/<CHANNEL_ID>`. The clean url with
      `/@ChannelName` doesn’t work.

## 24.09.2

- Improve logging for `clean_data`

## 24.09.1

### Breaking change

- Command `cleanup_old_updates` has been renamed into `clean_data`.
    - It still cleans up old feed updates and articles fetch errors.
    - It will also clean old articles from feeds if the _Keep articles_ option is not set to
      _Always_ in the configuration of the feeds.

### Other changes

- Display a count of unread notifications.
    - This makes the link more visible when a user has unread notifications.
- Correct text breaks of summary.
- Re-enable feed if we re-add a disabled feed.
- Correct article author in page metadata.
- Display a navigable table of content on the side of article details.

## 24.08.6

- Can disable read on scroll temporarily.

## 24.08.5

- Correct display of `figcaption` element on article details.
- Correct display of big `pre` blocks on article details to prevent horizontal scrolling of the
  whole page.
- Prevent overflow of article details content.
- Add a link to the disabled feeds in notifications.
- Add notification creation time on notifications page.

## 24.08.4

- Allow users to enable MFA.

## 24.08.3

- Add search:
    - Can search text in the body, summary, authors and source title of articles.
    - Can filter searches by tags.
    - Can update searched articles.

## 24.08.2

- Allow users to select a TZ to view times in their profile.
    - Ask user TZ on registration.
    - Update user profile to allow users to change their TZ.
- Automatic deactivation of broken feeds is more consistent with their refresh period.
- Prevent read on scroll to be completely broken in one request of the chain failed.

## 24.08.1

- Add notifications when a feed is disabled.

## 24.07.8

- Can configure SMTP user, password and TLS connection.

## 24.07.7

- Prevent overflow of tags and pagination selector (mostly a mobile issue).

## 24.07.6

- Prevent overflow for content with very long links.

## 24.07.5

- Improve documentation.

## 24.07.4

- Correct daphne port.

## 27.07.3

Skipped because of release script bug due to local testing.

## 24.07.2

- Scroll to the top of reading lists when going back to them.
- Refresh session at every request to prevent to reconnect to often while losing session rapidly on
  used devices.
- Don’t try to update the feed if we failed to fetch its file.

## 24.07.1

Initial release:

- Can subscribe to feeds.
    - Each feed is associated with tags that are used to tag the article.
    - Can select frequency of updated.
    - Invalid feeds are automatically disabled.
- Can manually add articles and tag them.
