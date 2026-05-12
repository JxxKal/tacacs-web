# 0010. React + Mantine + Vite + TypeScript frontend stack

- Date: 2026-05-12
- Status: Accepted

## Context

We need a single-page admin UI that covers a moderate but typical scope: a dozen entity tables with CRUD forms, a setup wizard, an audit-log browser, accounting search, an Effective Permissions view, and live status panels. The team building this is small and the project is public — contributor familiarity matters.

Realistic stacks considered:

- **React + Mantine + Vite + TypeScript**
- **React + MUI + Vite + TypeScript**
- **Vue 3 + PrimeVue (or Naive UI) + Vite + TypeScript**
- **Server-rendered HTMX + Jinja2** (would have collapsed backend + frontend into one container)

Auxiliary library choices: server-state (TanStack Query vs. Redux Toolkit Query), runtime schema validation (Zod vs. io-ts), routing (react-router-dom vs. TanStack Router), i18n (i18next vs. react-intl).

## Decision

- **React** (latest stable) as the SPA framework — largest open-source contributor pool, deepest ecosystem.
- **Mantine** as the UI component library — out-of-the-box tables, forms, notifications, date-pickers, modals, with a coherent admin-tool look-and-feel that requires almost no custom CSS.
- **Vite** as the build tool — fast dev server, simple production build.
- **TypeScript** end-to-end.
- **TanStack Query** for server state, **Zod** for runtime schema validation at the API boundary, **react-router-dom** for routing.
- **i18next** with `en` and `de` locale files **from day one** — i18n infrastructure is structurally hard to retrofit and we have committed to bilingual UI.
- Built artifact is served as static files by the `nginx` container; no SSR. The backend is a pure JSON API.

## Consequences

- Largest possible contributor pool — React + TypeScript is the most-known web stack as of 2026.
- Mantine's opinionated component set keeps us from inventing yet-another-design-system; visual consistency is essentially free.
- Bundle size is moderate (Mantine is tree-shakable; tables and forms can land split-route). Acceptable for an internal admin tool.
- i18n from day one costs roughly 15% extra UI-implementation time (every string in a `t()` call, two locale files in sync), but eliminates the future migration pain.
- We are not using SSR. SPA bootstrap latency is one extra round-trip after login. For an admin tool, fine.
- We do not bring HTMX. A future contributor who would have preferred it can fork; the SPA decision is part of the public-repo contract.

## Alternatives considered

- **MUI instead of Mantine** — strong contender; we picked Mantine for its tighter admin-UI defaults and faster iteration on forms/tables.
- **Vue 3 + PrimeVue/Naive UI** — equally capable; smaller contributor pool than React in the public-OSS context.
- **HTMX + server templates** — would have collapsed two services into one, big simplification, but we explicitly chose an SPA in the planning phase and that decision rules this out.
