"""Reads a game's content files. Knows the file format, nothing about any particular world.

Each game is a folder in games/<id>/ (world.md, rooms/, characters/, items/, quests/, tables/, curses/, scenes/, art/,
plus look.json and balance.json). Forged worlds (Stage 8) are folders of the same shape in state/worlds/<id>/: the
player's, not the kit's. rpg.py picks the active game with use_game() before reading anything.

A content file is Markdown with a front-matter block between two '---' lines.
Front matter is a tiny YAML subset:

    key: value
    key:
      - list item
    key:
      sub: value

Any value may end with a condition such as "(if bridge_clear)",
"(if not grukk_defeated)" or "(if a or b and not c)". 'and' binds tighter than 'or'.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GAMES = ROOT / "games"
WORLDS = ROOT / "state" / "worlds"  # forged worlds, installed by `rpg.py forge install`
KINDS = ("rooms", "characters", "items", "quests", "tables", "curses", "scenes")

_GAME = None  # the active game's folder; set by use_game()
_ID = None  # its id (a draft's folder isn't named after it)


def _ids_in(base):
    return {p.name for p in base.glob("*") if (p / "world.md").is_file()} if base.is_dir() else set()


def authored_games():
    """The kit's own games, in games/, sorted: the ones the checks cover."""
    return sorted(_ids_in(GAMES))


def is_forged(ident):
    """Whether `ident` is a world forged during play (state/worlds/), not one of the kit's games."""
    return ident not in _ids_in(GAMES) and ident in _ids_in(WORLDS)


def game_path(ident):
    return WORLDS / ident if is_forged(ident) else GAMES / ident


def use_game(ident, folder=None):
    """Make `ident` the game every other function reads. `folder` overrides where it lives (for drafts)."""
    global _GAME, _ID
    path = Path(folder) if folder else game_path(ident)
    if not (path / "world.md").is_file():
        raise KeyError("no game named %r (no world.md in %s)" % (ident, path))
    _GAME, _ID = path, ident


def game_dir():
    if _GAME is None:
        raise KeyError("no game chosen")
    return _GAME


def game_id():
    game_dir()
    return _ID


def list_games():
    """Every installed game's id, sorted: the kit's own and the forged ones."""
    return sorted(_ids_in(GAMES) | _ids_in(WORLDS))


def deep_merge(base, over):
    """`over` laid on `base`: dicts merge key by key, anything else (lists included) replaces."""
    out = dict(base)
    for k, v in over.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def kit_balance():
    return _json(ROOT / "rules" / "balance.json")


def kit_look():
    return _json(ROOT / "rules" / "look.default.json")


def balance():
    """The kit's rule numbers with the game's balance.json laid over them."""
    return deep_merge(kit_balance(), _json(game_dir() / "balance.json"))


def look():
    """The kit's default look with the game's look.json laid over it: colors, labels, tabs, phrases."""
    return deep_merge(kit_look(), _json(game_dir() / "look.json"))


def kit_presets():
    return _json(ROOT / "rules" / "presets.json")


def settings():
    """The owner's switches for the active game: its settings.json's preset, with its overrides laid
    over it. Settings say what the owner pays for; content's `generation:` says what may exist at all."""
    own = _json(game_dir() / "settings.json")
    presets = kit_presets()
    preset = own.get("preset", "normal")
    if preset not in presets:
        raise ValueError("settings.json: unknown preset %r (presets: %s)" % (preset, ", ".join(presets)))
    return dict(deep_merge(presets[preset], own.get("overrides") or {}), preset=preset)


def cast():
    """The game's cast (`cast.json`): the people who play it, one entry each, in order. Empty if it has none."""
    data = _json(game_dir() / "cast.json")
    return data if isinstance(data, list) else []


def game_json(name):
    """One of the game's own JSON files, unmerged (for validation)."""
    return _json(game_dir() / name)

_COND = re.compile(r"^(.*?)\s*\(if\s+(.+)\)\s*$")


def _scalar(text):
    text = text.strip()
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return text


def parse(text):
    """Return (meta dict, body string)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise ValueError("front matter has no closing '---'")
    meta, key = {}, None
    for raw in lines[1:end]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw.startswith((" ", "\t")):
            k, _, v = raw.partition(":")
            key = k.strip()
            meta[key] = _scalar(v) if v.strip() else None
            continue
        item = raw.strip()
        if key is None:
            raise ValueError("indented line with no parent key: %r" % raw)
        if item.startswith("- "):
            if meta[key] is None:
                meta[key] = []
            meta[key].append(_scalar(item[2:]))
        else:
            k, _, v = item.partition(":")
            if meta[key] is None:
                meta[key] = {}
            meta[key][k.strip()] = _scalar(v)
    return meta, "\n".join(lines[end + 1:]).strip()


def split_condition(value):
    """'trolls_hollow (if a or b)' -> ('trolls_hollow', 'a or b'); no condition -> (value, None)."""
    m = _COND.match(str(value))
    if not m:
        return str(value).strip(), None
    return m.group(1).strip(), m.group(2).strip()


def condition_holds(cond, flags):
    if cond is None:
        return True
    flags = set(flags)
    for alternative in re.split(r"\s+or\s+", cond):
        ok = True
        for term in re.split(r"\s+and\s+", alternative):
            term = term.strip()
            if term.startswith("not "):
                ok = ok and term[4:].strip() not in flags
            else:
                ok = ok and term in flags
        if ok:
            return True
    return False


def visible(values, flags):
    """Filter a list of possibly-conditional values down to the ones that apply now."""
    out = []
    for v in values or []:
        base, cond = split_condition(v)
        if condition_holds(cond, flags):
            out.append(base)
    return out


def sections(body):
    """Split a body into [(heading, text)] on '## ' headings. Text before the first heading has heading ''."""
    out, heading, buf = [], "", []
    for line in body.splitlines():
        if line.startswith("## "):
            out.append((heading, "\n".join(buf).strip()))
            heading, buf = line[3:].strip(), []
        else:
            buf.append(line)
    out.append((heading, "\n".join(buf).strip()))
    return [(h, t) for h, t in out if h or t]


def section_condition(heading):
    """'If a and not b' -> 'a and not b'; any other heading -> None."""
    m = re.match(r"^If\s+(.+)$", heading)
    return m.group(1).strip() if m else None


_PLAN = re.compile(r"^Plan:\s*([a-z][a-z0-9_]*)\s*(?:\(if\s+(.+)\))?\s*$")
PLAN_KEYS = ("does", "sets", "clears", "near", "rumor")


def is_plan(heading):
    """A `## Plan: …` section: what a character may do off-screen. It's for the rules, not for reading aloud."""
    return heading.startswith("Plan:")


_AT = re.compile(r"^At:\s*([a-z][a-z0-9_]*)\s*$")
AT_KEYS = ("when", "if", "sets", "seen", "rumor")


def is_timed(heading):
    """A `## At: …` section of world.md: something that happens when the world's clock reaches a day and a time."""
    return heading.startswith("At:")


def timed(body):
    """world.md's timed events: each `## At: <id>` section, whose lines are `when:` (day <n>, <a time of day>),
    `if:` (a condition, checked when the time comes), `sets:` (a shared flag), `seen:` (what everyone notices,
    wherever they are) and `rumor:` (what people say). Returns [{"id", <keys>..., "heading", "bad": [lines]}]."""
    out = []
    for heading, text in sections(body):
        if not is_timed(heading):
            continue
        m = _AT.match(heading)
        event = {"id": m.group(1) if m else None, "heading": heading, "bad": []}
        for line in text.splitlines():
            if not line.strip():
                continue
            k, _, v = line.partition(":")
            if k.strip() in AT_KEYS and v.strip():
                event[k.strip()] = v.strip()
            else:
                event["bad"].append(line.strip())
        out.append(event)
    return out


def plans(body):
    """A character's off-screen plans: each `## Plan: <step> (if <condition>)` section, whose lines are
    `does:`, `sets:` or `clears:` (one of the character's own flags), `near:` and `rumor:`.
    Returns [{"step", "when", <keys>..., "bad": [lines that aren't one of those keys]}]."""
    out = []
    for heading, text in sections(body):
        if not is_plan(heading):
            continue
        m = _PLAN.match(heading)
        step = {"step": m.group(1) if m else None, "when": m.group(2).strip() if m and m.group(2) else None,
                "heading": heading, "bad": []}
        for line in text.splitlines():
            if not line.strip():
                continue
            k, _, v = line.partition(":")
            if k.strip() in PLAN_KEYS and v.strip():
                step[k.strip()] = v.strip()
            else:
                step["bad"].append(line.strip())
        out.append(step)
    return out


def path_of(kind, ident):
    return game_dir() / kind / ("%s.md" % ident)


def exists(kind, ident):
    return path_of(kind, ident).is_file()


def load(kind, ident):
    p = path_of(kind, ident)
    if not p.is_file():
        raise KeyError("no %s named %r in %s/%s/" % (kind[:-1], ident, game_id(), kind))
    try:
        meta, body = parse(p.read_text(encoding="utf-8"))
    except ValueError as e:
        raise ValueError("%s/%s.md: %s" % (kind, ident, e))
    meta["id"] = ident
    meta["body"] = body
    return meta


def load_world():
    try:
        meta, body = parse((game_dir() / "world.md").read_text(encoding="utf-8"))
    except ValueError as e:
        raise ValueError("world.md: %s" % e)
    meta["body"] = body
    return meta


def ids(kind):
    d = game_dir() / kind
    return sorted(p.stem for p in d.glob("*.md")) if d.is_dir() else []
