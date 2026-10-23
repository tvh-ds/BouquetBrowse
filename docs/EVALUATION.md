# Evaluation status and protocol

No real labeled pilot dataset, paid model run, live platform response, GPU throughput test or timed recovery exercise was available for this baseline. No domain accuracy, market coverage, production latency or inference-cost target is reported as achieved.

Synthetic fixtures exercise30listings/eightfictionalsellers, repost identity, missing/range/from prices, delivery separation, stale advertisements, insufficient size evidence, seven-other-seller cohorts and explicitly synthetic price histories. Unit/integration tests check deterministic rules and workflow contracts; they do not measure flower recognition.

Before pilot release collect200permittedposts from≥12sellers, label≥300price cases and300identitypairs, and judge40search/referencequeries. Split by seller and product/repost family. Double-label≥20%, especially commercial ambiguity. Record abstention, published coverage, precision/recall intervals and disagreements. Freeze a holdout; preserve error evidence privately and add sanitized regression cases. Measure extraction, association, visual, identity, retrieval and cohort errors separately.

Release targets remain those in BLUEPRINT.md. Commercial price/currency/product association requires review until validated. Measure similarity precision@10 and search nDCG@10 against human judgments, cohort judged relevance, API p95 at stated load, enrichment latency including queue/provider distinction, and actual provider usage/cost per listing. Record model/commit/prompt/schema/dataset versions for every report. A new prompt sounding more fluent is not a promotion criterion.

Next bounded milestone is platform feasibility and permitted real evaluation inputs. Production setup requires Supabase/Meta/model configuration and private infrastructure. The app stays functional with imports and explicit unavailable-capability errors while those dependencies are unresolved.
