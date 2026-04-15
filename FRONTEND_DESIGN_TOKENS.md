# Frontend Design Tokens (Coinbase-inspired)

## Objetivo
Traducir `DESIGN.md` a tokens reutilizables para frontend React sin depender de fuentes propietarias.

## Color tokens
```css
:root {
  --color-brand-primary: #0052ff;
  --color-brand-hover: #578bfa;
  --color-link-secondary: #0667d0;

  --color-surface-base: #ffffff;
  --color-surface-secondary: #eef0f3;
  --color-surface-dark: #0a0b0d;
  --color-surface-dark-card: #282b31;

  --color-text-primary: #0a0b0d;
  --color-text-inverse: #ffffff;
  --color-border-muted: rgba(91, 97, 110, 0.2);
}
```

## Radius tokens
```css
:root {
  --radius-xs: 4px;
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xl: 24px;
  --radius-2xl: 32px;
  --radius-3xl: 40px;
  --radius-pill: 56px;
  --radius-full: 100000px;
}
```

## Spacing tokens
```css
:root {
  --space-1: 1px;
  --space-3: 3px;
  --space-4: 4px;
  --space-5: 5px;
  --space-6: 6px;
  --space-8: 8px;
  --space-10: 10px;
  --space-12: 12px;
  --space-15: 15px;
  --space-16: 16px;
  --space-20: 20px;
  --space-24: 24px;
  --space-25: 25px;
  --space-32: 32px;
  --space-48: 48px;
}
```

## Typography tokens
Por disponibilidad web, se recomienda fallback:
- Display: `"Sora", "Inter", system-ui, sans-serif`
- UI: `"Inter", system-ui, sans-serif`
- Body: `"Inter", system-ui, sans-serif`

```css
:root {
  --font-display: "Sora", "Inter", system-ui, sans-serif;
  --font-ui: "Inter", system-ui, sans-serif;
  --font-body: "Inter", system-ui, sans-serif;

  --text-hero-size: 80px;
  --text-hero-line: 1;
  --text-h2-size: 36px;
  --text-h2-line: 1.11;
  --text-card-title-size: 32px;
  --text-body-size: 18px;
  --text-body-line: 1.56;
  --text-button-size: 16px;
  --text-button-line: 1.2;
  --text-caption-size: 14px;
}
```

## Component rules
- CTA primario:
  - radio `var(--radius-pill)`
  - fondo `var(--color-surface-secondary)` o `var(--color-surface-dark-card)`
  - hover `var(--color-brand-hover)`
- Enlace destacado:
  - color `var(--color-brand-primary)`
- Foco accesible:
  - `outline: 2px solid var(--color-text-primary)`
  - `outline-offset: 2px`

## Breakpoints
```css
:root {
  --bp-400: 400px;
  --bp-576: 576px;
  --bp-640: 640px;
  --bp-768: 768px;
  --bp-896: 896px;
  --bp-1280: 1280px;
  --bp-1440: 1440px;
  --bp-1600: 1600px;
}
```
