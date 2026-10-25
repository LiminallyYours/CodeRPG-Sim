# The bench

Fixed moments of people's lives, put to them again cheaply before a change goes into a run (`tools/bench.py`;
`python3 tools/bench.py` with no arguments says how). Part of the instrument, so kept in git.

- `moments/`: one file a moment. **Frozen** ones hold a brief exactly as a past run's log had it (or a copy edited
  by hand, marked so): only the instructions can vary for them. **Saved** ones hold a whole save; their brief is
  rebuilt with the current code and wording each time, so they show every kind of change.
- `variants/`: instructions to try in place of `.claude/agents/player.md` (`run --variant <file>`). Not used in runs.
- `results/`: each live pass: every brief's and variant's version tag, every reply, its cost and exact model.
