# Threads discovery, bouquet understanding and digest

Approved 29 October 2026. This document supersedes older API-only Threads acquisition and universal-review publication assumptions. Implementation status is tracked below; acceptance targets are not measured results.

## Architecture and evidence

Embed LangGraph Python core in the existing worker package. Application jobs own scheduling, cancellation, heartbeat/fencing and budgets. A discovery graph captures conversations and dispatches independently checkpointed per-offer graphs. Application tables own evidence, identities, claims, call receipts, spending and catalog revisions; compact PostgreSQL checkpoints own continuation. No managed agent server, Redis or external tracing by default.

One global source-message identity has immutable text/media versions and reply/quote edges. Each capture records the observed subset, sorting, remaining expansions and stop reason. Neutral accounts may later acquire an evidence-backed seller link; buyer accounts are not seller profiles. Missing ancestors are unresolved references, not invented messages. Unknown publication dates remain null.

Offer occurrences use stable advertising-account/message/slot identities, not flower labels. Reposts stay distinct. Canonical configuration links require same-seller explicit product evidence or reviewed matching. Images alone never establish identity. Claims preserve seller applicability/publication time separately from system observation/correction time. Quotes anchor to an exact immutable message version with server-computed Unicode-code-point offsets. Shared association conflicts quarantine affected offers without blocking unrelated sellers.

## Workflow

The bounded browser controller exposes search, profile/post navigation, reading, reply expansion, available sorting, scrolling and return. The planner selects observation-versioned semantic handles; arbitrary model-generated scripts/selectors/navigation are forbidden. Use a dedicated persistent Chromium profile with direct user login, never copied cookies. Authentication/access challenges pause collection. External text is untrusted data; no social actions or private-message collection.

Capture seller-rooted posts and sellers' offer branches under buyer requests. Commercial claims need structural/explicit product binding; cross-branch semantic guesses stay candidates. Typed buyer-question/seller-confirmation derivations require an unambiguous proposition and both source versions. Recreation quotations are separate offers with labeled reference imagery. Generic/text-only advertisements enrich profiles/digests, not image-backed catalog bouquets. Collage product splits require review; analysis crops within one bouquet do not create offers.

Joint image/conversation recognition produces per-type florist composition. SigLIP features/label scoring are auxiliary until validated. Whole-image/multi-view analysis may trigger targeted crops and one stronger recheck. Non-detection is not absence; seller statements and visual observations remain distinct. No image-derived prices, exact visual counts, inventory/freshness claims or invented historical data. Version all taxonomy, association, model, prompt and media/crop dependencies. Taxonomy proposals require review. Use controlled bilingual descriptions.

After release gates, provisional offers can publish automatically with resolved seller/image/location evidence and explicit uncertainty. Clear provisional advertised prices participate in browsing/history but not benchmarks. Keep the completed revision visible while updating; suspend benchmark eligibility and reject stale commits. Mixed-flower comparisons require reviewed composition/size equivalence. Recreation quotations are initially ineligible. Existing seller balancing, sample suppression and price-independent cohorts remain mandatory.

Digests project durable catalog-change events into Hanoi-day snapshots after the final run. Missed days produce explicitly partial snapshots at startup; late enrichment belongs to the next digest. Include source links and actual observation/publication times, never buyer dossiers or inferred seller ratings.

## Defaults and recovery

- Starts: 06:00, 10:00, 14:00, 18:00, 22:00 Asia/Ho_Chi_Minh; twenty minutes each including planning; no sleep wake-up or burst catch-up.
- Browsing: 40% refresh, 40% search/profile discovery, 20% FYP; unused allocation spills. 120 browser actions/twenty planner decisions per run. Unresolved conversations next eligible run, active offers daily, established profiles weekly; thirty-day advertisement window.
- Roles: scheduler, one exclusive browser worker, one offer worker. Two-minute job leases, thirty-second heartbeats and fenced writes. External calls outside transactions; durable capture steps and semantic resume.
- Shared AI ceiling $100/month; total operations ceiling $200. Discovery inference $0.35/run, offer processing $0.10/offer; global reservations override local allowances. Planner gpt-6.1-sol, routine interpretation gpt-6-luna, bounded stronger checks; recognition support determined by evaluation.
- At most four images/call, two original-image chunks and one targeted recheck within budget. Explicit truncation. Media must be prepared before image analysis is considered complete.
- Durable call receipts precede dispatch. Completed results are reusable. Uncertain dispatched calls retain reservations and need explicit replay; job retry cannot repeat them silently. Domain/checkpoint writes are separately recoverable through receipts and idempotency.
- Pin graph behavior/prompt/schema/taxonomy/model configuration per execution. Resume compatible code or explicitly migrate; never replay paid work blindly after upgrades.
- Retention: raw/necessary buyer context thirty days, media ninety days, minimal permitted accepted facts twelve months, logs thirty days. Source policy/deletion overrides. Delete derived quotes, crops, vectors, checkpoints, digests and caches; restore replays deletion records. Expired evidence cannot continue supporting eligibility.

## Delivery and release gates

| Module | State |
|---|---|
| 10 Conversation foundation | Implemented: schema, contracts, commands, legacy migration and 12 regression tests; no live collection yet |
| 11 Durable runtime | Implemented with synthetic tests: fenced leases, durable model receipts, compact LangGraph workflows and private PostgreSQL checkpointer setup; no live browser/offer graph services enabled yet |
| 12 Threads browser discovery | Implemented with synthetic Chromium tests: bounded controller, visible-UI adapters, durable frontier/captures, dedicated login, authenticated admin APIs. Collector access/coverage with the dedicated profile remains unvalidated |
| 13 Conversation offers | Implemented with synthetic conversations: independent offer graphs, seller/ancestor price binding, exact quote validation, confirmation derivations, private exceptions and atomic revision receipts. Publication remains gated; no live quality claim |
| 14 Mixed-flower recognition | Implemented with synthetic/fake-provider tests: joint multi-view recognition, per-type composition/counts, targeted crops and one stronger recheck, auxiliary SigLIP scoring, dependency caches and offline benchmark tooling. Real 100-image results wait for the user's live-test command; visual categories remain tentative |
| 15 Catalog, profiles, digests | Planned |
| 16 Real pilot validation | Planned; no measured quality claims |
| 17 Local recurring operation | Planned; recurring publication disabled until gates pass |

Use ten seller-rooted and ten buyer-request real conversations, jointly reviewed once. Require zero wrong-seller publication, unsupported commercial binding or fabricated commercial claims; ambiguous cases must abstain. Benchmark 100 distinct mixed-bouquet images, approximately 60 development/40 holdout split by seller/image family, with 20% double review. Report joint and image-only precision/recall, uncertainty, abstention, latency and cost separately. A supported category targets >=95% observed precision and >=80% recall, with >=20 positive/20 negative examples overall and >=10 each in holdout; otherwise tentative. Evaluation identities cannot publish. Retain commercial challenge and retrieval/cohort tests.

Every module follows branch/test/push/PR/attach/current-head CI/diff review/squash merge. Only fictional/sanitized fixtures enter Git. Real captures, annotations, browser profiles and exports stay private. Capabilities, quality and live coverage must be reported separately from implementation and fixture tests.

The user deferred live sign-in, model keys and paid/live tests until an explicit later command. Continue implementation and synthetic CI with placeholders; do not start live collection during this delivery.
