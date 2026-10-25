# Developing CodeRPG-Sim

Notes for whoever works on the fork next, human or Claude. `README.md` covers running a simulation, the layout, formats and features; this file covers how to work on it safely, and what was learned building it (the original's lessons included).

## Start here (Claude)

In the simulation fork, the owner's messages are development or questions; Claude acts as the referee only inside `/rounds` (`.claude/skills/rounds/SKILL.md`, with `gm-turn` for each turn). There is no in-game reminder hook and no need for `ooc:`.
- Never test in the real `state/save.json`; that's the player's game. Use a scratch copy (below).
- Run `sh tools/check.sh` before and after changes.
- Read `HANDOFF.md` next (where the build stands and what was decided), then `PLAN.md` and `SIMULATION-FORK-PROPOSAL.md`.
- Anything that spends real tokens (a dry run, a live session) waits for the owner's say-so.

## The invariants

Break these and the design falls apart:
1. **Only `rules/rpg.py` writes `state/save.json`.** Claude, agents and the mod never do. The library (`state/library/`) is written only by `rpg.py` and the owner's `tools/library.py`.
2. **Code decides uncertain outcomes.** Claude never rolls or does damage math. Generated content gets its stats from tier tables in `balance.json`, never from the world agent.
3. **Content holds world facts; instructions hold procedure.** No world facts in `CLAUDE.md`, the skills or the agent definitions. Story branching lives in content flags.
4. **The dashboard and the mod are presentation only.** They read the save, the log and `rpg.py`'s printed output, and never write game files; the dashboard's buttons ask `rpg.py run pause | end`. The game must work without them.
5. **The story is stored last.** `narrate` records how things stand after the turn into the person's memory, so every state write of a turn comes before it. (For the original's mod, narration was the last text of a turn; see *How the mod classifies text*.)
6. **Player, NPC and world agents have no tools** (`tools: []`, `omitClaudeMd: true`). They propose; the referee checks and applies through `rpg.py`.
7. **The kit knows no game.** `rules/`, `mod/`, `CLAUDE.md` and the skills never name a room, character, item or flag of a particular game. Anything particular to a game lives in `games/<id>/`: its content, its `look.json` and its `balance.json`. Every game in `games/` must keep passing every check, so the others prove nothing slipped through.
8. **It is the same game** (proposal section 2). A cast member decides only from what `rpg.py brief` prints, built from the same data a human player's screen is drawn from, and is told only the stories stored with `narrate`. Nothing they read names the machinery: `test_rules.py`'s `FORBIDDEN` pattern (game, rules, dice, flag, agent, model, player, log, d20, DC, roll, check, ids with underscores, …) is checked against every brief in the tests, and a dry run reads the real ones.

## Checks

```
sh tools/check.sh
```
It runs `rpg.py validate` (the kit's games in `games/`: content references, formats, soundness, and look/balance keys; forged worlds in `state/worlds/` aren't checked here), a compile of the Python, `tools/test_rules.py` (the engine tests, in a temp copy), `claude plugin validate mod`, `claude plugin test mod` (the mod's tests, `mod/tests/`), and a TypeScript type-check of the mod.
- **Type-check:** it needs `mod/tsconfig.json`, which Claude Code writes the first time it loads the mod; open one `claude --plugin-dir ./mod` session if it's missing. TypeScript comes through `npx`.
- **"✘ … the plugin directory refuses a submission for":** this is about submitting to Claude Code's public plugin catalog, which wants a README and a LICENSE inside `mod/`. It doesn't affect local use.

## Testing the engine

Work in a scratch copy, with the dice seeded:
```
cp -R . /tmp/rpg-test && cd /tmp/rpg-test
RPG_SEED=3 python3 rules/rpg.py newgame
python3 rules/rpg.py move east
RPG_SEED=7 python3 rules/rpg.py attack grukk
```
`RPG_SEED` makes rolls repeatable, and overrides a run's own seed (`newgame <seed>`), which does the same thing for players across separate commands. `rpg.py game switch <id>` picks the game; each keeps its own save in the scratch copy's `state/`. Proposals for `generate` and `world-turn` are JSON files: write one to `proposals/x.json`, then run `rpg.py generate extra proposals/x.json`. Also test malformed shapes; the script must refuse them, never crash. Behaviour worth keeping belongs in `tools/test_rules.py`, which drives the CLI the same way.

A round by hand, with the reply and the story in files (the referee writes them with the Write tool; quotes and apostrophes don't survive the shell):
```
python3 rules/rpg.py game switch thirteenth_stroke && RPG_SEED=3 python3 rules/rpg.py newgame test-1
python3 rules/rpg.py round start                      # ROUND 1: Hester Gimbal (hester), ...
python3 rules/rpg.py brief hester                     # what she knows
printf 'DO: I go north.\nJOURNAL: To see the square.\n' > proposals/reply.txt
python3 rules/rpg.py reply hester proposals/reply.txt
python3 rules/rpg.py move north --as hester           # the turn: --as on every rules command
echo 'You climb to the square.' > proposals/story.txt
python3 rules/rpg.py narrate hester proposals/story.txt   # ends her turn
python3 rules/rpg.py round end                        # once everyone has had theirs
```
In a shell script, drive this from Python (`subprocess`), not zsh: zsh doesn't split an unquoted variable into words, so `for p in $order` runs once.

## A dry run of the referee

The check for anything that changes what the cast is told (`PLAN.md`: a step marked **dry run**). It spends real tokens: ask the owner first.
1. A scratch copy without git: `cp -R . <scratch>/dry && rm -rf <scratch>/dry/.git <scratch>/dry/state/log`. Cut the cast in its `cast.json` if fewer people will do; `game switch <id>` and `newgame <seed>` there.
2. The referee, headless, in the background: `cd <scratch>/dry && CLAUDE_CODE_FORCE_SESSION_PERSISTENCE=1 claude -p "/rounds 3" --model sonnet --settings .claude/settings.json --output-format stream-json --verbose > run.jsonl`. An untrusted scratch folder warns that its `permissions.allow` entries are ignored; the commands still ran (2026-10-24). Its last line carries the duration and cost.
3. Run `python3 tools/audit.py state/log/<run>.jsonl --transcript <the referee's session file>` (in the scratch copy; the session file is in `~/.claude/projects/<scratch path with dashes>/`). It lists every leak hit, any sign of Claude Code's own lines in what people wrote, what the referee kept for later rounds (place notes, the story so far, the townspeople's memories, and any minor townsperson spoken to with nothing remembered), each turn's onlookers' note, the flags, the condensings, coins, endings and spend, and the referee's cut reads and any spawn whose prompt isn't what `rpg.py` printed. Then read the log (`state/log/<run>.jsonl`): every `brief`, `narration` and `speech` against the `FORBIDDEN` pattern and by eye; every `coins` entry's reason; the `command` sequence against `gm-turn` and `/rounds`. Read `run.jsonl` for the agents spawned (`npc` and `world`) and the referee's own text; each person's replies come through `tools/ask.py` (`claude -p`), so their cost is the `spend` on each `action` and `memory` entry, not in `run.jsonl`.
4. `tools/dashboard.py --port <n>` on the scratch copy shows the run; for a screenshot, a Chromium browser runs headless (`--headless=new --screenshot=<png> --window-size=1280,1700 --virtual-time-budget=4000 <url>`; for phone width, load the page in a 390px iframe, since desktop Chromium won't lay out a window narrower than about 500px).

## Testing live (the original's mod)

`tools/play.py` drives a real interactive Claude Code session in a pseudo-terminal and captures everything it draws:
```
python3 tools/play.py /tmp/rpg-test '[[12, "I walk north into the tavern.\r"], [90, null]]' --trust \
  --grep 'The Gull · dusk' 'rpg\.py|Skill ?\(|Ran \d' 'Recording|narrating\.'
```
- **What to check:** that wanted things appear (the arrival rule, a speaker's keyline, the change line, the dice tray) and plumbing never does, in *any* frame. Every frame is in the capture, so brief flashes count too.
- **A capture is the stream of what was written, not whole frames:** something drawn once and never changed (Claude Code's "auto mode on" label) appears only once, at startup, even though it stays on screen. "Absent from every frame" holds only for things that are redrawn; check static rows on a real screen.
- **Grep patterns:** the capture keeps one space where the screen had several (the arrival rule's `  The Gull  ` reads ` The Gull `), and redraws can drop letters mid-word, so grep short, single-spaced pieces.
- **`--trust`:** answers the trust prompt for a folder Claude Code hasn't seen. Accepting it records that folder as trusted in your Claude Code settings.
- **Cost:** turns cost real tokens; `--model sonnet` (the default here) keeps it moderate.
- **Setup:** play the scratch copy forward with `rpg.py` commands first (a hand-written proposal for `generate`, `talk`, `move`, `coins`), so the live session only plays the part being tested.
- **Long runs:** several GM turns outlast Bash's 10-minute limit; run `play.py` in the background. With `CLAUDE_CODE_FORCE_SESSION_PERSISTENCE=1` the session's transcript lands in `~/.claude/projects/<scratch path with dashes>/`, which shows the GM's calls and exact text far more readably than the capture.
- **The pane (the margin):** its hotkeys work only while it has focus. Send `/sheet\r` first, then the key (each game names its own; the station's map is `p`, the guide is `g` everywhere). A Button's hotkey must be a digit or a lowercase letter.
- **Leaks to expect:** during long turns Claude Code nudges the model to say what it's doing, and the GM may answer in the narration's first paragraph. The story filter (`isGmNote`) strips known shapes; add each new one to the mod tests.
- **Headless:** for checking *what the GM does* rather than how it looks, use `claude -p --settings .claude/settings.json --output-format stream-json --verbose "<action>"` in the scratch copy and read the tool calls. Pass `--settings` explicitly, because an untrusted folder's project settings aren't loaded.

## Debugging a real session

Every session's transcript is a JSONL file in `~/.claude/projects/<project path with dashes>/`. To see what the referee actually did in a turn (tool calls, the exact text it wrote), find the file with `grep -l "<a phrase from the turn>"`, then walk its rows: `type` is `user` or `assistant`, and `message.content` holds the text, tool_use and tool_result blocks. Most display bugs so far were diagnosed this way.

## How the mod classifies text

The original's mod, unused in phase 1 of the fork but kept passing its tests. This is the subtlest part of `mod/hooks/register.tsx`. If narration goes missing or notes leak, start here.
- **`turn.start`:** resets the per-turn bookkeeping, unless a GM turn is already running. A prompt typed mid-turn must not reset it.
- **Every assistant text block of a non-`ooc:` turn is held `pending`,** hidden until the turn ends. Text still streaming is hidden while `running` is set.
- **Each game tool call** (`isPlumbing`) moves the narration start forward, except recording-only commands (`WRITE_COMMANDS`: chronicle, remember, note, flag, coins, gain, lose, equip, library). The narration may come before those. A shell call that chains several commands is recording-only only if every one of them is (`onlyRecords`): the GM chains `remember …; scene end …`.
- **At `turn.complete`** (for the GM only; subagent completions carry `agentId` and are ignored):
  - text after the narration start is narration, except blocks that look like GM notes (`isGmNote`);
  - everything else is an aside: hidden if it's a short note, dimmed otherwise;
  - the first narration block gets the arrival rule (with the time of day) or the title card, and the last gets the change line (`changesOf` the save at `turn.start` and now) and any ending card;
  - each block gets its speakers' colors (`speakerCards`) and a `delay`, so its paragraphs appear after the blocks before it (and after a title card typing itself out).
- **Speech:** a paragraph starting with a name tag (`Pell: "…"`) is that person's speech, tag removed (`speechTag`); an untagged one falls back to the old heuristic (`speakerOf`: a quotation and someone named outside it). A tag must name someone met or here (by name, or words all in their name), or be a short capitalized name followed by a quotation, so "Ysolde stands at the door: …" stays narration.
- **A turn counts as play** if it used a game tool, or no tools at all (a pure-dialogue reply). A turn that used other tools is development, and its text is shown plainly.
- **`stripPreamble`** removes a GM note from the top of a narration block. `isGmNote` must not catch real story; the tests list the false positives that have bitten before, and any new case belongs there.
- **Story entries are keyed** by length plus an FNV-1a hash of the whole text (`storyKey`).

## Claude Code and mod API gotchas

- **Subagents run in the background by default.** `.claude/settings.json` sets `CLAUDE_CODE_FORK_SUBAGENT=0` so the referee waits for agents' replies.
- **A subagent's reply arrives as a message of its own** (`<agent-message from="…">[Subagent hand-back]…`), even from a blocking spawn, and it raises the UserPromptSubmit hook like a typed prompt. The prompt hook skips those, task notifications and command output, so they neither pay a turn nor get the in-game reminder.
- **SendMessage doesn't wait for a reply,** so every NPC line is a fresh spawn with the recent scene passed in.
- **`tools: []` works** for a tool-less agent, and **`omitClaudeMd: true`** keeps `CLAUDE.md` out of it (verified).
- **The shell refuses commands mixing braces and quotes** ("expansion obfuscation"), so JSON can't be passed through a heredoc. The referee writes proposals and replies with the Write tool into `proposals/`, which needs an `Edit(proposals/**)` permission rule. `Write(...)` rules are ignored.
- **Claude Code nudges long silent turns** to post a status update. That text is GM text like any other, and the classification above keeps it out of the story.
- **`turn.complete` fires for subagent turns too,** with `agentId` set. `turn.start` doesn't carry one.
- **Tool rows draw before their input has streamed in** (input `{}`), so unfinished game calls are hidden on suspicion and judged again when the input arrives.
- **The running-agents list** shows each Agent call's `description`. Mods can't redraw it, but the `tool.call` hook rewrites the description to an in-world phrase.
- **The mod validator rejects:**
  - two hooks on the same event without a matcher;
  - a variable named `on` (it shadows the registrar);
  - a function that receives `$` unless it's declared at the top of the file.
- **A prompt the mod submits (`$.prompt.submit`, even `asUser: true`) is labelled "Prompt from the coderpg plugin"** in the transcript, and its row never reaches the mod's own `ui.render` hook, so the label can't be hidden. The pane's buttons therefore fill the prompt box (`$.prompt.fill`) and the player presses Enter; Enter reaches the box even while the pane has focus.
- **Slash commands the mod registers don't raise `prompt.submit` or `turn.start`.** They're answered without a Claude turn.
- **Skill commands (`/newgame`, `/game`) raise no `command.run`**, only `prompt.submit` with `e.command` set. And `$.command.run` is refused inside a hook the turn waits on, such as `prompt.submit`. To run `/clear` before a skill, the mod drops the submission and runs `/clear` and then the skill from `$.clock.after`. Claude Code always shows "Prompt dropped by a hook: <reason>" for a moment (even with an empty reason), and a dropped prompt **stays in the prompt box** unless the mod empties it with `$.prompt.fill`.
- **`tools/play.py` sessions keep no transcript** (a child session: "Transcript saving is off"). Set `CLAUDE_CODE_FORCE_SESSION_PERSISTENCE=1` to keep them, or diagnose from the capture.
- **Animations are surface modules** (`<Client module="./reveal.tsx" props={…} />`): they run on the drawing thread with their own state and `surface.every` frame clock, so nothing dispatches per frame. `module` must be a string literal, on an element written as `<Client …>` itself: the engine finds the modules by reading the source, so an alias (`const C = Client`) loads nothing. A module may not nest a `Client`, and three `setState`s in a row with no tick between count as a render loop. Each plays only when its story entry or tray is fresh (`FRESH_MS`); older ones are drawn still with the same pure frame function at its end, so history never replays. Tests drive them with `ui.advance(ms)` and read them with `find({ in: key })`; `mock.clock(on, { now })` stands in for `$.clock`, which tests otherwise lack (the mod treats a missing clock as "nothing is fresh").
- **Real usage** (`mod/hooks/spend.ts`, `/budget`): `turn.step`'s result carries each request's `usage` (four token counts and the model), with `agentId` on the input for a subagent; `agent.spawn` maps that id to its `subagentType`; `session.measure` brings the plan's rate-limit windows after each main turn. `turn.step` streams, so its hook is `async function* ($, e, next) { const r = yield* next(e); …; return r }`. `/clear` restarts Claude Code's own counters but not the mod's process, so the mod's totals carry on. **`$.store` is one file for every folder** (scratch copies too), so the spend records are keyed `spend:<project root>`.
- **`$.state` is per Claude Code session:** `/clear` (which `/newgame` and `/game` run) starts a new session in the same process, and every atom comes back empty; module variables survive. Anything that must outlive it is kept in `$.store` too and brought back (`ensureSpend`), or re-read from the save (`refresh`).
- **Ink boxes have no per-side borders.** The vitals frame is drawn by hand, row by row, with `fitCells` keeping rows inside the frame.
- **Mod tests:**
  - seed state with `on('state.get', { plugin: 'coderpg', key: 'save' }, () => ({ value: { value: SAVE, version: 1 } }))`. A test hook answering a `$` call wraps its answer in `{ value: … }`;
  - mount UI with `$.ui.mount({ plugin, surface, component, requestId, props })` and inspect it with `find`/`findAll`. Mounted elements expose `props` and `children`.
  - drive hooks by calling the event on the test's `$` (`$.session.start(…)`, `$.turn.step(…)`, `$.agent.spawn(…)`). Every hook beneath the mod, `on(...)` answering what the engine would, must be registered before the test's first `$` call. A test hook receives `($, e, next)`. Stand-ins must return the fields the engine checks (`session.start` `{ cwd }`, `turn.complete`'s input `{ answer }`). Writes the mod makes with `void` need `clock.settle()` before they're read (see the real-use test).
- **Untrusted folders** don't load their project `.claude/settings.json` (permissions, env, hooks).

## Changing things

- **New feature that spends tokens:** if it goes beyond playing the game as written (baseline play is never charged), give its kind a price in `rules/balance.json` `meter.prices`, charge it with `charge(kind)` where the spending happens (after every check that could refuse), refuse with an in-fiction reason when `can_pay(kind)` is false, and give it a switch in `rules/presets.json` (all three presets, the same keys) read through `SETTINGS`.
- **New `rpg.py` command:** add it to `COMMANDS`. A referee command that names the person itself (`brief <id>`) goes in `REFEREE_COMMANDS`; one that may also run for no one, between rounds, in `NO_ONE_COMMANDS` (world turns). Anything a person is told needs a `FORBIDDEN` check in the tests and a dry run. For the original's mod: If its output should show in the dice tray, add it to `TRAY_COMMANDS` and teach `trayLines` (`mod/hooks/tray.ts`) its format. If it only records something, add it to `WRITE_COMMANDS`.
- **New save field:** for a field read with `.get`, nothing more; otherwise bump `STATE_VERSION` and add a migration to `MIGRATIONS` (the fork starts at version 10, and refuses the original's saves). Extend `refresh_view` if an interface needs it.
- **New content field:** document it in the README, teach `rpg.py validate` to check it, and use it in both shipped games.
- **Writing JSON from Python:** use `ensure_ascii=False`, or icons such as ✦ are written as `\u2726`.
- **New look or balance setting:** add it with a default to `rules/look.default.json` or `rules/balance.json` (validate rejects keys the defaults don't have), mirror look keys in `CoderpgLook` and `DEFAULT_LOOK` (`mod/hooks/look.ts`), and read it from the save's `view.look`, never from a game folder.
- **New game:** a folder in `games/` with a `world.md`; everything else is optional. `validate` and `test_rules.py` pick it up automatically. It should also pass `validate --game <id> --kit-complete`, as both shipped games do.
- **The referee's behaviour:** `CLAUDE.md` holds the standing orders (keep it short), `.claude/skills/rounds/SKILL.md` the round and `.claude/skills/gm-turn/SKILL.md` the turn (there is no per-message reminder hook). Sonnet at medium effort cuts corners on short turns, so test procedure changes with it, in a dry run.

## Known limits

- **Between people, only words for now.** Handing something over, trading, contests and harm wait for phase 2; the referee treats an attempt as refused.
- **Rumors are heard among people,** not when someone tells them: the referee voices `[minor]` characters without a command the engine could catch, so a person hears the talk going around whenever any of the world's people is with them at their brief or `look`.
- **Claude Code adds its own lines to every person's call** (`tools/ask.py`), whatever `--system-prompt` says, and they can't be switched off. `ask.py` asks from `/tmp/here` (made if missing, outside any git repository), so the environment note names neither the project nor the owner. A person's own question about it is answered from those lines (step 28's probe), so the fiction rests on their not asking. `audit.py`'s *SIGNS OF CLAUDE CODE'S LINES* looks for their traces in what people write (the run's year, Claude, Anthropic, a model's name, macOS or darwin, an email address): read each hit, since a haiku may be a poem. `player.md` says nothing about them: a line telling a person to ignore something admits there is something to ignore (JW), so that waits until the audit ever finds one.
  - **See them:** `python3 tools/probe.py <id>` (free) makes that person's brief from a copy of the game, runs `claude -p` exactly as `ask.py` does with `ANTHROPIC_BASE_URL` pointed at a stand-in on 127.0.0.1 that forwards nothing and answers with an error, and prints every system block and message of the request as sent. It never keeps or prints a header, so the login token is never read. **Run it after every Claude Code update**, and compare with what it showed on 2026-10-25 (Claude Code 2.1.310, Dilly on Haiku): `system[0]` a billing line (`x-anthropic-billing-header: cc_version=…; cc_entrypoint=sdk-cli;`); `system[1]` "You are a Claude agent, built on Anthropic's Claude Agent SDK."; `system[2]` the player's instructions, exactly; `messages[0]` a `<system-reminder>` with `# userEmail` (the owner's login email), then the brief, exactly; `messages[1]` (a system message) `# Environment`: working directory `/private/tmp/here`, not a git repository, platform darwin, shell zsh, the OS version, a note on untrusted downloaded files, the model's name and id, its knowledge cutoff, and today's date; no tools. Anything new there is something a person now reads.
  - **Why no proxy to strip them** (JW, 2026-10-25): Anthropic's docs allow routing a subscription login through a gateway address, but tell gateways to forward requests unchanged and "inspect without modifying". The first system line and the attribution block are what Anthropic's servers use to recognise Claude Code traffic, and the legal page says Anthropic may enforce its authentication rules without notice. A proxy that rewrites requests is unsupported and would have to track every release; the account at risk is the one this whole project runs on. Four lines of boilerplate aren't worth that. (A free capture showed `claude -p` does send its requests, login attached, to a local `ANTHROPIC_BASE_URL`; that is all `probe.py` uses, and it forwards nothing.)
- **The meter refills per Claude Code session.** A long run on one meter slows to the game as written once it's spent (no world turns, no new orders), and the cast sees only that the maker is busy.

The original's mod (unused in phase 1):

- **Narration appears all at once** at the end of a turn, because text is held back so GM notes can't leak; it then shows a paragraph at a time (`page.tsx`, 150 ms each, dim then full: a terminal has no opacity, and `Markdown` draws only plain or dim). A key pressed meanwhile (`prompt.edit`) shows it whole.
- **A render's `viewport.columns` is the transcript's column** (narrower beside a docked pane); `$.ui.panes()` says whether the pane is placed and shown. Render hooks may not write state.
- **A slash command's echo (`❯ /map`) is Claude Code's own row:** the `UserMessage` hook sees only the brief row drawn while the command runs, then the engine redraws the echo without asking. So command answers stay at the left edge under their echo (moving only the answer splits them). `CommandOutput`'s `text` arrives with the plugin's name in front (`coderpg: …`).
- **No mod can restyle the prompt's `❯`, bind Esc, or hide the permission-mode label** in front of the hint line (no render component carries it; drawing `PromptHint` whole doesn't remove it, and drops Claude Code's pills). The pane takes keys after ctrl+x tab or a click; the play hint says so.
- **Story styling is per session.** A resumed session shows earlier narration plain.
- **Room pictures and a pixel-art map** (`Image`/`Raster` elements) are designed for but not built; see the pane ideas in the conversation history.
