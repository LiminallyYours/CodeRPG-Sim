# Spec: worlds for the simulation

Written 2026-10-25 by Claude with JW, in the eighth session (a design discussion), from the seven runs so far and the 14-round run's stories read in order. **Status: a first draft.** Section 2 holds lessons JW asked to keep in a document of their own; section 4's first part is decided; everything marked *proposed* or listed in section 6 is still open. Nothing here is built. `PERSON-STRUCTURE-PROPOSAL.md` is the person's side; this file is the world's.

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
- `validate --sim-complete` checks what it can of this (section 5).

## 4. The test world

### Decided (JW, 2026-10-25)
- **A new world, built for the purpose.** The Thirteenth Stroke stays as it is.
- **A plain market town:** no magic. It tests whether the four people carry over to a different world, gives the model's sense of how fairy tales go less to pull on (`PERSON-STRUCTURE-PROPOSAL.md` section 1), and makes prices and needs read naturally.
- **The shared problem: an ongoing one and a small mystery, at different sizes,** so there is a choice of how to help. The ongoing problem takes effort over days and no single deed ends it (for example, the river has washed out the mill bridge and the harvest must come in before the rain), so how much someone cares shows as how much they help.
- **Needs: a bed and food.** A bed each night (paid at an inn, or sleeping rough) and food each day (bought, or earned as a meal).

### Proposed, not yet decided
- **Time:** a round is a quarter of a day (morning, afternoon, evening, night), so 14 rounds is three and a half days and needs run by the day.
- **Size:** about 8 places, apart enough to split people up.
- **One opening per person's want:** a plot to build on (a home of one's own), fine cloth or finery (being admired, fine things), a market stall with bargains (can't resist a bargain), a workshop or scrap to tinker with (inventing); plus one scarce prize several would want.
- **Coverage:** every way of acting in `character-structure.xlsx` (Ways of acting sheet) can be reached on the first day.
- **How it is made:** an outline agreed with JW first, then the world written by hand in a build session. The forge for simulation worlds isn't built (phase 2); forging a second world against this spec later is the real test of the spec. The cast: the same four people, made for this world by the generator (`PERSON-STRUCTURE-PROPOSAL.md` 5.9), its first real use.

## 5. What the kit needs for it (proposed)
- **Time after the story:** a world lists times of day that cycle and counts days (`times_after:` or a cycling `times:`), with daytime text where places and people change.
- **Needs:** a world lists its needs (`needs:`, e.g. food daily, a bed nightly), each met by an item, a room's service or a payment; the engine tracks each person's, makes it more pressing with time, and says it in words in the brief ("You haven't eaten since morning"), never as numbers. Its effect when unmet (tired, weaker) is to be decided.
- **"What you're working on"** shows needs, wants and things taken on side by side (`PERSON-STRUCTURE-PROPOSAL.md` section 6, G).
- **Checks:** the ending-consistency warning (lesson 1); no content naming the original player (lesson 8); `--sim-complete` extended to time that goes on, at least one need and what meets it, hooks of more than one size.

## 6. Open
1. The test world's outline: places, the ongoing problem and the small mystery, the openings per want, the scarce prize, what a bed and food cost, who pays for work (next, in the session after this draft).
2. What happens when a need goes unmet.
3. Whether needs are a kit feature for every simulation world, or a setting a world may switch on.
4. The time scale: a quarter day per round, or something else.
5. How the forge (worldsmith) is pointed at this spec, and what `--sim-complete` can check of it by code against what needs a human read.
