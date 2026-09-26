/*
 * SPDX-FileCopyrightText: 2026 Legadilo contributors
 *
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

(function () {
  const root = document.querySelector(":root");
  const fontFamilyInput = document.getElementById("id_article_details_font_family");
  const fontSizeDesktop = document.getElementById("id_article_details_font_size_desktop");
  const fontSizeTablet = document.getElementById("id_article_details_font_size_tablet");
  const fontSizeMobile = document.getElementById("id_article_details_font_size_mobile");
  const maxWidthDesktop = document.getElementById("id_article_details_max_width_desktop");
  const maxWidthTablet = document.getElementById("id_article_details_max_width_tablet");

  // To keep in sync with the Python constant.
  const USER_SETTINGS_ARTICLE_DETAILS_MAX_WIDTHS_CHOICES_TO_CSS_VALUES = {
    small: "700px",
    medium: "900px",
    large: "1100px",
  };

  fontFamilyInput.addEventListener("change", () => {
    root.style.setProperty("--legadilo-article-details-font-family", fontFamilyInput.value);
  });

  fontSizeDesktop.addEventListener("change", () => {
    root.style.setProperty("--legadilo-article-details-font-size-desktop", fontSizeDesktop.value);
  });

  fontSizeTablet.addEventListener("change", () => {
    root.style.setProperty("--legadilo-article-details-font-size-tablet", fontSizeTablet.value);
  });

  fontSizeMobile.addEventListener("change", () => {
    root.style.setProperty("--legadilo-article-details-font-size-mobile", fontSizeMobile.value);
  });

  maxWidthDesktop.addEventListener("change", () => {
    root.style.setProperty(
      "--legadilo-article-details-max-width-desktop",
      USER_SETTINGS_ARTICLE_DETAILS_MAX_WIDTHS_CHOICES_TO_CSS_VALUES[maxWidthDesktop.value],
    );
  });

  maxWidthTablet.addEventListener("change", () => {
    root.style.setProperty(
      "--legadilo-article-details-max-width-tablet",
      USER_SETTINGS_ARTICLE_DETAILS_MAX_WIDTHS_CHOICES_TO_CSS_VALUES[maxWidthTablet.value],
    );
  });
})();
