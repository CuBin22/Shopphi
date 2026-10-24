# Shopphi storefront implementation plan

**Goal:** Apply the user's Shopee reference to the existing Django storefront: flat orange, rotating banner, complete product images.
**Architecture:** Reuse Django templates, the current product queryset, SVG icons and vanilla JavaScript. No new dependencies or demo data.
**Spec:** User's screenshot and approved proposal in this conversation; retain Shopphi branding, a wide search header, main carousel and two side panels, category shortcuts and product grid.

- [ ] Select up to five available products with uploaded images for banners; test hidden/locked products and empty catalog.
- [ ] Replace the home hero and style the shared header and cards with a flat orange palette, white image backgrounds and object-fit: contain.
- [ ] Add carousel controls, automatic rotation, pause/resume, focus/hover pause and reduced-motion support.
- [ ] Verify Django tests, JavaScript syntax and desktop/mobile browser layout and interactions.

Review focus: zero/one slide; long names; no image; narrow viewport; automatic motion must be stoppable. Existing search/cart/account functions must remain available. Implement inline in the existing non-Git workspace; no database writes needed.
