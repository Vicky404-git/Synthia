# Synthia — Design Guide

Synthia is styled as a **retro-futurist operator console**: a dark, cold-blue
workstation you sit down at, not a generic SaaS dashboard. The aim is a
believable "system tool" — precise, quiet and legible — with a small amount of
warm amber for status and warnings.

Everything below is implemented with CSS variables in
[`frontend/src/styles.css`](frontend/src/styles.css). Components reference the
variables rather than raw hex values; if you change a token, the whole UI
follows.

## Principles

1. **A machine you operate, not a page you scroll.** Monospace type, thin
   rules, tight letter-spacing and a visible system readout make the app feel
   like equipment.
2. **Blue is the signal.** Electric blue is the primary accent. Cyan marks the
   live microphone, amber marks anything that needs attention.
3. **Legibility beats atmosphere.** No decorative texture, scanlines or motion
   behind text. Contrast is checked against WCAG AA for body text.
4. **Progressive disclosure.** Chrome (title bar, status strip, nav) is dense
   but small; content gets the space.

## Palette

All values are CSS custom properties. Use the token, not the hex.

### Surfaces (darkest → lightest)

| Token          | Value     | Use                              |
| -------------- | --------- | -------------------------------- |
| `--bg-deep`    | `#060b16` | Page base, status strip, footer  |
| `--bg`         | `#0a1020` | App background (faint cold glow) |
| `--well`       | `#0b1526` | Recessed areas: inputs, code, chat bubbles |
| `--surface`    | `#111d33` | Panels                           |
| `--surface-2`  | `#182a46` | Raised rows, table headers, title bar gradient |

### Borders

| Token            | Value     | Use                      |
| ---------------- | --------- | ------------------------ |
| `--border-soft`  | `#24395a` | Internal dividers        |
| `--border`       | `#304b70` | Panel / control borders  |
| `--border-strong`| `#3c5c88` | Focused or emphasised edges |

### Text

| Token          | Value     | Contrast on `--surface` | Use                    |
| -------------- | --------- | ----------------------- | ---------------------- |
| `--text`       | `#e1eaf7` | ~13:1 (AAA)             | Primary copy           |
| `--text-dim`   | `#91a6c4` | ~6.6:1 (AA)             | Secondary copy         |
| `--text-faint` | `#7c93b8` | ~4.9:1 (AA)             | Labels, metadata       |

### Accents

| Token      | Value     | Meaning                                   |
| ---------- | --------- | ----------------------------------------- |
| `--blue`   | `#5a9cff` | Primary action, links, armed state        |
| `--blue-deep` | `#2f5da8` | Gradient base for primary buttons, user messages |
| `--cyan`   | `#75d9e8` | Live microphone / active detection        |
| `--amber`  | `#f0bb69` | Warnings, processing, "needs attention"   |
| `--danger` | `#f08a8a` | Errors                                    |
| `--ok`     | `#6fd8b0` | Success / healthy                        |

Each accent has a matching translucent `*-wash` variable for tinted
backgrounds and focus rings.

## Typography

- **Monospace** (`--mono`: JetBrains Mono, then system mono fallbacks) is the
  base font. It carries the "terminal" character and is used for all chrome:
  navigation, buttons, labels, tables, the status strip and code.
- **Sans** (`--sans`: system UI stack) is used **only for prose the user
  reads**: page subtitles, assistant/user message bodies, transcript text and
  alert copy. This is a deliberate blend — machine voice for the interface,
  human voice for language.

Type scale is small and dense (12–17px for UI; 14px prose). Headings are
uppercase with `letter-spacing: 1.6–3px`; body copy uses normal spacing and a
1.55–1.6 line-height for readability.

## Spacing & shape

- A 4px base scale: `--sp-1` (4) through `--sp-5` (24).
- Radii are intentionally small — `--radius: 4px`, `--radius-lg: 6px` — to read
  as machined metal rather than soft cards.
- Layout: a `52px` title bar + `30px` system strip, then a `216px` sidebar and
  a content column capped at `1120px`.
- On screens ≤760px the sidebar is replaced by a bottom tab bar.

## Motion

Motion is minimal and functional:

- `120ms` ease transitions on borders, colour and hover only.
- A `live` step animation for blinking status lights; a `pulse` ring on the
  active microphone; a `spin` for the transcription spinner.
- **All** animation and transitions collapse to ~0ms under
  `@media (prefers-reduced-motion: reduce)`.

## Component rules

- **Panels** (`.panel`) are sloped dark gradients with a 1px border and a single
  inset highlight — no drop shadows on nested content.
- **Buttons** (`.btn`): secondary buttons are raised gradients; `.btn-primary`
  is solid blue with dark text; `.btn-danger` is outlined, never filled.
- **Pills** (`.pill`) communicate state with a leading `.dot`. Colour carries
  meaning: green = healthy, amber = warning, red = error, cyan = demo, grey =
  unknown. Never rely on colour alone — the label is always present.
- **Alerts** (`.alert`) use a thick coloured left border plus a tinted wash;
  they are the only prose surfaces besides messages.
- **Icons** are a single inline SVG set (`components/icons.tsx`) with a uniform
  1.8px stroke. **No emoji** — they render inconsistently and read as casual.
- **The wake status bar** (`.wake-bar`) is the single surface for microphone
  state. Its left border and light colour track the lifecycle: blue = armed and
  waiting, cyan = detected/recording, amber = processing or unsupported, red =
  error.
- **Voice Commands** reuses the existing primitives (panels, pills, transcript
  strip, composer, microphone button) rather than introducing a second
  interface. Live vs. simulated is never colour-only: results carry a text
  badge (`live AWS` / `simulated`) and a simulated result repeats `DEMO DATA`
  in an info alert.

## Accessibility

- Focus is always visible: a 2px cyan outline with a 2px offset.
- Interactive elements keep a ≥36px hit area (`40px` for the mic button).
- Semantic landmarks (`header`, `nav`, `main`), `aria-label` on navigations,
  `role="status"` + `aria-live` on the wake bar and status strip, and
  `.sr-only` labels for icon-only controls.
- Status is never encoded by colour alone.
