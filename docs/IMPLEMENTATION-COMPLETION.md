# Completion audit

The original module deliveries did not finish every detail of the approved Threads plan. The remaining implementation is tracked explicitly here. Real collection, paid inference, annotation and recurring activation remain deferred until the user's live-test command; fixture success does not satisfy those release gates.

| Area | Completion work |
|---|---|
| Seller profiles and discovery | Implemented and merged in PR #12: public business profile evidence, controlled summaries, durable planner queries, yield and independent-seller prioritization. SQLite 178 passed; current-head CI passed including PostgreSQL, browser and clean containers |
| Curation | Backend implemented: immutable proposal/alias promotion, collision rejection, selective reprocessing, reversible same-seller canonical links, general conversation edges/gaps and profile suppression/deletion replay. Admin screens follow in the administration module |
| Evaluation | Durable joint/image-only batch execution, annotation/export and measured receipts |
| Crop retrieval | Immutable reviewed-region embeddings and similarity indexing |
| Administration | Health/proofs, general conversation explorer, taxonomy and canonical controls |
| Operations | Daily backup scheduling, actionable alerts, isolated startup/restore integration |

Each completion module records its validation in its PR and updates this document before merge.
