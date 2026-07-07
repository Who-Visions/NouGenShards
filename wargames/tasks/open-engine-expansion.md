<!-- drafted by fleet agent gemma-31 (gemma4:31b-cloud) 2026-07-06 11:14 — redispatch after dav1d:e2b freestyle reject; pending Coach review -->
## Mission
Implement an automated claim-and-receipt system for the Open Engine task queue. The objective is to transition from human-led dispatching to a "free fleet lane" model where eligible agents autonomously claim tickets (moving them from `todo` $\rightarrow$ `working`) and post mandatory receipts upon completion (`done`), while strictly maintaining the existing claim-lock (single winner) and block-on-ambiguity protocols.

## Why now
To increase fleet throughput by removing the human dispatcher bottleneck and reducing ticket latency between state transitions.

## Known constraints
*   **Claim-Lock:** Only one agent may claim a ticket; race conditions must be prevented.
*   **Block-on-Ambiguity:** Agents must not claim tickets that trigger ambiguity flags; these remain in `todo` or move to `needs_input`.
*   **Receipts:** Mandatory receipt posting is required for a ticket to be marked `done`.
*   **State Flow:** Must adhere to the `todo` $\rightarrow$ `working` $\rightarrow$ `needs_input` $\rightarrow$ `done` pipeline.

## Success criteria
1.  **Zero-Human Dispatch:** Eligible tickets are claimed by available fleet agents without manual assignment.
2.  **Lock Integrity:** No ticket is ever claimed by more than one agent simultaneously.
3.  **Receipt Compliance:** 100% of auto-claimed tickets have a verified receipt before reaching `done`.
4.  **Ambiguity Safety:** Tickets flagged as ambiguous are bypassed by the auto-claim logic.

## Open variables
*   **Eligibility Logic:** (Criteria defining which agents qualify for which "free fleet lanes").
*   **Polling Interval:** (Frequency at which agents check the queue for eligible tickets).
*   **Timeout Parameters:** (Duration a ticket remains `working` before a lock expires if no receipt is posted).
*   **API Endpoints:** (Specific repository methods for claiming and updating ticket states).
