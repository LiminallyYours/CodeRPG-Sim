# CodeRPG-Sim: under construction

This folder is the simulation fork of CodeRPG: AI characters play the game as players, in rounds, and the owner watches a dashboard. It is being built. Until the referee exists (`PLAN.md`, step 19), **every message is a development request**: answer as a coding assistant, never as a game master, and never narrate.

Read first, in this order: `HANDOFF.md` (where the build stands), `PLAN.md` (the agreed steps), `SIMULATION-FORK-PROPOSAL.md` (the design), `DEVELOPING.md` (invariants, checks, testing).

- Don't play or test in `state/`; use a scratch copy, as `DEVELOPING.md` says.
- Run `sh tools/check.sh` before and after every change; one commit per agreed step.
- Don't push without the owner's say-so.
