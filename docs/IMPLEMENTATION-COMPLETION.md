# Completion audit

The original module deliveries did not finish every detail of the approved Threads plan. The remaining implementation is tracked explicitly here. Real collection, paid inference, annotation and recurring activation remain deferred until the user's live-test command; fixture success does not satisfy those release gates.

| Area | Completion work |
|---|---|
| Seller profiles and discovery | Implemented and merged in PR #12: public business profile evidence, controlled summaries, durable planner queries, yield and independent-seller prioritization. SQLite 178 passed; current-head CI passed including PostgreSQL, browser and clean containers |
| Curation | Backend merged in PR #13 after current-head CI: immutable proposal/alias promotion, collision rejection, selective reprocessing, version-fenced same-seller canonical links, general conversation edges/gaps and profile suppression/deletion replay. Admin screens follow in the administration module |
| Evaluation | Implemented durable joint/image-only batch graphs, bounded regional rechecks, pre-inference annotation, private exports, paid-call receipts/costs/latency and proof staging. Real dataset execution remains deferred |
| Crop retrieval | Implemented immutable reviewed-region vectors, pinned encoders, stale-input rejection, catalog similarity selection and deletion. Optional local model weights remain unconfigured |
| Administration | Health/proofs, general conversation explorer, taxonomy and canonical controls |
| Operations | Daily backup scheduling, actionable alerts, isolated startup/restore integration |

Each completion module records its validation in its PR and updates this document before merge.
