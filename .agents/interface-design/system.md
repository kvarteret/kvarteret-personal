# Interface Design System

This repo uses server-rendered FastAPI/Jinja templates with Tailwind, HTMX, and
Alpine interaction fragments. Verify against `app/static/css/input.css` and
`app/templates/components/shared/ui_macros.html` before changing shared styling.

## Visual Language

- Background: `--background: #fff7e4`.
- Primary action color: `--kvarteret-red: #f54b4b`.
- Text/border color: navy/ink tokens such as `--foreground` and `--border`.
- Cards and panels use `--card: #fbf2df` with solid `2px` borders.
- Corners are square. The base stylesheet sets `border-radius: 0 !important`.
- Motion is small and tactile: buttons move by `1px` on hover/active.

## Components

- Use `.app-panel` for framed content panels.
- Use `.app-input` for text, select, and search controls.
- Use `.app-button` for primary actions and `.app-button-secondary` for
  secondary actions.
- Use `.app-badge` for compact status labels.
- Prefer shared Jinja macros from `ui_macros.html` before adding one-off
  markup: `page_header`, `form_field`, `flash_notice`, `blocker_notice`,
  `lazy_panel`, and `volunteer_picker_card`.

## UX Rules

- Keep admin workflows dense and operational. Avoid marketing-page layouts in the
  admin surface.
- Preserve Norwegian UI copy unless the surrounding template is already English.
- Do not introduce rounded cards, pill buttons, or soft SaaS styling unless the
  base stylesheet changes first.
- Check mobile and desktop widths for form-heavy pages; labels, validation
  messages, and action rows must not overlap.
