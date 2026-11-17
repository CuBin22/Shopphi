# Shopphi Modern UI Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` to implement this plan inline. Steps use checkbox syntax for tracking.

**Goal:** Give Shopphi’s storefront, checkout, shop, vendor and admin screens one polished, responsive visual system.

**Architecture:** Keep Django templates and the existing `app.css` / `storefront.css` split. Establish semantic CSS tokens and shared component rules in `app.css`, then make storefront-specific presentation consistent in `storefront.css`; only adjust templates where existing markup prevents a coherent layout.

**Tech Stack:** Django templates, existing CSS, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-10-31-shopphi-modern-design.md`

## Global Constraints

- Keep Shopphi’s red-orange brand color with neutral surfaces and semantic status colors.
- Cover storefront, shop/product detail, cart/checkout/orders, vendor and admin interfaces.
- Preserve business logic, payment/shipping flows, permissions, product data and copy.
- Do not add a UI framework or dependencies.
- Keep responsive behavior, visible keyboard focus and reduced-motion support.

## Review Focus

- Narrow screens: prevent horizontal overflow and keep forms/cards usable.
- Long product/shop names: contain text without displacing prices or actions.
- Tables and dashboards: preserve readable alignment and horizontal access on small screens.
- Keyboard focus and disabled/error/success states: remain visually distinct.
- Shared base styles: avoid regressions between public and management screens.

---

## Files and Responsibilities

- `catalog/static/catalog/css/app.css`: global tokens, shared controls, forms, tables, management layout and responsive foundations.
- `catalog/static/catalog/css/storefront.css`: public header, home showcase, product/shop cards, detail pages, cart and checkout presentation.
- `catalog/static/catalog/css/header-footer.css`: compact responsive header/footer and shared discovery-search styling.
- `catalog/templates/catalog/base.html`: public shell only if required to expose consistent structure.
- `shopping/templates/shopping/manage_base.html`: management shell only if required to expose consistent structure.
- `docs/superpowers/plans/2026-10-31-shopphi-modern-ui.md`: progress record for this implementation.

## Tasks

### Task 1: Normalize shared design tokens and controls

**Files:** `catalog/static/catalog/css/app.css`

- [x] Replace legacy color naming with clear semantic token aliases while preserving compatibility for existing selectors.
- [x] Unify type scale, spacing, borders, radius, shadows, button sizes, inputs, focus, status pills and panels.
- [x] Confirm public and management shells still share the same control language.

### Task 2: Refresh storefront surfaces

**Files:** `catalog/static/catalog/css/storefront.css`, and only necessary catalog templates.

- [x] Refine header/search/category navigation, hero showcase and section headings.
- [x] Align product cards into stable image/title/shop/price regions; use image fill without distorting source images.
- [x] Apply the same visual rhythm to shop catalog, product detail, cart and checkout.
- [x] Keep empty, loading, validation and selected states legible.

### Task 3: Refresh seller and admin surfaces

**Files:** `catalog/static/catalog/css/app.css`, `shopping/templates/shopping/manage_base.html` only if structure requires it.

- [x] Refine management sidebar, active navigation, dashboard metrics, panels and action hierarchy.
- [x] Improve forms, filters, order/product tables, pagination and mobile table access.
- [x] Keep state colors and destructive actions consistent and clear.

### Task 4: Responsive and visual review

**Files:** both stylesheets and only fixes required by review.

- [x] Visually review home, search and shop at desktop and mobile widths.
- [x] Fix responsive wrapping, image fill and inconsistent spacing found during visual review.
- [x] Rebuild the existing Docker app; homepage loaded after rebuild.

**Review note:** authenticated checkout, order-management, seller-dashboard and admin screens were not directly opened during this visual pass. Their shared CSS was refreshed; Docker Compose rebuild completed, but a later `docker compose ps` status query was denied by the local Docker Desktop pipe.

