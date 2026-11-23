#!/bin/zsh
# Land a PR the fleet way on the operator's free GitHub plan, end to end, never bypassing anything:
#   update from main if behind -> LOCAL GATE on the exact PR head (local_gate.sh, result posted on the PR)
#   -> headless non-Claude review -> aiwithdav3 approval only on READY at this head -> merge.
# Private repos: Actions does not run on the free plan and there is no branch protection, so the local gate IS the CI;
# never wait on, re-run or report GitHub Actions there. Public repos also wait on their (free) Actions checks.
#   land_pr.sh <owner/repo> <number>
set -u
setopt NO_NOMATCH
R=$1; N=$2
export PATH="/usr/local/bin:$HOME/.local/bin:$PATH"
OWNER=${R%/*}; NAME=${R#*/}
PRIV=$(gh api repos/$R -q .private)
BR=$(gh pr view $N -R $R --json headRefName -q .headRefName)
BEHIND=$(gh api repos/$R/compare/main...$BR -q .behind_by 2>/dev/null || echo 0)
if [ "${BEHIND:-0}" -gt 0 ]; then gh pr update-branch $N -R $R >/dev/null 2>&1 && echo "#$N updated from main ($BEHIND behind)"; sleep 10; fi
HEAD=$(gh pr view $N -R $R --json headRefOid -q .headRefOid)

# ---- local gate on the PR head, in a throwaway worktree of the local clone (cloned into $TMPDIR if there is none)
WORK=$(mktemp -d); W="$WORK/pr-$N"; CLONE=""
trap '[ -n "$CLONE" ] && git -C "$CLONE" worktree remove --force "$W" >/dev/null 2>&1; rm -rf "$WORK"' EXIT
for d in "$HOME/The Observatory/$NAME" "$HOME/The Observatory/NouGen/$NAME" "$HOME/Phoebus-gates/$NAME" \
         $(find "$HOME/The Observatory" "$HOME/Phoebus-gates" -maxdepth 3 -type d -iname "$NAME" 2>/dev/null); do
  [ -e "$d/.git" ] || continue
  git -C "$d" remote get-url origin 2>/dev/null | grep -qi "$R" && { CLONE=$d; break; }
done
if [ -z "$CLONE" ]; then
  CLONE="$WORK/clone"; gh repo clone $R "$CLONE" -- -q --filter=blob:none || { echo "#$N not merged: could not clone $R"; exit 1; }
fi
git -C "$CLONE" fetch -q origin "pull/$N/head" && git -C "$CLONE" worktree add -q --detach "$W" FETCH_HEAD \
  || { echo "#$N not merged: could not check out the PR head"; exit 1; }
[ "$(git -C "$W" rev-parse HEAD)" = "$HEAD" ] || { echo "#$N not merged: checked-out head is not $HEAD"; exit 1; }
for x in .venv node_modules ts/node_modules; do [ -e "$CLONE/$x" ] && [ ! -e "$W/$x" ] && ln -s "$CLONE/$x" "$W/$x"; done
GATE_OUT=$($HOME/.nougen/bin/local_gate.sh "$W"); GATE=$?
print -r -- "$GATE_OUT"
gh pr comment $N -R $R -b "Local gate on $(hostname -s) at \`${HEAD:0:9}\` (the fleet's CI; GitHub Actions is not used on this plan):
\`\`\`
$GATE_OUT
\`\`\`" >/dev/null 2>&1
[ $GATE -eq 0 ] || { echo "#$N not merged: local gate failed"; exit 1; }

# ---- non-Claude review, then approval on READY at this head
# aiwithdav3 failsafe reviewer: gate + codex/agy/NouGenOpen lanes + NouGenOpen supervisor; approves only on READY.
# Run bun from the PR's temp dir: bun auto-loads any .env in its cwd into process.env,
# and the reviewer's gate inherits it. Run from a workspace whose .env holds live keys,
# the gate's tests read real OPENAI/HF/HUD values (failing 9 tests and printing the
# values into the gate log, 2026-11-23). $WORK has no .env.
RV=$(cd "$WORK" && $HOME/.bun/bin/bun $HOME/.nougen/bin/aiwithdav3_review.ts $R $N 2>&1); RVC=$?
print -r -- "$RV" | tail -3
# The reviewer's own verdict decides: an older approval must not carry a PR past a failed review.
[ $RVC -eq 0 ] || { echo "#$N not merged: aiwithdav3 review did not approve this head"; exit 1; }

# ---- public repos: their Actions checks are free, so wait for them as a second opinion
if [ "$PRIV" = "false" ]; then
  PREV=-1; for i in 1 2 3 4 5 6 7 8; do C=$(gh pr checks $N -R $R 2>/dev/null | wc -l | tr -d ' '); [ "$C" -gt 3 ] && [ "$C" = "$PREV" ] && break; PREV=$C; sleep 30; done
  gh pr checks $N -R $R --watch --interval 30 >/dev/null 2>&1
fi

UNRES=$(gh api graphql -f query="{repository(owner:\"$OWNER\",name:\"$NAME\"){pullRequest(number:$N){reviewThreads(first:50){nodes{isResolved path}}}}}" -q '[.data.repository.pullRequest.reviewThreads.nodes[]|select(.isResolved|not)|.path]|join(",")' 2>/dev/null)
MS=$(gh pr view $N -R $R --json mergeStateStatus -q .mergeStateStatus)
RD=$(gh pr view $N -R $R --json reviewDecision -q .reviewDecision)
OK=0
if [ "$PRIV" = "false" ]; then
  # Never merge without an approval: an empty review decision is not a pass (that is how #1076 merged unreviewed).
  [ "$MS" = "CLEAN" ] && [ "$RD" = "APPROVED" ] && [ -z "$UNRES" ] && OK=1
else
  # No protection exists on a free private repo; red Actions marks there mean "never started". The local gate passed above.
  [ "$RD" = "APPROVED" ] && [ -z "$UNRES" ] && [[ "$MS" != (DIRTY|BLOCKED|BEHIND|DRAFT) ]] && OK=1
fi
if [ $OK -eq 1 ]; then
  gh pr merge $N -R $R --squash --delete-branch --match-head-commit "$HEAD" >/dev/null 2>&1
  echo "#$N $(gh pr view $N -R $R --json state,mergeCommit -q '.state+" "+(.mergeCommit.oid[0:9] // "")')"
else
  echo "#$N not merged: $MS ${RD:-no-review}${UNRES:+ | unresolved threads: $UNRES}"
fi
