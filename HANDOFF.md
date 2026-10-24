# HANDOFF: the simulation fork

Where the build stands, for whoever picks it up next, human or Claude. Read `PLAN.md` (the agreed steps) and `DEVELOPING.md` (invariants, checks) with it. Update this file at the end of each stage.

## Where things are (2026-10-24)
- **Plan:** `PLAN.md`, phase 1, approved by JW 2026-10-24 with assumptions A, B and C confirmed. Its *Decisions taken* section is the record of the first session's answers; the proposal's sections 10 and 12 carry them too.
- **Done:** stage 0, steps 1–4 (the fork's documents, the original's papers removed, development mode, The Thirteenth Stroke in `games/`).
- **Next:** stage 1, step 5 (the `simulation` preset).
- **Git:** commits are local. `origin` must be changed by JW to `https://github.com/LiminallyYours/CodeRPG-Sim.git` (the permission check blocked Claude doing it; the new repository exists and is empty). Don't push until JW asks; check `git remote -v` first.
- **`state/`** still holds JW's real game from the original, including the forged worlds in `state/worlds/`. It's discarded when the fork's `newgame` replaces the save format (step 6); don't test in it.

## Decided along the way
- Claude Code's agent list labels `tools: []` agents "All tools"; a live test (2026-10-24) showed they get only the hand-back tool. Trust the test, not the label.
