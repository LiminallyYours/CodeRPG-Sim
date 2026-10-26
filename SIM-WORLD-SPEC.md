# Spec: worlds for the simulation

Written 2026-10-25 by Claude with JW, in the eighth session (a design discussion), from the seven runs so far and the 14-round run's stories read in order. **Status: a first draft.** Section 2 holds lessons JW asked to keep in a document of their own; section 4 (the test world, Wendleford) is decided in outline, its numbers still to tune; what is listed in section 6 is still open. Nothing here is built. `PERSON-STRUCTURE-PROPOSAL.md` is the person's side; this file is the world's.

## 1. What this is for
Two uses:
1. **The new test world** (section 4): a world built as an instrument, to see whether people's wants, needs and personalities show in what they do.
2. **Every world generated later** (the forge, phase 2), test world or not: what a world must have and must avoid when several people live in it for many rounds, rather than one player for one evening.

The kit still knows no game (`DEVELOPING.md` invariant 7): what is particular to a world lives in its folder; what this spec asks of the kit is a feature or a check that works for any world.

## 2. What the runs taught about worlds
Each lesson: what happened, then the rule or check it implies.

1. **Every character and place must follow every way the quest ends.** In the 14-round run Tibbersnatch's craving for the whistle had no "and not shadows_freed", so after the shadows were freed his agent kept offering an empty jar for it, and all four people spent rounds 8–14 on that bargain. (This restates JW's fifth-session decision: a world's places and people follow every ending, since life goes on after one.) *Check:* `validate` warns when a character's want or trade section isn't conditioned on the quest's ending flags. A warning, not an error: The Thirteenth Stroke stays as it is (JW).
2. **An ending is an event, not an epilogue.** The quest's ending text, written to close a one-player game, says the clock strikes twelve "and when the town wakes the meadow is empty"; the referee put it in everyone's ending note, though the world's clock stops before midnight and the peddler was still there. *Rule:* ending text says what happens now; anything later happens through the world (time passing, a plan, a world turn). The referee's side is fix 5 in `PLAN.md` (an ending note tells only the present).
3. **A world must say what happens after its story.** The Thirteenth Stroke's times run from half past ten to a minute to midnight and stop, so 14 rounds ended at "a quarter to twelve" with "before midnight" still urgent and no day for work, saving or building. Hobb: "Four walls of my own can wait one more night." *Kit:* time goes on (a cycle of times of day that repeats, days counted), whatever the quest does.
4. **One big quest takes everyone, then leaves nothing.** Every person pursued it from their first turn; it was decided in round 4, 6 or 7 wherever a run went that long, and one person's deed ended everyone's purpose. *Rule:* hooks of different sizes, at least one open-ended or recurring; the world's problem is known to all but taken on by choice (`PERSON-STRUCTURE-PROPOSAL.md` section 6, item 13).
5. **The economy has to connect to wants and needs.** Across seven runs: one shed built, two trades, a gift, a button found. The makers sold things nobody in the cast wanted (Marigold loves fine things, and no one sells any; Hester spends on powders, and no one sells powders); every townsperson refused money, in their own words, because their files say so. *Rule:* each kind of want in the cast has something that serves it, for a price; some townspeople want money; a price is told when someone asks (never announced).
6. **Practical facts belong in public knowledge, not in openings.** Who makes things and who builds was told once, in each opening, and gone after turn 1 (`PERSON-STRUCTURE-PROPOSAL.md` R6). Makers and builders may be named there; which places pay for work, and who buys, may not.
7. **Rumors steer people strongly.** Hobb found the whistle through a rumor; world turns kept the leftover bargain alive. *Rule:* rumors follow endings too, and a world turn's brief carries what has ended.
8. **Worlds written for one hero leak the hero.** Townspeople called the cast "Umbrella", the original's lone player's trade. *Check:* no content names the original player or their trade; townspeople address people by name or a form that fits anyone.
9. **The layout makes the party.** One path from the square to the meadow put everyone together; a round with all four in one room cost the most and produced the most talk. *Rule:* places that are apart and each worth visiting, so people split up for reasons of their own and meet again.

## 3. What every simulation world needs
- **Time that goes on:** times of day that cycle, days counted, and a stated amount of world time per round.
- **Needs** that grow more pressing with time until met, and things in the world that meet them, for a price or for work (section 5).
- **Hooks of several sizes:** a shared problem everyone knows, smaller jobs, and openings tied to the kinds of want the cast has; at least one hook that recurs or never quite ends.
- **Scarcity:** at least one thing several people would want and only one can have.
- **An economy that closes:** ways to earn (work, a buyer, jobs), ways to spend (needs, wants, makers, a builder), prices told on asking, townspeople who take money.
- **Consistency:** every character, place and rumor follows every ending (section 2, lessons 1, 2 and 7).
- **Public knowledge** holding the practical facts (who makes, who builds, how money works), never which places pay for work or who buys.
- A stricter check than `--sim-complete` holds a world to this (section 5); The Thirteenth Stroke keeps passing `--sim-complete` and isn't held to it.

## 4. The test world: Wendleford

### Decided (JW, 2026-10-25)
- **A new world, built for the purpose.** The Thirteenth Stroke stays as it is.
- **A plain market town:** no magic. It tests whether the four people carry over to a different world, gives the model's sense of how fairy tales go less to pull on (`PERSON-STRUCTURE-PROPOSAL.md` section 1), and makes prices and needs read naturally.
- **The premise:** Wendleford, a small market town on a river, at harvest. Two nights ago a flood took the mill bridge; the mill and Farmer Dunn's fields are across the water, reachable only by the ford downstream; the barley is standing and rain is coming. Everyone knows; nobody is obliged to help.
- **The shared problem, at two sizes:** an ongoing one (the harvest and the bridge) and a small mystery (the wage box), so there is a choice of how to help.
- **Needs: a bed and food.** An unmet need brings **a small, lasting setback**, told in words, never numbers: a night without proper sleep, tired the next day (things that take effort go a little harder); a day without food, hungry; two days, weak (strength down one) until fed. Nobody is hurt or dies of it.
- **Night is a turn like any other:** sleep is something a person chooses to do (a paid bed, the hayloft, or rough); a night spent otherwise counts as no sleep.
- **Money is tight:** daily needs cost about 3 pennies, work pays 1–3 a visit, people start with 4–6, so everyone must earn by about day 2 and saving takes focus.
- **Two scarce prizes:** the cottage on Lark Lane (one tenant, first to pay) and the harvest honour at the supper (for whoever the town saw help most, worked out from the effort counts).
- **Effort on shared work is counted per person by code** (a shared project: work adds to a total; stages set flags), the direct measure of caring.
- **The town's problem reaches everyone's needs:** if the harvest isn't in before the rain, bread costs more from day 4.
- **Each person starts in their own situation,** all with little money, each with a need coming due within a day or two (for example: one boards at their employer's in return for work hours, one sleeps in the hayloft by the reeve's leave, one has a bed paid through tonight, one a room with rent due on day 2). The generator writes them from the archetypes and this world (`PERSON-STRUCTURE-PROPOSAL.md` 5.9).

### The outline (sketched by Claude, agreed by JW; numbers to be tuned)
**Time.** A round is a quarter of a day: morning, afternoon, evening, night. The run starts on the morning of day 1, a market day; the next market day is day 4. The rain comes on the night of day 3 (round 12) whatever anyone does, so a 14-round run sees what follows.

**Places (8).**
| Place | What's there | What it would show |
|---|---|---|
| Market Square | the hub; the pump; the notice board (the reeve's reward notice); the baker's stall; on market days, Ned Pike's stall of cheap seconds | bargains, news, meeting by chance |
| The Wheatsheaf (inn) | beds, suppers, talk; work washing pots (wits) | spending on needs; where rumors are heard |
| Fenn's, the draper | maker of clothes and finery to order | wanting fine things; saving for them |
| The Smithy | maker of tools and trinkets; work at the bellows (might); a scrap heap | earning; tinkering |
| The broken bridge | the rebuilding, paid by the reeve (a shared project); the wreck in the water (the mystery) | paid help; investigating |
| Dunn's fields and the mill (across the ford, a check to cross) | the harvest, unpaid, a meal for half a day's help (a shared project); the miller's lad | caring without pay |
| Lark Lane | Widow Mabry's empty cottage to let; a building plot beside it | wanting a home; the scarce prize |
| The tithe barn | the reeve's office; the hayloft (sleep free, but rough) | doing without; owing a favour |

**The town's people (9; ★ voiced by their own agent).** ★ Reeve Agnes Pollard (runs and pays the bridge work; lost the wage box; offers its reward; says who gets the harvest honour); ★ Jory Crane, carpenter (the builder: sheds, huts, lean-tos; wanted on the bridge too: he says so, but building a shed doesn't slow the bridge, for now); ★ Kit, the miller's lad (saw something bobbing on the flood night); Tom Harrow, innkeeper; Ida Fenn, draper (maker); Sam Tolley, smith (maker); Farmer Dunn; Widow Mabry; Ned Pike, dealer (buys things; sells seconds on market days). Every one of them takes money for something.

**The ongoing problem.** The harvest: about 8 person-turns of help before the rain; if it's in, a harvest supper on the evening of day 3; if not, part of the crop is lost and bread costs more from day 4. The bridge: about 12 person-turns of paid work, no deadline; while it's broken the far bank is reachable only by the ford.

**The small mystery: the wage box.** On the flood night the reeve's box of bridge wages vanished; until it's found she pays bridge work at half rate. It was swept off the bridge and is caught in the wreck under the water: found by searching the wreck (a check) or by asking Kit; a false lead in the rumors suspects the newcomer at the smithy. One deed ends it; the finder gets 4 pennies and the town's thanks, and only one person can be the one who found it.

**Prices (pennies, in the world's own `balance.json`; tuned on paper when it is written, then by the test run).** A bed at the Wheatsheaf 2 a night (the hayloft free, but rough: tired the next day); bread or a supper 1, or a meal earned at Dunn's or washing pots; finery about 4 (made as a trinket, at Wendleford's price for trinkets, so the smith's small things cost the same); a shed 10; the cottage 8 for a week, paid up front.

**One opening per person's want.**
| Person | Want | What serves it |
|---|---|---|
| Hobb | a place of his own; hates owing; thrifty | the cottage (scarce), or a shed on the plot from Jory; the hayloft is free, by the reeve's leave (owing) |
| Marigold | to be admired; fine things | finery from Fenn's; the harvest supper and its honour |
| Dilly | the credit; restless; can't resist a bargain | the wage box (one finder); Ned's seconds on market days |
| Hester | to invent; helps unasked; curious | the scrap heap and the smithy; the bridge as an engineering problem; the mystery |

**Ways of acting, all reachable on day 1:** use, build, influence, investigate, convince, buy, sell, trade, stay silent, go, work, give and help, grab, wait. Fight can happen but has no reason to; for a plain town that is honest, and noted rather than given an invented foe.

**How it is made:** written by hand in a build session from this outline; the forge for simulation worlds isn't built (phase 2), and forging a second world against this spec later is the real test of the spec. The cast: the same four people, made for this world by the generator, its first real use.

## 5. What the kit needs for it
- **Time after the story:** a world lists times of day that cycle and counts days (`times_after:` or a cycling `times:`), with daytime text where places and people change.
- **Needs:** a setting switches them on or off (like curses and the deadline clock), so a run can compare needs on against off; a world lists its needs (`needs:`: food daily, sleep nightly), each met by an item, a room's service, a payment or an act (sleeping); the engine tracks each person's, makes it more pressing with time, applies the setback when it goes unmet (section 4) and says it in words in the brief.
- **Things for sale at set prices:** bread, a bed, a week's rent, a dealer's seconds. Today buying exists only as making to order.
- **Shared projects:** work at a place adds to a shared total, counted per person in the log, with stages that set flags at set amounts (harvest in, bridge mended); the harvest honour is worked out from the counts.
- **A world's own prices** (`games/<id>/balance.json`); no new kind of item: finery is a trinket at the world's price (JW), and a separate kind is added only if a run shows it's needed.
- **"What you're working on"** shows needs, wants and things taken on side by side (`PERSON-STRUCTURE-PROPOSAL.md` section 6, G).
- **Checks:** the ending-consistency warning (lesson 1); no content naming the original player (lesson 8); a stricter check than `--sim-complete` (its name settled in the build), which Wendleford is held to: time that goes on, at least one need and what meets it, things for sale, a shared project, hooks of more than one size. The Thirteenth Stroke keeps passing `--sim-complete`.

**As built (steps 56–60, eleventh session, 2026-10-25):** time (`days: yes`, timed events `## At:`), needs (`needs:`, `sleep_at:`, food items, places to sleep, `meet`), things for sale (`sells:`, `bed_price:`, `rent:`), shared work (a room's `project:`, `most_<project>`), and **`validate --sim-strict`**. What code checks: days; at least one need, each with something to meet it; a seller; shared work; a quest; something scarce (a place to let or a thing in short stock); public knowledge present; no `## Who the player is`; and, as errors, the two warnings every world gets from `validate`: a character's conditional text or plan that turns on the story's flags but never on how the quest ended (lesson 1), and "the player" in what a townsperson's agent reads (lesson 8). **What only a reader can judge** (read before a run): each kind of want in the cast has something that serves it, for a price; some townspeople take money; public knowledge never says which places pay for work or who buys; rumors and timed events follow the endings too (lesson 7); places apart and each worth visiting (lesson 9); hooks of several sizes, at least one recurring.

## 6. Decided, and open

**Decided (JW, 2026-10-25):**
1. **The numbers are tuned on paper** when Wendleford is written (step 62): a day's earning against a day's needs, how long a shed takes to save for, how much help the harvest needs against the cast's time; the table is shown to JW before it is committed, and the test run says what to adjust.
2. **Finery is a trinket** at Wendleford's own price; no new kind of item unless a run shows it's needed.
3. **Needs are a switch,** and the spec's requirements are **a stricter check** that Wendleford is held to; The Thirteenth Stroke keeps passing `--sim-complete` as it is.
4. **The carpenter's time is only said to be scarce,** for now: building a shed doesn't slow the bridge. Linking them in code can come later.

**Open:**
5. **How the forge (worldsmith) is pointed at this spec,** and what the stricter check can verify by code against what needs a human read. Suggested (Claude): after Wendleford's run, once the spec has been tested once, revise it and then aim the forge at the stricter check.
