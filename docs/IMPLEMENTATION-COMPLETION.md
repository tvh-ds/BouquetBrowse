# Completion audit

The original module deliveries did not finish every detail of the approved Threads plan. The remaining implementation is tracked explicitly here. Real collection, paid inference, annotation and recurring activation remain deferred until the user's live-test command; fixture success does not satisfy those release gates.

| Area | Completion work |
|---|---|
| Seller profiles and discovery | Implemented and merged in PR #12: public business profile evidence, controlled summaries, durable planner queries, yield and independent-seller prioritization. SQLite 178 passed; current-head CI passed including PostgreSQL, browser and clean containers |
| Curation | Backend merged in PR #13 after current-head CI: immutable proposal/alias promotion, collision rejection, selective reprocessing, version-fenced same-seller canonical links, general conversation edges/gaps and profile suppression/deletion replay. Admin screens follow in the administration module |
| Evaluation | Merged in PR #14 after current-head CI: durable joint/image-only batch graphs, bounded regional rechecks, pre-inference annotation, private exports, paid-call receipts/costs/latency and proof staging. Real dataset execution remains deferred |
| Crop retrieval | Merged in PR #14: immutable reviewed-region vectors, pinned encoders, stale-input rejection, catalog similarity selection and deletion. Optional local model weights remain unconfigured |
| Administration | Implemented research workspace: health/alerts and spending, general conversation/branch/image explorer, saved-profile removal, versioned taxonomy decisions/rebase, reversible seller-bounded canonical links, private evaluation drafts/annotations/exports and audited proof review. All data stays behind existing admin authorization |
| Operations | Merged in PR #15: daily native backups, separate current deletion ledger, local/in-app alert delivery, ownership-checked startup management, and synthetic PostgreSQL restore/Windows lifecycle integration. Activation remains disabled |

Each completion module records its validation in its PR and updates this document before merge.

## Implementation boundary

All planned non-live implementation paths now have code, operator controls and synthetic verification. This includes separate discovery/offer/evaluation graphs, persistent evidence and frontier, conservative offer/price associations, multi-label recognition with bounded regional checks, composition-aware catalog and comparisons, seller facts, daily digests, release proofs, local scheduling, retention, backups and deletion replay. Existing listing URLs and private application access remain intact.

The following remain intentionally pending the user's live-test command, rather than marked complete: dedicated Threads login and real-page compatibility/coverage; production model credentials/optional local weights; the jointly reviewed twenty-conversation proof; the real 100-image benchmark and measured quality/cost/latency; a restore exercise against the user's actual PostgreSQL/media; and enabling startup, collection or automatic provisional publication. No synthetic result grants release approval. Cloud/Instagram automation and the earlier blueprint's V1/later features remain outside this approved local Threads delivery.

The completion branch validates backend, generated contracts, type/lint/build and all desktop/mobile flows. Current-head CI additionally tests PostgreSQL migrations, native PostgreSQL dump/restore plus later-deletion replay, mocked Windows task lifecycle and clean containers. The native restore fixture is deliberately tiny and does not establish production recovery time or recovery-point objectives.
