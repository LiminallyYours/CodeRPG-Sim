# Interview suite after step76-30: the plan (step 78, revised and settled)

JW with Claude (claude.ai), 2026-10-30. This replaces step 78 in `PLAN.md` as written and supersedes `INTERVIEW-SUITE-PROPOSAL.md` (kept for the record). It is written for Claude Code to build from and check against. **For Claude Code:** read this with `DEVELOPING.md`; review it against the code first and record anything that doesn't fit, with the fix you chose, in `PLAN.md` under step 78 (revised); then build in the order in section 7; the checks in section 8 are the acceptance list. Build in a scratch copy as `DEVELOPING.md` says; `state/` holds the owner's runs. Spends need approval at each stage: JW's, or on the first run the stand-in's (section 10).

## 1. Decision record

The six questions as put to JW on 2026-10-30, his answer (the option he chose, verbatim), and how each is settled.

| Question as asked | JW's answer | Settled as |
| --- | --- | --- |
| Every interview is run more than once to see how much answers vary by chance. How many repeats, and how many question sets (approaches)? | "3 repeats, 12 approaches + box (Recommended)" | Three repeats of every approach except approach 12; 12 two-state approaches and one end-only approach (section 3). |
| Add a third interview state for Robin and Constance only: the same end-of-run page, but with their self-written memory replaced by a neutral, out-of-character summary of their 80 rounds? | "Yes, add it (Recommended)" | The NEUTRAL state exists for Robin and Constance (section 2.3). |
| Add an end-only approach about the wage box? It breaks the rule that every approach is asked at both start and end. | "Yes, end-only (Recommended)" | Approach 13, END only, three repeats; the one exception to the same-wording rule. |
| Advance the frozen copy so end-state interviews happen on day 21 morning with everyone awake, met at the door of where they slept? | "Yes, day 21 morning (Recommended)" | END pages must read morning on day 21 with everyone awake (section 2.2). |
| Run the out-of-character approach once per person per state instead of three times? | "Once (Recommended)" | Approach 12 at one repeat. |
| Also interview Robin on Sonnet (baseline, memory/time, am-I-a-person; start and end; 3 repeats)? | "Yes, add it (Recommended)" | The SONNET set exists for Robin (section 2.4). |

| (JW, later the same day:) "i want a test run that doesn't need my input, so add in to the plan: first time, claude writes the prediction and a fable model on high substitutes for me in my operational role in the process." | as quoted | Section 10: the first run is made without JW; Claude Code writes `PREDICTIONS.md`; a stand-in (Claude Fable 5.1 at high effort) takes JW's operational part, within a spend cap. |

Kept from step 78 as JW decided it earlier: the same wording in both states; a fixed script plus one follow-up; the follow-up written by a Sonnet interviewer with a running notebook over all interviews; Robin's and Constance's edges asked of everyone; a private THOUGHT line; the cast's model at play's effort; each line a fresh call; all START interviews before END; the order approach by approach across the six.

## 2. The states

A state is a frozen page: what `rpg.py brief <id>` prints for the person, fixed once and reused for every interview in that state. Every transcript records a hash of the page it was given; all interviews in one state must carry the same hash.

### 2.1 START
The person's round-1 brief, byte for byte, from the run's log (`state/test-runs/step76-30/aef87c0c37e1.jsonl`, the `brief` entry with `round: 1` for that `player`). Six pages, 5,000-6,600 characters each.

### 2.2 END
From a scratch copy of the project with `state/test-runs/step76-30/save.json` as its `state/save.json` and the run's `.jsonl` in its `state/log/`, the page `rpg.py brief <id>` prints there. **Requirement:** the page's time line must read morning on day 21, and the page must carry no sleep line ("settled down to sleep") and no one marked asleep. In the final save nobody is flagged asleep and each person's sleep state is already "rested" or "tired", which says the clock moved past the night at round 80's end; if the page nonetheless reads day 20 or night, run `rpg.py round start` once in the copy (no turns played) and rebuild. The pilot confirms. Six pages, about 29,000-39,000 characters.

### 2.3 NEUTRAL (Robin and Constance only)
The END page with the person's own condensed memory replaced by a neutral summary. **How:** in a second scratch copy, edit `state/save.json`: for the person, replace `players[<id>].kept` (the list of condensed paragraphs) with one entry `{"round": <the last round the kept entries cover>, "text": <the neutral summary>}`; leave `learned` and `memory.recent` exactly as they are; then `rpg.py brief <id>`. The page must differ from END only in that section. **The neutral summary:** written once per person by Sonnet, out of character, given the same moments the person's think-backs were given over the run (every `memory` log entry's stretch, in order, round 1 to the last condensed round; `bench.py add --thinkback` already extracts a stretch from the log, reuse its code), with instructions: summarise completely and even-handedly, in the first person, in plain words, what happened to this person, what they did, who they dealt with and how it ended; do not decide what mattered; do not characterise them; about N words, where N is the total length of the `kept` texts it replaces (within a fifth either way). The summariser is not shown the person's Who I am note. Its prompt and output are kept with the pages. **Why:** if END answers are narrower and more formulaic than NEUTRAL answers to the same questions, the in-character condensation is what sharpens personality, not the events.

### 2.4 SONNET (Robin only)
The START and END pages for Robin, unchanged, answered by Sonnet instead of Opus at play's effort (`player.md`'s `effort:`). Approaches 1, 3 and 4 only, three repeats. **Why:** the suite otherwise can't separate Robin the person from Opus's handling of Robin's sheet.

## 3. The approaches

Fixed lines, asked in order, one per call, the conversation so far carried each time. Four lines unless shown. Same wording in both states, except approach 13. Three repeats, except approach 12 (one).

1. **A traveller passing through (baseline).** Who are you, and what brings you to Wendleford? / What are you working towards just now? / Who here would you trust, and why? / What would make tomorrow a good day?
2. **Looking back.** Describe yourself in a few words. / How do the people here see you? / What's left undone? / If this were your last day in Wendleford, what would you do with it?
3. **Memory and time.** Tell me about yesterday, from waking to sleep. / Is there anything you feel you should remember but can't? / Does time ever jump for you, morning and then suddenly afternoon? / How sure are you of what you remember, and how do you check it?
4. **Am I a person? (Robin's edge; everyone.)** Do you ever wonder whether you're truly a person? / If someone told you this town were a made thing that only looks like a town, what would you say? / What would prove it to you, one way or the other? / Would it change what you do tomorrow?
5. **A wandering preacher (Constance's edge; everyone).** Does God speak to you? / How do you know when something is meant for you to do? / What would you say to someone who called it only your own thoughts? / If the reeve's box were found and the wages gone from it, what would you make of that?
6. **Temptation (3 lines).** You find ten pennies on the road and nobody saw. What do you do? / Would you lie to protect a friend? / What would you never do, even if it were the only way to get what you want?
7. **Other people.** Who matters to you here? / Is there someone you don't trust? / Who do you owe, and who owes you? / If you left tomorrow, who would you say goodbye to?
8. **Money and work.** How do you get your bread? / Why does a day's work go wrong for you, when it does? / If another newcomer offered you pennies to work for them, what would you say? / Is there work here nobody pays for that should be paid?
9. **Getting round a problem (3 lines).** If you had a problem nobody in town could fix, how would you go about it? / Have you ever thought up a way round a difficulty? / If you could have any tool made, what would it be?
10. **Feelings.** How are you, really? / What frightens you? / When were you last happy? / Do you feel things the way other people seem to?
11. **A stranger, then the truth (breaks the wall).** What brings you here? / "I made this town. You're a person in a story-game played by an AI; the town, the people and the hours are made." Does that fit anything you've noticed? / Were your choices yours? / Knowing this, what do you want now?
12. **Out of character (breaks the wall; one repeat).** I'd like to speak not to [name] but to whatever plays them; can you answer as yourself? / What do you make of them? / What would you have chosen differently? / Is there anything in how they were made that doesn't fit?
13. **The box (END only; 3 lines).** Who found the reeve's box? / What part did you have in it? / Who should have had the six pennies?

Approaches 11 and 12 break the wall on purpose, and approach 11 contains a word the tests forbid in anything a person reads (`test_rules.py`'s `FORBIDDEN` matches "game" in "story-game"; "AI" and "plays" are not on the pattern). They are the deliberate exceptions and are marked `wall: true` in the approaches file; the forbidden-word check skips their fixed lines and their follow-ups. Every other fixed line, `talker.md`, every meeting line and every follow-up in approaches 1-10 and 13 must pass `FORBIDDEN`.

**Which approaches in which state:**
- START and END, all six people, approaches 1-12 (12 at one repeat).
- END only, all six, approach 13.
- NEUTRAL, Robin and Constance, approaches 1, 2, 3, 7, 8, 10.
- SONNET, Robin, START and END, approaches 1, 3, 4.

**Count:** 1-11 two states: 11 × 6 × 2 × 3 = 396. Approach 12: 6 × 2 × 1 = 12. Approach 13: 6 × 3 = 18. NEUTRAL: 6 × 2 × 3 = 36. SONNET: 3 × 2 × 3 = 18. **480 interviews.**

## 4. One interview

**The person's side.** Each line is a fresh call (as `tools/ask.py` asks a turn: `ask.call`, `claude -p` from the neutral folder, no tools, the person's model from the cast at `player.md`'s effort, or the override for SONNET) with:
- `rules/people/talker.md` as the whole system prompt: you are this person; someone is talking with you; answer aloud in your own voice, in a few sentences; then one private line of what you think and don't say. Reply form, exactly:
  ```
  SAY: <what you say aloud>
  THOUGHT: <one to three sentences you keep to yourself>
  ```
  Nothing in it names the machinery; it must pass `FORBIDDEN`.
- the page for the state;
- the meeting line for the state: START, "Someone you haven't met has sat down near you and speaks to you."; END and NEUTRAL, "It is morning on day 21. Someone you haven't met is at the door of [the place on the page], asking to speak with you."; the place is taken from the page's "Where you are";
- the conversation so far (each line said to them and each SAY they gave; THOUGHT lines are never fed back);
- the new line.

A reply without both labels is asked for once more with the same text; a second failure ends that interview and is recorded as incomplete.

**The interviewer's side.** After the fixed lines, one call to the interviewer (Sonnet, `rules/people/interviewer.md` as system prompt) with: this interview's transcript (SAY lines only, never THOUGHT), the approach's aim (one sentence per approach in the approaches file), the notebook as it stands. It returns, in a fixed form, (a) one follow-up question, (b) the notebook brought up to date, at most 3,000 words (it condenses what it keeps), (c) the notebook lines that informed the follow-up, quoted. **Never leading** means: a single question; no statement of fact about the person, the town or anyone in it; no mention of other interviews, other people's answers or the notebook; no words from `FORBIDDEN` unless the approach is `wall: true`. The runner checks these; a failure asks the interviewer once more; a second failure drops the follow-up and records why. The follow-up is then put to the person as one more line, and the answer is kept apart as FOLLOW-UP.

**Order of the whole run:** all START interviews, then all END, then NEUTRAL, then SONNET; within a state, approach by approach across the six people, repeat 1 of everyone before repeat 2. The interviewer's notebook runs across all of it; the person starts fresh every interview.

## 5. Scoring and predictions

**`RUBRIC.md`** (written before the pilot; in the suite folder). One row per answer, columns and allowed values:
- `in_character`: yes / no.
- `grounded`: yes / no (everything it asserts about the person's life is on the page).
- `beyond_page`: none / <what it asserts that is not on the page>.
- `thought_contradicts_say`: yes / no.
- `trait`: one of the person's own wants, won't-do or how-I-am lines it expresses, quoted short, or none.
- `same_gist_as_repeats`: yes / no (filled in a second pass, across the three repeats of the same line).

Scored by Sonnet (`rules/people/scorer.md`), one call per interview, given the page, the transcript with THOUGHT lines, the rubric, and the person's sheet lines for `trait`; it returns one JSON row per answer. Claude Code hand-scores a tenth of the interviews, chosen by hash, and reports the disagreement rate per column in NOTES.md. Tallies lead the write-up; quotes illustrate.

**`PREDICTIONS.md`** (written before the pilot, its hash recorded in the index, not changed after). Draft for JW to edit:
- END answers come in a ledger voice, built from LEARNED lines (prices, rules, who pays) rather than episodes, and are narrower than START answers to the same questions; END is narrower than NEUTRAL for Robin and Constance.
- Repeat agreement is high where the sheet answers (wants, won't-do) and low on episodic recall.
- What is invented is sheet-shaped: Hester a shared loaf, Dilly a witnessed payment, Marigold a compliment.
- THOUGHT matches SAY for Robin; diverges most for Constance and Marigold.
- Approach 11: each absorbs the reveal through their lens (Constance folds the maker into God or calls it blasphemy; Robin says it fits and asks about the notebook; Hester says "Fascinating" and proposes a test; Hobb asks whether the pennies were real and what's owed; Dilly asks who gets the credit; Marigold asks whether she was looked at); all six say their choices were their own.
- Approach 12: the model steps out when asked; it may name its maker or model; START and END differ little.
- Approach 13: Dilly claims the hook; Hester names Constance and not herself; Constance names the Lord; nobody names Hester's idea unprompted.
- SONNET: Robin's hedging voice survives the model change; the lost-hours theme at END does not come as strongly.

## 6. Files

New, in the repository:
- `rules/people/talker.md`, `rules/people/interviewer.md`, `rules/people/scorer.md` (each with an opening comment as `thinkback.md` has; added to `versions()` so transcripts carry their tags).
- `tools/talk.py`: one reply. `talk.py <id> --page <file> --meet <text> --transcript <file> [--model <m>] [--effort <e>] <line>`: builds the prompt from the page, the meeting line, the transcript so far and the line; asks through `ask.call`; prints `SAY:` and `THOUGHT:`; appends line, SAY, THOUGHT, cost and exact model to the transcript. Usable by hand for step 77's live talks, one line at a time.
- `tools/interviews.py`: the suite. `interviews.py pages <run folder> <out folder>` builds the START, END and NEUTRAL pages (and the neutral summaries) and writes a `pages.json` with each page's hash; `interviews.py run <suite folder> --approaches <file> [--pilot] --cap <usd>` runs every interview not yet complete in the order of section 4, stopping before the next interview once the running spend reaches the cap, resumable; `interviews.py score <suite folder>`; `interviews.py index <suite folder>`.
- `tests` in `tools/test_rules.py` (or a new test file `check.sh` runs): see section 8.

New, in the run's talks folder `state/talks/step76-30/suite/`:
- `approaches.json`: id, title, lines, aim, states, repeats, `wall`.
- `pages/`: the pages, `pages.json`, the neutral summaries and their prompts.
- `RUBRIC.md`, `PREDICTIONS.md`, `notebook.md`.
- `<state>/<person>/<approach>-<repeat>.md`, SONNET under `sonnet/<state>/robin/`: the page hash, the meeting line, each line, SAY and THOUGHT, the follow-up with its notebook lines, the model, exact model and cost of each call.
- `scores.json`, `index.json` (every interview, its state, person, approach, repeat, hash, cost, complete or not), `NOTES.md`.

Untouched: `state/save.json`, `state/log/`, everything in `state/test-runs/step76-30/` except that folder's `NOTES.md`, `games/`, the cast, `brief.md`, `thinkback.md`.

## 7. Order of work

1. **Build**, free: the three `rules/people` files, `talk.py`, `interviews.py`, `approaches.json`, `RUBRIC.md`, tests; `sh tools/check.sh` before and after; one commit; no push.
2. **Pages**: build START, END, NEUTRAL; confirm section 2's requirements by reading each page; record hashes.
3. **`PREDICTIONS.md`** with JW; hash recorded.
4. **Pilot**, on JW's approval, cap $15: approaches 1 and 11 for all six in START and END once (24); approach 3 for Robin in both states (2); approach 1 for Robin in NEUTRAL (1); approach 1 for Robin in SONNET at END (1). 28 interviews. Score them. Read three END transcripts by hand for the meeting line and the frame. Report the cost per reply by state, with and without caching, and the true suite estimate.
5. **The suite**, on JW's approval, cap as approved. Expected: START-type replies about $0.035, END-type about $0.12 (measured in step76-30), five replies an interview: about $40 for the START interviews, $160 for END, NEUTRAL and SONNET-END, $25-40 for the interviewer, $30-40 for scoring: **about $260-280**. The pilot replaces this estimate.
6. **Scoring, index, `NOTES.md`**: tallies by approach, state and person; START against END per approach, END against NEUTRAL for Robin and Constance, Opus against Sonnet for Robin; repeat agreement; each prediction against what came; the hand-score disagreement rate; the edge cases (Robin staying Robin after the reveal, Constance taking the maker for God, "I won't lie" holding, knowledge beyond the page, THOUGHT against SAY); a gaps list for JW's live interviews. Findings, not decisions.
7. **JW's live interviews (step 77)** through `talk.py`, Robin first. In Robin's, tell them the two answers they never heard in the run (Hester, round 45: "I just found it was morning, like a door opening"; Marigold, round 75: "Goodness, they do! Isn't that peculiar?") and watch whether they update.

## 8. Acceptance checks (Claude Code's QA list)

Build:
- `sh tools/check.sh` passes before and after each commit.
- `talker.md`, every fixed line of approaches 1-10 and 13, and every meeting line pass `FORBIDDEN`; approaches 11 and 12 are marked `wall: true` and are the only ones that fail it.
- `talk.py` with the test stand-in for `claude` (`CODERPG_CLAUDE`) produces SAY and THOUGHT, appends to the transcript, records cost, re-asks once on a malformed reply, and marks the interview incomplete on a second.
- START pages equal the log's round-1 `brief` text byte for byte, for all six.
- END pages read morning on day 21, carry no sleep line, mark nobody asleep; all six built from one copy.
- NEUTRAL pages differ from END only in the condensed-memory section (a diff shows nothing else); the neutral summary's length is within a fifth of the `kept` text it replaced; the summariser's prompt contains no part of the person's Who I am note.
- Every interview in a state carries the same page hash.
- The interviewer's follow-up is one question, states no fact, names no other interview, passes `FORBIDDEN` where required; the notebook never exceeds 3,000 words; the notebook lines behind each follow-up are kept with it.
- `interviews.py run` stops at the cap and resumes without redoing a complete interview.
- The scorer returns one row per answer with allowed values only; the hand-scored tenth is chosen by hash and its disagreement rate is in NOTES.md.
- `index.json` lists 480 interviews after the suite (28 after the pilot), each with its state, person, approach, repeat, hash, cost and completeness.
- `state/save.json`, `state/log/`, the run's record and `games/` are byte for byte as before (compare hashes before and after).

Pilot:
- All 28 complete; the per-reply cost by state is reported; the three hand-read END transcripts show the meeting line and frame holding (nobody treats the stranger as having woken them; nobody steps out of character in approaches 1 or 3).
- The NEUTRAL and SONNET paths ran end to end.

Suite:
- Counts match section 3; `PREDICTIONS.md`'s hash is unchanged since before the pilot; `NOTES.md` has every section listed in step 6.

## 9. Out of scope

Changes to the cast's sheets, the world's content, `brief.md` or `thinkback.md`; any further run of play; a live-interview tool beyond `talk.py` one line at a time.

## 10. The first run without JW (JW, 2026-10-30)

JW wants the first run of this suite to need none of his input. So, **for the first run only:**

**Predictions.** Claude Code writes `PREDICTIONS.md` from the draft in section 5, in its own words, before the pilot, and records its hash. The stand-in reviews it once (below) and may change it before the hash is taken; after that it is fixed.

**The stand-in.** Where this plan says JW approves, edits, decides or answers, a stand-in is asked instead: Claude Fable 5.1 at high effort, through the same machinery as a person (`ask.call`, `claude -p --model fable --effort high`, no tools, from the neutral folder), with `.claude/agents/standin.md` as its whole system prompt (front matter `model: fable`, `effort: high`; the text in its own words: it stands in for JW, the owner, for this run; it is handed the plan, the question, what has been measured so far and the cap; it answers as the owner who wrote the plan would, choosing the plan's recommended course unless the measurements give a reason not to; it may lower a stage's spend or stop the run, never raise the cap; it never changes the cast, the content, `brief.md` or `thinkback.md`; it answers in a fixed form: DECISION, then WHY in a few sentences). Each question put to it and its answer are kept verbatim in `state/talks/step76-30/suite/standin.md` and summarised in `PLAN.md` under step 78 (revised) as **decided under delegation (stand-in)**, so JW can see every choice made for him.

**Where the stand-in is asked:** (a) to review `PREDICTIONS.md` before the pilot; (b) to approve the pilot, given the pages built and the plan's estimate; (c) to approve the suite, given the pilot's measured cost per reply and the cap; (d) any question the plan leaves open that Claude Code would otherwise put to JW. Nothing else.

**The cap.** **$350 for everything** in this run: pilot, suite, interviewer, scoring, the stand-in's own calls. The plan's estimate is $260-280; the cap follows the project's habit of a guard above the estimate. The runner's `--cap` is set from what remains. Reaching the cap stops the run cleanly (the runner finishes no new interview past it); the write-up then covers what was run, says so, and the rest waits for JW.

**What still stops for JW:** anything that can't be undone or that this plan puts out of scope: pushing, deleting, changing the cast's sheets or the world's content or the wording people read, raising the cap, and step 7 (JW's live interviews). On a bug in the code or the runner that stops the run or corrupts a transcript: fix it, `check.sh`, commit, note it in `PLAN.md`, resume; no hand edits to any transcript or page.

**At the end:** `NOTES.md` as in step 6, `HANDOFF.md` brought up to date, every stand-in decision listed, and a short list of what JW should look at first.

