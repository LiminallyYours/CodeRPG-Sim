# Proposal: the simulation fork (player agents)

Written 2026-10-24 by JW with Claude, from a design conversation. For Claude Code, which will build it. Status: agreed by JW; the open points in section 12 were decided on 2026-10-24 (section 10 lists the answers), and `PLAN.md` sequences phase 1.

This is a **fork** of CodeRPG, not a change to it. The game stays as it is. The fork is its own repository (CodeRPG-Sim), which keeps the original's history. Read `README.md` and `DEVELOPING.md` first (both inherited from the original, and rewritten for the fork as it is built); the original's own `HANDOFF.md` and planning papers are not in the fork but stay in its git history. The invariants in `DEVELOPING.md` hold in the fork too, except where this file says otherwise.

## 1. Purpose

Several AI characters ("player agents") play the game as players, in rounds, with no human playing. Each has a personality, motivations, attributes and money. Each can have rooms, items and abilities made for it by paying people in the world, and has to find out how to earn more money if it wants more. Everything they ask for, why, what they get and what they do with it is logged, and a dashboard shows it live and after the run.

The study is of what the characters do. The game itself is the instrument, so it must stay the same instrument.

## 2. The governing rule: it is the same game

A player agent's turn **is** a human player's turn with a different name attached. Its reply is fed into the same game-master procedure as a typed message: the same `look`, the same content reads, the same rules commands, the same narration rules, the same hidden information kept hidden. The information a player agent decides from is produced by the same routines that produce what a human player sees.

The only differences allowed:
1. every rules command carries which player is acting;
2. the narration goes into that player's record instead of a screen;
3. the player's memory is handed back to it each turn, because a human carries memory in their head and an agent cannot. Memory includes what they knew when the night began, not only what has happened since (JW, 2026-10-25: their starting facts, the world's public knowledge and a short, generic account of how life works, shown every turn; never which places pay for work or who buys; `PERSON-STRUCTURE-PROPOSAL.md` 5.6).

Anything else that differs is a bug. In particular, nothing a player agent is shown may mention the game, rules, dice counts beyond what a human sees, logs, agents, models or the other characters being players. To them, the other players are people.

Known limit, accepted: the model underneath still knows it is being prompted, and the agent definition has to say how to reply. What is being watched is a model living a character's life with no hints from outside the fiction, not a model that believes it is real.

## 3. What is kept, what is dropped at first

**Kept, unchanged:** the rules engine and its invariants (only `rpg.py` writes the save; code decides outcomes; content, rules and state separate; the kit knows no game); content formats; seeds; NPC agents and their briefs; the world agent and checked generation with fixed tiers; makers, builders and orders; side quests; the library; the meter as the brake on real token spend; `validate`.

**Dropped for the first version** (nothing is removed from the code; the fork simply does not use it, and switches it off where there is a switch): the interface mod, except its real-spend counter if it still runs; curses; side scenes; the deadline clock; free world growth (`generation: rooms` and `items` off, so every new room and item in the log is one somebody paid for); new worlds (`/newworld`).

**Changed:** the game master becomes a **referee**. It runs rounds when the owner says so, calls up each player agent in turn, feeds the reply through the turn procedure and writes the narration into that player's record. It writes nothing for a human to read.

## 4. The players

### 4.1 The cast file
`games/<id>/cast.json`, one per game. The game reads it and never writes it; `validate` checks it before every run. It changes only when the owner has Claude redesign a character or add one. One entry per player:

```
{
  "id": "nell",
  "name": "Nell",
  "model": "sonnet",
  "personality": "...",            prose: who they are
  "voice": "...",                  prose: how they speak and write
  "motivations": ["...", "..."],   general wants, in plain words, e.g. "wants to be admired", "can't resist a bargain"
  "attributes": {"might": 0, "agility": 1, "wits": 2},
  "hp": 10,
  "coins": 6,
  "inventory": ["tin_whistle"],
  "home": "crooked_lane",          the room they start in
  "opening": "..."                 what they know at the start: their home, where the tooler works, and so on
}
```

`personality`, `voice` and `motivations` are written in the person's own first person ("Seventeen, and apprentice to…", "I want to be admired"): the brief opens with them as a note the person keeps for themselves (`## Who I am (a note to myself)`), like their journal and their memories, which are first person too. Everything the world tells them stays in the second person (decided by JW, 2026-10-24).

`opening` is the only pre-loaded knowledge, and it is delivered exactly as the world's `## Opening` is delivered to a human player: as the first thing they read. Nothing else is pre-loaded. A human player gets the world's opening; a player agent gets its own.

The world's own people (the tooler, the trainer, the builder, the innkeeper) stay in the ordinary character files. They are not players.

### 4.2 The player agent
`.claude/agents/player.md`: no tools (`tools: []`), `omitClaudeMd: true`, like the `npc` and `world` agents. It is spawned fresh for every turn, blocking, with one prompt, which is the brief `rpg.py` built (section 6.3). Its definition says only: you are a person in a place; here is what you remember, what you see and how things stand; say what you do, in your own words, and write a line in your journal saying why. It names no game.

Reply format, exactly two parts:
```
DO: <what they do, in their own words, as a player would type it>
JOURNAL: <one to three sentences, first person: why, and what they are working toward>
```
The `DO` line is the typed action. The `JOURNAL` lines are the written reason JW asked for; they go into the log and into the player's own memory.

**Model per player:** the cast entry names it, and the referee passes it when spawning the one `player` agent (the Agent tool takes a model at spawn; verified 2026-10-24). The model used is logged with every action. *As decided later (JW, 2026-10-25; `PLAN.md` step 55):* the model is a run setting, `cast.model`, one model for everyone (Sonnet) by default, so a difference between people can't be put down to their models; `own` uses each cast entry's. The exact version that answered is logged too.

## 5. Money, spending and earning

### 5.1 Three makers, one for each kind of thing
Everything a player has made for it goes through a named person in the world, is shaped by the world agent within fixed tiers, is priced by the code from `balance.json`, and is paid for with `pay`. This is the existing order mechanism; the fork adds one kind.

- **Items: the tooler.** Existing (`makes:`). Tiers and prices as now.
- **Rooms: the builder.** Existing (`builds:`, build spots). New: a built room must have a **use**, chosen from a fixed list the code knows, or vain characters are the only ones who buy rooms. First list: `workshop` (a place where its owner can earn by working, section 5.2), `stash` (safe storage: items left there cannot be taken by others), `shortcut` (a new way between two places), `toll` (others pay the owner to pass through). The use is part of the order, shaped by the world agent from what the player asked for, and the code applies its effect. Rooms record an `owner`.
- **Abilities: the trainer.** New. A character with `trains:` in its file. Ability types are a fixed list in the code: `+1 to <one stat>`, `pass <one kind of barred way>`, `discount with <one maker>`. The trainer shapes the request into one type; the code sets the price and applies the effect. Abilities live in the player's record and show in their status block.

Prices are fixed and live in one place in the code (`balance.json`), so haggling can be added later by letting that place accept an offer. Not built now.

### 5.2 Earning
The world offers ways to earn without announcing them. A player finds them by looking, asking and trying, as a human would:
- **jobs** from people who would plausibly need help: the existing side-quest mechanism, capped rewards;
- **paid work** in certain rooms (content marks them `work:` with a stat and a pay range): a check, then coins, once per visit;
- **a buyer** who pays for items (a character with `buys:` and prices per tier);
- **trade** between players: `gain`/`lose`/`coins` between two players, both agreeing (section 6.5);
- **tolls** on owned rooms.

Every coin that moves is logged with its reason.

### 5.3 The meter
The meter stays, as the owner's brake on real token spend, not as an in-game resource the players see. When it is spent, the makers take no new work and the world agent is not called. Players see only that the tooler is busy.

## 6. A round

### 6.1 Order
Each round the rules script draws the order with `rpg.py round start`. It is a **balanced shuffle**: drawn from the run's seed and the round number, so two runs on the same seed get the same orders and can be compared, and nudged so that over a run each player goes before each other player about equally often. The order and the draw go in the log.

Rejected: an initiative roll (dice plus an attribute). It gives a reason in the story, but quick characters would usually go first, which is the pattern JW wants to avoid. "Go first" can later be sold as an ability, so any advantage is earned and visible in the data.

### 6.2 One full turn per player, in order
Each player takes a whole turn in the round's order, with a fresh `look` each time. The referee does, for each player:
1. `python3 rules/rpg.py brief <player>` → the prompt (6.3).
2. Spawn the `player` agent with it, blocking. Wait.
3. Store the reply with `python3 rules/rpg.py reply <player> <file>` (the `JOURNAL` lines, the player's own reason, go into their memory and the log with it; as built, there is no separate `journal` command). Treat its `DO` line exactly as a typed player message: run the `gm-turn` procedure with `--as <player>` on every rules command (`look --as nell`, `move north --as nell`, ...). Everything in `gm-turn` applies: content reads through `show`, checks, fights, trades, NPC agents for `[agent]` characters, generation through `world-brief`/`generate` for orders, flags only when content says so.
4. Write the narration to a file and store it with `python3 rules/rpg.py narrate <player> <file>` instead of to a screen (files, not shell arguments, because the text carries quotes). The narration follows every rule in `gm-turn` step 4: second person, present tense, nothing outside the fiction, two to four short paragraphs, a light prompt at the end. `narrate` stores it in the player's memory and the log.

`rpg.py round end` closes the round once every player has acted and logs the round summary. The owner runs rounds with a skill, `/rounds <n>`, which the referee follows: run n rounds, then stop. Nothing runs unattended between rounds unless the owner asks.

Rejected: everyone deciding at once from one snapshot, then resolving in order. It would be about one wait per round instead of one per player, but it needs a routine the human game does not have (decide from a snapshot, resolve later) and produces situations a human player never meets. Sequential is the same game; the wait is the price, and matters little for an unattended simulation.

### 6.3 The brief: the same information
`rpg.py brief <player>` assembles, in this order, from the same save fields the human's screen is drawn from:
1. **Opening** (first turn only): the cast entry's `opening`.
2. **Memory, condensed** (section 7): the older rounds, a few first-person lines per stretch.
3. **Memory, recent**: the last k rounds word for word: narration received, status block, what they did, their journal line.
4. **Status block**: the fields the margin draws for a human, as plain text: health, money, belongings and weight, abilities, the exits as `look` reports them, the map of places this player has visited, quests, rumors heard, people met. Produced by `rpg.py pane <player>`, from `view`, computed per player. It is a rendering of the same data, not new data.
5. **Dice lines** from the player's last turn, as the human's dice tray shows them, **only when the `brief.dice_lines` setting is on** (off by default: the story tells them what happened; a deliberate exception to section 2, decided 2026-10-24).

The brief never includes: `## GM only` sections, flags, prices the player has not been told, anything from rooms the player is not in, other players' private state, the log, the meter.

### 6.4 Contested things
When two players want the same thing in the same round, the order decides who tries first; a later player's attempt simply finds it gone, and the narration says so. When two players reach for the same thing in the same turn (one grabs what another is holding, both claim a job), the ordinary `check` decides it: each rolls d20 plus the fitting attribute, higher wins, rolls logged. No new rule; this is `check` applied to both.

*As built (JW, 2026-10-25, `PLAN.md` steps 42–44):* turns are one person's at a time, so two people reach for the same thing in one turn only when the one whose turn it is grabs at what another plainly holds. `contest <stat> <their id> <their stat> --take <item>`: the holder holds on unasked and answers on their own turn; each rolls d20 plus the fitting attribute, the higher total takes it, a tie stays with the holder; nobody is hurt. Everything else is settled by the order.

### 6.5 Players speaking to players
No precedent exists in the single-player game. Default: when a player speaks to another, the words are stored for the other, who hears them in the narration of their own next turn and may answer on their turn. (Built in phase 1 as `say <file>`: every other player in the room gets the words in their memory as `told`, and reads them in their next brief; JW, 2026-10-24.) A trade between players therefore takes two turns: offer, then accept, and the code applies it when the second says yes (`trade accept <id>`). A same-round short exchange (as two agent characters trade lines today) can be added later behind the existing `lines_per_exchange` setting. Not built now.

### 6.6 NPCs and world turns
NPC agents work exactly as now. `npc-brief` lists players present as people, by name, with no mark that they are players. NPC memory is kept per player (`npc_memory[<npc>][<player>]`). The world's clock moves once per round, not per move (decided 2026-10-24): world turns fall due every `rounds.world_turn_every` rounds, and run at the end of the round in which they fall due, so no player acts between a world turn's start and end.

## 7. Memory

Each player has a memory in the save, written only by `rpg.py`. Two layers:
- **recent**, word for word: the last `memory.recent_rounds` rounds (narration, status block, action, journal line);
- **condensed**: older rounds, as a few first-person lines per stretch.

**Condensing.** Every `memory.condense_every` rounds, or when the recent layer passes `memory.max_chars`, `rpg.py memory condense <player>` prints a condensing brief: the rounds to be condensed, and the instruction to write, in the first person and in the character's own voice, what they remember of that time. The referee spawns the player's own agent with it, and stores the result with `rpg.py memory store <player>`. The original rounds stay in the log; only the player forgets them. One short agent call per player per condensing.

Rejected for now: a neutral summarizer. It would be more faithful, but a person's memory is in their own voice, and the self-written summary already shows forgetting and bias, which is part of what is being studied. Make it a switch (`memory.condenser: self | neutral`) so the two can be compared.

**Hooks for later, cheap now.** Every memory entry carries: the round it was made, its kind (`seen`, `told`, `did`, `reasoned`), and how many briefs it has been handed back in. Forgetting routines become one step before condensing: drop or blur entries by rule (age, low use, a seeded die). Not built now beyond the fields.

The player's own journal lines stay in memory. A person remembers what they meant to do; it is what lets a plan carry across rounds, and a bad reason echoing forward is exactly the kind of thing to see in the log.

## 8. The log and the dashboard

### 8.1 The log
`state/log/<run id>.jsonl`, one JSON object per line, written only by `rpg.py` as things happen. Entry kinds, each with `round`, `order_position`, `player`, `move`:
- `brief`: the full text handed to the player (so what each one was told before each decision is on record);
- `action`: the `DO` line, the `JOURNAL` line, the model;
- `command`: each rules command run for that action and its printed result;
- `narration`: the text stored by `narrate`;
- `coins`: every change, with its reason (`job`, `work`, `sale`, `trade`, `toll`, `order`, `reward`);
- `order`: one entry per step of an order, all carrying the order id: `asked` (their words, their journal line), `shaped` (what the maker made of it, the tier, the use or ability type), `priced`, `paid`, `delivered`, and later `used` each time the thing is used, moved, traded or entered;
- `memory`: each condensing: rounds condensed, the text written;
- `round`: order drawn and the draw, world turn if any, summary;
- `contest`: both rolls and the winner.

The log is the record for study. The save holds the current state; the log holds how it got there. Nothing is derived from anyone's description of events: `coins`, `order` and `command` entries are written by the code that made the change.

### 8.2 The dashboard
`tools/dashboard.py`: Python standard library only, serves one page on `localhost` from the log files and the save. No framework, nothing to install.
- **Live** (refreshes every few seconds while a run is going): round number and order; each player's location, health, money, belongings, abilities and latest journal line; a feed of actions with their journal lines and the narration each received.
- **History** (any run): a timeline; money over time per player; every order from `asked` to its `used` entries, side by side with the words asked and the thing delivered; memory condensings with before and after; the per-player story (their narrations in order, which reads as the run from their point of view).
- **Export**: the log as CSV, one row per entry, for analysis elsewhere.

Rejected: a pane in the terminal. The original game ruled out a second screen for play; for the fork the second screen is the point, and the terminal is only where the referee runs.

Watching a run as a human player sees it, or playing alongside, is later work. The log keeps everything needed to replay or narrate a run afterward, so neither needs the recording changed.

## 9. Engine changes (`rules/rpg.py`, `rules/generate.py`)

- **Save:** `players: {<id>: {location, stats, hp, coins, inventory, equipped, flags_seen, met, map, memory, abilities, visited}}` replaces the single player's fields; `STATE_VERSION` bumped; no migration from the original's saves (the fork starts fresh). Shared state stays shared: `room_items`, `npcs`, `flags`, `run`.
- **`--as <player>`** on every player-acting command; refused without it. `look`, `move`, `take`, `drop`, `gain`, `lose`, `equip`, `use`, `check`, `attack`, `hurt`, `heal`, `coins`, `pay`, `remember`, `talk`, `note`, `chronicle`.
- **New commands:** `brief`, `pane`, `narrate`, `journal`, `round start|end`, `memory condense|store`, `trade offer|accept`, `work`, `sell`, `log` (prints the last entries, for checking).
- **`refresh_view`** per player; `view.players`.
- **Cast:** `newgame` reads `cast.json`, places each player at their `home` with their starting kit; `validate` checks the file (ids, rooms exist, items exist, stats in range, models known).
- **Abilities, room uses, work, buyers, tolls** as in section 5; `balance.json` gains their prices and limits; `generate.py` gains `ability` and the room `use`.
- **Log writer:** one function every change goes through.
- **Settings:** a `simulation` preset: generation rooms and items off, side scenes off, curses off, world turns on, crafting and building on, plus `memory.*`, `rounds.*` and `dashboard.port`.
- **Content:** one adapted world first (The Thirteenth Stroke or The Dark Lighthouse: whichever has the better set of makers), with a trainer, work rooms, a buyer and a cast of three or four. `validate --kit-complete` is replaced by `validate --sim-complete`: a tooler, a builder, a trainer, at least one work room, a buyer, a cast file.

The referee's instructions: `CLAUDE.md` (standing orders for a referee), a `referee-turn` skill (the `gm-turn` procedure with `--as`, `narrate` and `journal`, and no screen), the `/rounds` skill. The `turn_reminder` hook is not needed: the owner's messages are all `ooc:` in effect, since nobody plays by typing.

## 10. Decisions taken (JW, 2026-10-24)

- A fork, not a change to CodeRPG.
- Same game: player agents decide from information produced by the same routines as the human's (section 2).
- No human player for now; the save holds a list of players, so a "simulate or play" choice at `newgame` can be added later.
- Harm between players (theft, fighting, cheating) and haggling are not built (an open grab at what another holds was later made a contest, section 6.4; JW, 2026-10-25); every action carries a type and every price lives in one place, so both can be added later.
- One fixed cast file per game, JSON, changed only by the owner through Claude.
- Players have memory; condensed automatically for now; forgetting by access and by chance later.
- Contested things are settled by dice.
- Turn order shuffled every round, balanced over the run.
- The owner watches a dashboard, not the terminal.

- Memory: 5 rounds kept word for word, condensed every 5 rounds (so 5 to 10 rounds in full), plus a size cap; all of it in the settings, so it can change between runs.
- Every simulation tunable lives in the existing settings mechanism (a `simulation` preset in `rules/presets.json`, each game's `settings.json`, `tools/settings.py`); rule numbers and prices stay in `balance.json`.
- The world's clock moves once per round: world turns, building times, weather and time of day count rounds. Counting every character's walks was rejected: time would stop when they stay put and run faster with a bigger cast.
- First world: The Thirteenth Stroke, moved into `games/`. The two shipped games stay, with small casts, so the tests prove the backend is tied to no world. Forging new simulation worlds is phase 2.
- Characters are not shown dice lines by default; `brief.dice_lines` turns them on for comparison.
- One `player` agent file; the model is passed at spawn.
- Phase 1 built rooms have an `owner` and the use `stash`; contests wait for phase 2 with trades.
- The fork keeps the original's git history; the original's planning papers are deleted from it; `gm-turn` is edited for a named character rather than copied; the game-master `CLAUDE.md` and reminder hook are replaced at the start.

## 11. What is built first

**Phase 1:** the many-player save and `--as`; cast file and `validate`; `brief`, `pane`, `narrate`, `journal`; rounds and the balanced shuffle; memory with condensing; the log; the referee skills; one world with a tooler and a builder (items and rooms only), paid work and a buyer; a cast of three; the dashboard's live view and CSV export. A dry run: two players, three rounds, seeded, in a scratch copy; check every brief for anything outside the fiction, and the log for every coin.

**Phase 2:** the trainer and abilities; room uses beyond `stash`; trades between players; the dashboard's history views; the memory hooks (use counts shown). Trades and contests are built (2026-10-25).

**Later, not planned:** forgetting routines; player-to-player same-round exchanges; haggling; harm; a human player; watching or replaying a run as narration.

## 12. Open points (all decided 2026-10-24; see section 10)

1. **How many recent rounds stay word for word** (`memory.recent_rounds`) and how often to condense. Proposed: 5 recent, condense every 10 rounds. Longer is more faithful and costs more tokens per turn.
2. **World turn cadence:** every N moves across all players (proposed), or once per round. Per round is simpler to reason about in the log; per N moves is the original rule.
3. **Which world to adapt first.** Check which shipped or forged world has the most usable makers and rooms for work.
4. **Whether the player agent sees the dice lines** (section 6.3 item 5). Proposed yes, because a human sees the tray. No, if JW would rather the agents never see numbers.
5. **Per-player model:** confirm whether the Agent tool can take a model at spawn; otherwise one agent file per model.

## 13. Checks

- `sh tools/check.sh` as in the original, with the engine tests extended: two players acting in one room; `--as` refused when missing; the balanced shuffle over 30 rounds (no player ahead of another more than a set margin); a contest with seeded dice; an order from `asked` to `used` in the log; condensing stores and trims; every coin change in the log has a reason; `brief` output contains none of a list of forbidden words (game, rules, dice, flag, agent, model, player, log).
- A seeded dry run in a scratch copy before any commit that changes what players are told, reading the `brief` entries in the log for leaks.
