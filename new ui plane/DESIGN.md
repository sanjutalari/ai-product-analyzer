# Design System Specification: High-Tech Editorial

## 1. Overview & Creative North Star
The Creative North Star for this design system is **"The Digital Architect."** 

We are moving away from the "template-heavy" look of standard SaaS platforms toward a bespoke, editorial experience. This system balances high-tech precision with human-centric accessibility. To achieve this, we prioritize **Atmospheric Space** over structural lines. By utilizing intentional asymmetry, oversized display type, and a "tonal-first" layering philosophy, we create a UI that feels engineered yet effortless. The goal is to make every screen feel like a curated page from a premium digital journal.

---

## 2. Colors & Surface Philosophy
The palette is rooted in a high-contrast foundation of `surface` (#f9f9fb) and `on_surface` (#1a1c1d), punctuated by vibrant, electric accents.

### The Palette
*   **Primary (Electric Purple):** `primary` (#4800b2) – Used for high-priority actions and brand presence.
*   **Secondary (Vibrant Teal):** `secondary` (#006a60) – Used for highlights, success states, and interactive secondary elements.
*   **Neutral Layers:** A spectrum from `surface_container_lowest` (#ffffff) to `surface_dim` (#d9dadc).

### The "No-Line" Rule
**Explicit Instruction:** Junior designers are prohibited from using 1px solid borders to define sections. Boundaries must be established through:
1.  **Background Shifts:** Transitioning from `surface` to `surface_container_low`.
2.  **Tonal Transitions:** Using padding and margin to let the underlying surface define the edge.

### Surface Hierarchy & Nesting
Treat the UI as a physical stack of premium materials.
*   **Base:** `surface` (#f9f9fb)
*   **Secondary Sectioning:** `surface_container_low` (#f3f3f5)
*   **Active Cards:** `surface_container_lowest` (#ffffff)
*   **Nested Insets:** Use `surface_container_high` (#e8e8ea) for search bars or input areas nested within a white card.

### The "Glass & Gradient" Rule
To inject "soul" into the high-tech aesthetic:
*   **Glassmorphism:** For floating navigation or modal overlays, use `surface` at 70% opacity with a `24px` backdrop-blur. 
*   **Signature Gradients:** Main CTAs should utilize a subtle linear gradient from `primary` (#4800b2) to `primary_container` (#6200ee) at a 135-degree angle. This adds depth that flat hex codes cannot replicate.

---

## 3. Typography
We use a dual-font strategy to balance authority with readability.

*   **Display & Headlines (Plus Jakarta Sans):** A bold, modern sans-serif. Use `display-lg` (3.5rem) with tight tracking (-0.02em) for hero moments. This font carries the "High-Tech" weight of the brand.
*   **Body & Labels (Inter):** A highly legible workhorse. `body-md` (0.875rem) should be the standard for all functional text to ensure the "Accessible" part of our North Star is met.

**Editorial Hierarchy:**
*   **Intentional Contrast:** Pair a `display-sm` headline with a `label-md` uppercase sub-header. The massive jump in scale creates the "Editorial" feel.

---

## 4. Elevation & Depth
In this system, depth is felt, not seen. We avoid the "floating box" look in favor of **Tonal Layering**.

*   **The Layering Principle:** Place a `surface_container_lowest` (Pure White) card on a `surface_container_low` background. The change in hex code provides enough contrast to signify a new layer without a single line of CSS border.
*   **Ambient Shadows:** For elements that must float (Modals, Popovers), use "Atmospheric Shadows":
    *   `box-shadow: 0 12px 40px rgba(26, 28, 29, 0.06);`
    *   The shadow is a tinted version of `on_surface`, creating a natural light-bleed effect.
*   **The "Ghost Border" Fallback:** If accessibility requires a container edge, use `outline_variant` at **15% opacity**. It should be a suggestion of a border, not a boundary.
*   **Roundedness:** Stick to the `md` (0.75rem) token for standard cards. Use `full` (9999px) for pill-shaped buttons to contrast against the structured grid.

---

## 5. Components

### Buttons
*   **Primary:** `primary` background, `on_primary` text. `full` roundedness. Subtle gradient shift on hover.
*   **Secondary:** `secondary_container` background with `on_secondary_container` text. No border.
*   **Tertiary:** Text-only using `primary` color, with a `surface_variant` background appearing only on hover.

### Cards & Lists
*   **The Rule:** No divider lines. Separate list items using `8px` of vertical whitespace and a `surface_container_low` background on the parent container.
*   **Cards:** Use `md` (0.75rem) roundedness and `surface_container_lowest`.

### Input Fields
*   **Styling:** Instead of a boxed border, use a "Soft Inset" look. `surface_container_high` background, `sm` roundedness, and a `Ghost Border` that turns `primary` on focus.
*   **Validation:** Use `error` (#ba1a1a) text for helper messages, but keep the input background neutral to avoid "visual noise."

### Floating Action Elements (Signature Component)
*   Utilize **Glassmorphism** (backdrop-blur) for any element that sits "above" the main content flow, such as a sticky header or a hovering "Chat" bubble.

---

## 6. Do's and Don'ts

### Do
*   **DO** use whitespace as a functional element. If in doubt, add 16px more padding.
*   **DO** use `display-lg` typography for key value propositions, even if it feels "too big" at first.
*   **DO** mix your surface tiers (`low`, `lowest`, `high`) to create a sense of organized architecture.

### Don't
*   **DON'T** use #000000 for text. Always use `on_surface` (#1a1c1d) to maintain a premium, softer look.
*   **DON'T** use 1px solid black or grey borders. Use background color shifts.
*   **DON'T** use standard "drop shadows" with high opacity. If you can see the shadow clearly, it’s too dark.
*   **DON'T** clutter the UI. If a screen feels busy, remove a background container and use typography scale to define the hierarchy instead.