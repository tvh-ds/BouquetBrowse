# Model-call failure diagnostics

New failed model requests retain sanitized metadata in `ModelCall.usage.failure`.
Administrators can retrieve it as `diagnostics` from `GET /v1/admin/model-calls`.
Job errors include a safe category, an HTTP status/allowlisted code when known,
and the receipt ID. Older receipts without metadata return null: this update
cannot reconstruct the cause of a past failure.

Categories distinguish rate limits, exhausted quota, authentication/permission,
unavailable models, invalid requests, provider server/HTTP errors, timeouts,
connections, schema validation, JSON decoding, truncated/refused/incomplete
responses, and otherwise unclassified application errors. Classification follows
SDK exception types and allowlisted structured codes, not message matching.
A category describes the observed failure; it does not prove whether a request
was billed or establish the provider's underlying cause.

Metadata contains only fixed categories/codes, bounded numeric HTTP status,
elapsed milliseconds and optional numeric Retry-After rounded up to seconds
(maximum one day). Unknown codes and date-form Retry-After are omitted. Request
IDs, headers, URLs, credentials, exception messages, validation inputs, response
bodies, captions and generated content are never copied into diagnostics. Logs
contain only receipt ID, category and HTTP status; exception chaining is suppressed
on the sanitized outward error. The admin API revalidates stored diagnostics.

An uncertain attempt remains uncertain, keeps its cost reservation, and requires
explicit admin replay with another reservation. No new automatic retry, request,
model fallback, tracing or external integration is introduced. Removing evidence
in flight prevents diagnostics from recreating its removed receipt data. Failure
metadata expires with the receipt's thirty-day retention, without refunding or
erasing its spending reservation. Deletion continues to scrub receipt usage.

For investigation, inspect the category and HTTP status before authorizing replay:
check account quota for rate limits, credentials/access for authentication errors,
request/model configuration for 4xx failures, and schema/output limits for
validation/truncation. A numeric Retry-After is advisory metadata, not permission
to repeat an uncertain paid request. Live replay remains an explicit operator
action; synthetic tests do not establish current provider availability.

No schema migration is needed: existing private receipt JSON stores metadata.
Existing graph versions, request hashes and cached-call identities are unchanged.
