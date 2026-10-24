---
name: newgame
description: Start a fresh run of the active CodeRPG game with its cast, resetting its save. Takes an optional seed, or "daily" for today's world. Switch games with /game.
disable-model-invocation: true
---

# New game

This is for the owner, who watches; nobody plays by typing. Narrate nothing.

1. Run `python3 rules/rpg.py newgame $ARGUMENTS`. The owner may have given a seed (`/newgame ember-4821`) or `daily` for today's world; with nothing, a new seed is chosen. This overwrites the active game's save with a fresh run built from its world file and its cast, so a run in progress ends there (its log stays in `state/log/`). The same seed always rolls the same run.
2. Tell the owner, in a few plain lines: the world (`NEW GAME:`), the seed, and who is in the cast, with their models and where each starts (`CAST:`). If `FROM EARLIER RUNS` lists places built or people befriended in earlier runs, say they're part of this world now. Don't repeat `THIS RUN` (the run's secrets) unless the owner asks.
3. The `look` that `newgame` prints at the end is the first person's view, for no one to read now: leave it. Nobody is told the opening here: each person's own opening reaches them in their first brief.
4. End by saying the run is ready, and that `/rounds` plays it.
