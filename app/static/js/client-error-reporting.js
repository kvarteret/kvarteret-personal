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

  var ENDPOINT = "/api/v1/telemetry/client-errors/";
  var REPORTING_SCRIPT = "client-error-reporting.js";

  function report(errorType, errorText, errorSource, details) {
    try {
      var payload = JSON.stringify(Object.assign({
        error_type: String(errorType || "Error").slice(0, 120),
        error_text: String(errorText || "").slice(0, 1200),
        error_source: String(errorSource || "").slice(0, 300),
      }, details || {}));
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
      return new URL(value || location.pathname, location.origin).pathname
        .replace(/\/\d+(?=\/|$)/g, "/:id");
    } catch (err) { return ""; }
  }

  var failures = new WeakMap();
  document.addEventListener("htmx:response:error", function (event) {
    var ctx = event.detail && event.detail.ctx;
    if (!ctx || !ctx.response) return;
    var fields = [], codes = [];
    try {
      var detail = JSON.parse(ctx.text || "{}").detail;
      if (Array.isArray(detail)) detail.slice(0, 50).forEach(function (issue) {
        if (Array.isArray(issue.loc)) {
          fields.push(issue.loc.map(function (part) {
            return typeof part === "string" && /^[A-Za-z_][A-Za-z0-9_]*$/.test(part) ? part : "[]";
          }).join("."));
        }
        if (typeof issue.type === "string" && /^[a-z_]+$/.test(issue.type)) codes.push(issue.type);
      });
    } catch (err) { /* HTML failures carry no field diagnostics. */ }
    var details = {status_code: ctx.response.status,
      validation_fields: fields.join(",").slice(0, 1000),
      validation_codes: codes.join(",").slice(0, 1000)};
    var source = pathOnly(ctx.request && ctx.request.action);
    report("HttpResponseError", "HTTP " + ctx.response.status, source, details);
    var target = event.target;
    var form = target && target.closest ? target.closest("form") : null;
    // Dependent GET fragments are failures, but are not submission attempts.
    if (!form || !/^(post|put|patch|delete)$/i.test(ctx.request && ctx.request.method || "")) return;
    if (target !== form && !target.matches('button[type="submit"], input[type="submit"]')) return;
    var history = failures.get(form) || {count: 0, fields: [], codes: []};
    if (history.count >= 3) return;
    history.count++;
    history.fields = history.fields.concat(fields);
    history.codes = history.codes.concat(codes);
    failures.set(form, history);
    if (history.count === 3) report("RepeatedFormSubmissionFailure", "Three unsuccessful form submission attempts", source, {
      form_id: pathOnly(form.action), attempt_count: 3, status_code: ctx.response.status,
      validation_fields: Array.from(new Set(history.fields)).join(",").slice(0, 1000),
      validation_codes: Array.from(new Set(history.codes)).join(",").slice(0, 1000)
    });
  });
  document.addEventListener("htmx:after:request", function (event) {
    var ctx = event.detail && event.detail.ctx;
    var form = event.target && event.target.closest ? event.target.closest("form") : null;
    if (form && event.target === form && ctx && ctx.response && ctx.response.status >= 200 && ctx.response.status < 400) failures.delete(form);
  });

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
