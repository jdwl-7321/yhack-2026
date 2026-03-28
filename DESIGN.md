# Design System Specification: High-Contrast Terminal

## 1. Overview & Creative North Star

**Creative North Star: "The Obsidian Architect"**
This design system is built for the elite coder. It rejects the soft, bubbly aesthetics of consumer web apps in favor of a "High-Performance Monolith" aesthetic. It draws inspiration from premium IDEs and advanced command-line interfaces, where every pixel serves a functional purpose.

To move beyond a "generic dark mode," this system utilizes **Intentional Asymmetry** and **Rigid Structuralism**. We break the template look by pairing massive, editorial-scale headings with ultra-dense, mono-spaced data clusters. The layout feels like a high-end architectural blueprint: sharp, authoritative, and unapologetically precise.

---

## 2. Colors

The palette is rooted in absolute blacks and deep charcoals to maximize contrast and focus.

### Surface Hierarchy & Nesting
Instead of using borders to define containers, we use **Tonal Layering**. Each "step" in the hierarchy is defined by a specific surface token.
*   **Base Layer:** `surface` (#131314) – Use for the primary background of the application.
*   **Lowered Areas:** `surface_container_lowest` (#0E0E0F) – Use for recessed areas like the code editor gutter or terminal background.
*   **Elevated Components:** `surface_container_high` (#2A2A2B) – Use for floating panels or active state cards.

### The "No-Line" Rule
Prohibit the use of 1px solid borders for sectioning large layout blocks. Instead, define boundaries through background color shifts (e.g., a `surface_container_low` sidebar sitting against a `surface` main content area).

### Signature Textures
*   **Electric Glow:** For primary CTAs, do not use flat colors. Apply a subtle linear gradient from `primary` (#ADC6FF) to `primary_container` (#4D8EFF) at a 135-degree angle. This adds a "backlit" luminosity reminiscent of high-end hardware.
*   **Glassmorphism:** For overlays (modals/tooltips), use `surface_container_highest` at 80% opacity with a `20px` backdrop-blur to maintain the "obsidian" depth.

---

## 3. Typography

The system utilizes a dual-typeface approach to separate "Interface" from "Logic."

*   **UI Interface (Inter):** High-readability sans-serif for navigation, labels, and headlines.
    *   *Editorial Impact:* Use `display-lg` for landing hero sections with `-0.04em` letter spacing to create a tight, professional "masthead" feel.
*   **Code & Data (JetBrains Mono):** For all technical content, test cases, and performance metrics.
    *   *Hierarchy:* Use `label-md` in Mono for metadata (e.g., execution time, memory usage) to reinforce the "terminal" aesthetic.

**Scale Highlight:**
*   **Headline-LG:** `2rem` / Inter / Medium (System navigation & Page Titles)
*   **Body-MD:** `0.875rem` / Inter / Regular (UI descriptions)
*   **Code-Block:** `0.875rem` / JetBrains Mono (The IDE experience)

---

## 4. Elevation & Depth

In this design system, "Depth" is a measure of light emission, not physical height.

*   **The Layering Principle:** Stack surfaces to create focus. A code execution panel should use `surface_container_low`, while the "Submit" action area uses `surface_container`.
*   **Ambient Shadows:** We avoid traditional drop shadows. If an element must float (like a dropdown), use a shadow with a `40px` blur, `0%` spread, and a color derived from `surface_container_lowest` at `40%` opacity. It should look like a soft atmospheric occlusion, not a "shadow."
*   **The "Ghost Border" Fallback:** If a divider is strictly required for accessibility, use the `outline_variant` token at **15% opacity**. This creates a "hairline" suggestion of a border that disappears into the background, maintaining the razor-sharp aesthetic.

---

## 5. Components

### Buttons
*   **Primary:** `0px` radius. Gradient fill (`primary` to `primary_container`). Text is `on_primary` (#002E6A), All-Caps, 700 weight.
*   **Tertiary/Ghost:** No background. `outline` color for text. On hover, background shifts to `surface_container_high`.

### Input Fields
*   **Style:** `surface_container_lowest` background. No border, only a 2px bottom-accent of `outline_variant`.
*   **Focus State:** The bottom accent transitions to `primary` (#ADC6FF) with a subtle outer glow (0px 0px 8px).

### The "Pulse" Chip
Used for test results.
*   **Success:** `secondary_container` background with `secondary` (#4EDEA3) mono-spaced text.
*   **Error:** `error_container` background with `error` (#FFB4AB) mono-spaced text.

### Cards & Lists
*   **Rule:** Forbid the use of divider lines.
*   **Separation:** Use `spacing.8` (2.75rem) of vertical whitespace or a background shift to `surface_container_low` to separate list items.

### Code Editor Fragment
*   **Background:** `surface_container_lowest`.
*   **Gutter:** `surface_dim` background with `on_surface_variant` text for line numbers.

---

## 6. Do's and Don'ts

### Do:
*   **Do** use `0px` border radius for everything. Sharpness is our primary brand signifier.
*   **Do** leverage "JetBrains Mono" for any numerical data or performance stats.
*   **Do** use extreme whitespace (`spacing.20` and `spacing.24`) between major sections to let the high-contrast elements breathe.

### Don't:
*   **Don't** use standard grey shadows. They muddy the deep black aesthetic.
*   **Don't** use rounded corners. Even a 2px radius breaks the "Terminal" immersion.
*   **Don't** use icons with "Fill" states. Stick to 1.5px stroke-based icons to match the thin-border aesthetic.
*   **Don't** use centered layouts for dashboards. Use left-aligned, asymmetrical grids to evoke a sophisticated, "engineered" look.
