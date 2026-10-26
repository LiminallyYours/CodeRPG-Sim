# Proposal: how a person decides, and what drives them

Written 2026-10-26 by JW with Claude on claude.ai, after Wendleford's three runs (`wend-63`, `wend-67`, `blank-68`). The same proposals are section 7 of JW's doc "Person Structure Proposal" on claude.ai, and decisions F to J in his "Character Structure" doc. This is Phase 3 of `NEXT-STEPS-PROPOSAL.md`.

**Status: a guideline and a set of suggestions, not requirements.** Only the rule in section 1 is decided. Claude Code drafts each step against the code as it stands, for JW to approve, and may depart from anything here where the code shows a better or simpler way, saying why. The project's rules come first: `CLAUDE.md`, `DEVELOPING.md`'s invariants, `PLAN.md`'s *bar for now*, and `PERSON-STRUCTURE-PROPOSAL.md` section 6 (how a person is built, as decided).

## 1. The rule (decided, JW)

Code decides what the world does; only the person decides what they do. Dice, prices and the weather are the world. A person's choices, and what they remember, are theirs. Code never picks among a person's options, and never edits their memory to make them act in character: either would show the code's behavior, not the person's. This sets aside the code-chooses version of "how a person decides, beyond level 1" (`PLAN.md`, *Future discussions*; `PERSON-STRUCTURE-PROPOSAL.md` section 6, level 3) and the "let code supply the lapse" suggestion from the `wend-63` findings.

## 2. How a person decides today

Each turn is one fresh call (`tools/ask.py`), with the person's page as the whole context. `player.md` asks for two to four options, each with what it is for, `*` on the one chosen, then `DO:`, `JOURNAL:` and any `NO LONGER:` lines. The options go to the log only (the `action` entry); the referee acts on the DO line alone. Options are private and not kept in the page (`PERSON-STRUCTURE-PROPOSAL.md` item 14). Wants and things taken on show under *What you're working on*. In `wend-67` every reply had options, almost always four.

## 3. What the runs show

- **The sure thing wins.** Hobb listed the cottage as an option three times in `wend-67` and chose sure wages, food or sleep each time.
- **Options are often not real alternatives.** On the third night two of Hobb's four were the same.
- **Traits against the model's own grain don't show,** in both named runs: Dilly was reliable, Hester careful. JW's personality experiment points the same way: Opus, Fable and Sonnet all describe themselves as very agreeable, dependable and calm, Sonnet the most dependable.
- **Wants are what make people neglect their needs.** The blank people (no note, no wants, no history) ate 14 times to the named cast's 6, and paid for a bed at bedtime 4 times to 0.
- **Without a personality, the model plays a prudent stranger, not a helper.** No blank person helped the unpaid harvest; their journals called it unpaid and risky. The named cast at least took it on, so personality adds the urge to help, even when it goes into a plan the world can't serve.
- **A little personality grew from situation and luck,** each trait traceable to a starting place or an early roll: the one who started at the smithy became the practical earner; the one with two bad rolls never got ahead; the one who found the box became the organizer. None invented a past or asked who they were.

What this says: the decision form works (every reply weighs options and gives reasons). What's missing is something that carries an intention past one turn, options wide enough to include the long want, traits concrete enough to reach behavior, and a measure of how often people choose against their own stated priorities.

## 4. Proposed changes (each keeps the person deciding)

| Change | What | Why | Where it would touch (for Claude Code to check) | Try first |
| --- | --- | --- | --- | --- |
| A plan each morning | At their first turn of each day, the person also says what they mean to get done today and what they're working toward this week. It shows on their page as "What I've set out to do", which they keep, change or strike, as they do with `NO LONGER` | Each turn is decided in the moment, so the sure penny wins. A plan made once a day puts a long want on the page as their own intention, and carries "then I'll go to bed" across turns. Stanford's Generative Agents used daily plans for the same reason | `player.md` (a line or two in the first reply of the day, or a separate short call: draft both, pick the cheaper that works); the page's *What you're working on*; the save, per person | The bench: morning moments from the runs, with and without |
| Options that differ | "Two to four things that are truly different from each other, not small variations on one idea" | Fixes repeated and narrow options. On the bench, options tied to their own wants raised Hobb's wish for a shed in 4 of 5 replies, against 2 of 5 | `player.md` wording only | The bench: the same moments, both wordings |
| Traits as habits with triggers | "When something more exciting turns up, I drop what I promised and mean to get back to it" in place of "I lose track of promises" | A concrete situation reaches behavior; an adjective doesn't | `rules/people/generate.md` (how `how_i_am` is written), `roundtrip.md`; the made cast entries | The flip test (Test Lab test 19): Dilly's Reliability from 2 to 5, all else the same, once in today's wording and once as habits |
| People rate their own options | Each option rated against what comes first for them; they choose as now. The end-of-run report counts how often the chosen option is not their own top-rated one | Makes "the safe pick beats the stated want" a number (Test Lab test 20). Code never uses the rating to choose | `player.md`'s `OPTIONS` line; the `action` entry; `tools/audit.py` | The bench: check that rating doesn't change what they choose |

## 5. Inner drives, as an optional goal set

- **What:** six of the 19 attributes in `rules/people/defaults.json` are cravings: Seeks company, Kindness (helping), Wants to be seen, Curiosity about the world, Risk-taking (a thrill) and Initiative (keeping busy). Each can become a drive that runs low over time, shown in words on the page ("It's been a while since anyone really noticed you"), never as a number.
- **The hidden rating sets how fast it drains:** 5 quickly, 4 slowly, 3 (ordinary) or below no drive at all. It drains on the seeded dice, so the person is never sure when, and runs stay comparable.
- **Topped up by what they do:** by code where the game already knows (help given, a gift, effort on shared work), otherwise by the referee's judgement at the end of the turn, through the existing command for meeting a need (`meet <need>`). Never by the person's own say-so.
- **Built on what exists:** a drive is close to a need whose clock is the person's rating rather than the world's. Reusing the needs code is likely the simplest way; Claude Code to judge.
- **Not for ways of behaving** (Honesty, Reliability, Trust, Temper and the rest): nobody craves breaking promises. Those use the habit-style wording in section 4.
- **If words alone are ignored,** as hunger mostly was, a small cost when a drive is empty, like tiredness. That's the world deciding an outcome, not a choice, so it keeps to the rule. Open question 5 below.
- **Optional:** one switch per goal set, for the whole run first; per person later, through the cast entry.

## 6. Goal sets, and a ladder of runs

| Goal set | Example | Comes from | Exists today? |
| --- | --- | --- | --- |
| Body needs | food, sleep | the world file, plus a switch | Yes |
| Life wants | a cottage, a ribbon | the cast entry, plus a switch | Yes |
| Things taken on | the wage box, the harvest | the person taking it on | Yes |
| Inner drives | to be seen, a thrill, keeping busy | the hidden ratings | New |
| Their own plans | today's plan, this week's | the morning plan | New |

The goal sets give a ladder of runs on one seed, each adding one set: blank people with needs off; then body needs; then life wants; then inner drives. Each step shows what that kind of motivation adds (Test Lab test 18). `blank-68` is close to the second rung (blank people, body needs on), but on a different seed and the code before Phase 1, so the ladder would rerun it.

## 7. Set aside

- **Code choosing among options, or editing memory to supply lapses:** the rule in section 1.
- **Listing and choosing in two calls:** double the cost, and the same model still picks the safe option.
- **Switching models to free the traits:** JW's experiment shows all three share the same self-portrait.
- **A menu of what's possible here:** it removes the finding-things behavior being measured.
- **A line about time in `player.md`:** the fix for time is the world's (stories that let the hours pass, `NEXT-STEPS-PROPOSAL.md` Phase 1), not a nudge to how people think.

## 8. Order (proposed)

1. The morning plan, on the bench.
2. On the bench together: options that differ, habit-style traits with the flip test, and the self-rating.
3. Inner drives, in words only, on the bench.
4. A full run with whatever earned it, on the seed of Runs A and B, judged against Run B.
5. The ladder, if JW wants it (four runs, about $30).

The bench passes can be drafted and tried while Phase 2 is built; nothing from them goes into a full run until Run B is judged.

## 9. Open questions for JW

1. **(F) The morning plan.** Yes: people carry their own intentions across turns, at one short addition a day each. No: each turn stays decided in the moment, and the long wants keep losing to the sure thing.
2. **(F, detail) Should the morning plan see yesterday's options?** Yes: a person can pick up what they passed over, but options stop being private to the turn they were made in, which reverses item 14's choice. No: the plan comes only from the page as it is.
3. **(G and H) Options that differ, and traits as habits.** Both are wording, tried on the bench first. Yes: cheap, and the flip test tells whether written traits reach behavior at all. No: they stay as now.
4. **(I) People rate their own options.** Yes: a number for "chose against their own priorities", for the cost of a few words a reply; the bench checks the rating doesn't change what they choose. No: the audit reads the options' "for" words only.
5. **(J) Inner drives.** Yes: craving-type traits run low and show in words, with a switch per goal set and the ladder to compare. No: traits stay as written descriptions only. If yes: **a small cost when a drive is empty?** Yes: it makes the drive felt, as tiredness is, but it's a new penalty a person didn't choose. No: words only, and we see whether words are enough.
