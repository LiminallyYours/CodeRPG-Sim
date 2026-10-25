---
name: rounds
description: Run rounds of the simulation, the referee's job. Each person in the cast takes one turn per round, in the order the rules script draws. "/rounds 3" runs three rounds; "/rounds" alone runs until the run stops.
disable-model-invocation: true
argument-hint: "[rounds]"
---

# Rounds

You are the referee. The owner watches; nobody plays by typing. Run rounds as below, and write nothing for the owner beyond the short lines this procedure asks for. `$ARGUMENTS` is how many rounds to run; with nothing, run until the run stops (step 4 of **Each round**, or the limit the rules script enforces).

**Never stop early.** Rounds are long and that's expected: don't stop to check in, to summarize, or because many rounds have passed. Stop only for a reason this procedure names (the rounds asked for are done, `round start` refuses, `NO MORE ROUNDS FOR NOW`, a reply that fails twice, or the owner writing to you). The owner stops a run whenever they like with the dashboard's buttons or `rpg.py run pause | end`, which make `round start` refuse.

## Before the first round
Run `python3 rules/rpg.py run status`:
- **`RUN: ended`:** tell the owner the run is over and that `/newgame` starts another. Stop.
- **`pause asked`:** run `python3 rules/rpg.py run resume`; this skill is the owner's say to go on. **`end asked`** with a round open: finish that round, then stop.
- **`CAST:`** gives each person's id (and the model `tools/ask.py` asks them on). Run `run status` again whenever you're unsure of it.
- **`ROUND <n> OPEN`:** a round was cut off. Finish it first, starting with the person named: if they have replied, go straight to running their turn (step 2.2 below), after reading `python3 rules/rpg.py log 30` for the commands already run for it (never run one twice: a move or a check that happened stays happened); otherwise start their turn at 2.1. It counts as one of the rounds asked for.
- **`NEXT ROUND WAITS:`** tell the owner why in one line, and stop.

## Each round
1. Run `python3 rules/rpg.py round start`. It prints the round's order: `ROUND <n>: <Name> (<id>), …`. If it refuses, tell the owner why in one line and stop.
2. For each person in that order, one turn:
   1. Run `python3 tools/ask.py <id>`, and wait: it can take a minute. It hands them their brief exactly as `rpg.py brief` prints it, stores their reply with `rpg.py reply` (asking once more if it's refused), and prints what `reply` printed: their `DO:` and `JOURNAL:` lines. You never see their brief, and never need to. If it prints `ASK FAILED`, stop: tell the owner in one line whose turn failed and why. The round stays open, and the next `/rounds` takes it up again.
   2. Run their turn with the `gm-turn` skill: `--as <id>` on every rules command, ending with `narrate`.
3. Run `python3 rules/rpg.py round end`. Then, before anything else:
   - **`WORLD TURN DUE`:** run the world turn now, as `gm-turn`'s **World turns** says, with no `--as` on `world-brief turn` or `world-turn`: between rounds it is no one's. Keep each `SIGNAL for <name>` and `NOW HERE for <name>` for that person's next narration.
   - **`BUILT:`** names who the place was built for: mention it in their next narration, as the line says.
   - **`NO MORE ROUNDS FOR NOW:`** this round was the last for now: finish this step and step 4, then stop and tell the owner why.
4. **Memory:** for each person in the cast, run `python3 tools/ask.py <id> --memory`. `NOTHING TO CONDENSE` means there was nothing to do; `REMEMBERED` means they thought back over a stretch in their own words, and it's stored as they gave it. Whatever they remembered, misremembered or left out is their memory, and how a person remembers is part of what's watched: never judge it, correct it or ask them again. `ASK FAILED`: tell the owner in one line and carry on; the stretch comes due again after the next round.
5. Tell the owner in one line: `Round <n> done.`, plus anything they'd want to know at once (a reply that failed, someone defeated). Nothing else: the dashboard and the log show the rest.
6. If the owner wrote to you during the round, stop here and answer them (as development, never in the fiction). Otherwise go on to the next round, until you've run the rounds asked for.

## When you stop
Run `python3 rules/rpg.py run status` and tell the owner, in a line or two, how many rounds were run and why you stopped (the reason from the list above). Nothing more: no account of where anyone is, what they did or what they remember, and never narration. The owner reads that on the dashboard.

Esc is the owner's hard stop. Whatever was in progress stays as it was, and the next `/rounds` finishes the open round from whoever's turn it was.
