# Discovery operations and journal surface

## Authority and scope

This records the built Threads discovery, evidence and digest UI extension in `apps/web/src`. It is an ordinary code-led extension of the pinned botanical system in [DESIGN.md](../DESIGN.md), not a replacement visual identity or a new token specification. Product truth remains in [PRODUCT.md](../PRODUCT.md), with operating boundaries in [THREADS-DISCOVERY.md](THREADS-DISCOVERY.md) and [BLUEPRINT.md](BLUEPRINT.md). The working surface brief and screenshot review artifacts stay in the operator's ignored local workspace.

The surface separates collection health, evidence quality and automatic-publication eligibility. Its two modes are administrator operation and participant reading of attributable changes. Collection and paid model testing remain deferred until a later explicit command; the UI controls described below are implemented affordances, not evidence of successful live operation.

## Navigation and layout

Authenticated header navigation includes **Nhật ký / Journal**, linking to `/digests`. The existing `/admin` Studio adds **Khám phá Threads / Threads discovery** for administrators. Reviewers retain the review tab without discovery controls. The Studio uses its existing selected forest tabs, ivory canvas, editorial headings, neutral rules and native form controls.

The discovery panel places its heading and Refresh action above Pause/Resume and Run once controls. A three-column definition list reports Collection, Automatic publication and Configuration separately, followed by recent runs, evidence exceptions and expandable frontier/model-call sections. Inspectors open inline beneath their respective lists; closing an inspector leaves the surrounding operational panel in place.

Journal pages use the standard page heading and rule-separated journal rows. `/digests` lists Hanoi calendar dates, partial/closed collection wording and completed/scheduled run counts. Each date and Read digest action opens `/digests/[day]`; the detail route provides a Journal back link, coverage context and change entries. Collection-day closure does not claim full platform coverage.

At widths up to 640px, discovery health fields become one column, heading/action groups and operational rows stack, inspector padding reduces from 1.5rem to 1rem, and row timestamps use 12px text. Action groups and evidence-image links wrap. Long frontier targets and event JSON wrap rather than extending the page. Journal rows also stack below 640px, and change-action links have a 44px minimum height. Header wrapping and small-screen navigation follow the existing system described in DESIGN.md.

## Implemented controls and states

- **Refresh** reloads discovery status, runs, frontier, evidence exceptions and model calls. Initial loading has explicit status text; failures appear as alerts and action results as status messages. Actions share a busy state.
- **Pause/Resume collection** submits the current settings version. **Run once** is disabled while busy, paused, discovery-disabled, model-unconfigured or outside PostgreSQL. The separate Configuration summary additionally checks browser installation. Automatic publication reports Qualified or Release gates closed independently of collection pause state.
- **Recent runs** show state, Hanoi-local creation time and stop reason. Inspect run opens event names, timestamps and structured details inline. Queued/running rows expose Cancel. An empty list explains that setup and direct sign-in precede an explicit test run.
- **Evidence exceptions** show their kind and open an offer inspector. The inspector distinguishes this offer's seller from other accounts, exposes evidence-image links, and requests exact seller-message quotations for offer ownership and Hanoi service. Product-region forms display normalized bounds and accept an optional region-bound price quotation; unknown price remains an available outcome. These forms submit the current evidence fingerprint.
- **Discovery frontier** is a native expandable section showing queue, kind, target, evidence gaps and Hanoi-local due time.
- **Model calls and spending** is a native expandable section showing model, state, amount in USD and attempt. Failed/uncertain calls expose Authorize replay, disabled after authorization or while busy. The panel states that uncertain calls retain their reservation and explicit replay requires a new reservation within the shared limit.

The local-setup copy identifies a dedicated browser requiring direct sign-in, no copied cookies, a 20-minute run limit and a shared $100/month AI ceiling. These are visible operating disclosures; this document does not certify browser authentication, runtime stopping or accounting enforcement.

## Evidence and privacy distinctions

Catalog price labels retain conditional fictional-demo badges. They additionally label provisional extraction and updating state. Cards show compact multi-flower composition; detail pages show the fuller composition list beside the evidence-state messages. Repeated flower/status pairs are collapsed for display. Tentative types expose uncertainty and alternatives; detail composition distinguishes seller-stated types from visual observations. No new visual label establishes inventory or benchmark qualification.

Detail evidence messages distinguish inaccessible source from sold out, an updating listing from its last completed revision, provisional publication from qualified price benchmarks, and partial conversation capture from complete reply coverage. Recreation quotations explicitly identify reference imagery as different from the seller's completed work. Existing seller-contact availability copy remains alongside these states.

Search adds a native multi-select flower field, ANY/ALL matching and Reviewed extraction only. These retain GET/URL state and the existing mobile filter-sheet behavior. Studio review forms accept optional reviewed flower taxonomy keys when a review fingerprint exists; leaving the field empty preserves uncertainty. Extraction review is not confirmation of seller inventory.

The conversation inspector explicitly restricts buyer context to the operational view. Participant change entries display a change category, observed time, optional advertised time and available bouquet, seller and source links. They do not render conversation message text. Supported categories are new offers, advertised-price updates, seller-profile updates and source-access changes. Seller pages reuse this change list when recent changes exist and separately show available seller-stated facts. Source links open in a new tab with `noopener noreferrer`.

## Journal empty and coverage states

The journal index's empty state says that digests appear after a collection day closes, states that live collection is not simulated, and links to bouquet search. A populated index distinguishes partial collection from a closed collection day and displays completed/scheduled runs. The detail page labels partial digests with explicit gaps for sleeping-computer periods and unavailable sources, and names Hanoi time. An empty change list says that the digest has no eligible changes. These states communicate observed coverage without treating an empty result as proof that no seller activity occurred.

## Bounded finish evidence

The supplied, verified captures for this extension are:

| Surface/state | Desktop | Mobile |
| --- | --- | --- |
| Discovery operations, empty/paused | `.impeccable/review/discovery-desktop.png` | `.impeccable/review/discovery-mobile.png` |
| Journal index, empty | `.impeccable/review/digest-desktop.png` | `.impeccable/review/digest-mobile.png` |

The detector result is `[]` in `.data/module15-design-findings.json`. The finish reviewer returned disposition **ship**, with no material findings within the captured empty/paused states and the reviewed code integration. This documentation records that supplied review result; it does not broaden the verdict.

Populated run and conversation inspectors, populated journal index/detail, seller change entries, live collection, paid model execution and end-to-end live publication were not visually certified by these captures. Code inspection establishes the controls and conditional rendering described here, not their behavior with real source data. The review is not a whole-application accessibility, privacy, live-data or product-completeness certification. No new raster asset or global design rule is introduced by this handoff.
