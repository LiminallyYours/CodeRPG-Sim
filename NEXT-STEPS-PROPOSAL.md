# Proposal: next steps

Written 2026-10-26 by JW with Claude on claude.ai, after Wendleford's three runs (`wend-63`, `wend-67` and the blank-people run `blank-68`), from a review of the runs and of JW's design docs on claude.ai.

**Status: a proposal for Claude Code to review, not requirements.** Nothing here is approved as steps. Claude Code reads it against the code and `PLAN.md`, drafts each step for JW to approve as `PLAN.md` does, and may change the order or the content where the code shows a better or simpler way, saying why. The project's rules come first: `CLAUDE.md`'s standing orders, `DEVELOPING.md`'s invariants and `PLAN.md`'s *bar for now*.

**In one line:** first fix what spoils the measurements, then let the town answer what people reach for, then work on how people decide, then build the tools that make experiments repeatable. Each phase ends with something measured, so we know it worked before the next one starts.

Detail lives in two companion files:
- `GROWING-WORLD-PROPOSAL.md`: Phase 2, a town that grows.
- `PERSON-DECISIONS-PROPOSAL.md`: Phase 3, how a person decides and what drives them.

## The rule over all of it

Decided by JW (26 October): **code decides what the world does; only the person decides what they do.** Dice, prices, weather, what a townsperson sells and what the town adds are the world. A person's choices and memories are theirs: code never picks among a person's options, never edits their memory to make them act in character, and never acts on their behalf. Anything below that seems to cross this line is a mistake in this proposal.

## Why this order

- **Foundations first.** Two problems spoil every measure: stories that carry a scene across hours (so people rarely sleep), and the referee and the world agent inventing things (the reeve's clerk, the straightened axle, the ford "too deep for wading"). Two of the fixes are also things the growing world depends on: `not_there` recorded every time, and a world agent that doesn't make up facts.
- **The town next.** Three runs with three different casts, the last with no personalities at all, missed the same things: nobody went to Lark Lane or Dunn's fields, nobody ordered from a maker, rented or helped with the harvest, and the harvest was lost every time. When the cast changes and the misses don't, the cause is the town. This is the biggest lever.
- **People after.** Until the town can answer, a person stuck on something that doesn't exist looks the same as a person choosing badly. Once it can, their choices can be read cleanly. The bench work for this phase is cheap and can start earlier, but nothing from it goes into a full run until the town's run is judged, so each run changes one thing.
- **Test tools last.** They make experiments repeatable once there are experiments worth repeating, and they're best shaped by the first few real ones.

## Phase 0: JW's answers

Ten questions wait in `PLAN.md` step 67 (*Open questions for JW* and *Further open questions from the blank run*), each with Claude Code's recommendation first. The review's lean: **Claude Code's recommendation on nine of the ten, and (b) on sleeping out of doors.** Two people lay down on the bank by the bridge on the blank run's first night and got no rest at all; a world should say what that's worth, and a rough night is what it would be. JW decides; this is only a lean.

Two notes on them:
- The people's question (a line about time in `player.md`) is best left at (a), no change. The fix for time is the world's (stories that let the hours pass), not a nudge to how people think, which is what's being studied.
- Fixing the ford's wording and Ida's pay by hand closes two gaps the growing world would otherwise answer. That's fine: plenty stay open (rope, Lark Lane, the harvest), and Runs A and B below share the same town.

Two new catches from the blank run, not yet in `PLAN.md`:
1. **A gift lapses if the giver walks away in the same turn.** In round 11 Entity1 said "I count out two pennies into their hand", offered them to Entity3 (`trade offer`, nothing asked back), then moved north in the same turn; the offer lapsed as they parted (`why: parted`), so the pennies never moved, though the words said they had. Options: (a) an offer that asks nothing back, made face to face, stays open until the receiver's next turn even if the giver has gone, and the receiver still accepts or declines (recommended: the receiver keeps the choice, and the words come true if they take it); (b) the referee is told not to move the giver after an offer in the same turn (fragile: it rests on the referee remembering); (c) leave it.
2. **The referee filled in what a blank page left out:** it called the cast "travellers", and Entity3 learned "Entity1 is another traveller" as fact. One generic line with the other slips (the open question on the referee's slips): never describe a person as anything their page and the world's files don't say.

## Phase 1: foundations

A commit each, drafted against the code first. Most are the answers to Phase 0.

1. **Going to bed in the evening counts** (open question: going to bed early).
2. **Stories let the hours pass:** each ends with the person's own doing done and the rest of that time of day going by; nobody left waiting on them; no story ends on a question ("What do you do?"); what the DO line says they'll do after (eat, go to bed) is carried out (open question: stories that let the hours pass). The bench found that a closed scene is what moves people on; one bench pass with the new wording before the run is worth its cost.
3. **The world agent's rumors are grounded:** its brief carries the world's `## For the referee` notes and public knowledge, and rumors tell what people did and said, never new facts about places or things (open question: rumors). The growing world's additions go through the same agent, so this comes first.
4. **The referee's slips and `not_there`:** coins, commands before `narrate`, names not ids, "reaching again for something no file holds is `not_there`", and the new line about describing people (open question: slips). This is the first link in the growing world's loop.
5. **The gift that lapses** (new catch 1), if JW takes (a).
6. **Wendleford's wording:** the ford can be waded with care, stake to stake; Ida's sewing paid, or its line taken out; "turns" reworded in `harvest.md` and `dunn.md`; sleeping out of doors as JW decides.
7. **The checks:** the leak scan reads only what people read; "turn" added to the leak words; and `validate` holds a world's own text (places, townspeople, quests, public knowledge) to the same forbidden-word list as people's pages, since townspeople and the referee repeat it. The last is the *World Framework* doc's suggestion; if it's too blunt for ordinary English ("turns the key"), a warning rather than an error.

**Gate: Run A.** The named cast, a fresh seed (call it S), 14 rounds, the usual setup (a scratch copy, the spend guard, the dashboard, `tools/rounds.py`), about $7.50, approved separately. Judged against `wend-67` on:
- nights slept before day 4 (was 3 of 12);
- stories ending on a question, or carrying a scene across hours (was common);
- rumors or stories that contradict the world's files (was several; aim: none);
- every reach for something absent recorded `not_there` (was 1 in the run);
- refusals (was 19);
- to watch, not to judge: whether anyone now helps with the harvest.

**Run A is also the "before" for Phase 2:** the same seed, the same cast, the same code minus growth.

## Phase 2: a town that grows

As `GROWING-WORLD-PROPOSAL.md` describes, in its order: the sales register; every townsperson speaking for themselves; the two lists in the world turn; clear no and hooks; then making things real. A switch turns growth on and off.

Its three open questions (its section 9) go to JW before its step 3. The review's lean: start at two additions a day; build steps 1 to 4 and run before deciding on step 5 (below); additions don't carry into the next run, but the end-of-run report lists them for JW to write into the town by hand.

**Gate: Run B,** after steps 1 to 4 (no making things real yet): the same seed S as Run A, the same cast, growth on, about $8. Judged against Run A on:
- visits to Lark Lane and Dunn's fields;
- help given with the harvest;
- turns spent reaching again and again for something the town doesn't have;
- townspeople's answers agreeing with their register (no back-pay disputes);
- every addition within the limits and agreeing with the world's files;
- cost per round.

The same seed keeps the world's rolls and variants alike; people's choices still differ, so one pair of runs is a signal, not proof. **Then JW decides on step 5** (making things real) from what Run B left unanswered. That answers the growing-world proposal's open question 2 with evidence instead of a guess.

## Phase 3: how people decide

As `PERSON-DECISIONS-PROPOSAL.md` describes. In short: a plan each morning that people write and keep themselves; options that are truly different; traits written as habits with triggers, checked with a flip test; people rating their own options, as a measurement only; and inner drives as an optional goal set. Bench first, then one run with what earned it, then the motivation ladder if JW wants it. Its decisions (F to J) are open and listed there.

The bench passes need no full run, so they can be drafted and tried during Phase 2; nothing from them goes into a full run until Run B is judged.

## Phase 4: test tools

From JW's *CodeRPG-Sim Test Lab* and *World Framework* docs (on claude.ai). An outline only: a detail file comes when Phase 3 is under way, shaped by its experiments.

- **A test file:** the question, the prediction, the arms (what differs between them, and only that), the size (rounds, runs per arm), the measures, the budget.
- **A runner** (`tools/experiment.py`): sets each arm up in its own scratch copy, runs it under the guard, keeps the record as `state/test-runs/` does today, and writes the audits side by side. It replaces the hand-made guard and copier scripts kept with `wend-67`.
- **The bench by rule:** conditions that change a frozen moment's page by a stated rule (a flipped rating, a line added), not by hand.
- **The world's testability declarations** (*World Framework*): knobs, staged starts, named variants, manual events, an answer key, the coverage list. Format and checks only, so they fit the bar.
- **An Experiments view** on the dashboard, and a way to draft a test with JW (a `/design-test` command or skill).
- **First uses:** the motivation ladder (Test Lab test 18), the flip test (19), choices against their own rating (20) and the unwatched test (1).

## Ways of working that carry through

- One change per run where possible; before and after on the same seed.
- The bench before a run whenever a change is to what people are told.
- Every run approved and budgeted by JW beforehand.
- A commit per agreed step, `sh tools/check.sh` before and after, no push without JW's say-so.
- This file and its two companions are guidelines. Where the code disagrees, the code wins and the file is corrected.

## Rough budget

| Phase | Spend |
| --- | --- |
| 0 | None |
| 1 | Builds free; a bench pass about $0.30; Run A about $7.50 |
| 2 | Builds free; voicing every townsperson adds about $0.30 to $0.50 a run; Run B about $8 |
| 3 | Bench passes about $2 to $4; one run about $8; the ladder about $30, only if JW wants it |
| 4 | Builds free; runs as experiments, each approved |

Through Run B: about $16.

## Rejected

- **The growing world first, foundations later.** The world turn would read outcome words the referee doesn't reliably write, and a world agent that invents facts would be the one adding things.
- **People's decisions first.** Until the town can say no or bring a hook, a poor choice and a dead end look the same.
- **A fresh seed for Run B.** It would mix the effect of growth with the luck of the dice.
- **Building the test runner first.** Two more runs by hand cost less than designing a runner before we know what the experiments need.
