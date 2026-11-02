# Planner reliability

The discovery planner now selects a candidate ID from a controller-owned menu.
Each candidate resolves to a complete action, target and optional curated Hanoi
flower query. The model cannot pair an action with another candidate's target.
The provider receives a per-observation enum schema; application membership and
the controller's current-observation/target checks remain authoritative. Page
text and descriptions are untrusted evidence, not instructions.

The planner receives up to twelve retained message versions, attributed account
roles (including unresolved), observed reply/quote edges, commercial excerpts up
to 1,000 characters per message, the task objective, evidence gaps, sorting and
remaining expansions, six recent action outcomes, deadline, decision allowance
and ledger budget headroom. Roles and missing ancestry are not inferred here.
Excerpts help browsing only; commercial extraction still uses original evidence.
Screenshots remain the existing bounded fallback, not general desktop control.

Code chooses frontier tasks, follows known URLs, filters redundant navigation,
finishes when no menu alternatives remain and defers a task after three steps
without new message versions or eight task steps. Known queries form search
candidates; this module does not generate unrestricted new search phrases.

Invalid target selections and changed-page observations persist as `rejected`
and `skipped` receipts respectively, together with a fresh capture. They do not
increment executed-action counts. The graph processes that capture, then replans
with the failure code. One corrective decision is permitted before deferring the
task. At most three corrective decisions per run are available; further failures
defer their tasks immediately. Deferral produces an execution event and schedules
the frontier for its next eligible check. Other tasks can continue within the
existing twenty-decision, 120-action, time and spending ceilings. A valid action
resets the consecutive-failure counter. A rejected `finish` cannot finish a task.

Completed, rejected and skipped receipts are terminal for their observation.
Domain commit followed by checkpoint failure resumes from the receipt rather
than repeating the browser action. Corrective request identities include their
semantic feedback/menu/history; changing only an observation UUID or deadline
cannot bypass an uncertain paid receipt. Every new request still reserves funds.
Malformed/refused/timed-out model calls remain uncertain and require explicit
admin replay. Login/access failures, cancellations, lease loss and takedowns do
not enter automatic corrective recovery. No arbitrary fallback clicks occur.

Graph behavior is `threads-graphs-v11`; new discovery commands pin
`discovery-menu-v2`. Old interrupted executions require compatible code or an
explicit new command/reprocessing, rather than silently changing behavior.
Existing release proofs do not qualify the changed execution configuration.

Synthetic tests cover menu serialization through the actual Groq SDK using a
mock HTTP transport, invalid membership, stable uncertain-call identity, one-shot
recovery, repeated-failure deferral, accurate counters, and restart after a domain
commit before checkpointing. These establish engineering behavior, not real
Threads coverage or flower-recognition quality. Recurring collection and
automatic publication remain disabled until their independent release gates.
