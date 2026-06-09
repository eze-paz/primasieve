# Module: `themes.js`

> Appearance — built-in theme palettes plus per-theme custom colours, applied as
> CSS variables.

| | |
|---|---|
| **Load type** | `classic` |
| **Global namespace** | bare globals (`setTheme`, `applySavedCustom`, …) |
| **Sidebar section** | `themeSection` (contains `#themeCustomize`) |
| **Status dot** | none |

## Public surface
`setTheme(name)`, `applySavedCustom()`, `applyThemePalette`, `buildPaletteUI`,
`updateThemeButtons`, `resetThemeColors`, `saveThemeColors` (used by inline
`onclick=` in the injected section markup).

## Events
- **Emits:** none.
- **Listens:** none.

## DOM owned
`#themeSection` with the theme buttons, `#themeCustomize` (the palette editor) and
`#themePaletteRows`. Injects a `:root { --sp-* }` CSS-variable block.

## Depends on
- **Host:** `SandpieMenu`, `localStorage` (`sandpie-theme`, per-theme palette keys).

## Notes / gotchas
- Restores the saved theme on its **own `DOMContentLoaded`** (`applySavedCustom()`),
  independent of any host boot — this is why the host no longer needs to call it.
- `setTheme` reads `#themeCustomize`; if the Appearance section failed to register
  (e.g. `SandpieMenu` broken) it would hit a null — keep the section registration healthy.

---
_Surface verified from source; for internal implementation see `modules/themes.js`._
