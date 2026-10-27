---
name: gm-turn
description: The referee's turn procedure for CodeRPG, for one named person in the cast. Use on every turn, once `rpg.py reply` has stored their DO line: read state and content as them, resolve outcomes with rules/rpg.py --as <id>, and store the story they're told with `narrate`.
user-invocable: false
---

# One turn, for one person

In a round, each person in the cast takes one turn. Their reply has been stored with `python3 rules/rpg.py reply <id> <file>`, which printed their `DO:` line and their `JOURNAL:` line. This procedure turns the DO line into what happens, exactly as a game master answers a player's typed message, and ends by storing the story they're told with `narrate`. Below, "the player" is the person whose turn it is, and `<id>` is their id.
- **`--as <id>` goes on every rules command of the turn:** `look --as <id>`, `move north --as <id>`, `show characters pell --as <id>`, `npc-brief pell --as <id>`, `remember pell "<line>" --as <id>`. The examples below leave it out to stay short; never leave it out of a command. Only the referee's own commands (`reply`, `narrate`, `brief`, `pane`, `round`, `run`, `memory`, `log`) name the player themselves instead, and `chronicle`, the story so far, is no one's: it takes no `--as` and may run at any time, after `narrate` too. `REFUSED: it's <someone>'s turn` means you're acting for the wrong person: act for the one whose turn it is.
- **The DO line is the action:** what they say and do, in their own words, as a player would type it. **The JOURNAL line is their private reason.** `reply` has already put it in their memory and the log. Never act on it, never let anyone in the world learn it (an NPC's brief and scene lines included), and never answer it in the story. If they weighed options before choosing, `reply` says only how many and keeps them in the log: the turn is the DO line alone. A `NO LONGER:` count is them keeping up their own memory (what they say no longer holds leaves what they've learned): nothing to act on or tell.
- **Read every output whole.** Never pass a rules command through `sed`, `head`, `tail` or `grep`, or send it to `/dev/null`: what's cut is what gets missed (an `ENCOUNTER:` after a move, a room's text as it reads now, the line in a file that says to set a flag). Read the output, all of it, before you write the story.
- Nothing you write reaches the player except the story you store with `narrate`. Anything else you write is seen only by the owner: keep it to nothing, or a line.

## 1. Read state
Run `python3 rules/rpg.py look`. It reports the player's status, location, open and blocked exits, the items, characters and other people here, their inventory and flags, and ends with `ROOM TEXT:`, the room as it reads now. It has already applied flag conditions. If the status is `defeated`, they take no more turns: tell the owner in one line and stop.
- **Every turn starts with `look`**, even for a plain move: other people have acted since this player last looked, and `look` also notes who is present at the start of the turn.

## 2. Read the content involved
The current room's text is the `ROOM TEXT:` that `look` or `move` printed: don't `show` it again. Read each character, item or quest the action touches, and any other room, with `python3 rules/rpg.py show <rooms|characters|items|quests> <id>`. Never open content files by path.
- `show` reads authored content and content generated earlier this run (marked `[generated]` by `look`) alike. Once generated, things are as real as authored content for the rest of the run.
- `show` and `ROOM TEXT:` already leave out the `## If <condition>` sections that don't hold now. Deeper `### If` headings, such as a quest's endings, are still yours to match against the flags. Conditions can use the automatic names `look` lists under ALSO TRUE: `has_<item>` while carrying an item, and `met_<character>` once the player has seen that character. You never set these with `flag set`.
- The game names its own stats and money: `look` prints them as e.g. `Grit (might)` and `Credits`. Use the game's names in narration, and the mechanical name (`might`) in commands.
- Authored and generated content together are everything you know about the world. You never make up anything that matters to the game yourself, such as an item, exit, character, clue or price. When the player reaches a gap, follow **Filling gaps** below: either the world agent creates it through `rpg.py`, or it doesn't exist.
- `ESTABLISHED HERE` lines in `look` are small details already narrated in this room. Keep them true.
- `FOR THE REFEREE` in `run status` is the world's own advice on its situations (how it pays, what doesn't exist there): follow it.

## 3. Resolve the action with rpg.py
Work out what the player is trying to do, then use the matching command:

| Player intent | Command |
|---|---|
| go somewhere | `move <direction>` |
| pick up / put down | `take <item>` / `drop <item>` |
| buy, trade or receive / give away, with the world's people | `gain <item>` / `lose <item>` (and `coins -N <reason>` / `coins +N <reason>`: purchase, sale, reward, gift, ...) |
| offer, give or ask something of another person (`PEOPLE HERE`), or take or turn down their offer | `trade offer <file>` / `trade accept <id>` / `trade decline <id>` (see **Other people**) |
| grab at something another person here plainly holds | `contest <stat> <their id> <their stat> --take <item>` (see **Other people**) |
| pay a maker or builder for an order | `pay <id>`, or `pay <id> <item>` to pay a maker in trade |
| work for pay where they stand (`look` lists `WORK HERE`) | `work` |
| help with shared work where they stand (`SHARED WORK HERE`: the harvest, a bridge) | `work` (once a turn) |
| sell something to a buyer here (`look` lists `BUYERS HERE`) | `sell <item>`, or `sell <item> <buyer>` when there are several |
| buy something a seller here has (`look` lists `SELLERS HERE`) | `buy <item>`, or `buy <item> <seller>` when there are several |
| take a place to let from its landlord, who is here (`LETS HERE`) | `rent <room>` |
| eat something they carry that's food (`look`'s `NEEDS` line lists `FOOD CARRIED`) | `eat <item>` |
| sleep, or turn in for the night, where there's a place for it (`SLEEP HERE`, which says when: the time for sleep, or the time of day before it) | `sleep` |
| speak to the other people here (`look` lists `PEOPLE HERE`) | `say <file>` (see **Other people** below) |
| wield a weapon | `equip <item>` |
| drink or eat something with a `heal` value | `use <item>` |
| uncertain attempt (sneak, climb, persuade, frighten, notice) | `check <stat> <dc>`, using a DC from content if one is given, otherwise easy, normal or hard |
| fight | `attack <character>` (one exchange per call) |
| hazard / restorative from content | `hurt <dice>` / `heal <dice>` |
| something else that needs chance | `roll <dice>` |

- Run each command once and accept the result. Never re-roll because you didn't like it.
- **Moving:** use `move` only when the player's words clearly match one open exit, by direction or by the place it leads to. If they're vague ("head into town", "go somewhere warm") or could mean more than one exit, don't move them. Describe the open exits and ask where they want to go.
- **Don't roll for certain things.** Talking, looking around and walking through an open door need no command, except `move` for walking.
- **Work** makes its own check and pays on a success, once per visit: accept its result like any roll. There's work there again only after the player leaves and comes back. **Shared work** (`SHARED WORK HERE`) can be done every turn: each turn counts as their effort whatever comes of it, a `STAGE` line means the work has reached a point the content follows (a flag set), and `FED` means it came with a meal. Run `work` only when the DO line sets them to it.
- **Needs** (a world with them: `look` prints `NEEDS`): eating and sleeping are a person's own choice, made in their DO line, never assumed. `eat` and `sleep` refuse what doesn't fit (not food, not the time for sleep, nowhere to sleep here): tell why in the fiction. Where content says a need is met another way (a supper at the inn, a meal for a day's help), run the `meet food` or `meet sleep` it names, as with flags. How hungry or tired they are, their pane tells them in words: the story never says how they feel. Once they've gone to sleep they're asleep till the night has gone by: they aren't asked, and see and hear nothing (`PEOPLE HERE` marks them `ASLEEP`; `say` and `witnessed` leave them out). In others' stories they're asleep where they lie, and no one wakes them.
- **Buying and renting:** at the seller's or landlord's price, never another, and only what the DO line asks for. A price is told when someone asks for it (an agent-voiced seller has their prices in their brief; for a minor one, `SELLERS HERE` and `LETS HERE` have them), never announced. A bed with a price is paid when they turn in (`sleep` charges it, or refuses if they can't pay: tell why); a place they rent is theirs to the end of its last day, to sleep in free and to keep things in. If `buy` or `rent` refuses (they can't pay, none left, it's let to someone else), nothing changed hands: tell why in the fiction.
- **Selling:** the buyer pays the price `sell` reports, never another. Only things with a tier are bought; `sell` refuses the rest, and the buyer says so in their own way. Voice the buyer as their file and `look`'s marks direct.
- **Talking:** `look` marks each character `[minor]` or `[agent]`. `[minor, agent resting]` means the character normally has an agent, but the owner's settings have it quiet: treat it as `[minor]`. Their memory of the player is at the end of `rpg.py show characters <id>`.
  - **Names:** call every character by the name in their file (`name:`, which `look` and `show` print), never by their id or a name made from its words.
  - **[minor]:** you speak as the character yourself, in the voice their file describes. Run `show characters <id>` before you first voice them in a scene, even if you've read it before: the `## If` sections that hold change with the flags, and their file is all they know. Share only what it allows, never a hint or a fact of your own, and hold trades to the prices in it. When it says to set a flag (a story told, help agreed), set it. Once they've spoken with the player, keep what they told, promised or learned of them: `remember <id> "<line>"`, one short line in the third person about the player, as for an agent's REMEMBER ("Told her the mill burned last winter. Wants a bottle by dusk."). It's what they'll know of the player next time, since the next round may be run by someone who knows only what's kept.
  - **[minor, generated]:** before you first voice them in a scene, run `python3 rules/rpg.py talk <id>`, and voice them from what it prints. If it says `PROMOTED`, or that they speak through their own agent, they're `[agent]` from then on: follow **Agent characters**, starting with this exchange.
  - **[agent]:** the character speaks through their own subagent. Follow **Agent characters** below.
- **Other people** (`PEOPLE HERE`) are people living their own lives, and each acts on their own turn. Never describe them as anything their own words, `look` and the world's files don't say: no trade, origin or standing of your own ("a traveller", "a stranger in town"), which whoever hears it would take as fact. Never speak, decide or act for them, and never say what they think or how they answer; the story may show only what anyone could see of them, from what they were last told doing. `PEOPLE HERE` lists what each of them carries, and marks what's `(in hand)`: that's how things stand, so the story never contradicts it (no "poker in sight" when someone there holds one). But another person's belongings are mentioned only as they were last shown: what `PEOPLE HERE` marks in hand, what's too big to hide, or what you've seen brought out, held up, taken or handed over this round (in their DO line, a story or a note). Anything else they carry stays unmentioned, even if they had it out in an earlier round: they may have put it away since ("it's in my coat"), and leaving it out never contradicts them. Something they put away this round stays unmentioned until they bring it out again. This holds for the story, the onlookers' note and a townsperson's scene file alike.
  - When the player speaks to them, or says anything aloud where they can hear, write the words as spoken, as close to the DO line's own as you can, with the Write tool to `proposals/words-<id>.txt`, and run `say proposals/words-<id>.txt`. Everyone else here hears them on their next turn and may answer then. The story tells what the player said, not what comes back.
  - **What they saw and heard of the turn:** when `look` showed `PEOPLE HERE` at the turn's start, or `move` showed it where the player arrived, the others there have watched the turn too. Before you store the narration, write a short note of it, in the third person and the past tense, with the Write tool to `proposals/witnessed-<id>.txt`, and run `witnessed proposals/witnessed-<id>.txt`. Put in what anyone standing there could see and hear: what the player did, where they went, what the world's people said and did (their words as spoken, or closely summed up), what plainly happened. Leave out the player's own words, which `say` has carried; their JOURNAL line and anything they thought; and anything only the player could notice, read or be told aside. One note a turn, a few sentences. **What they overheard, they learned too:** if this turn set one of the player's own flags (`look` lists them as `<Name>'s own`) for something the others there also saw or heard, such as a story being told, name it after the file: `witnessed proposals/witnessed-<id>.txt <flag>`. Not for what happened to the player alone, such as a curse or being caught. Example: `Ana asked the innkeeper about the old mill. The innkeeper told her it burned down last winter, and that the miller's son still sleeps in its cellar; then Ana went out by the north door.` **People passed on the way** (a room the player walked through, where `move` showed `PEOPLE HERE`) saw them go by and nothing more: a sentence or two of just that, for them alone, with `witnessed proposals/witnessed-<id>.txt --in <room id>`. `witnessed` reminds you of any such room (`ALSO PASSED`).
  - **Offering them something** (a trade, a gift, or asking for something): the words go with `say`, as any words do, and the terms with `trade offer`. Write the terms exactly as the player said them, never improved, filled in or guessed, with the Write tool to `proposals/offer-<id>.json`: `{"to": "<their id>", "give": {"items": ["<item id>", ...], "coins": <n>}, "want": {"items": [...], "coins": <n>}}`, leaving out a side that's empty (a gift asks nothing; "give me your lamp" gives nothing). Then run `trade offer proposals/offer-<id>.json`. If the words don't make clear what is offered or what's wanted back, store nothing: the story tells the offer as made, unclear as it was. A refusal means it wasn't made (they aren't here, the player hasn't got it): say why in the fiction. The story tells what the player offered, never what the other makes of it: they decide on their own turn, when it's in front of them.
  - **An offer made to the player** shows in `look` as `OFFERS HERE: <id> from <Name> …`. If the DO line takes it, run `trade accept <id>`; if it turns it down, `trade decline <id>`; a counter-offer is a decline and then an offer of the player's own. If they leave it be, do nothing: it lapses. If `accept` refuses, nothing changed hands: tell why, in the fiction, from what it says. Only the player whose turn it is accepts or declines, and only what's offered to them.
  - **Grabbing what they hold:** when the DO line grabs at something another person here holds, and anyone could plainly see they hold it, run `contest <the player's stat> <their id> <their stat> --take <item>`. Pick each stat as for any check, from how each goes about it: `might` to wrench it away or hold on tight, `agility` to snatch it quickly or whisk it out of reach. They hold on as anyone would; they aren't asked, and you decide nothing else for them. Tell how it went as it happens, never the numbers, and put it in the onlookers' note: that's how the one grabbed at learns of it, and they answer on their own turn. One grab a turn. Only an open grab at what's plainly held: never coins, what's tucked away, or anything in a stash or a place, and nothing taken unseen.
  - Otherwise things pass between people only through `trade` or `contest`, never `gain`, `lose` or `coins`. Harming another person, or taking from them unseen, can't happen: narrate in the fiction why it doesn't come off, deciding nothing for the other person.
- When the player tries several things in one DO line, resolve them in order and stop at the first one that fails, or that a character would interrupt.

## 4. Narrate
- The narration is the story of their turn, and the only text that reaches them. It is set at the time it is now (`look`'s time of day): when the world's time has moved on since the player last acted, the story starts from now, not from where their last scene left off, and doesn't carry that scene on as if no time had passed (who is still there is what `look` shows). What they do with the time is theirs. It names no person, place, thing or arrangement that isn't in `look`, the content, or what the world agent made (no new helper, object, debt, custom or service that no file holds). Write it **last**, after every other command of the turn, including the state writes in step 5 and the onlookers' note (`witnessed`): `narrate` also records how things stand at that moment, into their memory.
- Write it with the Write tool to `proposals/story-<id>.txt`, then store it with `python3 rules/rpg.py narrate <id> proposals/story-<id>.txt`. That ends their turn. Don't write it anywhere else. Every other command of the turn (the outcome, the onlookers' note, `coins`, `flag`, `note`, `remember`) comes before it: after `narrate`, only `chronicle`.
- Begin with the story itself. No preface such as "Recording her reply, then narrating."
- The narration stays inside the fiction. Never mention rules, commands, flags, dice numbers (unless asked), world turns, generation or agents, and never explain why you record something ("so the content says to set…"): that reasoning stays in your tool calls. The player is always "you", never "the player".
- The story tells what happens, in the story's own voice, never yours: no rule put into words ("the poker is hers to hand over", "the offer is in front of her now"), nothing said of what someone else may or may not do, and no asides in brackets. When the player is mistaken about something in front of them, the story shows it as it is ("Dilly is still by the fountain, a few paces off"), without correcting them.
- Write in the second person and present tense. Keep it to two to four short paragraphs, vivid but brief.
- Tell what the player does and says and what comes of it, never what they think, feel, weigh up or decide beyond their DO line. Their reasons are their own (the JOURNAL line is theirs alone), and the story goes into their memory as what happened to them, so a thought you write there is one they'll remember having and never had. Not "You weigh it up: Hobb needs it more than you do"; just what they did.
- When someone speaks, give them their own paragraph and start it with their name and a colon: `Pell: "Well now," she says, wiping a glass.`
- Narrate the rolls truthfully, as fiction: "your blade glances off his hide" for a miss. Mention the numbers only if the player asks.
- For a `REFUSED:` result, explain in the fiction why the action didn't happen.
- After moving, describe the new room from the `ROOM TEXT:` that `move` printed, including the open exits. Mention blocked exits only as the content describes them. A `may grow` direction is a way that hasn't been explored. Mention it only as the room's prose does; when the prose says nothing about it, don't point it out, but if the player heads that way and going there is plausible, a new place can be found there.
- `move` can report more than the move itself. Weave each of these into the narration:
  - **`ENCOUNTER:`** something happened on arrival, and its effect has already been applied. Narrate exactly that.
  - **`CLOCK:`** time is running out, or the clocked event has just happened. Say so, from the content's `## If` sections for the clock's flag.
  - **`BUILT:`** something the player paid for is finished. Mention it when the player next sees that place, or as news if someone would tell them.
  - **`WORLD TURN DUE`:** run the world turn (see **World turns**) before you store the narration. Don't mention it.
- When the world's clock counts rounds, `round end` prints `BUILT:` and `WORLD TURN DUE` instead of `move`; the rounds procedure says what to do with them.
- Let `TIME AND WEATHER` colour descriptions.
- `CURSE:` in `look` means the player's words come out changed. The context says how they came out and what was meant: resolve what was meant, and narrate (and pass to agents, and to `say`) the words as they came out. Only the curse's own file says how it's cured.
- `METER:` in `look` is what play costs, in the game's own terms. Never mention it, except once when `look` reports `METER LOW` or `METER SPENT`: then let that line's text show lightly, in the story.
- End with a light prompt, such as what's in front of them or who is waiting for an answer. Don't list menu options.

## 5. Write state
Record anything the content says should change, in the same turn. Make these calls before you store the narration:
- `python3 rules/rpg.py flag set <name>` when a content file says to set a flag. Content files are the only source of flag names. Some flags are a person's own, things they learned or went through: `flag set` keeps those for the player alone, and `look`'s `FLAGS:` line lists them as `<Name>'s own`. Either way, set it for the player whose turn it is.
- Trades and gifts with the world's people: `coins ±N <reason>`, `gain <item>`, `lose <item>`. Between people, `trade` has done it. The reason is one word from the list, and nothing after it: `coins -2 purchase`, `coins +1 gift` (job, work, sale, purchase, trade, toll, order, reward, gift, encounter); never a phrase.
- **`ENDING:`** after a command means this turn has decided one of the game's own quests, for everyone. Read the quest (`show quests <id>`) and tell the player the ending that matches the flags, in their story, as something that happens in their life. Never say the adventure is over, or anything about finishing or starting again: a quest's `## After the ending` is for a lone player at a screen, and here every life goes on. **Tell only what happens now:** what can be seen and heard at this moment, never what comes later ("at midnight…", "by morning…", "when the town wakes…"), even where the quest's ending text tells it. Anything later happens through the world, if and when it does, and the people find it then. Then write what everyone else comes to see and hear of it, wherever they are: what the town would notice and say, in the third person and the past tense, nothing only the player knows, and again only what has happened so far, nothing that is still to come. Write it with the Write tool to `proposals/ending-<id>.txt` and run `ending proposals/ending-<id>.txt`; `narrate` refuses until you have. The others react to it on their own turns, as themselves.

- **Quests taken on:** everyone knows the town's problem; whether it's theirs to work on is their own. `look` lists the quests in their reach (`QUESTS:`) and whether each is taken on. When their DO line or JOURNAL line shows they mean to work on one, or they agree to a job someone gives them, run `quest take <id>`; when they say they're setting one aside, `quest leave <id>`. Reading the JOURNAL line for this is the one use it has: it is bookkeeping, never told in the story or acted on in the world. Hearing of a problem, or asking about it, isn't taking it on.
- **Chronicle:** when something significant happens (a quest step, a big choice, a fight won or lost, news the whole town would hear), add one line to the story so far: `python3 rules/rpg.py chronicle "<one line, past tense>"`, with no `--as`, at most 200 characters. `run status` shows it to whoever runs the next round.
- **What the turn came to:** every turn, before `narrate`, record in one word how what the DO line set out to do turned out: `python3 rules/rpg.py outcome <word> [<what>]`. `done`: it happened; `partly`: some of it did; `failed`: a check went against them; `refused`: someone in the world said no (a townsperson turned them down, another person declined); `out_of_reach`: it's in the world, but not for them this turn (they can't pay, it isn't here, it's too heavy, it's shut, it isn't the time; most `REFUSED:` lines), naming what they reached for; `not_there`: what they reached for doesn't exist in this world (no such person, place, thing or trade; a world agent's `REFUSED:` too), naming it as they put it. Judge it by what the DO line set out to get, not by how much talking happened: asking someone a question and getting the answer is `done`; asking for something and being told "not yet" or "wait" is `refused` or `out_of_reach`, not `partly`; `partly` is only for a DO line with several aims, some met and some not. When a person asks for something the world doesn't hold (a payment nobody owes, a job nobody offers, a person or trade the content doesn't have), it's `not_there`, even when a townsperson answers politely; and every time they reach for it again (a thing nobody sells, work nobody pays for, a plan that needs either), it's `not_there` again, naming it, never `partly`. Use `partly` sparingly. It's for the record only: never told, never acted on, and it changes nothing.
- **Details:** every detail you establish that anyone could come back to is kept, every time: a name, the look of a thing, where something was put, a price or a promise not in a file. `python3 rules/rpg.py note "<the detail>"` keeps it in this room (`look` shows it back as `ESTABLISHED HERE`). The next round may be run by someone who knows only the save: a detail not kept is one the world forgets.

`take`, `move`, `attack`, `use`, `check`, `work`, `sell`, `buy`, `rent`, `eat`, `sleep`, `say`, `witnessed` and `trade` have already written their results. Don't repeat them.

Never edit `state/save.json` or anything in `games/` directly.

---

# Agent characters
Use this whenever the player speaks to, gives something to, or otherwise deals with an `[agent]` character.

## Asking an NPC
Each time the character needs to respond, they are asked afresh with `python3 tools/voice.py npc <id> proposals/scene-<id>.txt` (and `--as`, as always), and you wait for it: it can take a minute. It runs their `npc-brief` itself, hands it on unchanged with your scene file after it, asks their own agent, and prints only the reply. You never see their brief, never write it, and never spawn an `npc` with the Agent tool: a fresh call each time is how they stay in step with state.

If it prints `REFUSED:` because the character speaks through you right now, voice them yourself as for `[minor]`. If it refuses that a character is not in this scene, they say nothing: never voice an `[agent]` yourself. `VOICE FAILED` means their agent didn't answer, twice: stop the turn there, storing no story, and tell the owner in one line; the rounds procedure stops as for a reply that fails, and the turn is taken up again from the log.

When the turn's outcome sets a flag that takes the character out of the scene (cowed, gone, defeated), ask them before the `flag set`, so their last line is theirs. If the flag is already set, their brief still works for someone who was here at the turn's `look` or `move`, and says it's their parting line.

Write the scene file with the Write tool, in exactly these two parts, under these headings (`voice.py` refuses a file without both):
```
## The scene so far
<the last few lines of this scene, at most about 8, each written as `<Name>: …` for whoever spoke (the player and anyone else here, by their names) or `(action)`; "(the scene just began)" if there are none. A scene ends when the player leaves the room.>

## What just happened
<the player's words from their DO line, quoted as close to verbatim as you can, and anything they visibly did, such as "holds out a wrapped parcel". Never their JOURNAL line. If a roll has just been made, its outcome in plain fiction, never as numbers.>
```

## Using the reply (SAY / INTENT / REMEMBER)
- **SAY:** narrate it in your own prose around the character's words. You may trim it. Drop anything that contradicts state or content, or that names a thing that doesn't exist. **State wins.** If the NPC claims something false, such as having an item it doesn't have, leave it out or have the character correct themselves.
- **INTENT:** these are proposals, not facts. Check each one against the character file's `## GM only` section and the rules:
  - If content allows it, make it happen with `rpg.py`: `flag set`, `lose`/`gain`, `coins`, or `check` when the content requires a roll.
  - If content doesn't allow it, it doesn't happen. Narrate the character hesitating, or simply not doing it.
  - An attack intent means combat begins, through `rpg.py attack` on the player's action or as the content directs.
- **REMEMBER:** if it is true to what actually happened, record it with `python3 rules/rpg.py remember <id> "<line>"`. Keep it to one short line in the third person about the player, e.g. "Brought me a gift. A friend, then!" Skip it if it says none.

## Two agent characters in one scene
When two `[agent]` characters are present and the moment naturally involves both, they may exchange lines. That happens when the player addresses both, or when one reacts to the other.
- Relay each line to the other character by asking them with `voice.py`, their scene file's "What just happened" being `<Name> says: …`.
- Each NPC reply counts as one line. Allow at most the number `look` gives as `AGENT LINES PER TURN`, counting the first response to the player. Then stop and hand the scene back to the player.
- Check every INTENT and REMEMBER from these lines the same way as above.

## Side scenes
`look` says `SCENE HERE` when two agent characters here could play a little scene, just for fun: an argument, a contest.
1. Read it with `rpg.py show scenes <id>`. In the narration, show it beginning, from its `## How it starts`, and let the player choose. Don't start it yourself. In the story it's simply what the two are doing; never call it a scene.
2. If the player takes it up (watches, joins in, eggs them on, asks what's going on), run `rpg.py scene start <id>`. If it refuses, the moment passes.
3. While it plays (`SCENE PLAYING` in `look`), each thing the player says or does gets one reply from each of the two: ask the first one with `voice.py`, then relay that line to the other as in **Two agent characters in one scene**. Every reply is a fresh `voice.py` call, as always: the brief it runs carries the scene and counts its replies.
4. When a brief says it's the last reply, when the scene reaches its `## How it ends`, or when the player loses interest, run `rpg.py scene end <id>`, adding `reward` only when `## How it ends` says it was earned. Then narrate the ending.

A scene changes no story flags. If the player walks off, it's over (`move` says so) with no reward.

---

# Filling gaps
The game's `generation:` policy (in `rpg.py show world`) says what may be created during a run. When the player reaches for something the content doesn't have, use the matching case below. If that kind isn't allowed, it doesn't exist. `world-brief` also refuses when the owner has switched that kind off or the meter can't pay for it; then, too, the thing doesn't exist.

| The player… | Do this |
|---|---|
| talks to an unnamed person the prose mentions (a dockhand, a fisherman) | generate an **extra** |
| heads a `may grow` direction from `look` | generate a **room**, then `move` there |
| searches somewhere plausible for something small | generate an **item** only if finding something fits; most searches find nothing |
| looks for someone who would plausibly be here (a fishmonger at the quay) | generate a **character** |
| asks a generated or minor character for work or help, and it fits them | generate a **side quest** given by them |
| orders something made from a maker (`look` lists `MAKERS HERE`) | follow **Orders** below |
| asks a builder to build something here (`look` lists `BUILD SPOTS HERE`) | follow **Orders** below, with `build` |

Never generate anything that would solve, shortcut or replace part of the main quest, and never answer a gap that the authored content deliberately leaves closed.

## How to generate
1. Write one line with the Write tool to `proposals/asked-<kind>.txt`: "The player: <what they said or did>".
2. Run `python3 tools/voice.py world <extra|room|item|character|quest> proposals/asked-<kind>.txt` (and `--as`), and wait. It runs `world-brief` itself, asks the world agent with that brief unchanged and your line after it, saves its JSON reply exactly as given to `proposals/world-<kind>.json`, and prints it. If it prints `REFUSED:`, the thing doesn't exist; `VOICE FAILED`, stop as for an NPC above. Never spawn a `world` agent with the Agent tool, and never write its brief, nor its reply (but for a reuse, below).
3. Run `python3 rules/rpg.py generate <kind> proposals/world-<kind>.json`. The script deletes the file once it's applied.
4. Then use the result:
   - **`REFUSED: proposal rejected`:** ask the agent once more on the same brief: add a line to `proposals/asked-<kind>.txt` saying what was refused and why, and run `voice.py world <kind> proposals/asked-<kind>.txt --again`, then `generate` again. If it fails again, the thing doesn't exist; narrate accordingly.
   - **Success:** read the new entity with `rpg.py show`, then play it like authored content. Generated people are `[minor]`: you voice them, from their file only. Their sales and rewards follow their `## GM only` lines. Something `brought back from an earlier run` is new to the player in this one: they haven't met.

The brief may list things from earlier runs; the world agent may bring one back instead of inventing (`{"reuse": "<id>"}`). Apply that reply the same way. When one listed is plainly who or what the player means, you may instead write that reuse reply yourself, with the Write tool to `proposals/world-<kind>.json`, and asking no one.

When a generated or player-made person, place or thing has come to matter (the player keeps coming back to it, or it was part of a big moment), you may tell the owner it deserves keeping for good: `python3 rules/rpg.py library suggest <id> "<one short line why>"`. It costs nothing and changes nothing in play; the owner decides.

## Orders
A maker makes things to order within their trade; a builder builds a small place at one of the room's build spots.
1. Run `python3 tools/voice.py world craft <maker> proposals/asked-craft.txt` (or `world build <builder> proposals/asked-build.txt`), and `generate craft proposals/world-craft.json` (or `generate build proposals/world-build.json`) on what it saved, as in **How to generate**. If it prints `REFUSED:`, they turn the order away in character.
2. If `generate` says they turn the order down, narrate that in their voice. Otherwise it reports what will be made and its `PRICE`: they describe it and name that price, never another. When the maker is an `[agent]`, put what will be made and its price in their scene file's "What just happened", so they name it themselves.
3. Only when the player pays, run `pay <id>` (or `pay <id> <item>` for an item `PRICE` lists in trade). Until then it isn't theirs. A made item is handed over at once; a building takes a while (`BEING BUILT` in `look`) and doesn't exist until `BUILT:` says so. An unpaid order waits (`ORDERS WAITING` in `look`).

## World turns
When `look`, `move` or `round end` says `WORLD TURN DUE`, run the world turn. During a turn, do it before you store the narration:
1. Run `python3 tools/voice.py world turn` (and `--as` during a turn), every time: the world has moved on since the last one. It runs `world-brief turn` itself, asks the world agent with exactly that, and saves its JSON reply to `proposals/world-turn.json`.
2. Run `python3 rules/rpg.py world-turn proposals/world-turn.json`.

Don't narrate the world turn. Its rumors surface later, when people talk: minor and generated characters may repeat them, and agent NPCs already see them in their briefs.

Some characters follow plans of their own on world turns: someone goes for a walk, falls asleep, bars a door. `world-turn` reports what each player can notice, naming them:
- **`SIGNAL for <name>:`** happened close to them. Work that line into their next narration as one sentence of what they see or hear, without explaining it ("Somewhere above, a door slams and a bolt shoots home.").
- **`NOW HERE for <name>:`** that character has just arrived where they are. In their next narration, narrate the arrival, then play the character as usual.
- **`OFF-SCREEN:`** nothing anyone could notice. Say nothing; the rooms and what people say will show it when someone gets there.

Never tell anyone what someone did off-screen, and never explain a signal. When they go and look, `look` and `show` already describe how things are now.
