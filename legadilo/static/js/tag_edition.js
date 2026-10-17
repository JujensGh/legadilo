// SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
//
// SPDX-License-Identifier: AGPL-3.0-or-later

import Tags from "/static/tags.js";

let tagsInstances;

const setupTagsInstance = () => {
  const potentialTagsElements = document.querySelectorAll("[data-bs5-tags=true]");
  if (potentialTagsElements.length === 0) {
    return;
  }

  if (tagsInstances) {
    tagsInstances.forEach((tagInstance) => tagInstance.dispose());
  }

  tagsInstances = Array.from(potentialTagsElements).map((tagElement) => {
    return new Tags(tagElement, {
      allowClear: true,
      onSelectItem(item, instance) {
        if (!item.hierarchy) return;

        const alreadyAddedItems = instance.getSelectedValues();
        item.hierarchy
          .filter((tag) => !alreadyAddedItems.includes(tag.slug))
          .forEach((tag) => instance.addItem(tag.title, tag.slug));
      },
    });
  });
};

document.addEventListener("DOMContentLoaded", setupTagsInstance);

document.addEventListener("htmx:after:swap", setupTagsInstance);
