#!/usr/bin/env bash
# UserPromptSubmit hook.
# When the user asks to build/implement an OpenSpec change, inject this repo's
# execution-discipline rule so a fresh session uses the superpowers disciplines
# (TDD off the spec scenarios -> verification-before-completion -> code-review
# -> archive) instead of naively checking off tasks.md.
# See CLAUDE.md "Executing an OpenSpec change". No-op for every other prompt.

input="$(cat)"

# Fire only when BOTH a build/implement intent AND an OpenSpec-change signal are present.
intent='(build|implement|execut|begin|start|work on|let.?s build)'
target='openspec|\b[pP][0-3]\b|add-(sveltekit-frontend-foundation|public-observation-browsing|authed-station-management|superuser-frontend-tools)|frontend (rewrite|foundation|change)'

if printf '%s' "$input" | grep -qiE "$intent" \
   && printf '%s' "$input" | grep -qiE "$target"; then
  cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"[Repo rule — executing an OpenSpec change] tasks.md IS the plan; do NOT run writing-plans. Build with the superpowers execution disciplines, not by naively checking off tasks: (1) test-driven-development — turn each spec-delta '#### Scenario' (WHEN/THEN) into a FAILING Playwright/pytest test first, then implement the task that makes it pass; (2) one change in flight, phases in order; (3) verification-before-completion — run the suite and SHOW the output before claiming done: frontend 'npm run lint && npm run check && npm run test' + Playwright, backend 'bash scripts/lint.sh && bash scripts/test.sh' when backend/ is touched, plus 'openspec validate <change-id> --strict'; (4) requesting-code-review before archiving (archiving folds deltas into openspec/specs/); (5) systematic-debugging for failures, subagent-driven-development for independent siblings. P0 (add-sveltekit-frontend-foundation) is a deploy-model spike (nginx-static → Node SSR, localStorage → BFF cookie) — verify it in the real compose stack, not just unit tests. Full rule: CLAUDE.md § 'Executing an OpenSpec change'."}}
JSON
fi
exit 0
