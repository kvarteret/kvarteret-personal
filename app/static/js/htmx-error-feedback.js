/*
 * The shared HTMX config keeps 4xx/5xx responses out of page swaps. Surface a
 * safe server-provided error instead of leaving boosted forms looking inert.
 */
(function () {
  "use strict";

  var ROOT_ID = "htmx-error-feedback";
  var DEFAULT_MESSAGE = "Noe gikk galt. Prøv igjen.";

  function errorMessage(ctx) {
    var contentType = ctx.response.headers.get("Content-Type") || "";
    if (contentType.indexOf("application/json") !== -1) {
      try {
        var payload = JSON.parse(ctx.text || "{}");
        if (typeof payload.detail === "string" && payload.detail.trim()) {
          return payload.detail.trim();
        }
      } catch (error) {
        return DEFAULT_MESSAGE;
      }
    }
    return DEFAULT_MESSAGE;
  }

  function removeFeedback() {
    var existing = document.getElementById(ROOT_ID);
    if (existing) existing.remove();
  }

  function showFeedback(message) {
    removeFeedback();

    var root = document.createElement("div");
    root.id = ROOT_ID;
    root.className = "fixed inset-x-4 top-4 z-50 mx-auto flex max-w-xl items-start justify-between gap-4 bg-kvarteret-night px-5 py-4 text-kvarteret-surface shadow-2xl";
    root.setAttribute("role", "alert");
    root.setAttribute("aria-live", "assertive");

    var text = document.createElement("p");
    text.className = "text-sm leading-6";
    text.textContent = message;

    var close = document.createElement("button");
    close.type = "button";
    close.className = "shrink-0 text-xl leading-none text-kvarteret-surface";
    close.setAttribute("aria-label", "Lukk feilmelding");
    close.textContent = "\u00d7";
    close.addEventListener("click", removeFeedback);

    root.append(text, close);
    document.body.append(root);
  }

  document.addEventListener("htmx:before:request", removeFeedback);
  document.addEventListener("htmx:response:error", function (event) {
    var ctx = event.detail && event.detail.ctx;
    showFeedback(ctx ? errorMessage(ctx) : DEFAULT_MESSAGE);
  });
  document.addEventListener("htmx:error", function (event) {
    // Superseded live searches are expected cancellations, not failures.
    if (event.detail?.error?.name === "AbortError") return;
    showFeedback("Kunne ikke kontakte serveren. Sjekk tilkoblingen og prøv igjen.");
  });
})();
