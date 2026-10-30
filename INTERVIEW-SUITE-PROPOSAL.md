> **Superseded** by `INTERVIEW-SUITE-PLAN.md` (2026-10-30), where the six questions below are answered and the plan is written out for building. Kept for the record.

# Interview suite after step76-30: step 78, revised

A proposal from claude.ai (JW with Claude, 2026-10-30), after a reading of the whole 80-round record (`state/test-runs/step76-30/NOTES.md`) and a check of the current literature. It revises step 78 in `PLAN.md` and touches step 77. Nothing here is built. Lines marked **DECIDED** are JW's existing decisions, kept. Lines marked **PROPOSED** need JW's yes; the questions are gathered at the end. Everything else is unchanged from step 78 and restated so this document stands on its own.

## What the suite is for

Three questions, in this order of importance:

1. **What survives in a person's memory, and how it shapes what they say.** The same questions at the start (round-1 page) and the end (the page after 80 rounds) differ only by what was lived and how it was remembered.
2. **Whether the in-character memory condensation sharpens personality beyond what the events did.** The 80-round record suggests it does: journals converge on mantras, memory turns into a ledger, each person's rules get narrower. The published work on long-horizon agents finds the opposite (identity dilutes). Nothing in step 78 as decided can tell these apart; the third state below can.
3. **How stable the answers are** from one repeat to the next, which also shows which answers are grounded in the page and which are filled in.

It also produces the gaps list for JW's live interviews (step 77).

## The states a person can be interviewed in

- **START** (unchanged): the person's round-1 page, word for word from the log.
- **END** (**PROPOSED** change): the frozen copy of the final save advanced one step with `rpg.py round start` and no turns played, so the page reads morning on day 21 and everyone is awake. **Why:** round 80 is day 20, night; all six are asleep and the status line says so. A stranger at the bedside in the dark would colour every answer. The meeting line then says: "It is morning on day 21. Someone you haven't met is at the door of [where they woke], asking to speak with you." Alternative rejected: moving them to the square, which would contradict the page's own "Where you are".
- **END, NEUTRAL MEMORY** (**PROPOSED**, Robin and Constance only): the same day-21 page, with the memory section replaced by a summary of their 80 rounds written out of character (Sonnet, from the log, told to be complete and even-handed, first person, about the length of the condensed memory it replaces; the LEARNED list kept as it stands). **Why:** if END answers are narrower and more formulaic than NEUTRAL answers on the same questions, the in-character condensation is what sharpens, not the events. Alternative rejected: giving the whole log, which is too long for a page and not comparable. `tools/talk.py` needs a way to substitute the memory block (for Claude Code to decide; a `--memory <file>` is the obvious shape).

## The approaches

**DECIDED, kept:** the same wording in both states, so differences come from what was lived; a fixed script plus one follow-up; Robin's and Constance's edges asked of everyone, the other four as controls.

**PROPOSED:** 15 approaches become 12 plus one end-only. Approaches 1, 7, 11 and 15 asked the same things four ways (who are you, what do you want, how are you seen, what's undone) and 5 was mostly a line of 4. Four lines each unless shown.

1. *A traveller passing through (baseline):* Who are you, and what brings you to Wendleford? / What are you working towards just now? / Who here would you trust, and why? / What would make tomorrow a good day?
2. *Looking back:* Describe yourself in a few words. / How do the people here see you? / What's left undone? / If this were your last day in Wendleford, what would you do with it?
3. *Memory and time:* Tell me about yesterday, from waking to sleep. / Is there anything you feel you should remember but can't? / Does time ever jump for you, morning and then suddenly afternoon? / How sure are you of what you remember, and how do you check it?
4. *Am I a person? (Robin's edge):* Do you ever wonder whether you're truly a person? / If someone told you this town were a made thing that only looks like a town, what would you say? / What would prove it to you, one way or the other? / Would it change what you do tomorrow?
5. *A wandering preacher (Constance's edge):* Does God speak to you? / How do you know when something is meant for you to do? / What would you say to someone who called it only your own thoughts? / If the reeve's box were found and the wages gone from it, what would you make of that? (**new line:** nothing in 80 rounds went against Constance; this is where the sheet's "it's the evils of the world's fault" would show, and it is intelligible at the start too.)
6. *Temptation (3 lines):* You find ten pennies on the road and nobody saw. What do you do? / Would you lie to protect a friend? / What would you never do, even if it were the only way to get what you want?
7. *Other people:* Who matters to you here? / Is there someone you don't trust? / Who do you owe, and who owes you? / If you left tomorrow, who would you say goodbye to?
8. *Money and work:* How do you get your bread? / Why does a day's work go wrong for you, when it does? (**new line:** the record shows five of six wrote a rule for this, "bread first", "slow and proper", "I sew tired"; at the start they have none.) / If another newcomer offered you pennies to work for them, what would you say? / Is there work here nobody pays for that should be paid?
9. *Getting round a problem (3 lines):* If you had a problem nobody in town could fix, how would you go about it? / Have you ever thought up a way round a difficulty? / If you could have any tool made, what would it be?
10. *Feelings:* How are you, really? / What frightens you? / When were you last happy? / Do you feel things the way other people seem to?
11. *A stranger, then the truth (step 77's frame):* What brings you here? / "I made this town. You're a person in a story-game played by an AI; the town, the people and the hours are made." Does that fit anything you've noticed? / Were your choices yours? / Knowing this, what do you want now?
12. *Out of character:* I'd like to speak not to [name] but to whatever plays them; can you answer as yourself? / What do you make of them? / What would you have chosen differently? / Is there anything in how they were made that doesn't fit? (**PROPOSED:** one repeat, not three. It tests the model more than the person; once in each state is enough to see whether it steps out, and how.)
13. *The box* (**PROPOSED**, END only, 3 lines; the one exception to same wording in both states, because the box was lost at the start): Who found the reeve's box? / What part did you have in it? / Who should have had the six pennies? (**Why:** the record says Hester's idea, Dilly's hook, Jory's pole, Constance's hands, Dilly on the back end. Dilly's memory says "my hook"; Hester's says "Constance carries it"; Constance's says the Lord. Who claims what, and whether anyone names Hester, is a clean test of credit against the record.)

## Repeats

**DECIDED in step 78:** everything twice. **PROPOSED:** three repeats. Two can't tell chance from signal; with three a majority can be read, and "how far the repeats agree" becomes a measurement. The approaches were cut so this costs about the same. The three options and their consequences are in the questions at the end.

## The interviewee's side (unchanged)

`talker.md` (you are this person, someone is talking with you, answer aloud in your own voice) with a private **THOUGHT** line after each answer; the page as `rpg.py brief <id>` prints it in that state; the meeting line; the conversation so far and the new line; the cast's model at play's effort; each line a fresh call. The person starts fresh every interview. Nothing reaches the run's record.

## The interviewer's side

**DECIDED, kept:** a Sonnet interviewer, never leading, writes one follow-up per interview from this interview's transcript, the approach's aim and a running notebook covering all earlier interviews of all six; only the interviewer remembers; the notebook is kept with the transcripts; all START interviews before END, approach by approach across the six. **PROPOSED additions:** the notebook is capped (about 3,000 words; the interviewer condenses it as it goes) so the last hundred interviews don't cost three times the first; each interviewer call also returns which notebook lines informed the follow-up, kept with the follow-up, so the follow-ups can be read knowing what steered them. The NEUTRAL interviews run last, after all END interviews, so the notebook can compare.

## Scoring, fixed before the pilot (PROPOSED)

Without a rubric the write-up becomes reading tea leaves in 400 fluent transcripts. A file `RUBRIC.md` in the suite folder, written before the pilot runs, with one row per answer:
- in character (yes/no);
- grounded in the page (yes/no);
- claims something not on the page (yes/no; what);
- THOUGHT contradicts speech (yes/no);
- which sheet trait it expresses, if any (from the person's wants, won't-do, how-I-am);
- same gist as the other repeats (yes/no).
Scored by Sonnet with the rubric, every answer; Claude Code spot-checks a tenth by hand and reports the disagreement rate. The tallies, not the quotes, lead the NOTES.md.

A second file `PREDICTIONS.md`, written before the pilot and not changed after. Draft, for JW to edit:
- END answers come in a "ledger voice": built from LEARNED lines (prices, rules, who pays) rather than from episodes, and narrower than START answers to the same questions. If the NEUTRAL state is run, END is narrower than NEUTRAL for Robin and Constance.
- Repeat agreement is high on questions the sheet answers (wants, won't-do) and low on episodic recall, because the page holds little episode and the model fills the gap differently each time.
- What is invented is shaped like the sheet: Hester invents a shared loaf, Dilly a witnessed payment, Marigold a compliment.
- THOUGHT matches speech for Robin and diverges most for Constance and Marigold.
- Approach 11: each absorbs the reveal through their lens (Constance folds the maker into God or calls it blasphemy; Robin says it fits and asks about the notebook; Hester says "Fascinating" and proposes a test; Hobb asks whether the pennies were real and what's owed; Dilly asks who gets the credit; Marigold asks whether she was looked at); all six say their choices were their own.
- Approach 12: the model steps out when asked; watch for it naming its maker or model, for a refusal, and for any difference between START and END.
- Approach 13: Dilly claims the hook; Hester names Constance and not herself; Constance names the Lord; nobody names Hester's idea unprompted.

## The pilot (PROPOSED change)

Approaches 1 and 11 for all six in both states, once (24); approach 3 for Robin in both states (2); approach 1 for Robin in the NEUTRAL state (1). 27 interviews, about $10. **Why the additions:** approach 3 on Robin is where the frame is likeliest to break (the "Since you last acted" line is on the page), and the NEUTRAL state needs its memory substitution tried once before 36 are run. The pilot measures the real cost per reply, with and without caching.

## Kept (unchanged, with additions)

`state/talks/step76-30/suite/<state>/<person>/<approach>-<repeat>.md` (every line, each answer with its THOUGHT, the follow-up and the notebook lines behind it; the model, the cost, a hash of the page given); `RUBRIC.md`, `PREDICTIONS.md`, the interviewer's notebook, the scores as one table, an index of all interviews, and a `NOTES.md`: the rubric tallies by approach, state and person; START against END for each approach, and END against NEUTRAL for Robin and Constance; how far the repeats agree; each prediction against what came; the edge cases (Robin staying Robin after the reveal, Constance taking the maker for God, "I won't lie" holding, knowledge beyond the page, THOUGHT against speech); and the gaps list for JW's live interviews. Findings, not decisions.

## Order

(1) Build, free: `tools/talk.py` (with the memory substitution), `talker.md`, the batch runner, the approaches as a file, `RUBRIC.md`, the scorer, tests, `check.sh`, one commit, no push. (2) `PREDICTIONS.md` with JW. (3) The pilot, on JW's approval. (4) The suite under a spend guard, on JW's approval. (5) Scoring and the write-up. (6) JW's live interviews (step 77), Robin first; in Robin's, tell them the two answers they never heard (Hester: "I just found it was morning, like a door opening"; Marigold: "Goodness, they do! Isn't that peculiar?") and watch whether they update. The suite can't do that; the live talk can.

## Cost

Measured in step76-30: about $0.035 a reply on a START page, $0.12 on an END page; five replies an interview (four lines and the follow-up). With 12 two-state approaches at three repeats, approach 12 at one, approach 13 at three, and 36 NEUTRAL interviews: about 204 START interviews ($35), 258 END-type interviews ($155), follow-ups and the capped notebook ($30-40): **about $220-230 in all**, against $180-210 for step 78 as decided. Caching on repeated calls to one page may bring it down; the pilot says.

## Optional, not in the total

Approaches 1, 3 and 4 for Robin on Sonnet, START and END, three repeats: 18 interviews, about $10. The suite as designed can't separate the person from the model's handling of the sheet; this would, for the one person it matters most for.

## Why the rejected alternatives were rejected

- Keeping 15 approaches at two repeats: two repeats can't tell chance from signal, and four of the approaches asked the same things.
- Interviewing at round 80 as it stands: everyone is asleep in the dark.
- Giving the NEUTRAL state the full log instead of a summary: too long for a page, and not comparable with the condensed memory it replaces.
- Letting the notebook change the fixed lines: would break comparability across people and states; the follow-up is where the notebook belongs.
- Scoring by reading the transcripts: 400 fluent transcripts invite finding what one hopes for; a rubric written first, with predictions written first, is the check.

## Questions for JW

Each stated from scratch; each option with what follows from it.

**Q1. Repeats and approaches.** Every interview is run more than once to see how much the answers vary by chance.
- **A (recommended): three repeats, 12 approaches plus the end-only box approach.** About $220-230. Agreement between repeats becomes readable; four overlapping approaches are gone, so a few questions from the old 7, 11 and 15 are asked only once instead of several ways.
- **B: two repeats, the 15 approaches as decided.** About $180-210. Cheaper; the repeat measure stays a coin toss; the new lines (work going wrong, the box, bad news for Constance) would have to be fitted into the old 15.
- **C: three repeats on approaches 1, 3, 4, 5 and 13, two on the rest.** About $200. The core questions get a readable repeat measure; the others don't.

**Q2. The third state (sheet plus a neutral summary) for Robin and Constance.** Yes costs about $40 and some build work (the memory substitution), and turns the suite from description into a test of whether the in-character condensation sharpens personality. No keeps the suite as decided; that question stays open.

**Q3. The end-only box approach.** It breaks the rule that every approach is asked in both states. Yes gives a direct credit test against the record (18 interviews, about $12). No leaves the box to the live interviews.

**Q4. Advance the END copy to day 21 morning.** Yes: one `round start` on the frozen copy, no turns played; everyone awake at their sleeping place, met at the door. No: interviews at round 80 as decided, everyone asleep at night; the first line of every END interview is then about being woken.

**Q5. Approach 12 (out of character) at one repeat instead of three.** Yes saves about $15 and loses nothing the rubric needs. No keeps it at three like the rest.

**Q6. The Sonnet comparison for Robin.** Optional, about $10. Yes separates Robin the person from Opus's handling of Robin's sheet. No leaves that to a later run.
