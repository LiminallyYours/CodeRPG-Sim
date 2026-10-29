# Writing a CodeRPG world

How to write a whole game for the kit: every file, its format, and what `validate --kit-complete` requires. It's for anyone authoring a world, and it's the worldsmith agent's reference when it forges one from a player's sentence. The kit's own games in `games/` are worked examples of everything here: read them for tone and structure, not to copy.

A world is played by a game master (Claude) who knows **only what the files say**, plus a rules script that does every roll and keeps the save. So a world is mostly careful writing: what each place looks like, what each person knows and wants, and exactly what happens, in which commands, when the player does the things the story allows.

## The shape of a world

One folder:
```
world.md                  title, start, the player's stats and kit, variants, the clock, tone, opening
look.json                 its look: colours, the meter's name and icon, stat names, money, terrain tiles, phrases
balance.json              (optional) rule numbers that differ from rules/balance.json
rooms/<id>.md             one file per place (5 to 8)
characters/<id>.md        one file per person or creature (3 or 4)
items/<id>.md             one file per thing that can be carried
quests/<id>.md            the one main quest
tables/<id>.md            encounter tables: small things that can happen on arrival
curses/<id>.md            at least one curse with a cure
scenes/<id>.md            at least one side scene between two characters with their own agents
```
Nothing else: no other files, no subfolders beyond these, no room art or pictures, and no `settings.json` (installing the world writes it). Rooms take the kit's pictures for their terrain, so where a kit terrain fits (`water`, `grass`, `stone`, `indoors`), use its name; a terrain of the world's own is drawn as a field in its map colors. Each file at most 20,000 characters; most are a tenth of that.

**Scale:** small. About six places a few steps apart, three or four people, one problem to solve in an hour of play, with at least two different ways to solve it. A clock that makes it urgent. Ordinary people with wants, not chosen ones; small places, not empires.

## The file format

Every content file is Markdown with front matter between two `---` lines:
```markdown
---
name: The Old Mill
exits:
  east: village_green
  up: mill_loft (if ladder_mended)
items:
  - flour_sack
characters:
  - miller (if not miller_asleep)
terrain: indoors
---
Prose the game master reads…

## If miller_asleep
More prose, used only while that condition holds.
```
- **Front matter is a tiny YAML subset**, nothing more: `key: value`; `key:` followed by `  - item` lines (a list); or `key:` followed by `  sub: value` lines (one level of map). No quotes needed, no nesting deeper than one level, no lists of maps, no multi-line values. A line starting with `#` is a comment. Whole numbers become numbers; everything else is text.
- **Ids** are lowercase letters, digits and underscores, starting with a letter (`mill_loft`). A file's name is its id: `rooms/mill_loft.md`. Ids are what everything refers to.
- **Flags** are named facts about what has happened (`ladder_mended`), lowercase with underscores. Nothing is a flag until some file says to set it (`flag set ladder_mended`). Two kinds of name are automatic and never set: `has_<item>` (the player carries it) and `met_<character>` (the player has been in a room with them). A place with `rent:` also gives `let_<room>`, true for everyone while it's let to someone.
- **Conditions** end a value as `(if …)`: `(if a)`, `(if not a)`, `(if a and not b)`, `(if a or b and c)`. `and` binds tighter than `or`; there are no brackets. They work on exits, room items, room characters and a board's notices, and on body sections headed `## If <condition>`; a room's paid work takes one as its own `if:` line (paid work there only while it holds). A room with `board: yes` has a notice board: people put up notices there (`post`), and so may the world's off-screen turn, one at a time; everyone there reads them. A room with a board may list `notices:`, put up by its townsfolk from the start (each `- <text>`, signed in the text, at most 160 characters, with an optional `(if …)`); each shows only while its condition holds, and none can be taken down. Write conditions on flags something really sets (see *Soundness*).
- **Body sections** start with `## `. Sections the kit knows by name are listed below for each kind; `## If …` sections show only while their condition holds; `## GM only` holds mechanics a character must never see; anything else is prose.

## world.md

```markdown
---
title: The Old Mill
start_room: village_green
stats:
  max_hp: 10
  might: 1
  agility: 1
  wits: 1
rolls:
  max_hp: 2d3+8
  might: 1d2
  agility: 1d3-1
  wits: 1d3-1
coins: 3
inventory:
  - walking_stick
equipped: walking_stick
variants:
  hiding_place: key_in_well, key_under_stone
clock:
  name: The flood comes down the valley
  moves: 2d6+10
  flag: flood_came
  also_if: not sluice_open
  also_flag: mill_drowned
weather:
  - rain hammering on the roofs
  - a grey, dripping calm
times:
  - evening
  - night
generation:
  extras: yes
  rooms: anywhere
  items: yes
  characters: yes
  side_quests: yes
---
# The Old Mill

## Who the player is
One or two sentences: who they are, why they're here, what they carry.

## Opening
What the game master narrates first: where the player stands and what's wrong.

## Tone
The world's feel in a few sentences, and what doesn't belong in it. Generated additions follow this.

## Public knowledge
- Things everyone here knows, one per line. Generated people may repeat these.
```
- `stats` are the defaults; `rolls` (dice like `1d3-1`) replace them each new game. Stats are small: −1 to +3. `max_hp` around 10.
- `coins` the player starts with (3 or 4); `inventory` item ids (each needs a file); `equipped` one of them with `damage`.
- `variants`: each line picks one of its comma-separated flags at random at each new game, so runs differ (where a key is hidden, what a character craves). At least two flags per line, and use the flags in conditions.
- `clock`: counts down one per move; when `moves` (dice) run out, `flag` is set, plus `also_flag` if `also_if` holds then. This is the deadline; the quest's failure usually hangs on it.
- `weather`: a list of short phrases; `times` (optional): a list of times of day the clock moves through.
- `generation`: what may be created during play. Each of `extras`, `items`, `characters`, `side_quests` is `yes` or `no`; `rooms` is `anywhere` (the world may grow from any room in a free direction), `yes` (only where rooms list `expand:`), or `no`.
- The four body sections are required: `## Who the player is`, `## Opening`, `## Tone`, `## Public knowledge`.
- Optional: `## Who may arrive`, for a world with days that lets the world's off-screen turn bring someone new, at most one a day: who may come, and who never. Without it, no one arrives that way.

## look.json

How the interface draws this world. Required: a `palette` and a `resource`; everything else falls back to the kit's defaults in `rules/look.default.json` (read it for every key and default).
```json
{
  "palette": { "accent": "#c98f4a", "warn": "#e0b84f", "heal": "#7fdc9a" },
  "resource": { "name": "Lamp oil", "icon": "✦", "low": "Your lamp gutters.", "spent": "Your lamp is out. The world goes quiet until you return." },
  "stat_labels": { "might": "Strength", "agility": "Nimbleness", "wits": "Cunning" },
  "stat_short": { "might": "STR", "agility": "NIM", "wits": "CUN" },
  "currency": "pennies",
  "tagline": "a CodeRPG adventure",
  "terrain": { "mud": { "bg": "#4a3b26", "fg": "#e8d8b8", "moves": false } }
}
```
- Colours are `#rrggbb`. `resource` is the in-world name for the session's budget of extras: something that runs out and comes back (lamp oil, breath, nerve). `low` and `spent` are one sentence each, in the world's voice.
- `terrain`: each room's `terrain:` must be a kind here or in the defaults (`water`, `grass`, `stone`, `indoors`). Add your own kinds with `bg`, `fg` and `moves` (true for water that ripples on the map).
- Optional: `phrases` (`idle`: a few short in-world lines shown while the game master thinks), `tab_labels` and `tab_keys` (renaming the margin's map and journal screens and the key back to the margin, each one lowercase letter other than `l` and `g`), `sections` (the margin's six labels: `where`, `you`, `at_stake`, `act`, `carrying`, `more`), `sounds` (only names from the kit's bank in `mod/sounds/`). Unknown keys are rejected.

## Rooms

```markdown
---
name: Village Green
exits:
  north: old_mill
  east: river_path
  west: chapel (if not chapel_locked)
items:
  - rope_coil
  - copper_key (if key_under_stone)
characters:
  - baker
  - miller (if miller_on_green)
expand: south
build:
  southeast: an empty plot by the duck pond, staked out but never built on
encounters: green_events
terrain: grass
---
Two or three short paragraphs: what the player sees, hears and smells; who is here; every way out, in words ("To the north, the mill's wheel turns slowly").

## If chapel_locked
The chapel door is shut, a heavy padlock on its hasp.

## Details
- Things the player might examine, each with what happens: "The well: a Wits check (`check wits 12`) spots a key glinting far down. On a failure, only dark water."
```
- **Exits** map a direction to a room id, with an optional condition (the way is blocked until it holds). Write every exit both ways: if the green's north is the mill, the mill's south is the green. Directions: north, south, east, west, up, down, northeast, northwest, southeast, southwest, in, out.
- **The map** is a grid laid out from the start room through the exits: north/up one square up, south/down one down, east and west sideways, the diagonals diagonally (in and out aren't drawn). Two rooms may not land on the same square, so lay the world out on a small grid first.
- **items** are what lies here at the start of each game (with conditions, decided when the game starts; a variant flag can choose where something is). **characters** stand here while their condition holds. Every place a character can be is a room listing them with a condition; at any moment a character should be in at most one room.
- **expand** (optional): the directions a generated room may attach here, or `no`. Use `no` on rooms that must stay closed (a cave, a vault). Don't name an existing exit.
- **build** (optional): each direction with what could be built there. The prose must mention the spot. A builder (`builds: yes`) must be among the room's characters, the direction must not be an exit or an expand direction, and its map square must be free.
- **encounters** (optional): a table id. **terrain** (required): a terrain kind.
- **## If** sections describe the room under conditions. **## Details** (optional, any name) lists things to examine and their exact mechanics.

## Characters

```markdown
---
name: Hester Crane
role: the miller, who hasn't slept since the dam cracked
minor: no
card: #b89a6e
---
## Personality
Two or three sentences.

## How she speaks
Voice, habits, what she calls the player.

## What she knows
- Facts, one per line. Only what she would know. This is everything she can tell.

## What she wants
One or two sentences.

## What she will trade or reveal
- What she gives, sells (with prices) or tells, and on what terms.

## If miller_asleep
How things stand for her while that holds (shown to her as "right now").

## GM only
- **Selling flour:** `coins -2 purchase`, then `gain flour_sack`.
- **Persuading her to open the sluice:** `check wits 12`. On a success, `flag set sluice_open`.
```
- **minor:** `yes` means the game master voices them directly from this file (shopkeepers, creatures, passers-by). `no` means they speak through their own agent, which sees this file without `## GM only` and plan sections, the scene, and its memory of the player. A world needs **at least two** with `minor: no`: the people who matter.
- **Sections:** `## Personality`, `## How <she|he|it|they> speak(s)`, `## What … know(s)`, `## What … want(s)`, `## What … will trade or reveal`, any `## If …`, and `## GM only` with the mechanics: every trade, check, flag and reward, as commands in backticks.
- **Fighters:** anyone who can be fought gives `hp`, `defense`, `attack` and `damage` (dice). Defeating them sets `<id>_defeated` automatically; say in `## GM only` what that means, and give the rooms conditions so they're gone afterwards. Use the kit's foe tiers for numbers: weak 5 HP, defense 9, attack +0, 1d4; average 8, 11, +1, 1d6; tough 12, 12, +2, 1d8. A tough foe is a real danger at 10 HP.
- **card** (optional): a `#rrggbb` colour for their speech.
- **Makers:** `makes:` lists item tiers they make to order (`trinket`, `light_weapon`, `weapon`, `tonic`), optionally `accepts:` items they take instead of money. Add `## What <she|he|it|they> make(s)`: their trade and its limits ("only what her hands can carve from bone and line; nothing magical"). The rules set the prices.
- **Builders:** `builds: yes`, and `## What … build(s)`: what they put up and its limits. They build at the build spots of the room they stand in.
- **Plans** (only for `minor: no`): things they do off-screen on world turns. Each is a section:
  ```
  ## Plan: to_green (if not miller_on_green and not sluice_open)
  does: walks down to the green to watch the river
  sets: miller_on_green
  near: A door bangs at the mill, and boots crunch down the path to the green.
  rumor: Hester's been standing on the green, staring at the river.

  ## Plan: back_home (if miller_on_green)
  does: goes back up to the mill
  clears: miller_on_green
  near: Boots crunch back up the mill path, and a door bangs shut.
  rumor: Hester went back to her mill.
  ```
  Each step sets or clears one flag of **their own**, named `<their id>_<word>` (`miller_on_green` for `miller`… so ids and flag names must match: a character `hester` would have `hester_on_green`). Never a flag the main quest uses. Every flag set by one step is cleared by another. Rooms do the rest: the mill lists her `(if not miller_on_green)`, the green `(if miller_on_green)`, so she's always in exactly one place, before and after any step. `near:` is what the player notices nearby (one sentence, shown not explained); `rumor:` what people say elsewhere. Something outside the character file must use each plan flag (a room's characters or prose).

## Items

```markdown
---
name: Coil of Rope
weight: 2
---
One or two sentences: what it looks like and what it's for.
```
`weight` (1 small, 3 heavy; the player carries about 8–12 in all). Weapons give `damage` (1d4 light, 1d6 heavy); consumables give `heal` (1d4+1, 2d4). Anything else an item does is written where it matters: a room's `## Details` or a character's `## GM only` ("if the player carries `rope_coil`, they can climb down: `lose rope_coil`, then `flag set well_climbed`").

## The quest

```markdown
---
name: Hold Back the Flood
giver: hester
started_by: quest_heard
completed_by: sluice_open and not mill_drowned or village_warned
failed_by: mill_drowned and not village_warned
objectives:
  - Find out what's wrong at the mill. (done when quest_heard or sluice_open or village_warned)
  - Open the sluice, or warn the village. (done when sluice_open or village_warned)
---
## Summary
What the problem is, in a few sentences.

## Stages
1. **Hear the problem.** Who tells it and what's set.
2. **Choose a way.** Each way, the flags it sets, and where the details are.

## The clock
What happens when time runs out.

## Endings
Narrate whichever single ending matches the flags.

### If sluice_open and not mill_drowned
The ending for that way.

### If village_warned
The ending for the other way.

### If mill_drowned and not village_warned
The ending when time ran out.

## After the ending
The adventure is over. Tell the player that they finished *<title>* and that they can explore freely or type `/newgame` to play again and try another way.
```
Exactly one quest. At least two objectives, each ending `(done when <condition>)`; the journal shows the done ones and the current one. **At least two ways through**: an `or` in `completed_by` or in an objective. At least two `### If` endings under `## Endings`, and an `## After the ending` section. Every flag here must be set somewhere by a `flag set` in some file (or by the clock, a variant, or a defeat).

## Tables

```markdown
---
name: On the green
chance: 1 in 6
entries:
  - A goose hisses at you and you step back into a puddle. (effect: none)
  - You find a penny in the grass. (effect: coins +1) (once)
  - You slip on the wet bank. (effect: hurt 1d2)
---
Things that can happen on the village green. The rules roll for them when the player arrives.
```
`chance` is `N in M`. Effects: `coins +N`/`coins -N`, `gain <item>`, `hurt <dice>`, `heal <dice>`, `flag <name>`, `none`; `(once)` per game. A room uses a table with `encounters:`. At least one room must have one.

## Curses

```markdown
---
name: The Gabble
effect: word_limit 3
caused_by: drank_from_well
cured_by: gabble_lifted
---
What it is and how it starts, in a few sentences.

## How it shows
How people react to the player's changed words.

## The cure
Who can cure it and how.

## GM only
- It starts when … (see that room): the room's Details say `flag set drank_from_well`.
- <who> cures it when asked: `flag set gabble_lifted`.
```
`effect` is one of `reverse_words`, `mirror`, `word_limit <n>`, or `suffix "<phrase>"`. It changes how the player's words come out while `caused_by` holds and `cured_by` doesn't. Something must set the cause (a room's Details, usually something the player chooses to do: drink, touch, read) and something must set the cure (a character's `## GM only`). Make it optional and funny, never needed for the quest.

## Side scenes

```markdown
---
name: The Great Loaf Debate
with:
  - hester
  - baker
where: village_green
when: miller_on_green and not mill_drowned
reward: coins 1
chronicle: Refereed a shouting match between the miller and the baker over whose bread was better.
---
## How it starts
What the game master shows to offer it: the two starting up, in a couple of sentences.

## Premise
What's going on, for both of them, and the player's place in it (take a side, broker a deal, watch).

## hester
Her part: what she wants out of it and how she argues.

## baker
His part.

## How it ends
It ends when …, or with the last reply. If the player brokers a deal both can live with: `scene end <id> reward`. Otherwise, `scene end <id>`.
```
A little silly scene for two characters with `minor: no`, both of whom can stand in `where` (that room lists them both, with conditions). `when` is a condition; `reward` is `none` or `coins 1` or `coins 2`; `chronicle` one line. One `## <character id>` section each. It changes no flags.

## Writing for the game master

- **Refer to things by name or id, never by file path:** "see the Chalk Head room", or "(see `vane`)", not `rooms/chalk_head.md`. The game master reads content only through the rules script.
- **Everything that matters is written down.** The game master invents only small harmless colour. If the player can get past someone, the file says how, in commands. If a character sells something, the price is written. If a search can find something, the room says where and with what check.
- **Mechanics are commands in backticks**, exactly as the rules script takes them, in `## GM only` sections and room `## Details`:
  - `` `flag set <name>` ``, `` `flag unset <name>` ``
  - `` `coins +3 reward` ``, `` `coins -2 purchase` `` (every change of money names its reason: job, work, sale, purchase, trade, toll, order, reward, gift)
  - `` `gain <item>` `` (from a character), `` `lose <item>` `` (given away or used up), `` `take <item>` `` (from the room)
  - `` `check <might|agility|wits> <number>` `` (8 easy, 12 normal, 16 hard), and what happens on success and on failure
  - `` `hurt <dice>` ``, `` `heal <dice>` ``, `` `attack <character>` ``
  - `` `scene end <scene> reward` ``

  The checks reject a command naming an item, character or scene that doesn't exist.
- **Ways through the quest** should be different in kind: a gift or trade, a check (persuade, frighten, sneak), a fight, a clever use of an item. A good way to give the player a choice is a character who wants something, which a variant decides.
- **Clues** live in the world: what people know (`## What … know(s)`), what rooms show (`## Details`), public knowledge. Each step should be findable within a room or two.
- **Write the `## If` sections** a change in flags needs: how the room looks once the door is open, how a character speaks once befriended, and how the place looks after each ending.
- **Keep it short.** Rooms of two or three paragraphs, characters of a screen or less. Plain words.

## Soundness: what `validate` checks in every world

- Every exit, item, character, table and scene a file names exists; every room's terrain is in the look; dice parse.
- **Every flag a condition uses can be set by something:** a `flag set <name>` written in some file, an encounter's `(effect: flag <name>)`, a variant, the clock's flags, a plan step's `sets:`, or defeating someone with `hp` (`<id>_defeated`). A condition on a flag nothing sets is reported.
- Every rules command written in backticks is a real one, with the right arguments, naming things that exist.
- Plans: well formed, the character's own flags, never the quest's, each set flag cleared by another step, used outside the file, and the character never in two rooms or in none.
- Scenes: two `minor: no` characters who can both be in `where`, a small reward, the required sections, no flag changes.
- Curses: a valid effect, a cause and a cure something sets.
- Build spots: a builder there, a free map square, not an exit or expand direction.

## Kit-complete: what every forged world must have

`python3 rules/rpg.py validate --dir <folder> --kit-complete` checks all of the above, plus:
- world.md with `title`, `start_room`, `stats`, `rolls`, `coins`, `inventory`, `variants` (at least one line), `clock`, `weather`, `generation`, and the sections `## Opening`, `## Tone`, `## Public knowledge` (and `## Who the player is`);
- a `look.json` with a `palette` and a `resource` with a `name` and an `icon`;
- 5 to 8 rooms, each with a `terrain`, every one reachable from the start room by exits; at least one room with `encounters:`;
- 3 or 4 characters: at least two with `minor: no`, at least one with plans, a maker (`makes:`), and a room with a build spot and a builder;
- exactly one quest with `started_by`, `completed_by`, `failed_by`, two or more objectives, two ways through, two or more `### If` endings and `## After the ending`;
- at least one curse and one side scene;
- only the files listed under *The shape of a world*, at most 80 files, none over 20,000 characters.

It prints `CONTENT OK … (kit-complete)` when the world passes, and otherwise one line per problem naming the file. Fix them all and check again.

## A good order of work

1. **Plan first, before writing any file** (not in a file: the world's folder holds only the world): the premise; the map on a grid; the people and what each wants; the problem, the deadline, and the two or three ways through with the flag each sets; the variant; the curse and its cure; who has plans and what they do; the scene.
2. Write `world.md`, then the rooms, then the characters, items, quest, table, curse and scene, then `look.json`.
3. Check, fix, and check again until it passes.
4. Read it through once as the game master would: can every way through actually be played from what's written?
