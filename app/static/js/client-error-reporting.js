/*
 * Client-side error reporting for the admin UI.
 *
 * Captures uncaught errors and unhandled promise rejections and forwards a
 * small, sanitized summary to the same-origin telemetry endpoint
 * (/api/v1/telemetry/client-errors). The server logs it through the existing
 * structured-logging pipeline (JSON logs, exported to PostHog logs in
 * production), so frontend failures become visible in PostHog instead of
 * only in the browser console.
 *
 * Loaded from the base layout. Safe under the strict CSP: no eval, no
 * external resources, plain fetch/sendBeacon to the same origin.
 */
(function () {
  "use strict";

  var ENDPOINT = "/api/v1/telemetry/client-errors";
  var REPORTING_SCRIPT = "client-error-reporting.js";

  function report(errorType, errorText, errorSource) {
    try {
      var payload = JSON.stringify({
        error_type: String(errorType || "Error").slice(0, 120),
        error_text: String(errorText || "").slice(0, 1200),
        error_source: String(errorSource || "").slice(0, 300),
      });
      var blob = new Blob([payload], { type: "application/json" });
      // sendBeacon survives page teardown; fall back to a keepalive fetch.
      if (typeof navigator !== "undefined" && navigator.sendBeacon) {
        if (navigator.sendBeacon(ENDPOINT, blob)) return;
      }
      fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
        keepalive: true,
      }).catch(function () {});
    } catch (err) {
      // Reporting must never break the page or loop back into itself.
    }
  }

  function pathOnly(value) {
    try {
      if (value && value.indexOf(location.origin) === 0) {
        return value.slice(location.origin.length);
      }
    } catch (err) {
      return "";
    }
    return value || "";
  }

  window.addEventListener("error", function (event) {
    if (
      event.filename &&
      event.filename.indexOf(REPORTING_SCRIPT) !== -1
    ) {
      return; // never report failures of the reporter itself
    }
    report(
      "uncaught",
      event.message || "Unknown error",
      pathOnly(event.filename) || location.pathname
    );
  });

  window.addEventListener("unhandledrejection", function (event) {
    var reason = event.reason;
    if (reason instanceof Error) {
      report("unhandledrejection", reason.message || String(reason), location.pathname);
    } else if (reason) {
      report("unhandledrejection", String(reason), location.pathname);
    } else {
      report("unhandledrejection", "Unknown rejection", location.pathname);
    }
  });
})();
