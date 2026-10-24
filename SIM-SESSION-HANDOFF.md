# Handoff: starting the simulation fork (CodeRPG-Sim)

Written 2026-10-24 by JW with Claude. For the first Claude Code session in the fork. Read this file first, then `SIMULATION-FORK-PROPOSAL.md`, then the original's `README.md` and `DEVELOPING.md`.

## What this is
`CodeRPG-Sim/` is a copy of the CodeRPG folder, made by JW on 2026-10-24, to become a separate game: several AI characters play the game as players, in rounds, with no human playing, and the owner watches a dashboard built from the logs. The full design is `SIMULATION-FORK-PROPOSAL.md`. It is agreed in principle; its section 12 lists the points still open, and section 10 the decisions already taken, which are not to be reopened.

The original game in `CodeRPG/` stays as it is. Nothing done here goes back to it.

## Things to know about the copy before touching anything
- **The copied `.git` still points at the original's GitHub repository** (`origin` = LiminallyYours/CodeRPG). Do not push anywhere until JW has created the fork's own repository and changed `origin`. Ask JW for the new repository's address; until then, commit locally only.
- **`CLAUDE.md` still makes every session the game master**, and the `UserPromptSubmit` hook adds an "in-game action" reminder to every message without `ooc:`. Until `CLAUDE.md` and the hook are replaced (an early task below), JW starts every message with `ooc:`, and this session is development throughout.
- **`state/` holds JW's real game from the original** (`save.json`, `shelf/`, `library/`, `meter.json`, `worlds/`). Don't play in it or test in it. The fork's save format replaces the original's with no migration (proposal section 9), so this state is discarded when the fork's `newgame` is built; until then, test in scratch copies as `DEVELOPING.md` says.
- **The planning documents from the original** (`HANDOFF.md`, `NEXT-PLAN.md`, `IMPLEMENTATION-PLAN.md`, `NEWSTAGEIDEAS*.md`, `UI-REDESIGN-*`, `ABOUT-v2.md`, `docs/`, `tempshots/`, `tempdocs/`) describe the original's history, not this fork. Propose what to do with them (move under one folder as a record, or delete) and wait for JW's answer. This file and the proposal are the fork's own documents; `README.md` and `DEVELOPING.md` are to be rewritten for the fork as the build goes, not at the start.
- **`sh tools/check.sh` should pass as copied.** Run it first and report.

## The first session's jobs, in order
1. **Read** this file, the proposal, `README.md`, `DEVELOPING.md`. Run `sh tools/check.sh` and `git status -sb`. Report both in a few lines.
2. **Confirm the technical checks the proposal depends on** (read-only, no changes):
   - whether the Agent tool can take a model when spawning a subagent (proposal 4.2 and open point 5);
   - that `tools: []` and `omitClaudeMd: true` still work for a tool-less agent (they did in the original);
   - how much of `rpg.py` assumes one player (`state["location"]`, `state["inventory"]`, `state["stats"]` and the like), as a count and a short list of the functions involved, to size the many-player change.
3. **Propose the open points** (proposal section 12), one at a time or together, each stated from scratch in plain language with no assumption that JW remembers the project's internals: the question, the options, what each means now and later, and a recommendation. Wait for JW's answers. Don't build before they're answered.
4. **Propose the housekeeping**: the fork's name and repository, what to do with the original's planning documents, and the replacement of `CLAUDE.md`, the `gm-turn` skill and the hooks with the referee's (proposal section 9, last paragraph). Wait for answers.
5. **Write `PLAN.md`** for phase 1 (proposal section 11) from the answers: the sequence of changes, each small enough for one commit, with the checks each needs. JW approves it before building starts.
6. **Build phase 1** following the plan, one commit per agreed change, checks before and after, a seeded dry run in a scratch copy before any commit that changes what players are told. Keep a `HANDOFF.md` for the fork current at the end of each stage, in the shape of the original's: where things stand, what was decided, what's next.

## How JW works (keep to these)
- Replies short, in everyday language, needing little knowledge of the project's internals.
- Every decision put to JW is stated from scratch: the question, the options, and each option's immediate and later consequences. No jargon.
- Build only what was asked for. If something extra seems worth adding, ask first.
- Targeted changes with the reasons given, not wholesale rewrites.
- A finding JW counters is withdrawn or reworked, not defended.
- In documents meant to be read by later sessions: direct, specific, plain; say what must exist or happen, why, and why alternatives were rejected; don't over-talk it.
- The invariants in `DEVELOPING.md` hold in the fork: only `rpg.py` writes the save; code decides outcomes; content, rules and state stay separate; agents propose, the referee checks and applies; the kit names no particular game.
- Visible machinery is always a bug. In the fork that means: nothing a player agent is shown may mention the game, rules, logs, agents, models or the other characters being players (proposal section 2).
