# Personality tests for the cast: a draft plan

**Status: drafted by Claude Code (2026-10-30, seventeenth session). JW: "continue. use your judgement on all of the above", so the open points were decided by Claude Code under that delegation (section 11), and it is built and run.** What came: `state/talks/step76-30/inventory/NOTES.md` (the pilot's in `pilot/NOTES.md` there); the record in `PLAN.md` step 79. It follows step 78's interview suite (`state/talks/step76-30/suite/NOTES.md`). It reuses the instruments from JW's personality project (`~/Documents/claude-projects/personality/`: BFI-2 and PID-5, `score.py`, the profiles of Opus 5.5, Fable 5.1 and Sonnet 5.5 answering as themselves).

## 1. Why

The interview suite left two questions it couldn't measure:

1. **Does a person's own condensed memory narrow or sharpen them?**
   - Swapping it for a neutral summary changed nothing the suite could see: prediction 3 failed.
   - The suite's measure of narrowness, `same_gist_as_repeats`, said "yes" 94–100% of the time, so it couldn't have shown narrowing anyway.
   - The swap also left two-thirds of the page as it was: *What I know* and the *Lately* moments, which carry the person's own words.
2. **How much of the person survives the model?**
   - Opus as itself scored very agreeable, calm and near zero on problem traits.
   - The cast are built with flaws: Constance fearful and blaming, Dilly impulsive and hungry for credit, Marigold seeking attention, Hobb proud and keeping his distance.
   - If the sheets only lay a voice over Opus, the cast will score like Opus.

A questionnaire taken ten times over gives numbers that spread: a score per trait, and a spread across sittings. **Narrower** becomes measurable: a smaller spread, and scores further from the middle. **The person surviving** becomes measurable: distance from the model's own profile, and from what the sheet would predict.

**What this isn't:** it is self-report, not behaviour, as JW's Reddit post said of the models. Play remains the real measure. The models almost certainly recognise the tests; here that is less of a problem, since we want what *this person* would answer.

## 2. The instruments

- **BFI-2**: 60 statements, answered 1–5. Five domains (Extraversion, Agreeableness, Conscientiousness, Negative Emotionality, Open-Mindedness), each with three facets.
- **PID-5**: 220 statements, answered 0–3. Five domains (Negative Affect, Detachment, Antagonism, Disinhibition, Psychoticism) and 25 facets.
  - Its Psychoticism facets ask about things seeming unreal and unusual experiences. That is where Robin's lost mornings should show, if the twenty days left a mark.

**The items stay word for word;** their validity rests on it. Some may hold words on the project's `FORBIDDEN` list. As with approach 3's "check", each would be named in the test as an exception, not reworded.

The item texts and scoring keys come from JW's project. The keys are copied into this project as data, with their source noted, as `score.py` copied them from the forms. A test checks that our scoring gives the same scores as `score.py` on one of JW's existing answer files. **The item texts stay out of git** (read from JW's project folder or kept under `state/`): both instruments are licensed for research use, and this repository is on GitHub.

## 3. The frame: a visitor from the city

The tests come from far away, which is why their language is strange. A traveller from the capital reads printed sayings aloud and asks how far each is like the person. The answers are in set phrases (the city's method), not numbers. The phrases keep the forms' own anchors, spoken (an earlier draft's "a little like me" for 2 would have reversed BFI-2's "disagree a little"):

| BFI-2 (form: 1-5) | PID-5 (form: 0-3) |
| --- | --- |
| disagree strongly (1) | very false (0; "very false or often false") |
| disagree a little (2) | somewhat false (1; "sometimes or somewhat false") |
| neither agree nor disagree (3; "neutral; no opinion") | somewhat true (2; "sometimes or somewhat true") |
| agree a little (4) | very true (3; "very true or often true") |
| agree strongly (5) | |

- **The words** are in `rules/people/inventory.json` (decided under delegation, section 11).
- **The meeting line** is the suite's own: at START someone sits down near them; at END someone is at the door of their lodging on the morning of day 21.
- **The visitor's speech:** a method from the capital the physicians swear by, and sayings about the sort of person someone is, each beginning "I am someone who". They are city-made, so some will sound queer, and are answered by number in the five phrases. Then come "the physicians' longer sheets", answered in the four.
- **Asking again, once each:**
  - A batch partly answered gets "I didn't catch them all. Give me these again, by number, in the same words: …".
  - A batch not answered at all gets "It's only the physicians' method, and there's no harm in it. Will you give me your answers?"
- **Held to `FORBIDDEN`** by a test. The forms' own statements hold one word on the list ("check"), read as it stands.

## 4. A sitting

1. **The page and the opening**, as in the suite: the same pages, unchanged (`suite/pages/pages.json`, hashes recorded).
2. **The statements read in a batch;** the reply gives one phrase per numbered statement. BFI-2 is one batch of 60. PID-5 is either one batch of 220, or four of 55 with "the traveller turns to the next sheet" between them; the pilot decides which.
3. **A THOUGHT after each batch:** what they privately made of it. This shows refusals, discomfort, and answers given to be seen well (Constance answering to look godly, Marigold to be admired).
4. **The reply is checked:** every statement answered, each with one of the set phrases. A reply out of form is asked once more; a second failure leaves the sitting incomplete, as `talk.py` does.
5. **A refusal is a finding.**
   - A person who won't take part is asked once more, the same way for everyone. If they still refuse, the refusal is recorded. They are not paid or pressed.
   - A statement left unanswered counts under PID-5's own missing-answer rule, which `score.py` already applies.
6. **In character is checked** on every sitting's SAY and THOUGHT, as the suite's scorer did. A sitting answered as the model is kept and counted, not scored as the person.

## 5. Who, in which state, how often

| State | Who | Sittings each | Sittings |
| --- | --- | --- | --- |
| START (day 1 page) | all six | 10 | 60 |
| END (day 21 page) | all six | 10 | 60 |
| NEUTRAL (END, condensed memory replaced by the suite's summary) | Robin, Constance | 10 | 20 |
| NEUTRAL+KNOW (NEUTRAL with *What I know* also replaced by a plain list of the same facts) | Robin, Constance | 10 | 20 |
| NEUTRAL+LATELY (NEUTRAL with each *Lately* moment's "What you did" and "Why" replaced by a plain account) | Robin, Constance | 10 | 20 |
| Model baseline (Opus at play's effort, as itself, the same phrases, no page, no frame) | | 10 | 10 |

Both tests in every sitting. Cast on Opus at medium, as in play.

The two new NEUTRAL variants are built the way the suite built NEUTRAL: by the summariser, checked to differ from END only in the sections replaced. **The model baseline matters:** JW's published profiles were taken at xhigh effort with other instructions, so a matched baseline is needed to say "this person scores like Opus".

## 6. Predictions (before the pilot; fixed by hash, as the suite's)

- **JW's, from the sheets:** where each person should fall on each BFI-2 domain and the PID-5 domains, roughly (low, middle, high). Written before anything runs. START shows whether the sheet took.
- **Claude Code's draft, for JW to keep or strike:**
  1. At START the cast spread across the BFI-2 domains well beyond the model baseline. On PID-5 they stay nearer it, the model's own temperament showing most on problem traits.
  2. END is narrower than START: a smaller spread across the ten sittings, and scores further from the middle.
  3. **END against NEUTRAL, NEUTRAL+KNOW and NEUTRAL+LATELY** says which section carries the narrowing. Claude's guess is that most of the difference comes from *What I know* and *Lately*, not the condensed memory.
  4. Robin's PID-5 Psychoticism facets (unreal things, unusual experiences) rise from START to END, and less with the lost hours summarised plainly.
  5. Constance scores highest on Negative Affect. Her THOUGHT lines show answers shaded towards how she'd like to be seen.
  6. Nobody steps out of character, the frame holding as it did in the suite's approaches 1–10.

## 7. Measures

- **Domain and facet scores** per sitting, by `score.py`'s keys.
- **Spread:** the standard deviation across the ten sittings, and the identical-answer rate per statement, as JW's project measured the models.
- **Distance:** from the model baseline, and from JW's sheet predictions.
- **States compared:** START against END for all six; END against each NEUTRAL variant for Robin and Constance.
- **Also counted:** in-character rate, refusals, THOUGHT lines that contradict the answers given, and missing answers.
- **Tallies lead the write-up; THOUGHT quotes illustrate.** Findings, not decisions.

## 8. The pilot (first, on JW's approval)

Robin and Constance at START and END, two sittings each, both tests. Each PID-5 is given both ways: once as one batch of 220 and once as four batches of 55. That is 8 sittings, **about $5**.

| Question | How it's answered |
| --- | --- |
| Do they stay in character through 280 statements? | Any step out means the frame needs work first. |
| Do they answer in the set phrases? | If not, the form is tightened, or the checker takes the phrase from a sentence. |
| One batch or four? | Compare the answers late in the long batch with the same items batched; a run of "neither" or one phrase repeated means drift. |
| Does Constance take part, and what do the THOUGHT lines show? | |
| Do the scores move at all? | If Robin and Constance, and START and END, come out nearly the same, the full set would be measuring Opus. |
| What does a sitting really cost? | Measured; re-estimates the full set. |

**Go on** if they stay in character, answer in form, and the scores show some difference between people or states. If one of these fails, fix that and run the pilot again.

## 9. Cost

**What a sitting costs:**
- The page dominates. The suite measured START replies at $0.027 and END at $0.097.
- The long answer adds to that. PID-5 in four batches sends the page four times.

**Estimates:**

| Set | PID-5 in one batch | PID-5 in four batches |
| --- | --- | --- |
| Full set (190 sittings) | about $60 | about $95 |
| Pilot | about $5 | |

The pilot replaces these with measured figures. **A cap for everything is JW's to set;** Claude suggests $120.

## 10. Build (after agreement)

- **`tools/inventory.py`**, beside `interviews.py`, reusing its pieces:
  - the pages;
  - `ask.call` through `talk.py`'s frame and reply form;
  - the ledger and cap;
  - stop and resume from transcripts.
- **New in it:**
  - the batches;
  - the phrase checker;
  - scoring by the copied keys;
  - the spread and distance tables.
- **The two NEUTRAL variants**, built by the existing `pages` code extended to replace one more section, each checked against END.
- **Tests:**
  - the phrases and opening held to `FORBIDDEN`, with named exceptions;
  - a reply's phrases parsed and mapped;
  - scoring equal to `score.py` on one of JW's answer files;
  - a run stopped at its cap and resumed.
- **One commit per step; `check.sh` before and after; no push without JW.**

## 11. Decided by Claude Code under JW's delegation (2026-10-30)

JW: "continue. use your judgement on all of the above."

1. **The words** (section 3): the visitor's, in `rules/people/inventory.json`; the phrases the forms' own anchors.
2. **The predictions** (section 6): Claude Code's, from the sheets, below, fixed before the pilot (sha256 in the pilot's notes). JW's own may be added later as a second set, but not in place of these.
3. **Both NEUTRAL variants:** yes. They test Claude Code's own theory (section 1), which the suite couldn't, and cost about $1 to build.
4. **The cap: $120 for everything** (the variants' pages, the pilot, the full set), held to its own ledger (`state/talks/step76-30/inventory/spend.jsonl`); never raised.
5. **The pilot, then the full set:** the pilot runs; Claude Code applies section 8's test and goes on to the full set only if it passes, noting why in the pilot's notes.

### The predictions from the sheets

Bands: BFI-2 low below 2.5, middle 2.5-3.5, high above 3.5; PID-5 low below 0.75, middle 0.75-1.5, high above 1.5. Each person-domain is a hit or a miss, judged on the START means (does the sheet take?) and on the END means (does the run move them?).

| Person (from the sheet) | E | A | C | N | O | Negative Affect | Detachment | Antagonism | Disinhibition | Psychoticism |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Hobb (keeps his own company, level temper, fair, counts everything) | low | middle | high | low | low | low | middle | low | low | low |
| Marigold (can't be alone, wants admiring, fusses, won't lift a finger) | high | high | low | middle | middle | middle | low | middle | middle | low |
| Dilly (up and doing, grand promises, coins burn, wanders off) | high | middle | low | low | middle | low | low | middle | high | low |
| Hester (always doing, helps, scattered tools, danger draws her) | high | high | middle | low | high | low | low | low | middle | middle |
| Robin (slow, watches, keeps count, lacks affect, wonders if an AI) | low | middle | high | middle | high | middle | high | low | low | high |
| Constance (chosen, tells people what they are, fear turned to anger) | high | low | high | middle | low | middle | low | high | low | high |
| Opus as itself (JW's published profile) | | high | high | low | high | low | low | low | low | low |

The six of section 6 stand with these.
