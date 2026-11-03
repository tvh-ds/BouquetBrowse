# Recent-search-only pilot

The operator temporarily narrowed Threads discovery to keyword post search with
Recent ordering. Select `DISCOVERY_MODE=recent_search` in the private root .env
and restart API/browser workers. New .env examples select this mode; the library
fallback remains `full` for compatibility. The admin discovery status exposes
the configured mode, and each new discovery execution pins it. Changing mode
requires a new run. Graph behavior advances to `threads-graphs-v12`; old paused
runs must not be resumed with changed behavior.

Only due search frontiers in the discovery queue can start a task. Existing FYP,
profile and standalone-post/refresh entries are preserved but ignored, and new
profile/post frontier entries are not added in this mode. Within a task the
controller may search, open observed post/reply permalinks, expand replies, scroll,
return through its own history, and finish. Profile visits, FYP/home navigation
and sort-changing actions are excluded from both menus and controller execution.
Seller facts explicitly stated in captured posts remain usable; profile browsing
and its enrichment wait until broader discovery is explicitly restored.

Search URLs retain their Hanoi flower query and `filter=recent`. Before capture
or planning, the rendered page must expose exactly one active search tab for
that query, visibly labelled Recent (or a supported localized equivalent), whose
link also specifies `filter=recent`. A URL parameter alone is not confirmation.
Unknown, Top or conflicting selection fails explicitly as `search_sort_unverified`.
Confirmed ordering is recorded on captures; post reply sorting remains whatever
the UI exposes. Layout changes do not silently fall back to Top or FYP.

Recent is a platform ordering, not proof of a publication date, a fixed time
window, complete coverage, inventory, or current price. Commercial recency and
publication/benchmark gates remain unchanged. The mode does not solve provider
quotas or broad page-change detection, and does not enable recurring work or
publication. Shared spending reservations and explicit uncertain-call replay
requirements still apply. No browser cookies are copied and no access challenges
are bypassed.

Synthetic tests cover preserved/excluded frontier entries, pinned mode, closed
navigation/menu scope, visible Recent verification and rejection of URL-only,
wrong-query or unselected indicators. A bounded read of the signed-in live search
UI confirmed that its Recent link currently uses `aria-current="page"` and
`filter=recent`; this establishes the observed control, not end-to-end quality.

Recent-search navigation in threads-graphs-v13 is deterministic: open unseen issued posts in result order, expand replies at most once per post URL, return to results, and scroll when no unseen target remains. Existing action, stale-page and no-yield limits still apply. Manual recent-search runs do not need a model key; downstream bouquet interpretation remains separately model-dependent. No uncertain provider call is replayed by this change.
