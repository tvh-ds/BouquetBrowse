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

## Research administration extension — 29 October 2026

The code-led extension uses the existing Studio shell, botanical identity and native controls. Its direction contract is `.impeccable/surfaces/apps-web-src-app-admin-page-tsx.md`: evidence, release readiness and the next action remain readable together. No approved comp or QUALITYBAR reference was introduced, and no new shipping raster assets were added.

Built artifacts: `apps/web/src/components/research-studio.tsx`, `research-studio.module.css`, `research/*.tsx`, the Research tab in `studio.tsx`, and the optional observed summary in `apps/web/src/app/sellers/[id]/page.tsx`.

### Built controls and flow

| Workspace | Current controls and meaningful states |
| --- | --- |
| Health & alerts | Recurring-collection, publication-gate and monthly-budget summary; versioned incident acknowledgement; process heartbeat freshness, real-data coverage and backup outcomes. Not activated, closed gates, overdue heartbeats, no incidents and empty backup history remain explicit. Health polls every 30 seconds only while its workspace and document are visible. |
| Conversations & images | Capture selection opens messages, reply ancestry, ordering, stop reason, remaining expansions and offers. Disclosures retain identifiers and reply/quote relationships. Offer inspectors show associated private images and roles; image selection adds to the evaluation draft. Unobserved ancestors, expired evidence, unknown expansion counts and no captures have distinct copy. Saved profile details can be removed. |
| Flower taxonomy | Review proposed keys and literal aliases, inspect current vocabulary, approve a new version, reject, or rebase an older proposal. Decisions require a reason and fingerprint. A new label remains visually unvalidated until its benchmark passes; no proposals is an explicit state. |
| Canonical configurations | Select a seller-backed offer, link to a same-seller group or create one, and supply a reviewed-match reason. Accepted links can be revoked with a reason and retained history. Version fingerprints protect decisions; no available seller-backed offers is explicit. Offer identity and listing URLs remain stable. |
| Evaluation & annotations | Select private offer images, author dataset provenance and JSON draft, open a dataset and annotate visible/assessable flower types, split, image family and reference reviewers. Synthetic data is visibly ineligible for real-data gates. Run requires configured model access, PostgreSQL and annotations; completed sets enable proof staging and private JSONL export. Cost and latency appear per image; inference cannot publish listings. |
| Release proofs | Stage independent conversation or mixed-flower reference data, inspect sample/provenance state, per-category holdout precision/recall/support and recorded failures. Null metrics read “Not assessable.” Full reports and configuration identity remain available in a disclosure. Eligible real reports expose permission-reference and joint-review attestation; approved reports expose revocation. Synthetic, under-sampled and target-unmet evidence cannot imply live quality. |

Workspace switching preserves mounted research panels, selection and unsaved forms. Adding an image deduplicates by media ID and opens evaluation; invalid existing draft JSON stays intact with a correction alert. Refresh reloads evidence. Leaving the outer Research tab unmounts research state; there is no persistent draft guarantee. Errors are alerts, success/loading are status messages, and busy submits are disabled.

### Responsive behavior

Desktop retains the Studio tabs, research heading/refresh pair, native workspace selector and adjacent ruled operational rows. At 640px and below, headings and rows stack, three-column summaries and two-column annotation controls become one column, and inspectors reduce their padding. Actions wrap; long source text and identifiers wrap. Proof tables scroll inside their own containers. Private evidence images use contained 4:5 frames. Research buttons and ordinary fields are at least 44px high; checkbox labels retain 44px rows. Existing focus and reduced-motion rules apply.

### Research finish evidence and boundary

The fresh finish reviewer returned **ship**, found all five contract sections present and requested no material fixes. All twelve supplied captures were opened and validated in that finish review, at desktop width 1440px and mobile width 390px:

| Workspace | Desktop | Mobile |
| --- | --- | --- |
| Health | `.impeccable/review/research-health-desktop.png` | `.impeccable/review/research-health-mobile.png` |
| Conversations | `.impeccable/review/research-conversations-desktop.png` | `.impeccable/review/research-conversations-mobile.png` |
| Taxonomy | `.impeccable/review/research-taxonomy-desktop.png` | `.impeccable/review/research-taxonomy-mobile.png` |
| Canonical | `.impeccable/review/research-canonical-desktop.png` | `.impeccable/review/research-canonical-mobile.png` |
| Evaluation | `.impeccable/review/research-evaluation-desktop.png` | `.impeccable/review/research-evaluation-mobile.png` |
| Proofs | `.impeccable/review/research-proofs-desktop.png` | `.impeccable/review/research-proofs-mobile.png` |

The detector returned `[]` in `.impeccable/review/research-detector.json`. Reported verification for this implementation: 197 backend tests passed and two skipped; 22 desktop/mobile end-to-end tests passed; type/lint checks and frontend build passed. These checks verify implementation behavior within their fixtures, not live recognition quality or publication readiness.

The optional seller summary is documented from code only; no seller screenshot was supplied or visually validated. Live Threads collection, paid model evaluations, the twenty-conversation workflow proof, the 100-image mixed-bouquet proof and Windows activation remain deferred by the user. This finish disposition covers the research admin extension and named captures; it does not create visual approval, attest live proofs or activate collection.
