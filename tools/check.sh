#!/bin/sh
# Every automated check, from the project root:  sh tools/check.sh [--docs] [--snapshot]
#   --docs      only the content and the compile, for a change to the top-level documents alone (PLAN.md, HANDOFF.md,
#               the proposals...; never CLAUDE.md, the referee's standing orders): refused if anything else has changed
#   --snapshot  check a copy of the project as it stands now (without .git and state/), so editing can go on meanwhile
# The engine tests run in parallel (tools/test_rules.py --jobs 8). The type-check needs mod/tsconfig.json, which
# Claude Code writes the first time it loads the mod (any `claude --plugin-dir ./mod` session); it downloads
# TypeScript through npx on first use.
set -e
cd "$(dirname "$0")/.."
docs=; snapshot=
for a in "$@"; do
  case $a in
    --docs) docs=1 ;;
    --snapshot) snapshot=1 ;;
    *) echo "usage: sh tools/check.sh [--docs] [--snapshot]"; exit 2 ;;
  esac
done
if [ -n "$docs" ] && [ -z "$CHECK_DOCS_GATED" ]; then
  others=$(git status --porcelain --untracked-files=all | cut -c4- | awk '!/^[^\/]+\.md$/ || $0 == "CLAUDE.md"')
  if [ -n "$others" ]; then
    echo "--docs is only for changes to the top-level documents (not CLAUDE.md); these have changed too:"
    echo "$others"
    exit 1
  fi
fi
if [ -n "$snapshot" ]; then
  tmp=$(mktemp -d "${TMPDIR:-/tmp}/check-snapshot.XXXXXX")
  tar -cf - --exclude=./.git --exclude=./state . | tar -xf - -C "$tmp"
  echo "== snapshot: $tmp"
  status=0
  CHECK_DOCS_GATED=1 sh "$tmp/tools/check.sh" ${docs:+--docs} || status=$?
  rm -rf "$tmp"
  exit $status
fi
echo "== content";        python3 rules/rpg.py validate   # every game in games/
echo "== python";         python3 -m py_compile rules/*.py && rm -rf rules/__pycache__ && echo "compiles"
if [ -n "$docs" ]; then
  echo "== docs only: the engine tests and the mod's checks skipped (only top-level documents changed)"
  echo "OK"
  exit 0
fi
echo "== rules: tests";   out=$(python3 tools/test_rules.py -q --jobs 8 2>&1) || { echo "$out"; exit 1; }; echo "$out" | tail -1
echo "== mod: validate";  claude plugin validate mod | grep -E "✔|✘"
echo "== mod: tests";     claude plugin test mod | tail -2
echo "== mod: types";     npx -y -p typescript@5.6.3 tsc -p mod && echo "types ok"
