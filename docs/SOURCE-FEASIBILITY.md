# Source capability experiment — not yet established

As of this baseline, no Meta credentials, granted-scope evidence or permitted real pilot dataset has been supplied. **Real records indexed: 0. Real sellers indexed: 0.** Thirty synthetic listings and eight fictional sellers are development fixtures, not coverage results.

| Route | Baseline behavior | External evidence still required |
|---|---|---|
| Operator JSON import | Implemented, validated, idempotent; source-linked review/publication | Operator supplies permitted captions/media and confirms acquisition context |
| Threads keyword_search | Official-host client, explicit configuration and permission gates, request budget, visible job errors | App/token identity, granted threads_keyword_search, actual response fields, approval, quotas/pagination/coverage |
| Instagram business_discovery | Known registered professional handles only; explicit configured Graph version and approval gate | Eligible account setup/token/scopes, professional handle access, actual fields/media access and limits |
| Instagram hashtags | Deferred supplementary adapter | Product-specific approval/coverage case |
| Seller-authorized connections/catalog feeds | V1 | Seller onboarding and authorization |

Disabled clients return capability errors. They never substitute fixtures. Sync imports only known source accounts with operator-confirmed grants and usable timestamps/captions. The initial live clients retrieve a bounded page and record returned checkpoint metadata; exhaustive pagination/backfill and full deleted-post refresh are not certified.

Run the seven-day experiment before claiming live coverage: record app identity/scopes without tokens, test Vietnamese flower/Hanoi queries and known professional handles, record returned/missing fields, media access, page completion, errors and quota headers; repeat daily and annotate price/size evidence. Keep actual payloads private; only manually sanitized contract fixtures belong in Git. No publishing, messaging or comment permissions are needed.

References supplied in the approved plan: [official Threads keyword search](https://www.postman.com/meta/threads/request/34203612-b3b2c12a-7ce6-4d86-a3c6-6d31e3b66ea1), [Instagram Facebook Login](https://www.postman.com/meta/instagram/folder/u4g5a2a/instagram-api-with-facebook-login), [Instagram Login](https://www.postman.com/meta/instagram/folder/6raa77c/instagram-api-with-instagram-login). Recheck current documentation when enabling an adapter; this document makes no quota or eligibility guarantee.
