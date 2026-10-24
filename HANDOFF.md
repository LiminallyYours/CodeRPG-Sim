# HANDOFF: the simulation fork

Where the build stands, for whoever picks it up next, human or Claude. Read `PLAN.md` (the agreed steps) and `DEVELOPING.md` (invariants, checks) with it. Update this file at the end of each stage.

## Where things are (2026-10-24)
- **Plan:** `PLAN.md`, phase 1, approved by JW 2026-10-24 with assumptions A, B and C confirmed. Its *Decisions taken* section is the record of the first session's answers; the proposal's sections 10 and 12 carry them too.
- **Done:** stage 0 (steps 1–4) and stage 1 (steps 5–8): the `simulation` preset; players in the save (version 10) with `--as`; the cast file; NPCs that see the players as people and remember each separately.
- **Next:** stage 2, step 9 (the log).
- **Git:** commits are local. `origin` must be changed by JW to `https://github.com/LiminallyYours/CodeRPG-Sim.git` (the permission check blocked Claude doing it; the new repository exists and is empty). Don't push until JW asks; check `git remote -v` first.
- **`state/`** still holds JW's real game from the original, including the forged worlds in `state/worlds/`. It's discarded when the fork's `newgame` replaces the save format (step 6); don't test in it.

## Decided along the way
- Claude Code's agent list labels `tools: []` agents "All tools"; a live test (2026-10-24) showed they get only the hand-back tool. Trust the test, not the label.
- **Step 5 as built:** what moves the world's clock is a setting, `rounds.clock` (`move` or `round`), and the existing `world_turns.every_moves` counts ticks (rounds in the simulation preset, where it is 2). `PLAN.md` was updated to say so. `clock.on` and `curses.on` are enforced; `memory.*`, `brief.dice_lines` and `dashboard.port` are stored for later steps.
- **Step 6–7, how the engine knows who acts:** `ACTOR` (from `--as`, taken from any position in `main()`) and `me(state)`, the acting player's record; `with acting(pid):` reads the save as another player (the view, NPC briefs, finished side quests). Commands about the installed games (`WORLD_COMMANDS`: game, validate, settings, meter, forge) ignore `--as`; `newgame` and `game switch` end with the first player's look.
- **Cast entries may leave out** attributes and hp, coins, belongings and the weapon in hand; those then come from `world.md`'s starting character (rolled as before). Each shipped game's first cast member does this, so its seeded tests keep their dice. The Thirteenth Stroke's two-person cast is a **placeholder** until step 15.
- **The test helper** `rpg()` acts as the save's first player unless told otherwise (`as_="corin"`, or `as_=False` for none).
- **The `npc` agent's instructions** no longer say "the player" (they say "the person talking to you"): with several people present it was ambiguous, and it marked who was a player. Its dry run (step 8, Ysolde with Wren and Corin, two real spawns) kept the two apart and stayed in character.
- **Not yet per player** (later steps): world turns and plans still read the scene from the acting player only (step 10); `signals` are shared; the mod's type file lags the version 10 save (the mod is unused).
