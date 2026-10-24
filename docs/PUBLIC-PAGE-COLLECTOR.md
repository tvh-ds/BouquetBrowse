# Public post collector

The operator authorized anonymous public web-page collection after the API approval route proved unavailable for the personal pilot. This bounded collector supplements official API adapters and does not mark their permissions approved.

## Workflow

Sign in as admin, open Studio → Import, paste an individual Threads or Instagram post URL, then choose **Collect page & draft**. The server fetches anonymous HTML, reads JSON-LD SocialMediaPosting or Open Graph caption metadata, and fills the existing import editor. Complete seller name/slug, district, missing username, and the original publication timestamp. Verify that the caption is complete and the images belong to the advertised product. Confirm permitted use explicitly, then use Import & queue. The worker extracts commercial claims and the resulting listing remains in the review queue until accepted.

Missing dates remain null. Observation time is never substituted for advertisement time. Seller location is not inferred from a keyword or image. The fixed Hanoi market in the draft is the pilot's import scope and must be checked against the seller, not treated as parsed location evidence. Images are candidates, not verified product associations. HTML captions can be truncated and require source review.

## Boundaries

- Individual `threads.com`/`threads.net` `/@handle/post/ID` and Instagram `/p/ID` or `/reel/ID` URLs only. Threads `/share/CODE` links are resolved through their normal public redirect to a Threads post. No global search, profile crawling, pagination, or video download.
- HTTPS, exact host allowlist, no URL credentials or nonstandard ports, public DNS addresses only. Connections pin the validated IP with original Host/TLS SNI. Environment proxies are disabled.
- At most three HTTP requests including redirects, 15-second request timeout, 2 MB decoded body limit, HTML MIME check, and a shared persisted application allowance of 100 requests/day. No automatic retries for access restrictions.
- Redirects must stay on an allowed host and identify the same platform post. Login/private-network redirects, access challenges, unsupported markup, and oversized responses fail explicitly.
- No account cookies, API tokens, authenticated browser sessions, hidden platform endpoints, script execution, proxy rotation, or challenge solving. The public-page path is distinct from API search approval.
- Preview requires admin authentication through the existing private API proxy and does not persist raw HTML, create listings, or download media. Existing imports retain attributable source/caption snapshots; existing private media validation applies to selected CDN candidates.

JSON-LD is parsed as data, with bounded traversal and ambiguity checks. Multiple post objects or conflicting post identities abstain. Accepted source-ID deduplication and commercial-review gates are unchanged. Real HTML contracts and coverage depend on the source and may fail even for a browser-visible page. Synthetic HTML tests are contract/security tests, not proof of real platform coverage.

## Verification

Live smoke check on 2026-10-24: one operator-supplied Threads share link resolved and yielded a 62-character caption, a seller handle, and one image candidate without credentials. No publication timestamp was exposed, so it remained null. This is a one-post retrieval result, not a coverage or extraction-accuracy claim. No live seller content is committed as a test fixture.

Run the backend suite, frontend check/build, and browser checks. Tests cover anonymous pinned requests, private-address rejection, redirects, source restriction responses, body/MIME limits, malformed and ambiguous metadata, missing facts, admin authorization, and preview → import → worker → review. Live checks use operator-supplied post URLs; keep raw pages and seller data out of Git. Report a source block as a block, not a successful collection.
