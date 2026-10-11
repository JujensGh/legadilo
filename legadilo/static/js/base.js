// SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
//
// SPDX-License-Identifier: AGPL-3.0-or-later

(function () {
  const setupHtmxConfirmWithPopup = () => {
    document.addEventListener("htmx:confirm", (htmxEvent) => {
      const elementForModal = getElementForModalData(htmxEvent);
      if (!elementForModal) {
        return;
      }

      const modalId = elementForModal.dataset.modalId;
      if (!modalId) {
        return;
      }

      htmxEvent.preventDefault();
      const modalTitle = elementForModal.dataset.modalTitle;
      const modalBody = elementForModal.dataset.modalBody;
      const dialogElt = document.getElementById(modalId);
      dialogElt.querySelector(".modal-title").textContent = modalTitle;
      dialogElt.querySelector(".modal-body").textContent = modalBody;

      const proceedButton = dialogElt.querySelector("button.proceed");
      const closeButton = dialogElt.querySelector("#danger-modal-close-btn");
      const cancelButton = dialogElt.querySelector("#danger-modal-cancel-btn");

      const handleClose = () => {
        dialogElt.removeEventListener("close", handleCancel);
        dialogElt.removeEventListener("click", handleCloseOnClickAway);
        proceedButton.removeEventListener("click", handleProceed);
        closeButton.removeEventListener("click", handleCancelWithAnimation);
        cancelButton.removeEventListener("click", handleCancelWithAnimation);
      };

      const closeWithAnimation = () => {
        handleClose();
        dialogElt.classList.add("closing");
        dialogElt.addEventListener(
          "animationend",
          () => {
            dialogElt.classList.remove("closing");
            dialogElt.open && dialogElt.close();
          },
          { once: true },
        );
      };

      const handleCloseOnClickAway = (event) => {
        if (event.target === dialogElt) {
          htmxEvent.detail.dropRequest();
          closeWithAnimation();
        }
      };

      const handleCancel = () => {
        handleClose();
        htmxEvent.detail.dropRequest();
      };

      const handleCancelWithAnimation = () => {
        closeWithAnimation();
        htmxEvent.detail.dropRequest();
      };

      const handleProceed = () => {
        closeWithAnimation();
        // When we use HTMX confirm, HTMX will lose the last button clicked and thus won't transmit
        // its name. It's a problem. In which case, we force it ourselves with the hx-vals attribute.
        // To avoid having multiple names in other cases (and thus interfering with form actions)
        // we remove it afterward.
        if (
          htmxEvent.explicitOriginalTarget &&
          htmxEvent.explicitOriginalTarget.getAttribute("name")
        ) {
          const buttonName = htmxEvent.explicitOriginalTarget.getAttribute("name");
          htmxEvent.target.setAttribute("hx-vals", JSON.stringify({ [buttonName]: "" }));
        }
        htmxEvent.detail.issueRequest();
        htmxEvent.target.removeAttribute("hx-vals");
      };

      // In this case, the browser will close the dialog with a non-cancellable event. If the
      // animation is set up, the dialog will close automatically due to our handler on the next
      // open as part of the animation that didn't run previously.
      dialogElt.addEventListener("close", handleCancel);
      dialogElt.addEventListener("click", handleCloseOnClickAway);
      proceedButton.addEventListener("click", handleProceed);
      closeButton.addEventListener("click", handleCancelWithAnimation);
      cancelButton.addEventListener("click", handleCancelWithAnimation);
      dialogElt.showModal();
    });
  };

  const getElementForModalData = (htmxEvent) => {
    // By default, we look at the form, but sometimes we only want confirmation on a certain button.
    // In which case, we want to put the data-* attribute for the modal on it directly.
    if (htmxEvent.target.dataset.modalId) {
      return htmxEvent.target;
    }

    if (
      htmxEvent.explicitOriginalTarget &&
      htmxEvent.explicitOriginalTarget.dataset &&
      htmxEvent.explicitOriginalTarget.dataset.modalId
    ) {
      return htmxEvent.explicitOriginalTarget;
    }
  };

  window.addEventListener("DOMContentLoaded", setupHtmxConfirmWithPopup);
})();
