# Rules

How the game works. The numbers live in `balance.json`, and the arithmetic lives in `rpg.py`. This file explains both in plain language. The game master never rolls dice or does damage math in its head. It runs the matching `rpg.py` command and accepts the result.

## The player
- **HP**: health. Reaching 0 means **defeat**, and the game is over until `/newgame`.
- **Might**, **Agility**, **Wits**: small modifiers, usually −1 to +3, added to d20 rolls.
  - Might: strength, force, intimidation, melee attacks, how much you can carry.
  - Agility: speed, stealth, balance, dodging (it raises your defense).
  - Wits: noticing, persuading, recalling, tricking.
- **Coins**: money. Coins can't go below 0.
- Starting values come from the game's world file (`games/<id>/world.md`).

## Skill checks: `check <stat> <dc>`
Use a check when the player tries something whose outcome is uncertain and that matters.

Roll d20 + stat against a difficulty (DC). If the total is at least the DC, the check succeeds.

| DC | name |
|---|---|
| 8 | easy |
| 12 | normal |
| 16 | hard |

A content file may name an exact DC for a specific action, and that DC wins. A natural 20 always succeeds and a natural 1 always fails.

Don't roll for things that are certain, trivial, or impossible. Just narrate those.

## Combat: `attack <character>`
Only characters whose file gives `hp`, `defense`, `attack` and `damage` can be fought. Each `attack` is **one exchange**:
1. **You swing.** Roll d20 + Might against the foe's `defense`. On a hit, roll your equipped weapon's `damage` dice, or 1d2 if you're unarmed. Every hit deals at least 1.
2. **The foe swings back if it's still standing.** It rolls d20 + its `attack` against your defense, which is **10 + Agility**. On a hit, it rolls its `damage` dice.
3. **Critical:** a natural 20 on an attack rolls the damage dice twice.
4. **When a foe reaches 0 HP**, the flag `<id>_defeated` is set automatically. The character's own file says what that means for the story.
5. **Fleeing:** an Agility check (normal DC unless content says otherwise). On a success, `move` away. On a failure, you stay put and the foe gets a free hit on you: `hurt <foe's damage dice>`.

A foe's wounds are kept in state (`npcs`), so they persist if you leave and come back.

## Damage and healing
- `hurt <dice>`: damage from the environment (a fall, a trap) when the content calls for it.
- `heal <dice>`: healing from the story, such as rest or a kind character, when the content calls for it.
- `use <item>`: consumes an item that has a `heal` value. HP never rises above max HP.

## Carrying: `take`, `drop`, `gain`, `lose`, `equip`
- Each item has a `weight`. You can carry up to **8 + 2 × Might** in total.
- `take` and `gain` are refused when they would go over the limit.
- `take` and `drop` move an item between you and the current room. `gain` and `lose` move an item between you and a character (trades and gifts).
- Only items with `damage` can be equipped. Dropping or giving away your equipped weapon leaves you unarmed.

## Movement: `move <direction>`
You can only use exits listed in the room file. An exit with a condition, such as `(if bridge_clear)`, is blocked until that condition holds.

## NPC memory and talk: `remember <character> <line>`
- Each non-minor character keeps a short memory of the player in state: at most `npc.memory_lines` lines (6) of up to `npc.memory_line_chars` characters (160) each. When a new line is added past the limit, the oldest is dropped.
- When two NPC agents talk to each other, at most the owner's `npc_agents.lines_per_exchange` lines (4 in the normal preset) are spoken per turn.

## Flags: `flag set <name>` / `flag unset <name>`
Flags are named facts about what has happened. Content files say when a flag should be set and what changes because of it. The rules don't care what any flag means.

Two kinds of names are automatic and can't be set: `has_<item>` is true while you carry that item, and `met_<character>` is true once you've been in a room with that character. Content conditions can use them like flags.

## A run's variation
- **Seed:** every run has a seed: one the player names, `daily` (today's date, so everyone gets the same world that day), or a new one. Each die is drawn from the game, the seed and how many dice the run has rolled so far, so the same seed rolls the same dice in the same order. Choices made differently, or agents speaking differently, lead to different commands and so to different dice later on.
- **New game:** `newgame` rolls any stats `world.md` lists under `rolls:` and picks one flag from each `variants:` line. It also places starting items whose conditions hold and starts the clock.
- **Moves and the clock:** every `move` is one tick. The clock counts down. When it runs out, its flag is set, plus `also_flag` if `also_if` holds at that moment.
- **Weather** may change every `world.weather_every_moves` moves (5).
- **World turns:** every `world_turns.every_moves` moves in the owner's settings (5 in the normal preset), a world turn falls due, if world turns are on and the meter can pay for one.
- **Encounters:** arriving in a room with `encounters:` rolls the table's chance (e.g. 2 in 6). On a hit, one entry is picked and its effect applied. An entry marked `(once)` happens at most once per run. A `hurt` effect from an encounter can wound but never kill: it leaves you with at least 1 HP.

## Generated content
- The world agent proposes, and `generate.py` decides whether the proposal fits:
  - ids and names are new;
  - descriptions are short;
  - new rooms attach only where the game's growth rule allows (`generation: rooms:` in world.md): `anywhere` means any free way from a room (its `expand:` list if it has one, else north, south, east and west; `expand: no` for none), onto a free map square, up to `generation.max_depth` (2) generated rooms deep; `yes` means only authored rooms' `expand:` directions;
  - no new place lands on another room's map square, or on a build spot's;
  - each room yields at most 1 found item and 2 extras;
  - each run allows at most the owner's `generation.max_per_run` generated entities (16 in the normal preset).
- **Stats come from tiers, never from the proposal.**
  - Items: trinket (weight 1); light_weapon (1d4, weight 1); weapon (1d6, weight 3); tonic (heals 1d4+1, weight 1).
  - Foes: weak (5 HP, defense 9, +0, 1d4); average (8, 11, +1, 1d6); tough (12, 12, +2, 1d8).
  - Generated prices are 1–6 coins, and side-quest rewards at most 4 coins.
- **Side quests** may only use their own `side_<id>_<word>` flags, plus `has_` and `met_` names.
- Everything generated is tagged `made_by: world`; what the player orders is tagged `made_by: player`. Both pass the same checks.

## Things made to order
- A **maker** is a character whose content gives `makes:` (item tiers) and maybe `accepts:` (items taken instead of money).
- **Ordering:** the player describes what they want; `world-brief craft <maker>` (price `craft`, 2) asks the world agent to shape it into one item of a tier the maker makes, or to turn it down if it's outside the trade. `generate craft` checks it and stores it as an unpaid order.
- **Paying:** `pay <id>` takes the tier's price from `generation.craft_price` (trinket 2, light weapon 3, tonic 3, weapon 5), or `pay <id> <item>` takes one item the maker accepts. The item is handed over at once and is the player's own.
- **Limits:** the owner's `crafting.max_per_run` orders per run (2, 5, 10 by preset); orders don't count toward the generation limit, and a game's `generation:` policy doesn't apply to them.

## Earning: paid work and a buyer
- **Paid work:** a room with `work:` pays for a job done there. `work` makes a check (`check` with the room's stat and DC) and, on a success, pays a number of coins rolled in the room's range; a failure pays nothing. Either way it's once per visit: leaving and coming back is a new visit. Pay is at most `work.max_pay` (4) a time.
- **A buyer** (`buys:`) pays a set price per item tier, always below what having one made costs. `sell <item>` (and the buyer's id, if two are here) hands it over for that price. Only things with a tier are bought: made to order, or found. The world's own things have none.
- Every coin earned is logged with its reason: `work` or `sale`.

## The library
- Every generated person, place and thing, and everything the player had made or built, goes into the game's library (`state/library/<game>.json`). Side quests don't: they belong to one run's people. A person keeps their wares, a place what was in it.
- **A new game** brings back the places the player built (at their build spots, if the content still has them) and the people they befriended, where they were, each remembering one line: their last memory of the player, or the job done. Authored characters, flags, inventory and quests reset, so the main quest is whole again.
- **Befriended** means the player finished the side quest that person gave, or that they were promoted.
- **Reuse:** a world brief lists at most `library.brief_entries` (5) fitting world-made entries, those first made where the player is first. A proposal `{"reuse": "<id>"}` brings one back with the same checks as something new; its stats come from today's tiers. It costs 1: the brief's 2, less 1 given back.
- **Size:** at most `library.max_entries` (40) per game. When full, forgotten entries go first, then the least recently seen; the player's places, friends and anything marked for keeping stay.
- **Keeping:** entries the player built, befriended people, and those the game master suggests (`rpg.py library suggest`) are marked worth keeping. Only the owner decides, with `tools/library.py list | keep <id> | forget <id> | unforget <id>`. `keep` writes the entry into the game's folder as authored content (and links it into its room) and validates; if the game no longer validates, nothing changes.

## People who find their own voice
- The game master runs `talk <id>` before voicing a generated person in a scene. It counts at most one conversation per scene (a scene lasts until the player moves).
- After the owner's `promotion.after_conversations` (3 in the normal preset), the person is promoted: `minor: no` for the rest of the run, speaking through their own NPC agent with their own memory of the player. Promotion costs 2 once (price `promote`); the agent's replies are free, like an authored character's.
- Not while promotion is off (thrifty), past `promotion.max_per_run` (2), while the owner has agents off, or when the meter can't pay.
- A promoted person is befriended: they come back in later runs, still speaking for themselves, and `keep` writes them as `minor: no`.

## Places built to order
- A **builder** (`builds: yes`) builds at the build spots (`build:`) of the room they stand in.
- **Ordering:** `world-brief build <builder>` (price `build`, 3); the world agent shapes the player's request into one small, empty place at a build spot, checked like a generated room by `generate build`.
- **Paying:** `pay <id>` takes `generation.build_price` (5), in money only. The place is finished `generation.build_moves` (3) moves later: it joins the world with a way to it, marked `made_by: player`, and a rumor spreads so people start using it.
- **Limits:** the owner's `building.max_per_run` (1, 3, 5 by preset). A newer order for the same spot replaces an unpaid one.

## The meter: what the extras cost
Playing the game as written is free: every game-master turn, every rules command, and the authored characters speaking through their agents. Only extras beyond it have a price, set by the game (`meter.prices` in balance.json): generating something new 2, a world turn 2, having something made 2, having something built 3, bringing something back from the library 1, a person getting their own agent 2. One point is roughly one extra round of game-master work. The game shows the meter as its own resource (lamp oil, power), with a capacity from the owner's settings (30 in the normal preset).
- **Paying:** `world-brief` pays for each generation or world turn after every check that could refuse, so a refused extra costs nothing and a retry pays again.
- **Running low:** at `meter.low_at_percent` (25%) or below, the game warns once.
- **Spent:** when the meter can't pay for an extra, it doesn't happen: nothing new is generated, no `may grow` ways are offered, and no world turns fall due. The game as written plays on, agents included.
- **Refill:** each time Claude Code is opened or resumed in the folder (a SessionStart hook); a `/clear` doesn't refill it. The meter lives in `state/meter.json`, outside every save, so it carries across new games and game switches.

## The owner's switches
Each game's `settings.json` picks a preset from `rules/presets.json` (`thrifty`, `normal`, `rich` or `simulation`) and may override any of its switches:
- `meter.capacity`;
- `npc_agents`: `on` (off: the game master voices everyone), `lines_per_exchange`, and `characters` to switch single characters off;
- `world_turns`: `on` and `every_moves`;
- `generation`: `on`, `max_per_run`, and `kinds` (extras, rooms, items, characters, side_quests). Something is generated only if the game's own `generation:` allows it **and** the switch is on.
- `crafting`: `on` and `max_per_run` (orders placed with makers).
- `building`: `on` and `max_per_run` (places ordered from builders).
- `promotion`: `on`, `max_per_run` and `after_conversations` (generated people getting their own agent).
- `rounds`: `clock` (`move` or `round`: what moves the world's clock), `time_every`, and `max_per_run`, the most rounds a run may have (50 in every preset; 0 for no limit). Raising it lets a stopped run go on.

**A run of rounds** (the simulation) is the owner's to pause or end: `rpg.py run pause`, `run resume`, `run end`, and `run status`. Neither cuts into a round: the round in progress finishes, and the next doesn't start (`round start` refuses). A paused run goes on when resumed; an ended one is closed for good, with a summary in the log, and a new run starts with `newgame`. A run also stops at `rounds.max_per_run`.

`rpg.py settings` and the instant command `/budget` show them. Only the owner changes them, with `tools/settings.py`, which the game master can't run.

## Curses
A game's content may define curses (`curses/<id>.md`). Each changes the words the player types: `reverse_words`, `mirror` (each word spelled backwards), `word_limit <n>` or `suffix "<phrase>"`. A curse is on the player while its `caused_by` condition holds and its `cured_by` doesn't. Both are flag conditions set by content, so a new game always starts uncursed, and every curse has a cure in the same game (`validate` checks that something sets its cure).

A curse changes the story, not the rules: the game master is told what the player meant and resolves that, while everyone in the story hears the words as they came out. `ooc:` messages and slash commands are never cursed. Curses cost nothing from the meter.
