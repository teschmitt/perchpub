> **SKELETON — design-first.** These are investigation/decision tasks, not implementation checkboxes. Resolve the open questions in [design.md](./design.md), then rewrite this list as concrete, file-referencing implementation tasks (and flesh out the spec deltas) before building.

## 0. Design spikes (do these first)

- [ ] 0.1 **Revocation spike (Q1, load-bearing).** Prototype short-lived-cert + renewal vs CRL/OCSP against the real step-ca 0.29.0 + Traefik mTLS edge. Decide what "revoke" means at the edge and record the decision in design.md.
- [ ] 0.2 **Rate-limit/quota mechanism (Q2).** Decide middleware vs dependency and Redis-backed vs in-proc; pick concrete limit values; record in design.md.
- [ ] 0.3 **Audit model (Q3).** Decide table vs logs vs both, fields, and retention/PII posture; record in design.md.
- [ ] 0.4 **SPKI-only identity audit (Q4).** Trace every consumer of the presented leaf; confirm none authorizes on CN/SAN; decide where the guard/requirement lands.
- [ ] 0.5 **Capability decomposition (Q5).** Decide final capability split and restructure the spec deltas accordingly.

## 1. Implementation (expand after §0)

- [ ] 1.1 TBD — derive from resolved design decisions, one phase per capability, TDD off the spec scenarios per CLAUDE.md.

## 2. Verify and gate

- [ ] 2.1 `cd backend && bash scripts/lint.sh && bash scripts/test.sh` green.
- [ ] 2.2 `openspec validate harden-enrollment-for-multitenancy --strict` passes.
- [ ] 2.3 `requesting-code-review` before merge; then archive.
