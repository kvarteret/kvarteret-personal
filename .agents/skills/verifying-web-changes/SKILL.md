---
name: verifying-web-changes
description: Verify FastAPI web routes, Jinja templates, Tailwind styles, HTMX, Alpine fragments, and Vercel runtime behavior.
---

# Verifying Web Changes

Use this skill for FastAPI web routes, Jinja templates, Tailwind styles, HTMX,
Alpine fragments, and Vercel runtime behavior.

## Workflow

1. Identify the route, template, macro, and CSS files that render the changed
   surface.
2. Prefer shared macros from `app/templates/components/shared/ui_macros.html`
   before adding duplicate markup.
3. Run targeted tests for the route or service when available.
4. Start the app with `make run` when browser behavior matters.
5. Verify the changed page in a browser at desktop and mobile widths.

## UI Checks

- Square-corner Kvarteret styling is preserved.
- Form labels, validation messages, and action buttons do not overlap.
- HTMX swaps target the intended container and do not drop persistent state.
- Alpine state is scoped to the component that owns it.
