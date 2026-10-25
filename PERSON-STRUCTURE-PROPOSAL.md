# Proposal: a sturdier structure for the people in the cast

Written 2026-10-25 by Claude with JW, from a review of the code at commit `6b6edd2` and a design conversation. **Status: agreed in outline by JW; its open choices were decided in the eighth session (2026-10-25). Section 6 lists what is decided and what is still open, and is the source for this part. Nothing is built.** The spreadsheet `character-structure.xlsx` holds the same structure as tables; where the two differ, this file is the source.

## 1. What this is for

Two goals:
1. **Robust:** a person behaves for the same reasons from run to run, and keeps what they need to know.
2. **Easy to update:** a change to how people work is made in one place, tested before a run, and traceable in the log afterward.

One uncertainty is accepted, not fixed: a person in the town knows only what a person would know, but the model underneath also knows the whole genre, including where a story about a peddler who takes shadows usually goes. That can't be taken away. It can be seen: a DO line that rests on something no page ever told them is the trace, and the logs so far show people acting on what they were told. Watch for it; don't design around it.

---

## 2. What a person has today (in any world)

### 2.1 The parts

| Part | Where it lives | Same for everyone? | Who changes it |
|---|---|---|---|
| Cast entry | `games/<world>/cast.json` | No, one per person | JW, through Claude |
| Instructions (system prompt) | `.claude/agents/player.md` | Yes | JW, through Claude |
| Brief layout, headings and labels | Inside `rules/rpg.py` (`cmd_brief`, `pane_text`, `memory_text`) | Yes | Code change |
| Memory think-back prompt | Inside `rules/rpg.py` (`condensing_brief`) | Yes | Code change |
| Memory | `state/save.json`, per person | No | Only `rpg.py` |
| Memory and brief settings | `rules/presets.json` (`simulation`), `games/<world>/settings.json` | Yes | `tools/settings.py` |
| Model | The cast entry's `model` field | No | JW, through Claude |
| Claude Code's own lines (billing line, "a Claude agent", owner's email, date, model name, folder) | Added by `claude -p` | Yes | Can't be removed (DEVELOPING.md, Known limits) |

### 2.2 Cast entry template (today)

```json
{
  "id": "<lowercase id, not also a world character's id>",
  "name": "<name>",
  "pronouns": "<she/her | he/him | they/them>",
  "model": "<haiku | sonnet | opus | fable>",
  "personality": "<first person: who I am>",
  "voice": "<first person: how I talk>",
  "motivations": ["<first person, one line>", "..."],
  "attributes": {"might": 0, "agility": 0, "wits": 0},
  "hp": 10,
  "coins": 5,
  "inventory": ["<item id>"],
  "equipped": "<item id of a weapon in inventory>",
  "home": "<room id>",
  "opening": "<second person: how it begins for me, and what I know at the start>"
}
```

| Field | Required | Limits checked by `validate` | What the person sees of it |
|---|---|---|---|
| `id` | Yes | Lowercase, unique, not a world character's id | Nothing |
| `name` | Yes | Unique | "I'm <name>" every turn |
| `pronouns` | No (default they/them) | Written like `she/her` | **Nothing.** Only the referee, the world agent and the townspeople see it |
| `model` | Yes | One of `balance.json` `cast.models` | Nothing directly (Claude Code's environment line names it) |
| `personality` | Yes | Some text | Every turn, under "Who I am" |
| `voice` | Yes | Some text | Every turn, and in the memory think-back |
| `motivations` | Yes | A non-empty list of lines | Every turn, as "What drives me" |
| `attributes` | No | Each −1 to 3. If left out, the world's starting character is used (rolled) | Status block, under the world's own labels ("Gumption +2") |
| `hp` | Only with `attributes` | 1 to 30 | Status block |
| `coins` | No | 0 to 50. If left out, the world's starting amount | Status block, in the world's money ("6 buttons") |
| `inventory` | No | Items must exist | Status block |
| `equipped` | No | Must be a weapon in the inventory | Status block ("in hand") |
| `home` | Yes | Must be a room | Where they start |
| `opening` | Yes | Some text | **First turn only**, then dropped. It is never saved into memory |

### 2.3 What the person is handed each turn (the brief)

```
## Who I am (a note to myself)
I'm <name>. <personality>
How I talk: <voice>
What drives me: <motivations, joined with ;>.

## How it begins                                ← until their first turn only
<opening>

## What you remember from before                ← once a stretch has been condensed
<one paragraph per stretch, in their own words>

## Lately                                       ← the last 5 rounds, word for word
### Moment <n>
What you did: <their DO line>
Why: <their JOURNAL line>
What happened: <the referee's story of their turn> / <a note of someone else's turn they saw> / <a nearby sign of the world moving> / <news of an ending> / <a building finished>
What you were told: <Name> says: "<words>"
How things stood after: <a full copy of the status block, as it was then>

## Where you are        place, time, weather, ways on, who's with you
## You                  health, stats, money, what they carry and its load, their own places, orders waiting
## Offered to you / ## You offered
## What you're working on    the main quest, and side jobs from people they've met
## People you've met / ## Places you've been
## Talk going around    rumors, only those heard while one of the town's people was with them

What do you do now?
```

They reply with exactly two lines, `DO:` (what they do) and `JOURNAL:` (why, and what they're working toward). Only the DO line causes anything.

### 2.4 Memory today

- **Kinds:** each entry is one of `did`, `reasoned` (the journal), `seen` (the story, onlookers' notes, signals, endings), `told` (words spoken to them) or `status` (a status snapshot).
- **Recent:** the last 5 rounds (`memory.recent_rounds`) are kept word for word.
- **When it's condensed:** once 10 rounds are held (5 kept plus `memory.condense_every` 5), or the recent text passes 45,000 characters (`memory.max_chars`) with more than 5 rounds held.
- **Who condenses it:** the person, in a separate call. That call gets only their name, their voice and the rounds to remember. The answer is stored exactly as given and never corrected. The original rounds stay in the log.
- **Use counts:** each entry counts how many briefs it has appeared in. Nothing uses the count yet.

### 2.5 Problems with today's structure

1. **The opening vanishes after the first turn.** It's the only place a person is told who makes things and who builds (Nell, Ambrose). After turn 1 they know it only if a story or their own journal happens to repeat it.
2. **The world's `## Public knowledge` already exists, but only the world's own people get it.** The cast, who live in the town, never do. Instead, the same facts are copied by hand into each opening.
3. **The think-back call can't see the person's wants.** It sees only their voice, so what they keep is shaped by how they talk, not by what they want.
4. **People aren't told their own pronouns.** Dilly's DO line once said "his".
5. **The model is part of the character.** Hester runs on Opus and Dilly on Haiku, so a difference in behavior can't be put down to personality or to model.
6. **Much of what a person reads is written inside `rpg.py`.** That includes the headings, the labels, the closing question and the whole think-back prompt. Changing a word means changing code.
7. **Nothing records which version of the instructions, prompts or cast entry a person was given.** The brief is logged, but `player.md` isn't, and neither is the cast entry's version.
8. **Status snapshots make up most of each brief.** In the test run, Hobb's brief grew from about 2,400 to about 21,000 characters by round 10, and most of that was repeated snapshots.
9. **"Personality" and "motivations" have no set shape.** Behavior and life history are mixed in one paragraph; people have 2 to 4 motivations of mixed kinds. People aren't comparable, and a new one takes longer to write.
10. **Each turn is a fresh call, so nothing keeps a person consistent except the page.** Where two wants pull against each other, each call can resolve it differently.
11. **There's no cheap way to try a change before a run.** `probe.py` shows what's sent, but not how a person answers.

---

## 3. Existing examples

### 3.1 Hobb Ashcombe, The Thirteenth Stroke (a full entry)

```json
{
  "id": "hobb",
  "name": "Hobb Ashcombe",
  "pronouns": "he/him",
  "model": "sonnet",
  "personality": "Big, slow and soot-grimed, about twenty-five. I carry coal from the coal merchant's to every hearth in Wumbleby. I grew up on the parish, owing everybody for everything, and I've hated owing anyone ever since. I keep a tally of every button. I sleep on the coal sacks in the yard behind the Tock Tower by old Ambrose's leave, which counts as owing, and galls me, and I save what I earn in a sock. What I want most in the world is four walls and a door that locks, and nobody's leave to sleep behind it. I'm kinder than I let on. I've noticed the hearths have gone cold in the houses where the children sleep.",
  "voice": "Few words, said slow and plain. I count things out loud, half to myself. I say \"fair's fair\" and mean it, and I'd rather pay twice than say thank you, because thanks feels like owing.",
  "motivations": [
    "I want a place of my own",
    "I hate owing anyone",
    "I never spend a button I don't have to"
  ],
  "attributes": {"might": 2, "agility": 0, "wits": 1},
  "hp": 13,
  "coins": 6,
  "inventory": ["tally_stick"],
  "home": "tock_tower",
  "opening": "You've come in from the coal yard behind the Tock Tower, where you sleep on the sacks by old Ambrose Tock's leave, because you can't sleep tonight either. You have six buttons in your sock, which is what passes for money in Wumbleby, and not one of them is owed to anybody. Above you the clock ticks loud and fast, and the chains twitch. For three days now, ever since a peddler gave away wind-up toys in the square, children all over town have been asleep and smiling, and nobody can wake them. Under a lamp, they cast no shadow.\n\nYou carry coal to every door in town, so you know it well. The tower's door opens south onto the Lopsided Square, and across the square, on its east side, is Fizzlewick's sweet shop, where Nell Fizzlewick will make sweets, tonics and trinkets to order on her copper still, for a price. Ambrose himself puts up sheds and porches for anyone who pays; he has said as much about the coal yard, and the nettle patch beside the tower."
}
```

What it shows: every field is set. The opening mixes three kinds of thing: tonight's scene, the town's shared situation (the sleeping children), and practical facts (who makes and builds). Only the scene belongs in a one-time opening. The other two are lost after turn 1.

### 3.2 Wren, The Dark Lighthouse (a minimal entry)

```json
{
  "id": "wren",
  "name": "Wren",
  "model": "sonnet",
  "personality": "A restless traveller who came to the coast to start over. I'd rather be useful than idle.",
  "voice": "Plain and quick; I ask more questions than I answer.",
  "motivations": [
    "I want to be thought capable",
    "I hate leaving a job half done"
  ],
  "home": "harbor_square",
  "opening": "It's dusk, and a cold wind is coming in off the sea. The boat that brought you is already pulling away. Above the village the lighthouse stands tall and completely dark. It has been dark for three nights, people say, and the fishing fleet is due home through the rocks any night now."
}
```

What it shows: no pronouns, stats, health, money or belongings. Those come from the world's starting character (stats rolled), which keeps the tests' seeded dice stable. The personality is two sentences, so there's little for a person to act from.

### 3.3 Ade, Tidewell Station (a short entry with its own stats)

```json
{
  "id": "ade",
  "name": "Ade",
  "model": "haiku",
  "personality": "A junior technician. I rode out the storm upstairs, and I'm embarrassed that I hid.",
  "voice": "Nervous and apologetic; I talk too much when I'm scared.",
  "motivations": [
    "I want to be admired",
    "I want to stay dry"
  ],
  "attributes": {"might": 0, "agility": 1, "wits": 1},
  "hp": 9,
  "coins": 2,
  "inventory": ["med_patch"],
  "home": "the_landing",
  "opening": "You rode out the storm in a module of Tidewell Station and have just climbed down to the floating landing, soaked. The power is failing, an alarm chirps somewhere inside, and the tide is still coming in."
}
```

What it shows: the motivations mix a lasting want ("to be admired") with a passing comfort ("to stay dry"). The opening tells Ade nothing about who could make, build or pay for anything.

---

## 4. What must exist, and why

Each item says what must exist, why, and what was rejected.

**R1. Every word a person reads lives in text files, not code.**
- *What:* the brief's headings, labels and closing question, the think-back prompt and the generator's instructions (R4) move out of `rpg.py` into `rules/people/`.
- *Why:* wording changes without touching the engine, and everything a person reads can be reviewed in one place.
- *Rejected:* leaving the words in code. Every wording change is a code change, and the words are spread over four functions.

**R2. The log records which version of everything each person was given.**
- *What:* every `brief`, `action` and `memory` entry carries a short tag for the instructions, the brief template, the think-back prompt, the definitions file, the person's cast entry and the world's public knowledge. The run's first log entry holds the full text of each. `audit.py` reports any version that changed partway through a run.
- *Why:* once people are shown more, they act differently, so runs before and after a change are different experiments. Without the tag, comparing them is guesswork.
- *Rejected:* relying on git history. The log would still not say which commit a run used, and a run can start with uncommitted edits.

**R3. A test bench.**
- *What:* `tools/bench.py` (section 5.10). Its first test is the round-trip check of a cast entry (section 5.9). Its others are fixed situations taken from real runs, re-asked with the current templates.
- *Why:* it shows whether a change did what was meant for well under a dollar, before a $4–20 run.
- *Rejected:* testing only by full runs. They're slow and costly, and they change too many things at once to tell what caused what.

**R4. Two layers: the character anywhere, and the character in this world.** (Decided, section 6.)
- *What:* an archetype file per character, world-independent, holding what is set and varied; and the cast entry per world, made from the archetype and the world by a generator at authoring time, checked by code, read by JW, then committed as `games/<world>/cast.json`. Section 5.2.
- *Why:* ratings never appear on a person's page as a list (which would read as a menu of options), each person's note is in their own voice and the world's register, and the same four characters can be put into every world. The engine is unchanged: it reads `cast.json` as it does today.
- *Rejected:* generating the note fresh each run. Two runs with the same ratings would get different prose, a second source of variance; and "does this read like a menu" needs a human read, which fits authoring, not a run. A switch can add per-run generation later, as its own experiment.
- *Rejected:* showing ratings as fixed first-person lines. Identical lines across characters, no world register, and a list shape.

**R5. One definitions file for attributes and ways of acting.** (Decided, section 6.)
- *What:* `rules/people/defaults.json`, overridable per world by `games/<world>/people.json`, holding the scale, which rating is ordinary, and each attribute's and way's name and low and high lines. The archetype carries ratings only; `validate` checks them against the file; the generator and the round-trip check read the lines.
- *Why:* the same pattern the engine already uses for display names (`look.default.json` and a world's `look.json`). A wording change reaches every character; a world can phrase a line in its own register.
- *Rejected:* lines in each cast entry. Four copies that drift.

**R6. What a person knows, in layers.** (Decided, section 6.)
- *What:* section 5.6. Starting facts and the world's public knowledge shown every turn; a short generic text on how life works anywhere; the opening kept to tonight's scene; pronouns shown.
- *Why:* the fix for problems 1, 2 and 4. It is the governing rule's memory allowance, clarified: memory includes what they knew when the night began, not only what has happened since.
- *Rejected:* keeping the opening in every brief. It's written as tonight's scene and would read as if every turn were the first night.
- *Rejected:* a standing text naming which places pay for work and who buys. The proposal says the world offers ways to earn without announcing them; a human player discovers them by playing.

**R7. Memory changes.** Section 5.8; partly open (section 6).

**R8. The model becomes a run setting.** Open (section 6).

---

## 5. The structure

### 5.1 The four parts of a character

| Part | What it holds | Set in |
|---|---|---|
| **Self** (who the character is) | Name, pronouns, look, voice, backstory, wants and needs, avoids and dislikes, won't do, people in their life | Archetype for what holds anywhere; cast entry for this world |
| **Personality structure** (how they behave) | Priorities (a ranked list), and a rating on each attribute (section 5.5) | Archetype |
| **Ways of acting** (practical preferences) | A rating on each way of acting (section 5.5) | Archetype |
| **What they know** | Eight domains, each with what is known from the start, learned from the world, and learned from their own thinking (section 5.6) | Cast entry, world file, memory |

Plus the **starting kit** (stats, health, money, belongings, home: the game's numbers, as today) and the **model**, which is a run setting under R8.

The ratings are what is set and varied. They are never shown as numbers or as a list. They shape the behavior paragraph the generator writes (section 5.9), and they are what the round-trip check measures.

Attributes say *why* (disposition); ways say *how* (habit). Some pairs overlap (curiosity and investigating; using people and influencing). Keep an archetype's ratings consistent across such pairs, or the log can't say which one drove a behavior.

### 5.2 Two layers

| Layer | File | Holds | Changes |
|---|---|---|---|
| **The character anywhere** (archetype) | `cast/<id>.json` | Self parts that hold in any world (name, pronouns, voice, wants in the abstract, avoids, won't do), priorities, attribute ratings, way ratings | By JW, through Claude; rarely |
| **The character in this world** (cast entry) | `games/<world>/cast.json` | Everything the engine reads today, plus the new Self fields, starting facts, and the generated behavior paragraph | Made by the generator from the archetype and the world, checked, read by JW, committed |

The engine reads only the cast entry, as it does today. The archetype is an authoring input. Its id is recorded in the cast entry so the log can carry both versions.

### 5.3 Archetype template

```json
{
  "id": "hobb",
  "name": "Hobb",
  "pronouns": "he/him",
  "voice": "<first person: how I talk, phrases I use. 20 to 60 words>",
  "wants_and_needs": ["<first person, in the abstract: 'a place of my own'. 1 to 3 lines>"],
  "avoids_and_dislikes": ["<first person. 1 to 3 lines>"],
  "wont_do": ["<first person: a line I won't cross. 1 to 2 lines>"],
  "priorities": ["<which of my wants comes first when two pull against each other, in order>"],
  "attributes": {"initiative": 4, "seeks_company": 2, "takes_charge": 3, "...": 3},
  "ways": {"use": 3, "build": 4, "influence": 2, "...": 3}
}
```

Every attribute and way in the definitions file must have a rating. A rating of 3 (ordinary) is the default and carries no line.

### 5.4 Cast entry template (new)

```json
{
  "id": "hobb",
  "archetype": "hobb",
  "name": "Hobb Ashcombe",
  "pronouns": "he/him",
  "look": "<what others see: build, clothes, what's carried openly. One or two lines>",
  "voice": "<copied from the archetype>",
  "backstory": "<first person: age, work, where I sleep, my history here. 50 to 150 words>",
  "wants_and_needs": ["<the archetype's wants, in this world's terms>"],
  "avoids_and_dislikes": ["<in this world's terms>"],
  "wont_do": ["<copied from the archetype>"],
  "priorities": ["<copied from the archetype, in this world's terms>"],
  "people": [{"who": "<cast id or character id>", "how": "<first person: how I know them. One line>"}],
  "knows": ["<first person: a fact I know as the night begins. 3 to 8 lines>"],
  "how_i_am": "<first person: the behavior paragraph the generator writes from the ratings, in my voice and this world's register. 60 to 150 words. Never a list; never the definition lines verbatim>",
  "attributes": {"might": 2, "agility": 0, "wits": 1},
  "hp": 13,
  "coins": 6,
  "inventory": ["tally_stick"],
  "equipped": null,
  "home": "tock_tower",
  "opening": "<second person: tonight's scene only, where I am and what I'm doing. 40 to 100 words. No facts that belong in knows or in public knowledge>",
  "model": "<optional; used only when the run setting says to use each person's own>"
}
```

What changes from today:
- `personality` splits into `backstory` (the facts of a life) and `how_i_am` (behavior); `motivations` becomes `wants_and_needs`, `avoids_and_dislikes`, `wont_do` and `priorities`.
- New: `archetype`, `look`, `people`, `knows`, `how_i_am`.
- `pronouns` is required and shown to the person.
- `opening` is limited to the scene.
- `model` is optional (R8).
- `look` goes to the referee (in `look`'s `PEOPLE HERE`) and to the townspeople's briefs (`npc-brief`'s `Present:` line), so onlookers describe a person the same way.
- `people` seeds the engine's list of people met at `newgame`; otherwise the status block's "People you've met" and the character files' "if met" conditions would disagree with the note.
- `validate` checks every slot's presence and length, that `people` names a cast member or world character, that `archetype` exists, and the forbidden-word list over every text field.
- All three worlds' cast files are rewritten, and the tests updated. The shipped games' first cast members still leave out stats and kit, so their seeded dice hold.

### 5.5 The definitions file

`rules/people/defaults.json`, overridable per world by `games/<world>/people.json` (same shape; only the keys given are replaced):

```json
{
  "scale": {"min": 1, "max": 5, "ordinary": 3},
  "attributes": {
    "initiative": {"name": "Initiative", "low": "I wait for things to come to me", "high": "I get up, get on with it and find a way"},
    "seeks_company": {"name": "Seeks company", "low": "I keep to myself", "high": "I seek people out, and can't bear to be left"},
    "...": {}
  },
  "ways": {
    "use": {"name": "Use", "low": "I forget what I'm carrying", "high": "I make use of whatever I have on me"},
    "...": {}
  },
  "universe": [
    "<a generic sentence on how life works anywhere, in the fiction's words; {currency} is filled in>"
  ]
}
```

The attributes and ways, with their test facets and what each would show in a run, are listed in the spreadsheet's Personality and Ways of acting sheets. The test names (BFI-2, PID-5) stay in the spreadsheet and never go in the definitions file, so neither the generator nor a person ever reads them.

### 5.6 What they know

| Domain | Known from the start (stays) | Learned from the world | Learned from own thinking | How it fades |
|---|---|---|---|---|
| About the universe (how life works anywhere) | The `universe` sentences: people make things to order, builders put up places, some work pays, some folk buy, things change hands only by agreement. Generic: never which place or who | How these work in practice | Their own theories | Start: never. Learned: with memory |
| About the world (this place) | The world's `## Public knowledge`; the cast entry's `knows` | Places been, people met, rumors heard, what they're told | What they conclude about people and places | Start, places and people: never. Rumors: the latest few. Told and concluded: with memory |
| About this run | | Endings, buildings finished, news | What it all means | Endings and news: never (proposed). The rest: with memory |
| About this situation now | Tonight's scene, first turn only | Worked out fresh each turn | | Replaced each turn |
| About me now | | Worked out fresh each turn | | Replaced each turn |
| Recent history (mine) | | The story of each of my turns | What I meant to do | 5 rounds word for word, then in their own words |
| Recent history (others, the world) | | Words spoken to me, what I saw others do, signs nearby | | As above |
| My own journal | | | Every journal line | The latest kept as written for longer than the rest (proposed); older ones in their own words |

**Decision (JW, 2026-10-25): the first two rows' "known from the start" columns are memory,** under the governing rule's third allowed difference: a human player remembers the opening, and a resident knows what the town knows. The proposal's section 2 gains one sentence: *memory includes what they knew when the night began, not only what has happened since.* Two limits keep it inside the rule: the `universe` text stays generic, and neither it nor a world's public knowledge may name which places pay for work or who buys. `validate` can't check meaning; the world guide says so, and the audit reads for it.

### 5.7 The brief

```
## Who I am (a note to myself)
I'm <name> (<pronouns>). <backstory>
How I talk: <voice>
What I want: <wants_and_needs>
What I steer clear of: <avoids_and_dislikes>
What I won't do: <wont_do>
What comes first: <priorities, in order>
People I know: <who: how; ...>
<how_i_am>

## What I know
- <knows, one per line>
- <what I've learned, one per line>            ← if open choice B is taken

## What everyone around here knows
- <universe sentences>
- <the world's public knowledge>

## How it begins                                ← first turn only
<opening>

## What you remember from before
<one paragraph per stretch>

## Lately
### Moment <n>
What you did / Why / What happened / What you were told
What changed: <one line>                        ← if open choice A is taken; else the status copy as today

<status block, unchanged>

What do you do now?
```

Size: "Who I am" and "What I know" come to about 1,500–2,500 characters, roughly today's note plus a screen. If choice A is taken, briefs shrink by far more than that.

### 5.8 Memory

1. **The think-back sees the whole "Who I am" note,** not only the voice (proposed default; a setting `memory.thinkback_sees: voice | who_i_am` keeps today's behavior for comparison). Otherwise what a person keeps is shaped by how they talk, not by what they want.
2. **Open choice A:** older moments keep one line of what changed (money, place, belongings, health), worked out by the code, instead of a full status copy. The current status block at the end of the brief is unchanged.
3. **Open choice B:** a "What I've learned" list the person keeps up at each think-back (`LEARNED:` lines, capped by `memory.learned_max`, proposed 20), shown under "What I know".
4. **Endings and finished buildings never fade** (proposed, small): a `keeps` mark on those entries, which condensing leaves in place.
5. **Journal lines are held as written for longer** than the rest of a round (proposed, small): `memory.journal_rounds`, so a plan carries across a think-back.

### 5.9 Making a cast entry: the generator and the checks

`tools/cast.py`, built on the same call mechanism as `tools/ask.py` (the owner's Claude Code login, `claude -p`, no tools; never the Anthropic API):

- **`make <world> <id>`:** reads the archetype, the definitions file (with the world's override), and the world as `world-brief` already gives it to the world agent (opening, tone, public knowledge, the rooms, characters and items). Hands them to one fresh call with `rules/people/generate.md` as instructions. The reply is a full cast entry (section 5.4). The tool then checks it: valid shape (`validate`'s cast checks); every text field passes the forbidden-word test; `home` is a room; every `people` entry and `inventory` item exists; `name`, `pronouns`, `voice` and `wont_do` are the archetype's, verbatim; no rating appears as a number; no definition line appears verbatim in `how_i_am`. It writes the result to `proposals/cast-<id>.json` and prints what failed. JW reads and edits it.
- **`apply <world> <id>`:** moves the proposal into `games/<world>/cast.json`, replacing that person's entry, and runs `validate`.
- **`check <world> <id>`:** the round-trip check. Builds "Who I am" exactly as the brief would show it, hands it to a fresh call with the definitions as questions ("For each, 1 to 5, where 1 is *<low>* and 5 is *<high>*"), and prints the archetype's rating beside the answer for every attribute and way, flagging any two or more apart. It is JW's BFI-2 and PID-5 experiment turned into a tool: it says, before a run, whether the note carries the ratings or the model's own personality has softened them. Run it after `make`, and again whenever the definitions, the generator's instructions or the entry change.
- The model used for `make` and `check` is the owner's choice (`--model`, Sonnet by default) and is recorded in the proposal and in the log's version entry.

Nothing here runs during a round. The generator is an authoring tool, like the forge.

### 5.10 Version record and test bench

- **Versions (R2):** a short tag (a hash of the text) for `player.md`, `brief.md`, `thinkback.md`, `generate.md`, the definitions file as resolved for the world, the person's cast entry, their archetype, and the world's public knowledge. Every `brief`, `action` and `memory` log entry carries them; the run's first entry holds the texts.
- **`tools/bench.py` (R3):** `save <name>` copies the save as it stands, plus which person, into `bench/<name>.json`; `run [<name>]` rebuilds each situation's brief with the current templates and asks the person exactly as `ask.py` does, printing the new reply beside the one given in the run (from the log) with both version tags, then runs `audit.py`'s leak and Claude Code-trace checks over the new briefs and replies; `--dry` builds the briefs without asking anyone. A full pass over five situations for a cast of four should cost well under a dollar.

### 5.11 Set aside for later

- **How people get things, as a strategy.** A ranked preference (find it, make it or have it made, earn and buy it, ask for it, take it) was considered in place of separate ratings for Find, Build, Buy and Grab, and set aside with the Find way of acting (JW, 2026-10-25). Note for then: under the simulation settings item generation is off, so a search finds only what's authored lying in a room (about ten things in The Thirteenth Stroke). For "find rather than buy" to be a real choice, either author more things lying about (content only) or turn item generation on for searches (one setting; every found thing is then new content, which the log marks).
- **Per-run generation of `how_i_am`** as an experiment of its own (R4, rejected for the default).
- **Forgetting by age, use or chance** before condensing: the fields exist (`uses`, `round`); the routine is still "later" in the fork proposal.

---

## 6. Decisions and open choices

### Decided (JW, 2026-10-25)

1. **The four-part structure** (Self, Personality structure, Ways of acting, What they know) is adopted, with the starting kit and the model alongside.
2. **Memory includes what they knew when the night began.** Starting facts, the world's public knowledge and a generic how-life-works text are shown every turn, as the governing rule's memory allowance, not a fourth difference. Never which places pay for work or who buys. One sentence goes into `SIMULATION-FORK-PROPOSAL.md` section 2.
3. **Two layers, with the cast entry made by a generator at authoring time,** checked by code, read by JW, committed. Never per run by default. The round-trip check is built with it.
4. **The definitions file** (scale, ordinary rating, low and high lines), shared with a per-world override; the archetype carries ratings only.
5. **Find, and the "how I get things" ranking, are set aside** (section 5.11).
6. **What a person knows unprompted against what the model knows** is left as an experiment uncertainty (section 1), stated once, watched in the log, not designed around.

### Decided in the eighth session (JW, 2026-10-25)

The open choices A–D and three additions the runs asked for. The evidence is in `PLAN.md`, *The eighth session*.

7. **A: yes.** Each older moment in memory keeps one line of what changed (money, place, belongings, health), worked out by the code, instead of a full copy of the status block. The current status block at the end of the brief is unchanged. In the 14-round run Hobb's brief reached 34,000 characters, and the quest's ending, the last line of a moment after a full status copy, was the one thing he didn't act on.
8. **B: yes.** People keep a "What I've learned" list, updated at each think-back (`LEARNED:` lines, capped by `memory.learned_max`), shown under "What I know". It is second to item 2: Hobb's fact about who builds was never in the rounds he condensed, so only his starting facts would have kept it.
9. **C: one model for everyone, Sonnet,** as a run setting (R8). Rotating models by run stays possible later, as a study of its own. The cast entry's `model` is used only when the setting asks for each person's own.
10. **D: yes.** The think-back sees the whole "Who I am" note; `memory.thinkback_sees: voice | who_i_am` keeps today's behavior for comparison.
11. **What this run has done has a standing place.** Endings and finished buildings never fade (the `keeps` mark, 5.8 item 4), and they are shown under "What I know", not only as a line in "Lately". (In the 14-round run Hobb set off to trade for a jar his own brief had just told him was empty.)
12. **Makers and builders may be named** in a cast entry's `knows` and in a world's public knowledge; the limit on decision 2 is only on naming which places pay for work, and who buys.
13. **The world's problem is known; caring is the person's own.** Everyone knows the world's shared problem (it goes into the world's public knowledge), but its quest appears in "What you're working on" only once that person has taken it on (a personal flag). How much they care, and what they do about it, comes from who they are: Kindness and priorities, above all.
14. **Options considered (level 1 of how a person decides).** The reply gains an `OPTIONS:` list before `DO:` and `JOURNAL:`: two to four things they could do, each with what it is for (`(for: <which want, need or concern it serves>)`); the journal says why this one over the others. Options are private, like the journal: kept in the log (the `action` entry), shown in the dashboard's feed and counted by the audit, never shown to anyone else and not kept in the brief. `player.md` changes, so the version record (R2) comes first. **Evidence:** Hobb's round-8 moment from the 14-round run, re-asked four ways, three replies each ($0.32; `state/test-runs/hobb8-options/`): he asked Ambrose to build him a shed in 0 of 3 replies as in the run, 0 of 3 with only a "What I know" section naming Ambrose as a builder, 0 of 3 with only the options list, and **3 of 3 with both**, still putting repaying Ambrose first. Knowing and weighing belong together, so item 2's knowledge layers (R6) and this are built as a pair and tested with the bench (R3). One situation, chosen as the best case: the bench should also try ordinary moments, to see that the list doesn't make people restless or drop what they've promised.
15. **A separate evaluator is acceptable** for a later level of how a person decides (below).

### Open

**E. Order of work.** Proposed in the eighth session, not yet confirmed by JW, as part of the whole plan in `PLAN.md` (*The eighth session*, steps 45–61): R1 and R2 first (words into files, version record: the briefs before and after must be identical); then the bench (R3), with Hobb's round-8 moment as its first situation; then options considered (item 14) and R6 (knowledge layers) back to back; then R7 (memory: items 7, 8, 10, 11) and R8 (item 9); the definitions file and the generator (R5, R4) with the round-trip check come once the new test world (`SIM-WORLD-SPEC.md`) exists, since its cast is the generator's first real use. This differs from the order first proposed (generator before knowledge layers) because the runs and the Hobb test point at knowledge and options first, and the generator pays off when there is a second simulation world.

### For a future discussion (may lead to requirements)

**F. How a person decides, beyond level 1.** JW's question (eighth session): should a person's choice be a defined procedure that code enforces (first work out what they could do, then weigh each option against who they are, then choose), so that personality demonstrably causes behavior instead of colouring it? The levels discussed:
- **0 (today):** one call; the person decides; personality is implicit in the note.
- **1 (decided, item 14):** one call, options listed before the choice; visible, not enforced.
- **2:** two calls, options first, then the choice with the note and the options in view.
- **3:** the person lists options in their own words; each is scored on fixed dimensions (serves a want or need? costs money? helps others? risky? involves others?) by the person or by a separate evaluator; code combines the scores with the person's hidden ratings and priorities and draws a seeded choice, which the person then acts out. The ratings stay unseen and become causal; the log holds every option, score and draw.

What is at stake: at level 3 the model proposes and code chooses, which is a different experiment from "a person decides only for themselves"; if built, it should be a switch (`decide: free | weighed`) compared on the same seed. Whatever the level, options can come only from what a person knows (item 2, R6).

**G. How needs, wants and goals taken on are weighed against each other.** JW: a person should consider what they want to do next from who they are; how does a quest, even a small one, weigh against "I'm hungry and want to eat"? The shape discussed:
- "What you're working on" shows three kinds of goal side by side: **needs** (from the world's state, worked out by code, growing more pressing until met, told in words, never numbers: "You haven't eaten since morning"), **wants** (from `wants_and_needs`) and **things taken on** (quests accepted; later perhaps promises).
- The personality fields play different parts: **won't do** a hard filter (never chosen; at level 3 code can refuse it), **avoids and dislikes** a cost, **priorities** the order between wants, and ratings as weights: Kindness (how much others' trouble counts), Follow-through (how sticky a goal taken on is), Impulsiveness (what's in front of them against a plan), With money (hold on or spend), Risk-taking.
- Needs need a world with time that goes on and things that meet them, so this meets `SIM-WORLD-SPEC.md` (the test world has needs for a bed and food).

The build session should draft each step for JW before writing code, as `PLAN.md` does.
