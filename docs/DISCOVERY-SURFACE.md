# Discovery surface brief

## Authority and scope

Mode: **Operate**. Hanoi flower buyers discover attributable bouquets, narrow results and compare configurations before contacting the original seller. The approved quiet botanical direction and original tagline come from PRODUCT.md; DESIGN.md records the current built system. No approved comp exists. This is a code-led implementation preserving the original direction.

Primary artifact: `apps/web/src`. Discovery is the principal surface; comparison and admin captures check continuity of the same visual language. Product truth and scope remain in PRODUCT.md and docs/BLUEPRINT.md.

## Built surface contract

Desktop starts with brand/navigation, research-session context, editorial discovery heading, search and a featured bouquet; catalog filters and photo-led results follow. The featured photo disappears below 600px so phones prioritize search and two-column results. Catalog imagery remains 4:5. Essential mobile catalog metadata is 12px; card compare/detail actions and tray clear controls are 44×44px.

Filters remain inline above 640px. On phones the filter trigger opens a native modal bottom sheet with focus containment, Escape, close control and backdrop dismissal. Search/filter values submit through GET forms to the URL. Persistent comparison selection supports four items. Removal on `/compare` changes stored selection, the URL and the visible column; clearing opens the empty state.

Fictional records retain their own conditional demo badges adjacent to price evidence on discovery, detail and comparison surfaces. Session context alone cannot establish whether an individual listing is fictional. Benchmarks have separate conditional demonstration notices. Recommendations and qualified benchmarks remain distinct.

## Bounded finish evidence

Review captures supplied for this finish pass:

| Surface | Desktop | Mobile |
| --- | --- | --- |
| Discovery | `.impeccable/review/desktop.png` | `.impeccable/review/mobile.png` |
| Comparison | `.impeccable/review/compare-desktop.png` | `.impeccable/review/compare-mobile.png` |
| Admin | `.impeccable/review/admin-desktop.png` | `.impeccable/review/admin-mobile.png` |

The detector ran once and returned `[]` (`.impeccable/review/detector.json`). The fresh finish reviewer returned **pass**, with disposition **ship**, for the four listed fixes: conditional per-item demo labels, comparison removal updating URL and rendered column, essential mobile metadata size, and the named touch targets. All four were resolved within that review's scope and six screenshots.

This disposition applies to those fixes and captures. It is not a whole-app visual, accessibility, live-data, or product-completeness assertion. No new product scope or visual approval is recorded by this document.
