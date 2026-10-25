# Design review: how the simulation plays out

Written 2026-10-25 by Claude at the end of the seventh session, for the eighth: a **discussion session**, not a build session. JW wants to step back and talk, at a higher level, about how the player agents are structured, what they know, how the game's architecture (quests above all) shapes what they do, and how the simulation plays out. The open decisions from the 14-round run (`PLAN.md`, *The long run*) start it off and give it context: answer them in that wider light, and keep tracking the fixes. Nothing here is decided; it is the evidence and the questions. **The eighth session answered section 1 and part of section 5:** see `PLAN.md` (*The eighth session*), `PERSON-STRUCTURE-PROPOSAL.md` section 6 and `SIM-WORLD-SPEC.md`.

## 1. What is waiting for JW (from `PLAN.md`, *The long run*)
**Four referee fixes** (Claude's recommendation: all four, a commit each):
1. **Belongings as last seen.** Stories showed Hobb's whistle "in his hand" four times after he'd said three times it was in his coat. The referee sees everything a person carries (`PEOPLE HERE`) but not what's in view, so the rule would be: mention another's belonging only as it was last shown.
2. **Agents asked outside the referee's context** (`tools/voice.py`, as `tools/ask.py` does for people). Round 10's referee rewrote all three briefs it gave the townspeople and the world agent; the rule alone has now failed twice.
3. **`chronicle` runs for no one, any time,** so a line after `narrate` isn't refused (Ambrose lost his memory of Hobb's round 1 to the same ordering slip, with `remember`).
4. **`/rounds` names the chronicle's 200-character limit** (9 of 14 first tries refused).

**Three content questions on The Thirteenth Stroke** (the recommended answer first):
1. **Should the world go on past its one night?** (a) once the quest is decided, time runs on into days (`times_after:` in `world.md`, a small kit feature, plus daytime text); (b) keep one night; (c) let time pass midnight regardless.
2. **What is money for?** (a) make what exists wanted and findable after the ending (Ambrose builds again, Nell's shop reopens, more paid work by day); (b) as (a) plus new people (a seller of fine things, a lodging house that charges rent); (c) leave it and study it as it is.
3. **Tibbersnatch after the shadows are freed:** (a) gone from the meadow by the next round; (b) stays, wanting nothing.

These may look different after the wider discussion: question 1 is really "what kind of world suits a simulation", and question 2 "what makes a person want something".

## 2. How a person is built today
- **The cast entry** (`games/<id>/cast.json`): name, model (Sonnet, Haiku or Opus), pronouns, attributes, health, buttons, belongings, home, and three passages in their own first person: personality, voice, motivations ("I want a place of my own; I hate owing anyone; I never spend a button I don't have to"). Plus an **opening**, the only knowledge given in advance.
- **The instructions** (`.claude/agents/player.md`, the whole system prompt): you are a person living your own life; what you're handed is everything you know; others are people like you; decide one thing, in a few sentences, and write a journal line saying why and what you're working toward. It lists what a person might do: speak, go, look, try, buy, sell, trade, ask for something to be made, work, wait.
- **Each turn is a fresh call** (`tools/ask.py`, `claude -p` under JW's login, no tools): the brief, as `rpg.py brief` prints it. Its sections: *Who I am (a note to myself)*, *How it begins* (first turn), *What you remember from before* (condensed, in their own voice), *Lately* (the last 5 rounds word for word: their DO and journal, the story they were told, what others said and did near them, how things stood after), *Where you are*, *You* (health, attributes, money, belongings), *What you're working on*, *People you've met*, *Places you've been*, *Talk going around*. By round 14 Hobb's brief was 34,000 characters, most of it *Lately*.
- **Memory:** rounds 1–5 are folded into a few paragraphs, by the person themselves, at the end of round 10, and so on every 5 rounds. Their own journal lines stay in memory, so a plan carries across rounds.
- **What they never get:** dice, flags, the rules, other people's private state, the log. Claude Code adds a few lines of its own to every call (a billing line, "You are a Claude agent…", the owner's email, the date); they can't be removed, and no one has yet asked about them (`DEVELOPING.md`, Known limits).

## 3. How the world is built
- **The Thirteenth Stroke was written for one player on one night**, then adapted: one main quest with two variants (free the shadows from the peddler's jar, or jam the town clock before it strikes thirteen), a deadline clock (switched off in the simulation), and times of day that run from half past ten to a minute to midnight and stop there.
- **One main quest for everyone.** It is the game's own quest, in every person's *What you're working on* from the start; their openings lead with its problem (the sleeping children). Some flags are personal (what you've heard), most shared (what the world is). When anyone decides it, everyone is told, and life goes on with nothing new to work on.
- **Added for the simulation:** a maker (Nell), a builder (Ambrose), a buyer (Mags), paid work (Nell's fizz-still, the gearloft), trades and grabs between people. The openings name Nell's and Ambrose's trades.
- **The world's people:** some are voiced by the referee from their file, others by their own agent (Pip, Tibbersnatch, Ambrose). A world turn every 2 rounds adds rumors, which people hear when townsfolk are near, and which steer them.
- **The referee** is a fresh session every round, working from the save and its own notes (the story so far, place notes, the townsfolk's memories).

## 4. What the runs show
Evidence from JW's two real runs and five test runs (2026-10-24 and 25):
- **The quest takes over at once and ends early.** Every person pursues it from their first turn; where a run went long enough it was decided in round 4, 6 or 7.
- **Money is almost never used.** Across all of them: one built shed (Hobb, 5 buttons, phase 1's last test), two trades (a poker given, then paid for), a gift of a button to a townsperson, a button found in the lane. No paid work, no sale to Mags, no order from Nell in any run. In the 14-round run every offer of money was refused by the townsfolk themselves.
- **After the ending they latch onto leftovers.** In the 14-round run all four spent rounds 8–14 on the peddler's bargain (a whistle for a jar that no longer existed), kept alive by his agent and by rumors.
- **Motivations show in journals more than in deeds.** Hobb wrote "keep saving toward my four walls" in six journals and never asked Ambrose to build; Dilly wants the credit in nearly every line; Marigold wants to be seen at the finish.
- **People cooperate and are cautious.** They form parties, wait for one another, verify before acting ("Hypothesis… Test…"), promise to go in together. No one has fought; one person, once, set out to take a thing back that he'd been told was his.
- **Models differ.** Haiku (Dilly) writes the shortest memories and repeats a catchphrase; Opus (Hester) costs about half of all the people's spend; Sonnet is in between.
- **The machinery holds.** No leaks in hundreds of briefs, stories and notes; the referee's cost is flat round after round; memory condenses in each person's own voice; endings reach everyone.

## 5. Questions for the wider discussion (a starting list)
- **What should drive a person: the world's quest or their own wants?** Should the opening present the quest, or should it be found? Should *What you're working on* list the game's quest for everyone, or only what that person has taken on, and their own aims?
- **Quests for many people:** one shared quest that ends in five rounds, or many smaller ones, personal or competing, some recurring? Where do scarcity and conflict come from?
- **Time:** what is a round in the world's time? A one-night adventure against a world that goes on for days.
- **Needs:** does money mean anything without things people need (food, rent, tools) or want badly enough to save for?
- **What people know:** a brief of 34,000 characters, five rounds word for word, a personality note written as their own; is that the right shape and size?
- **The referee:** how much it may invent, how continuity is kept between fresh referees, and moving more of its work outside its own context.
- **The instrument:** what is being measured, how runs are compared (seeds, casts, models), and what a "good" run is.

## 6. Where the evidence is
- **`PLAN.md`:** every step as built, and each run's results (under steps 22, 26, 35, 41, the contests draft and *The long run*).
- **`state/test-runs/`** (local, not in git): `long-14/` (the 14-round run: its log, save, `stories.txt` with every turn and story in order, `audit.txt`), `dry-42/` (the six-round test run after step 41), `dry-42-r7-staged/` (the staged grab, with the stand-in script). JW's real runs' logs are in `state/log/`.
- **Tools:** `python3 tools/audit.py <log> [--referee]` reads a log back; `python3 tools/probe.py <id>` shows what a person is sent, for free.
