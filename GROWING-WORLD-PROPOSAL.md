# Proposal: a town that grows

Written 2026-10-26 by JW with Claude, in a design discussion on claude.ai after Wendleford's two runs (wend-63 and wend-67), and updated after the blank-people run (blank-68). The same text, with a diagram, is JW's doc "A Town That Grows" on claude.ai. It is Phase 2 of `NEXT-STEPS-PROPOSAL.md`.

**Status: a guideline and a set of suggestions, not requirements.** Nothing here is built or approved as steps. Claude Code drafts each step against the code as it stands, for JW to approve, as `PLAN.md` does, and may depart from anything here where the code shows a better or simpler way, saying why. The project's rules come first: `CLAUDE.md`'s standing orders, `DEVELOPING.md`'s invariants (above all: only `rpg.py` writes the save, code decides outcomes, the kit knows no game) and `PLAN.md`'s *bar for now*.

**The point:** the town should grow by listening to what people reach for. The world's regular update reads what people asked for and didn't find, and answers in one of three ways: it makes the thing, says a clear no, or brings a hook to people. Code checks every change, as it does today.

## 1. The problem

In both runs the town stayed as written while people pushed against its edges. The same four things went wrong each time.

| What went wrong | Run 1 (wend-63) | Run 2 (wend-67) |
| --- | --- | --- |
| People asked for something the town doesn't have, and nobody said no | Hobb pressed Agnes for back pay over nine visits | Marigold sat with Ida eight times, but Ida has no way to pay her. Dilly and Hester planned a rope line, and no one in town sells rope |
| Things planted in the town were never found | Nobody went to Lark Lane (the cottage, the carpenter's yard, the building plot) or to Dunn's fields | The same. Hobb ended with 20 pennies, wanting "a door that locks"; the cottage costs 8 for a week |
| Townspeople didn't know what the game did with them | Agnes never knew the bridge work had already paid Hobb | Agnes's wages reached Hester while Agnes wasn't there |
| The referee made things up | A "reeve's clerk" who doesn't exist | A straightened iron axle the game had refused to make; Hester now remembers owning it |

All four come from one gap: the town can't react to what people do. It can only wait to be found.

The blank-people run (blank-68), with no personalities at all, points the same way. Nobody went to Lark Lane or Dunn's fields, though Jory told two of them to come to his yard; in three runs nobody has. Nobody ordered from a maker or rented, and the harvest was lost again. These misses come from the town, not the people. It also showed what the town leaves unsaid: two people lay down to sleep on the bank by the bridge on the first night, which Wendleford doesn't count as rest, and the free hayloft appears nowhere they could read.

## 2. How it works (the loop)

1. Someone reaches for something: rope, wages, a home.
2. The referee records it with the turn's outcome word (`not_there`, or `refused` by someone) and never makes the thing up.
3. The world's update (the world turn) reads two lists: what people asked for that the town doesn't have, and what's waiting that nobody has found.
4. It answers in one of three ways: make it real, say a clear no, or bring a hook to people.
5. Code checks and logs every change: fixed prices from the tiers, a daily limit, the town's never-add list.
6. People find the result on later turns, at most one world turn later.

Steps 2 and 3 rest on two fixes in `NEXT-STEPS-PROPOSAL.md` Phase 1: the referee recording `not_there` every time (in wend-67 it did so once, though two people spent about ten turns each on a rope line), and the world agent's rumors grounded in the town's files.

## 3. What to build

Three pieces, each built on something that already exists.

**Piece 1. Every townsperson speaks for themselves and keeps a record.**
- What: one setting so that all of a world's townspeople answer through their own fresh call (`tools/voice.py`), as the non-`minor` ones do now. Today the referee voices the `minor` ones from a few remembered lines.
- Their record includes what the game did with them: code writes in each sale, rent, wage and order ("Sold Hobb a loaf, one penny, morning of day 2"). Section 5 has the details.
- Why: a townsperson can only give a clear answer, or keep a promise, if they know what has already happened. In run 1 the missing record caused the back-pay fight.
- Cost: about 30 to 50 cents more per run.

**Piece 2. The world's update hears what people reached for.**
- What: the world turn already runs every `world_turns.every_moves` rounds (2 in the simulation preset: twice a day in Wendleford), sees the whole town and adds rumors and moves. Its brief gains two lists:
  - What people asked for that the town doesn't have: the referee's outcome words for each turn (`not_there`, `refused`), with what was reached for.
  - What's waiting that nobody has found: places never visited, quests nobody has taken on, things for sale nobody has asked about.
- Why: the run's own measurements become the signal for when to create something. No new way of noticing is needed.

**Piece 3. It answers in one of three ways.**

| Answer | When | Example from the runs |
| --- | --- | --- |
| Make it real | A town like this would normally have it, and the town's limits allow it | Rope for sale at Ned's stall on market day; Ida takes on a paid helper |
| Say a clear no | It doesn't fit, or a limit forbids it | Written into the right townsperson's knowledge: "There's no rope this side of market day." "I've company to offer, not wages." |
| Bring a hook to people | Something planted is waiting and nobody has found it | A rumor or a townsperson's plan: "Widow Mabry's asking round the square for a tenant." Dunn shouts across the river that he'll feed anyone who helps cut |

Today the update can add people, rumors, moves and side jobs. It would also need to add three new kinds of thing: something a townsperson sells, paid work at a place, and a line a townsperson knows. Every answer goes through code: the same checks, prices from the fixed tiers, and a log entry marking it as grown. Nothing is added by description alone.

**What the referee stops doing.** When someone reaches for something that isn't there, the referee says so in the story and records it with `not_there`. It never makes the thing up. Creating things happens in one place, the world's update, at most one world turn later.

## 4. Two kinds of missing thing

The update answers differently depending on whether a town like this would normally have the thing.

| Kind | Example | What the update does | Why |
| --- | --- | --- | --- |
| Something a town like this would have | Rope in a market town; plain sewing work for a seamstress | Makes it real at the town's ordinary prices, without fanfare | Its absence is a gap in the writing, not a fact of the town. It teaches people nothing except that the town is thin |
| Something that wouldn't normally be there, but would be interesting | A tinker who really does turn up; a stranger bidding for the cottage; the river rising again | Nothing, by its own choice. It goes into a test plan as a named event, written before the run | It changes the experiment. Whoever designs the test should choose it, write it down first, and keep it the same across the runs being compared |
| Something unusual that a person makes | Hester's wire hook | Nothing new: it goes to a maker or the builder as an order, which already exists | It is someone's own doing, and paid for, so it fits the rule that new things appear when someone pays. Sam already makes "small brass and copper gadgets made to someone's drawing"; Hester never asked him |

- **Telling the first kind from the second.** One test: would someone who lives in a town like this expect to find it within a day of asking? Rope, candles, a day's sewing: yes. A ferry, a stranger with money, a second cottage: no. The town's `## Tone` and its never-add list settle close calls. When in doubt, it is the second kind, and the answer is a clear no.
- **Ordinary additions become a list for JW.** Each one shows where the written town is thin. The end-of-run report lists them, and JW decides which to write into the town for good. That gives a middle answer to open question 3: additions vanish at the end of a run, so runs compare cleanly, while the written town still grows between runs.
- **Unusual things, later.** If a study wants to see how people meet the unexpected, a separate switch could let the update add one unusual thing every few days, off by default and logged apart. Not in the first version: the model's sense of how stories go would pull runs toward drama, and runs couldn't be compared.

## 5. Townspeople who know their trade

This expands piece 1. Today a townsperson's brief (`npc-brief`) holds their character sketch, a price list if they sell or let, the town's rumors, and up to six lines about the one person in front of them, written by the referee (`remember`, `npc.memory_lines`). They keep no record of money, remember no one else (Agnes talking to Hester knows nothing of Hobb), and have no list of what they don't do. Four parts fix that.

| Part | What it holds | Who writes it | Why |
| --- | --- | --- | --- |
| Sales register | Every sale, wage, rent, order and gift involving them: who, what, how much, when. Their brief shows their dealings with the person in front of them, and a one-line summary for everyone else ("Hobb: 7 spells hauled, 18 pennies paid") | The game, as each change happens | It can't drift or be made up. It fixes the Agnes problem in both runs, and the referee and the world's update read the same record |
| Trade card | What they sell, make, let or hire for, with prices, and a few "I don't" lines ("I don't lend the bridge's rope") | The town's author, or the world's update when it adds something | They can give a clear yes with a price, or a clear no, on the spot. Marigold's eight visits and Dilly's question about posts would each have ended in one |
| Trade knowledge | A few lines of what they'd tell anyone who asks about their work ("rope comes on Ned's cart on market day") | The town's author | It is the route to facts both runs missed. Nothing goes into people's pages; they learn it by asking the right person, as a human player would |
| Their own impressions | One line per person they've dealt with, in their own voice, rewritten after each conversation ("Hobb counts everything and owns his mistakes"), a few lines at most | The townsperson's own agent. The referee stops writing these | Attitudes stay consistent and in character. Facts stay in the register |

- **Wages paid while the payer is away** (Hester, paid with Agnes gone) still go in the payer's register, so the payer knows. Pay doesn't wait for the payer; that would add a new way to miss things.
- **Two checks for a town written for the simulation** (`validate --sim-strict`): every service has a trade card, and every important thing (each item for sale, place to let, paid job) is known by at least one townsperson besides its owner.
- **Ida, as an example.** Her file says she wants "someone to sit with her and sew while her eyes go," but gives her no way to pay. The author either gives her a paid helper on her card ("a penny a hem") or an "I don't" line ("I don't pay for help, but I'll teach").
- **Order:** the register first (step 1 below), then trade cards and trade knowledge, then their own impressions, which need every townsperson speaking for themselves (step 2).
- **Rejected:** long free memories for townspeople (they would drift and cost more each call, the referee's problem again); one shared mind for all townspeople (Kit knows things Agnes doesn't, and that difference is what makes asking the right person matter); townspeople setting their own prices or haggling (prices stay fixed in the game for now).

## 6. Guard rails

Without limits the town would hand people whatever they ask for, and there would be nothing left to measure: no scarcity, nothing missed, no hard choices.

- **A daily limit** on how much the world may add, counted in the end-of-run report.
- **A never-add list in each town.** For Wendleford: no second cottage, no ferry or boat, no second baker. Scarce prizes stay scarce. Its `## For the referee` notes already say some of this.
- **The town's own register and prices.** No magic in Wendleford, and anything sold is priced from its own price list.
- **Additions agree with the town's files.** In wend-67 the world agent made up a rumor that the ford is "too deep for wading" (the room and the rules say knee-deep, an easy check); townspeople repeated it, one person learned it as fact, and everyone stayed off the harvest. Anything the update adds is checked against what the town already says, and its brief carries the town's `## For the referee` notes and public knowledge.
- **A switch.** Growth changes the fork's founding rule that new things appear only when someone pays for them. With a switch, runs with and without growth can be compared on the same seed, and runs 1 and 2 stay comparable with later runs.

## 7. Rejected

- **One all-seeing overseer** that voices every townsperson and grows the world. One agent holding the whole town in its head drifts and invents, which is already the referee's problem (the axle). It is also hard to check: one long reply mixes voices, facts and new things. What has worked in this project is small fresh calls that only propose, with code checking each proposal.
- **Letting the referee create things.** It starts fresh each round, its job is applying the rules, and it already invents when it shouldn't. The power to create would reward that.
- **Hints in people's pages** ("the cottage is to let", "you must eat"). They would make runs easier to follow, but they remove the behavior being measured: what people find, and what they choose.
- **Creating things the moment they're asked for.** People would get whatever they name, mid-turn, and the referee would be the one deciding. Waiting up to one world turn keeps the decision in one checked step.

## 8. Order of work, and where the effect is

The biggest effect for the least work is steps 3 and 4.

1. **The sales register** (section 5). Cheap, and everything else needs it.
2. **All townspeople speaking for themselves.** One setting.
3. **The two lists in the world turn's brief.**
4. **Clear no and hooks.** They use what already exists (townspeople's knowledge, rumors, plans) and fix the two biggest wastes in the runs: people stalled for days on things that don't exist, and the cottage and harvest never found.
5. **Making things real.** Last, because it needs the new kinds of addition and the guard rails, and it is the one that can break scarcity.

Then one run with growth switched on, after steps 1 to 4, on the same seed as the run that ends `NEXT-STEPS-PROPOSAL.md` Phase 1 (Run A), and judged against it. Whether to build step 5 is then decided from what that run leaves unanswered.

## 9. Open questions for JW

1. **How much may the town add each day?** One or two things: it stays close to the town as written and runs are easier to compare, but people may still get stuck. More: fewer dead ends, but the town drifts further from what was written and comparisons get harder.
2. **Should the first version make things real, or only say no and bring hooks?** Only no and hooks: cheaper, and the rule that new things appear only when paid for still holds. With making things real: a richer town, but it needs the three new kinds of addition and changes that rule.
3. **Should what the town adds last into the next run?** No: every run starts from the same town, and runs compare cleanly. Yes: the town learns across runs, but each run starts from a different place.
