# AGENTS.md

This repository has a small local dashboard UI. Future edits need to keep the interface consistent and Plex-adjacent instead of introducing one-off styling.

## Dashboard Design System

The source of truth for dashboard styling is:

- `src/media_library_manager/static/styles.css`

That file is intentionally organized around three layers of tokens:

1. foundation tokens
   colors, typography, spacing, radius, shadows, layout
2. semantic tokens
   surfaces, text roles, border roles, state colors
3. component tokens
   cards, buttons, fields, pills, list items

## Required rules for future UI work

- Do not hardcode new hex colors, rgba colors, font sizes, spacing values, radii, or shadows directly in component rules if the value is meant to be reused.
- Add or update a token in `:root` first, then consume that token in the component selector.
- Prefer semantic tokens such as `--surface-panel` or `--text-secondary` over raw brand tokens unless the component is intentionally brand-accented.
- Reuse existing primitives before inventing new component styles:
  - `.card`
  - `.btn`
  - `.pill`
  - `.field`
  - `.collection-item`
  - `.empty-state`
- Reuse the shared icon patterns for dashboard chrome and section headings:
  - `.nav-icon`
  - `.icon-badge`
- For component variants, prefer local CSS custom properties on the component class rather than copy-pasting whole blocks.

## Visual direction

The dashboard should stay close to this visual language:

- dark charcoal surfaces
- warm gold accent
- compact but readable admin density
- IBM Plex Sans typography
- restrained motion and clear state contrast

This is not meant to be a pixel copy of Plex, but it should remain recognizably inspired by Plex and avoid drifting into unrelated design styles.

## HTML and JS constraints

- Avoid inline styles in `index.html` or `app.js`.
- If a new UI state needs styling, add a class and style it in `styles.css`.
- Keep view structure aligned with the existing dashboard sections and navigation patterns.

## Responsive behavior

When adding new layout blocks, check that they degrade cleanly at the current breakpoints:

- `1180px`
- `960px`

If a new component needs its own responsive rule, keep it in `styles.css` near the existing media-query section.

## If you add a new reusable pattern

Update both:

- the token section in `styles.css`
- this `AGENTS.md` file if the new pattern changes the design-system rules or conventions
