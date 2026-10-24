# HANDOFF: the simulation fork

Where the build stands, for whoever picks it up next, human or Claude. Read `PLAN.md` (the agreed steps) and `DEVELOPING.md` (invariants, checks) with it. Update this file at the end of each stage.

## Where things are (2026-10-24)
- **Plan:** `PLAN.md`, phase 1, approved by JW 2026-10-24 with assumptions A, B and C confirmed. Its *Decisions taken* section is the record of the first session's answers; the proposal's sections 10 and 12 carry them too.
- **Done:** stages 0–3, steps 1–14: the `simulation` preset; players in the save (version 10) with `--as`; the cast file; NPCs among several people; the log; rounds and the balanced shuffle; a player's turn (`reply`, `narrate`) and memory with condensing; orders in the log and the stash; `pane` and `brief`; the `player` agent.
- **Next:** step 15: The Thirteenth Stroke's additions (a buyer, work rooms, a cast of three, a second build spot) were put to JW as a list on 2026-10-24; write them only once approved. Then step 16 (`work`, `sell`, `--sim-complete`).
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
- **Steps 11 and 12 were swapped** (memory first, since an order's `asked` entry needs the turn's own words). `reply <id> <file>` and `narrate <id> <file>` read files in `proposals/`, not shell arguments (quotes and apostrophes). In an open round only the player whose turn it is can be acted for (`whose_turn`); referee commands (`REFEREE_COMMANDS`) name the player themselves.
- **The log** is held in memory and written with the save (`flush_log`), so a refused command leaves only its own `refused` command entry. `coins` takes a reason (`COIN_REASONS`); content and generated text name it.
- **Orders** carry ids `o1`, `o2`, ... from `world-brief craft|build`; `asked` carries the player's DO and JOURNAL from this turn. Every built place is its owner's stash in phase 1 (`stash_owner`).
- **The brief opens with "Who you are"** (personality, voice, motivations from the cast entry); the proposal's list left it out. Each round's memory keeps the pane as it stood after the turn ("How things stood after"), as the proposal says; it is the bulk of a brief's size.
- **The `player` agent can't be spawned in the session that created it** (agent files load at session start). It was checked headless instead: `claude -p --agent player --model haiku "<brief>"` in a scratch copy replied in exactly the two parts.
