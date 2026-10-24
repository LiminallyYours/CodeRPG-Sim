# CodeRPG

A text RPG that runs inside Claude Code. Claude is the game master, and you type what you do at the normal prompt.

## How to play
1. Open Claude Code in this folder with the interface mod: `cd CodeRPG && claude --plugin-dir ./mod`. Plain `claude` works too, without the game look.
2. Type `/newgame`. Add a seed to replay a run exactly (`/newgame ember-4821`), or `daily` for today's world, the same for everyone; the title card shows the date and seed. Type `/game` to see the installed games, and `/game <id>` to switch; each game keeps its own save.
3. Type actions in plain English, for example "look around", "go to the tavern", "ask Pell about the troll", "attack the troll".
4. To talk to Claude as a developer instead of the GM, start your message with `ooc:`. Without it, a hook reminds the GM that the message is an in-game action.
5. Instant commands (no Claude turn, no cost): `/inventory`, `/map`, `/sheet` (reopens the margin, the pane beside the story), `/sound` (turns sound effects on or off) and `/budget` (what's left of the meter, what the extras cost, what's switched on, and what the session really used in tokens).

Two games ship on the kit:
- **The Dark Lighthouse** (`dark_lighthouse`): a fishing village with a stolen lamp lens. Six rooms, three characters, six items and one quest with three branches.
- **The Flooded Station** (`flooded_station`): a half-flooded research station and a rising tide. Six rooms, three characters, five items and one quest with two branches. It's deliberately different: its own colors, stat names (Grit, Reflex, Know-how), currency (credits), tab names and a faster world clock, with no time of day.

## Layout
```
CLAUDE.md                     GM role + standing orders (procedure only, no world facts)
.claude/skills/gm-turn/       the turn-by-turn procedure
.claude/skills/newgame/       /newgame
.claude/skills/game/          /game: list the installed games or switch between them
.claude/skills/newworld/      /newworld <a sentence>: a whole new world, forged in the background while you play
.claude/agents/npc.md         the NPC subagent: no tools, sees only the brief it's given
.claude/agents/world.md       the world subagent: proposes new people/places/items/side quests as JSON
.claude/agents/worldsmith.md  the worldsmith (Opus): writes a whole new world into its draft folder, in the background
.claude/hooks/forge_guard.py  the worldsmith's guard: it may write only in its draft and run only the world check
.claude/hooks/session_start.py  refills the meter each time Claude Code is opened here
.claude/settings.json         lets the GM run rules/rpg.py without permission prompts;
                              makes the GM wait for NPC replies (CLAUDE_CODE_FORK_SUBAGENT=0)
games/<id>/                   ONE GAME: everything particular to it lives here
  world.md                    title, start room, starting stats/kit, opening
  rooms/ characters/ items/ quests/ tables/ art/   one file per room, character, item, quest...
  look.json                   its look: colors, stat and tab names, currency, spinner phrases
  balance.json                its rule numbers, laid over the kit's rules/balance.json (optional)
  settings.json               the owner's cost switches: a preset plus overrides
rules/                        THE KIT: knows nothing about any particular game
  RULES.md                    the mechanics in plain language
  WORLD-GUIDE.md              how to write a whole world: every format, and what a complete world needs
  balance.json                every tunable number (the defaults)
  look.default.json           the default look, which each game's look.json changes
  presets.json                the owner's presets: thrifty, normal, rich
  dice.py  content.py  rpg.py the code that rolls dice and does the arithmetic
  generate.py                 checks world-agent proposals and turns them into run content
  png.py                      reads, checks and writes room pictures (standard library only)
  art/terrain/                the kit's pictures for rooms without their own: water, grass, stone, indoors
proposals/                    world-agent JSON waiting to be applied (emptied automatically)
state/save.json               what has happened in the game being played (created by /newgame)
state/shelf/<id>.json         the other games' saves, waiting while you play another
state/active.json             which game is being played
state/meter.json              what's left to spend this session (shared by every game)
state/forge/<draft>/          a new world being written by the worldsmith agent (/newworld)
state/worlds/<id>/            the worlds forged in play: games like those in games/, but yours, not the kit's
mod/                          the Claude Code interface mod (Phase 3), loaded with --plugin-dir
tools/                        check.sh (every automated check), test_rules.py (engine tests), play.py (drive a live session),
                              pictures.py (redraws the shipped room pictures),
                              settings.py (the owner's switches; the GM can't run it), library.py and worlds.py
                              (the owner keeps or forgets library entries and forged worlds)
DEVELOPING.md                 how to work on the game safely: checks, testing, invariants, gotchas
```

## Technical choices
- **Python 3 with the standard library only**, compatible with 3.9. There's nothing to install, and macOS already ships it.
- **Content is Markdown with a small front-matter block.** The front matter holds the data the scripts need, such as exits, items, weights, damage and combat stats. The body holds prose the GM reads, such as descriptions, personality, voice, knowledge, and trades. The front matter is a tiny YAML subset (`key: value`, `- list`, one level of `sub: value`), so it's parsed by about 40 lines of code with no PyYAML dependency.
- **The kit and the games are separate.** `rules/` and `mod/` never name a room, character or item. Each game is a folder in `games/` with its content, its look and its rule numbers. The rules script copies the game's look into the save (`view.look`), so the mod draws each game differently with no code change. The game master reads content only through the rules script, which applies the current flags, so the procedure doesn't depend on where files are: `look` and `move` end with the room's text as it reads now (`ROOM TEXT:`), so a move is one command, and `rpg.py show` reads everything else.
- **State is one JSON file per game**, `state/save.json` for the one being played, now at `"version": 9`. Version 9 added `run.present` (who was in the scene as of the last look or move, so a character a flag has just removed can still speak that turn); version 8 added orders placed with makers and builders (`run.commissions`). Version 7 added `game` (which game the save belongs to) and `view.game` / `view.look`; older saves can't be continued and are replaced by `/newgame`. Earlier versions: version 2 added NPC memory. Version 3 added `map` (the rooms you've visited and their open exits) and `view` (display-ready values recomputed on every save) for the interface. Version 4 added `met` (characters you've seen), each foe's `max_hp`, and people, foes, quests and room art in `view`. Version 5 added `run`: everything about this particular playthrough (rolls, variants, the clock, generated content, notes, the chronicle and rumors). Version 6 gave each run an `id`, so the interface can tell a new game from a continuing one. Only `rpg.py` writes it, and it writes atomically. Switching games moves the current save to `state/shelf/` and brings the other game's back. If the format changes later, add an upgrade function to `MIGRATIONS` in `rpg.py` and saves from version 7 on will upgrade on load.
- **The rules engine is one CLI**, `python3 rules/rpg.py <command>`. Every roll and every change to state goes through it, so outcomes can't be fudged. It prints plain text for the GM to narrate. A `REFUSED:` result means the action didn't happen and state is unchanged.
- **The GM prompt is split.** `CLAUDE.md` holds the short standing orders. The `gm-turn` skill holds the longer procedure. Neither contains any world facts.

## NPC agents (Phase 2)
- **Who gets an agent:** every character whose file says `minor: no` speaks through its own `npc` subagent. Characters marked `minor: yes` (here, Pell and Morwen) are played by the GM directly to save cost. Changing which is which is a one-line edit.
- **What an NPC knows:** `rpg.py npc-brief <id>` builds the NPC's whole world from its character file. That's every section except `## GM only`, plus the `## If` sections that apply now (without the flag names). Then it adds who else is in the scene and the character's **memory of the player**, which is kept in state (`npc_memory`, at most 6 short lines).
- **Each exchange is one fresh, blocking spawn.** The GM passes the brief, the last few lines of the scene, and what just happened. I tested continuing an agent with SendMessage, and it doesn't wait for the reply, so it can't keep turns in sync. A fresh spawn also means the NPC always sees current state.
- **NPCs propose, the GM decides.** The NPC replies with `SAY` / `INTENT` / `REMEMBER`. The GM checks each intent against the character file's `## GM only` rules and applies it with `rpg.py`, or doesn't. If an NPC contradicts state, state wins. NPCs have no tools at all (`tools: []`), and they don't load CLAUDE.md, so they can't touch files.
- **Two agents in one room** can trade lines, up to the owner's `npc_agents.lines_per_exchange` (4 in the normal preset) per turn. In the starter world this happens in the friendly-troll ending, when Grukk and Ysolde are both in Harbor Square.
- **Model:** NPCs run on `sonnet` (set in `.claude/agents/npc.md`). Switch to `haiku` for cheaper, faster, flatter characters.

## What the extras cost: the meter and the switches
Playing the game as written is free. The meter is a budget for the **extras** that go beyond it, shown as an in-world resource: **lamp oil** in the Lighthouse, **power** on the station (each game names and styles its own in `look.json`). It sits in the status band and the pane, warns when it runs low, and refills each time Claude Code is opened in the folder.

| | Price (the game's `balance.json`) | When the meter can't pay |
|---|---|---|
| generating something new (a person, place, item, side quest) | 2 | it doesn't exist; no `may grow` ways are offered |
| a world turn (life going on off-screen, people's plans included) | 2 | none falls due |
| having something made (a maker shapes your order) | 2 | the maker takes no new work |
| having something built (a builder shapes your order) | 3 | the builder takes no new work |
| bringing something back from an earlier game, instead of inventing it | 1 (the brief costs 2; 1 comes back) | |
| a person you keep coming back to getting their own agent (once; their replies are free) | 2 | they stay voiced by the storyteller |
| a side scene between two characters | 2 | it isn't offered |
| a whole new world (`/newworld`) | not on the meter: one costs more than a whole meter, so only the owner's `new_worlds` switch (off in `thrifty`) and the player's confirmation stand in its way | `/newworld` says new worlds are off |
| every game-master turn, every rules command, the authored characters' agents | free | |

One point is roughly one extra round of game-master work (about 10–15k tokens, weighted as the API prices them). Measured on Sonnet, an ordinary turn costs about 30k and an agent's reply about 5k; the turn is the cost of playing at all, so it's never charged. Prices are charged by the rules script where the extra happens (`world-brief`), after every check that could refuse. The owner's switches live in each game's `settings.json`, a preset from `rules/presets.json` with overrides:

| Preset | Meter | NPC agents | World turns | Generation | Crafting | Building | Promotion | Side scenes |
|---|---|---|---|---|---|---|---|---|
| `thrifty` | 10 | off: the GM voices everyone | off (and no plans) | extras, rooms and items only, 6 per run | 2 orders per run | 1 per run | off | off |
| `normal` | 30 | on, 4 lines between two per turn | every 5 moves, with plans | everything the game allows, 16 per run | 5 orders | 3 | 2 per run, after 3 conversations | 2 per run, 6 replies each |
| `rich` | 60 | on, 6 lines | every 4 moves, with plans | everything the game allows, 24 per run | 10 orders | 5 | 4, after 2 | 4, 10 replies |

Change them with `python3 tools/settings.py preset thrifty` or `set npc_agents.characters.grukk false`; `/budget` shows what's in effect. The station overrides one switch: its world turns come every 4 moves.

**What a session really used.** The prices above are estimates. Below them, `/budget` shows what this Claude Code session actually used, in tokens, as the mod counts it from every model request (the game master's and each helper's):
- **per play turn:** seconds, requests and weighted tokens (input + 1.25 × cache writes + 0.1 × cache reads + 5 × output, the API's price ratios), the figures to compare before and after a speed change;
- **by who:** the storyteller, the characters' agents, the world agent and the worldsmith;
- **extras:** points spent, and what a point really cost: the turns that spent points less as many plain turns, per point, set against the 10–15k a point is priced as;
- **plan usage:** how far the session moved the 5-hour and weekly windows, on a subscription;
- **development turns** (`ooc:`), kept out of the play figures;
- **the last 10 sessions**, kept in the mod's own storage, per project folder.

It counts per Claude Code session, as the meter refills, and carries on across `/newgame`. No dollar figure: on a subscription it would only be an estimate. Without the mod there's nothing to count with.

## A different game every run
The authored world is fixed, but each run varies within limits the content sets, and the world can grow during play. This replaced the original rule "never invent anything": nothing is invented freely, but the **world agent** may propose new things that the rules script checks and stores.

| Layer | Who decides | Where it's defined | Where it's kept |
|---|---|---|---|
| **Seed:** every run has one (named, `daily`, or chosen for you); the same seed in the same game rolls the same stats, variants, clock and dice in the same order. What agents say can still differ | `/newgame [seed\|daily]` | | `run.seed`, `run.dice_n` |
| **Rolled character:** stats rolled at `/newgame` | dice | `world.md` `rolls:` | `run.rolls` |
| **Variants:** e.g. what Grukk craves (honey cake or smoked fish), where the cutlass and the spare tonic are | dice pick one flag per line; content branches on the flags | `world.md` `variants:` plus `## If` sections | flags, `run.variants` |
| **Encounters:** a gull steals a coin, a fall, a found tonic | dice, on arriving in a room | `games/<id>/tables/*.md`, linked from rooms by `encounters:` | effects applied; `(once)` entries remembered |
| **The clock:** the fleet comes home after 2d6+12 moves. If the lamp is still dark, `fleet_lost` is set and the quest fails | dice, counting moves | `world.md` `clock:` | `run.clock` |
| **Time and weather:** time follows the clock; the weather changes every few moves | dice | `world.md` `times:` and `weather:` | `run.weather` |
| **Extras:** the unnamed dockhand you try to talk to becomes a real, minor person | world agent proposes, `generate.py` checks | `world.md` `generation:` and `## Public knowledge` | `run.characters` and `run.placements` |
| **New rooms:** wherever the game's growth rule allows: with `rooms: anywhere`, any free way from a room (north, south, east, west, or the room's own `expand:` list), onto a free map square, up to `generation.max_depth` (2) generated rooms deep; with `rooms: yes`, only the `expand:` directions | world agent / checks | `world.md` `generation: rooms:`, room `expand:` | `run.rooms` and `run.exits` |
| **Places you have built:** a builder standing at a build spot (Morwen at the net-loft footing, Bucket at the railing gap) builds what you describe; you pay, it's done a few moves later, and the map marks it ⌂ | world agent shapes it, `generate.py` checks it like a generated room; the price is `balance.json` `build_price` | room `build:`, character `builds:` | `run.commissions`, then `run.rooms` (`made_by: player`) |
| **Items, minor characters and side quests:** stats come from the tier tables, never the agent; side quests use only their own `side_<id>_…` flags and can't touch the main quest | world agent / checks | `balance.json` `generation` | `run.items`, `run.characters`, `run.quests` |
| **Things made to order:** you describe something to a maker (Morwen the net-mender, Bucket the drone); it's shaped within their trade, and once you pay it's yours, marked as made for you | world agent shapes it, `generate.py` checks its tier; the price comes from `balance.json` `craft_price` | character `makes:` and `accepts:` | `run.items` (`made_by: player`), `run.commissions` |
| **The library:** everything generated or player-made goes into the game's library, which lasts across new games. A new game brings back the places you built and the people you befriended (finished their side quest), each friend remembering one line about you; the world reuses a fitting entry (the same dockhand turns up again) rather than inventing one | `rpg.py` records, carries over and reuses; the owner keeps or forgets entries with `tools/library.py` | `balance.json` `library` (`max_entries` 40, `brief_entries` 5) | `state/library/<game>.json`, outside every save |
| **People who find their own voice:** a generated person you keep coming back to (3 conversations in the normal preset, one per scene) is promoted to their own NPC agent with their own memory of you, for the rest of the run and in later runs; the journal marks them ★ | `rpg.py talk` counts and promotes | `settings.json` `promotion` | the person's `minor`/`promoted` in `run.characters`; the library entry |
| **World turns:** every few moves (the owner's `world_turns` setting) the world agent adds rumors and moves generated people around | world agent / checks | `settings.json` | `run.rumors` |
| **People with plans:** on a world turn, each major character the player isn't with may do one thing their file allows: Ysolde walks down to the quay or sleeps with her door barred, Grukk forages on the coast road, Halloran checks her tanks or dozes off, Bucket mops the Control Room. The change sticks until another step undoes it. Close by, the player notices a sign (a sentence in the story and a chime); further off, it becomes a rumor | the world agent picks among the steps open now; `rpg.py` checks and applies them | character `## Plan:` sections; room conditions on the plan flags; `world_turns.plans` | flags, `run.signals`, `run.rumors` |
| **Side scenes:** two agent characters in the same place may play a short scene for fun: Grukk begging Ysolde to let him hold the lens (after the friendly ending), Bucket and Halloran arguing over a puddle (when Bucket's plan brings it up to the Control Room). It starts only if you take it up; each thing you say gets one reply from each, up to the scene's cap; it may end with a coin and always with a line in the chronicle. It never touches the story | `rpg.py scene start\|end` checks and counts; the npc briefs carry it | `games/<id>/scenes/*.md`; `side_scenes` | `run.scenes`, `run.chronicle` |
| **Notes and chronicle:** small details the GM established, and one line per significant event | GM, through `rpg.py note` and `chronicle` | | `run.notes`, `run.chronicle` |

**How generation works:**
1. **Brief:** `rpg.py world-brief <kind>` writes the agent's brief: tone, public knowledge, where you are, every name in use, and the JSON shape.
2. **Proposal:** the `world` agent (no tools) replies with JSON. The GM saves it to `proposals/`.
3. **Check:** `rpg.py generate <kind> <file>` validates the proposal and either refuses it with a reason or stores it.

Generated things are then as real as authored ones for the rest of the run: `look` marks them `[generated]`, and `rpg.py show` prints them like a content file. Each run allows `generation.max_per_run` generated entities in all (16 in the normal preset). An adventure that wants none sets `generation:` to `no`.

## The interface mod (Phase 3)
`mod/` is a Claude Code plugin made of function hooks, written in TypeScript and run by Claude Code itself, with nothing to install. It reads `state/save.json` and the rules script's printed output, and it never writes game files. A *play turn* is any turn that doesn't start with `ooc:` and touches the game. In `ooc:` turns, Claude Code looks normal.

| What you see | How |
|---|---|
| **The page.** Narration is plain prose, 72 columns at most, centered in the space beside the pane (at least 4 in; on a very wide screen without the pane, centered in the first 120 columns, so it stays near the prompt), appearing a paragraph at a time: each fades in dim, then full; any key shows the whole turn. Arriving somewhere puts a rule on top: `──── The Gull · dusk ────`. When someone speaks, their paragraph sits beside a keyline in their color, under their name. Under a turn that changed anything, one dim change line, the record you can trust: `✧ −2 ♥ · +5 coins · gained Brass Lens · ✓ objective · the world grows · Gorse Thicket`. A new game opens with a title card between thin rules, and finishing the quest or falling adds an ending card. | Story text is remembered per session, so resumed sessions show older narration plain. The change line comes from the save as the turn found it and left it, not from the prose. |
| **Dice tray.** Checks, attacks, rolls, damage and healing show as one line each, e.g. `🎲 Might check: d20 16 +1 = 17 vs DC 14 SUCCESS`. Every other plumbing call (rules script, content reads, the turn skill, NPC agents) is hidden. | Parsed from the rules script's output. |
| **In-world chrome.** The waiting line says things like "The fight is on" or "Grukk considers your words" instead of Claude's words, with no timer or token count (beside the pane the band carries it; otherwise the mod draws it at the page's column). The turn timer is hidden, and your own words show dim, after a quiet `› go north`. The hint under the prompt is the game's (`⏎ act · ooc: speak to the builder · ctrl+x tab to the margin · /guide help`), and Claude Code's mode labels on the right are hidden in play. | Claude Code's own hint returns in `ooc:` turns. A mod can't restyle the prompt's `❯` or hide the permission-mode label ("⏵⏵ auto mode on") Claude Code puts in front of the hint. |
| **Status band** above the prompt. Beside the docked pane: `♥ 10`, red or cyan for the turn it changed, and while Claude works, what it's doing (`♥ 10 │ ◌ Reading the room`); the turn's changes are in the change line under the story. Without the pane: `◆ The Gull · ♥ 12 · ◎ 3 · ✦ 28 · ⧗ 14 · dusk · ▸ current objective`. | |
| **The margin**, a pane of six sections under thin labelled rules, no boxes. **Where:** room art, the place, the time and weather as a sentence. **You:** health, the meter and coins as exact numbers with grey bars (amber when the meter runs low, red when health is at a quarter or the meter is spent), any foe under health, and your stats. **At stake:** the clock in segments (red at 3 moves or fewer), every objective still in play, curses. **Act:** exits (keys `1`–`9`) and `look around` (`l`), which put the move in your prompt box for you to send with Enter, and `talk to …` in each speaker's color. **Carrying:** what you have, stacked, with the weight. **More**, pinned at the bottom: `m` map, `j` journal, `g` guide, each taking over the pane (the same key again, `h`, or `‹ back` returns). What the last turn changed stays colored until the next one: health red or the heal color, coins and the meter the heal color or amber, a new item the heal color. **Map:** colored tiles with a legend. **Journal:** quests, the story so far, rumors, and the people you've met. | Docks by itself on terminals 144 or more columns wide (asking for 58 columns); `/sheet` opens it otherwise. Labels and the map and journal keys are each game's (`sections`, `tab_keys`). When the dock is too short, the carried list gives way first (`+3 more · /inventory`), then the art. Buttons take clicks in fullscreen mode, or keys once the pane has focus. |
| **Living world.** The status band and the margin show the clock (`⧗ 14`, red when 3 moves or fewer are left), time and weather. The dice tray shows encounters and "✧ The world grows: …" when something is generated. The Journal adds side quests, failed quests, "The story so far" and "Heard around". Losing the main quest ends with a quieter "THE END" card. | |
| **Feedback.** Routine changes go in the change line. Toasts are kept for what needs attention now and isn't in the story: the resource running low, out or refilled, a curse taking hold, a new world ready. Someone acting on their plan close by gets only a chime, since the story tells it. What changed stays colored in the margin until the next turn, and sound effects play for dice, hits, misses, coins, healing, footsteps, the quest fanfare and defeat. | `/sound` toggles sound, and the setting is remembered. Sounds play through macOS `afplay`. `mod/sounds/generate.py` rebuilds them. |
| **Instant commands:** `/inventory`, `/map`, `/sheet`, `/sound`, `/budget`, `/guide` (how to play, with the keys and commands in the game's own names). | No Claude turn, no cost. |
| **Look and feel.** The title card types itself out and an ending card draws in line by line. In a fight, both health bars share one line, drain and flash, and the damage rises and fades; dice tumble before every result. The map is colored tiles by terrain, with water rippling and your marker blinking. While Claude works, the waiting line says which stage the turn is in, in the game's voice, with a soft chime per stage. The accent color shifts with the time of day. | Animations are surface modules (`reveal.tsx`, `trayfx.tsx`, `tilemap.tsx`) on the terminal's own frame clock (and `page.tsx` for the paragraphs): each plays once, when fresh, and history is drawn still. Each game picks its colors, phrases and sounds in `look.json`. |
| **Curses.** Under a curse, your row shows your words as they came out (✶), the band and the margin name the curse, and characters react to what you actually said; the game master still knows what you meant, so a cursed "go north" still goes north. `ooc:` and slash commands are never cursed. | The prompt hook asks `rpg.py curse-text` and gives the GM both versions; the mod draws your row with a port of the same transforms. |
| **A clean start.** `/newgame`, and `/game <id>` when it switches to another game, first clear the screen and Claude's conversation, so the new game starts lean. The save keeps everything that matters. | The mod runs `/clear` first. Without the mod, nothing is cleared. |

Checks: `sh tools/check.sh` runs everything, including `claude plugin test mod` (99 tests) and `python3 tools/test_rules.py`.

## Content format
```markdown
---
name: Greywater Bridge
exits:
  west: coast_road
  down: trolls_hollow (if grukk_friend or grukk_cowed)
items:
  - brass_lens                  # starting placement only; state tracks it after that
characters:
  - grukk (if not grukk_defeated)
---
Prose description…

## If grukk_defeated
Extra prose shown only when that flag is set.
```
- **Conditions** use `(if flag)`, `not`, `and` and `or`, with `and` binding tighter than `or`. They work on exits, items and characters in front matter, and on `## If …` sections in the body.
- **Characters** with `hp`, `defense`, `attack` and `damage` can be fought. Defeating one sets `<id>_defeated` automatically. `minor: yes|no` decides who plays them. A `## GM only` section holds mechanics the character itself must never see.
- **Items** have a `weight`, plus `damage` (for weapons) or `heal` (for consumables).
- **Flags** are set by the GM only when a content file says so. All branching is written in the content files. Conditions can also use two automatic names: `has_<item>` (carrying it) and `met_<character>` (have seen them).
- **Quests** list their `objectives:` in front matter, each ending `(done when <condition>)`. The journal shows the finished objectives and the current one.
- **Room pictures** are optional: `games/<id>/art/<room id>.png`, shown in the margin's Where section as a mosaic 44 cells wide and 14 rows tall (two pixels to a cell, so 44 x 28 pixels; a picture 4:3 or wider is cropped to that around its middle and averaged down). At most 256 pixels wide and 64 KB, not interlaced. A room without one takes a picture for its terrain: the game's own (`games/<id>/art/terrain/<terrain>-<n>.png`), else the kit's (`rules/art/terrain/`, for water, grass, stone and indoors), always the same one for the same room; with none, a field in the terrain's map colors. `python3 tools/pictures.py` redraws the shipped ones (`--preview sheet.png` shows them all); any can be replaced by a hand-made PNG of the same name. `rpg.py` decodes the picture into the save (`view.picture`), so the interface only ever reads the save.
- **Room art** (text) is optional too: `games/<id>/art/<room id>.txt`, plain text up to about 30 columns, shown where there's no picture (off the terminal).
- **Starting items** in a room may have conditions; they're placed at `/newgame`, after the variants are rolled.
- **Rooms** may also list `expand:` (the directions a generated room may attach in; `no` for none) and `encounters:` (a table id).
- **Build spots:** a room may give `build:`, each direction with what could be built there (`southwest: the bare stone footing of a burned-out net-loft`). Say so in the room's prose, so the player can see it. A build spot is kept for the player: the world never grows onto its map square. A character with `builds: yes` among the room's characters builds there to order; a `## What <she|he|it|they> build(s)` section describes what they build. `validate` checks each spot has a builder and a free map square.
- **Tables** (`games/<id>/tables/<id>.md`) give a `chance:` like `2 in 6` and `entries:`. Each entry may end with `(effect: coins -1 | gain <item> | hurt <dice> | heal <dice> | flag <name> | none)` and `(once)`.
- **Quests** may give `failed_by:` as well as `completed_by:`.
- **Rooms** may give `terrain:` (a kind from the look's `terrain`, e.g. water, grass, stone, indoors; the station adds metal and flooded) and `color:` for their map tile. Generated rooms take a terrain too, or their neighbour's.
- **Curses** (`games/<id>/curses/<id>.md`) give `effect:` (`reverse_words`, `mirror`, `word_limit <n>` or `suffix "<phrase>"`), `caused_by:` and `cured_by:` (conditions), and prose: how it shows, the cure, and a `## GM only` section. A curse is on the player while its cause holds and its cure doesn't, so none survives a new game. `validate` refuses a curse whose cure nothing in the game can bring about. The Dark Lighthouse has the Backwards Tongue (a cracked mirror in the troll's hoard; Pell's salt cures it); the station has Radio Habit (the comms headset; Halloran snaps you out of it).
- **Plans** (major characters only): each `## Plan: <step> (if <condition>)` section in a character file is one thing they may do off-screen, with the lines `does:` (a few words, for the world agent), `sets:` or `clears:` (one of their own flags, `<id>_<word>`), `near:` (what the player notices in or next to the room it happens in) and `rumor:` (what people say otherwise). The rooms do the rest with conditions on those flags: who stands where (`- ysolde (if not lamp_lit and not ysolde_on_quay)`), which ways are barred, and `## If` prose for how a place looks while someone's away. `show` and the NPC's own brief leave plan sections out. `validate` checks that plan flags are the character's own and never the main story's, that each one set can be cleared again, that something outside the file uses it, and that no combination of them puts the character in two rooms at once.
- **Scenes** (`games/<id>/scenes/<id>.md`) give `with:` (two characters with `minor: no`), `where:` (a room both can be in), `when:` (a condition), `reward:` (`none`, or `coins N` up to `balance.json` `scenes.max_reward_coins`, 2) and `chronicle:` (one line), and the sections `## How it starts` (what the GM shows to offer it), `## Premise` (both characters get it), one `## <character id>` each (their part), and `## How it ends` (when it's over and when the reward is earned). A scene sets no flags.
- **Characters** may give `card: #8fae4a`: the paragraphs where they speak are drawn beside a keyline in that color, under their name. Anyone without one takes the next of the look's `speaker_colors`, in the order the player met them. The game master starts a speech paragraph with the speaker's name and a colon (`Pell: "Well now…"`); the interface takes the tag off.
- **Makers** are characters with `makes:` (the item tiers they make to order) and optionally `accepts:` (items they take instead of money). A `## What <she|he|it|they> make(s)` section describes their trade; the world agent reads it when shaping an order. The Lighthouse has Morwen the net-mender on the square; on the station, Bucket makes things from scrap.
- **`look.json`** may set `palette` (`accent`, `good`, `bad`, `warn`, `heal`, and `accent_by_time`, a color per time of day from world.md's `times`), `terrain` (each kind's tile `bg`, `fg`, and `moves` for water), `sounds` (which kit sound each beat plays, or `null`: step, dice, hit, miss, coin, heal, fanfare, defeat, wipe, type, meter_low, and `phase_<reading|considering|shaping|stirring|resolving>`), `stat_labels` and `stat_short` (names for might, agility and wits), `currency`, `tagline` (under the title card), `speaker_colors` (six colors for speakers without a `card:`), `sections` (the margin's six labels: `where`, `you`, `at_stake`, `act`, `carrying`, `more`), `tabs` with `tab_labels` and `tab_keys` (one lowercase letter each, not `l` or `g`, which the margin uses), and `phrases` (`idle`, `by_command`, and `phases`, what the waiting line says in each stage of a turn; `{name}` is who's thinking). Anything left out comes from `rules/look.default.json`. `validate` flags unknown keys.
- **`balance.json`** in a game folder overrides any number in `rules/balance.json`, key by key; `validate` flags unknown keys.
- **Writing a whole world:** `rules/WORLD-GUIDE.md` is the full reference, for human authors and for the worldsmith that forges worlds on request.
- **Checking a game:** `rpg.py validate` checks the kit's games (`--game <id>` any installed one, `--dir <folder>` a draft). Besides references and formats it checks soundness: every flag a condition uses can be set by something (a `flag set` in some file, an encounter's flag effect, a variant, the clock, a plan step, or defeating someone with hp), and every rules command written in content in backticks (`` `lose honey_cake` ``) is a real one naming real things. `--kit-complete` adds what every kit feature needs, which forged worlds must pass and the kit's games do: a full world file, a `look.json` with a palette and a resource, 5–8 rooms all reachable from the start, an encounter table, 3–4 characters (two with agents, one with plans, a maker, a build spot), exactly one quest with two ways through, its endings and *After the ending*, a curse and a side scene.
- **`world.md`** may give `rolls:`, `variants:`, `clock:` (name, moves, flag, and optionally `also_if` / `also_flag`), `weather:`, `times:`, `generation:` (each kind `yes` or `no`; `rooms` may also be `anywhere`), and body sections `## Tone` and `## Public knowledge` for the world agent.

## Changing things
- **Rewrite a world:** edit the files in `games/<id>/`, then run `python3 rules/rpg.py validate` to check every game's references and settings (`--game <id>` for one).
- **Rebalance:** edit a game's `balance.json` (or the kit defaults in `rules/balance.json`), or the stats in a character or item file. `RULES.md` describes the formulas.
- **New game:** add a folder to `games/` with at least a `world.md` and its rooms, run `validate`, then `/game <id>` and `/newgame`.
- **Inspect or debug:** `python3 rules/rpg.py look` shows the current state. Set `RPG_SEED=<n>` to make dice repeatable.
