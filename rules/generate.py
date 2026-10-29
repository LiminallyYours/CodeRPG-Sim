"""Checks what the world agent proposes and turns it into run content. Pure: no files, no state.

Every function takes the proposal (parsed JSON) and a Context and returns a Patch: the entities
to add to the save's `run` section. Anything out of bounds raises ValueError with the reason.
Numbers never come from the proposal: item and foe stats come from the tiers in balance.json.

Everything made here is marked `made_by`: "world" when the world invented it, "player" when the player
ordered it from a maker or builder. Both go through the same checks; only the tag and the gate differ.
"""
import copy
import re

OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east",
            "up": "down", "down": "up", "in": "out", "out": "in",
            "northeast": "southwest", "southwest": "northeast", "northwest": "southeast", "southeast": "northwest"}
ID = re.compile(r"^[a-z][a-z0-9_]{2,29}$")
TERM = re.compile(r"\b(?!and\b|or\b|not\b)([a-z][a-z0-9_]*)\b")


class Declined(ValueError):
    """The maker turns the order down (outside their trade): not a malformed proposal, so no retry."""


class Context:
    """What a proposal is checked against. Built by rpg.py from content and the save."""

    def __init__(self, *, location, taken_ids, taken_names, expand, policy, balance, count,
                 items_found_here, extras_here, characters_here, room_ids, generated_people,
                 terrains=(), terrain_here=None, moves=0, maker=None, makes=(), builder=None, build_spots=None,
                 depth_here=0, plan_steps=None, board_rooms=(), arrival_open=False):
        self.location = location                    # the player's room id
        self.taken_ids = set(taken_ids)             # every id in use, any kind
        self.taken_names = {n.lower() for n in taken_names}
        self.expand = list(expand)                  # unused directions this room may grow in
        self.policy = policy                        # {"extras": True, "rooms": False, ...}
        self.balance = balance                      # balance.json "generation"
        self.count = count                          # entities generated so far this run
        self.items_found_here = items_found_here
        self.extras_here = extras_here
        self.characters_here = list(characters_here)
        self.room_ids = set(room_ids)
        self.generated_people = set(generated_people)
        self.terrains = list(terrains)              # the look's terrain kinds, for the map
        self.terrain_here = terrain_here            # the player's room's terrain: a new room's default
        self.moves = moves                          # moves made this run
        self.maker = maker                          # who the player is ordering from (craft), or None
        self.makes = list(makes)                    # the item tiers that maker makes
        self.builder = builder                      # who the player is ordering a building from, or None
        self.build_spots = dict(build_spots or {})  # {direction: what fits there}: this room's free build spots
        self.depth_here = depth_here                # how many generated rooms deep the player's room is (authored: 0)
        self.plan_steps = dict(plan_steps or {})    # {character: [plan steps open now]}: who may act off-screen
        self.board_rooms = list(board_rooms)       # rooms with a notice board (`board: yes`)
        self.arrival_open = arrival_open           # whether someone new may arrive on this world turn


NOTICE_CHARS = 160  # a notice on a board, whoever puts it up (a person through `post`, or the world's turn)


def empty_patch():
    return {"rooms": {}, "characters": {}, "items": {}, "quests": {},
            "exits": {}, "placements": {}, "room_items": {}, "commissions": {}, "rumors": [], "moves": [], "plans": [],
            "notices": [], "arrival": None}


def _allowed(ctx, kind):
    if not ctx.policy.get(kind):
        raise ValueError("this adventure does not allow generated %s" % kind)


def _obj(x, what):
    """Each nested part of a proposal must be a JSON object; say which one isn't."""
    if not isinstance(x, dict):
        raise ValueError("%s must be an object like the brief shows, not %s" % (what, type(x).__name__))
    return x


def _list(x, what):
    if x is None:
        return []
    if not isinstance(x, list):
        raise ValueError("%s must be a list" % what)
    return x


def _text(p, key, limit, required=True):
    v = p.get(key)
    if v is None or (isinstance(v, str) and not v.strip()):
        if required:
            raise ValueError("missing %r" % key)
        return ""
    if not isinstance(v, str):
        raise ValueError("%r must be text" % key)
    v = " ".join(v.split())
    if len(v) > limit:
        raise ValueError("%r is too long (%d characters, at most %d)" % (key, len(v), limit))
    return v


def _lines(p, key, most, limit, required=True):
    v = p.get(key) or []
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise ValueError("%r must be a list of text lines" % key)
    if required and not v:
        raise ValueError("%r needs at least one line" % key)
    out = [" ".join(x.split()) for x in v][:most]  # extra lines are dropped, not an error
    for x in out:
        if len(x) > limit:
            raise ValueError("a line in %r is too long (at most %d characters)" % (key, limit))
    return out


def _claim(p, ctx, patch_ids):
    ident = p.get("id")
    if not isinstance(ident, str) or not ID.match(ident):
        raise ValueError("id must be 3-30 lowercase letters, digits or underscores, starting with a letter")
    if ident in ctx.taken_ids or ident in patch_ids:
        raise ValueError("id %r is already in use" % ident)
    name = _text(p, "name", 40)
    if name.lower() in ctx.taken_names:
        raise ValueError("the name %r is already in use" % name)
    patch_ids.add(ident)
    ctx.taken_names.add(name.lower())
    return ident, name


def _budget(ctx, n):
    if ctx.count + n > ctx.balance["max_per_run"]:
        raise ValueError("this run has generated as much as it may (%d)" % ctx.balance["max_per_run"])
    ctx.count += n


# ---------------------------------------------------------------- kinds

def _tiered_item(p, ctx, patch, ids, made_by, tiers=None):
    """An item whose stats come from its tier (one of `tiers`, by default every item tier). Returns its id."""
    tiers = tiers or list(ctx.balance["item_tiers"])
    tier = p.get("tier")
    if tier not in tiers:
        raise ValueError("tier must be one of %s" % ", ".join(tiers))
    ident, name = _claim(p, ctx, ids)
    meta = dict(name=name, generated="yes", made_by=made_by, tier=tier, **ctx.balance["item_tiers"][tier])
    patch["items"][ident] = {"meta": meta, "body": _text(p, "description", 400)}
    return ident


def item(p, ctx, patch=None, ids=None, place=True):
    """A found or traded item. `tier` picks its stats: trinket, light_weapon, weapon or tonic."""
    _allowed(ctx, "items")
    patch = patch if patch is not None else empty_patch()
    ids = ids if ids is not None else set()
    ident = _tiered_item(p, ctx, patch, ids, "world")
    _budget(ctx, 1)
    if place:
        if ctx.items_found_here >= ctx.balance["items_found_per_room"]:
            raise ValueError("this room has already yielded a generated item")
        patch["room_items"].setdefault(ctx.location, []).append(ident)
    return patch


def craft(p, ctx):
    """An item the player ordered from a maker, within the maker's tiers. It waits as a commission until
    paid for; the price comes from balance.json, never the proposal. It doesn't count toward the run's
    generation limit (crafting has its own), and the content's generation policy doesn't apply."""
    if p.get("refuse") is not None:
        raise Declined(_text(p, "refuse", 200))
    if not ctx.maker:
        raise ValueError("no order is open: run `world-brief craft <maker>` first")
    patch = empty_patch()
    ident = _tiered_item(p, ctx, patch, set(), "player", tiers=ctx.makes)
    tier = p["tier"]
    patch["commissions"][ident] = {"kind": "item", "maker": ctx.maker, "price": int(ctx.balance["craft_price"][tier]),
                                   "status": "ordered", "ordered_at": ctx.moves}
    return patch


def _character_body(p, kind):
    knows = _lines(p, "knows", 3, 160)
    parts = []
    if kind == "extra":
        parts += ["## Look", _text(p, "look", 200)]
    else:
        parts += ["## Personality", _text(p, "personality", 300)]
    parts += ["## How they speak", _text(p, "speech", 200), "## What they know"] + ["- " + k for k in knows]
    if kind == "character":
        parts += ["## What they want", _text(p, "wants", 200)]
    return parts


def extra(p, ctx):
    """An unnamed person from a room's prose, made into someone the player can talk to."""
    _allowed(ctx, "extras")
    if ctx.extras_here >= ctx.balance["extras_per_room"]:
        raise ValueError("this room already has as many generated extras as it may")
    patch, ids = empty_patch(), set()
    ident, name = _claim(p, ctx, ids)
    body = _character_body(p, "extra") + [
        "## GM only",
        "- A generated extra: no items, no trades, no combat, no flags. They only know public things and gossip.",
    ]
    patch["characters"][ident] = {"meta": {"name": name, "role": _text(p, "role", 80), "minor": "yes", "generated": "yes",
                                           "made_by": "world", "extra": "yes"}, "body": "\n".join(body)}
    patch["placements"].setdefault(ctx.location, []).append(ident)
    _budget(ctx, 1)
    return patch


def character(p, ctx, patch=None, ids=None, room=None):
    """A minor character with an optional trade and an optional fighting tier."""
    _allowed(ctx, "characters")
    patch = patch if patch is not None else empty_patch()
    ids = ids if ids is not None else set()
    ident, name = _claim(p, ctx, ids)
    meta = {"name": name, "role": _text(p, "role", 80), "minor": "yes", "generated": "yes", "made_by": "world"}
    body = _character_body(p, "character")
    gm = ["## GM only", "- Generated for this run."]
    trades = _list(p.get("trades"), "trades")
    if len(trades) > 2:
        raise ValueError("trades must be a list of at most 2")
    if trades:
        body.append("## What they will trade or reveal")
    for t in trades:
        if not isinstance(t, dict) or not isinstance(t.get("item"), dict):
            raise ValueError("each trade needs an 'item' (a new item) and a 'price'")
        price = t.get("price")
        if not isinstance(price, int) or not 1 <= price <= 6:
            raise ValueError("a trade price must be a whole number of coins from 1 to 6")
        item(t["item"], ctx, patch, ids, place=False)
        iid = t["item"]["id"]
        body.append("- Sells %s for %d coins." % (patch["items"][iid]["meta"]["name"], price))
        gm.append("- Sale: `coins -%d purchase`, then `gain %s`." % (price, iid))
    tier = p.get("tier")
    if tier is not None:
        tiers = ctx.balance["foe_tiers"]
        if tier not in tiers:
            raise ValueError("tier must be one of %s, or left out for someone who won't fight" % ", ".join(tiers))
        meta.update(tiers[tier], fights=tier)
        gm.append("- Fights (as a %s foe) only if attacked or badly provoked." % tier)
    patch["characters"][ident] = {"meta": meta, "body": "\n".join(body + gm)}
    patch["placements"].setdefault(room or ctx.location, []).append(ident)
    _budget(ctx, 1)
    return patch


def _place(p, ctx, ids, directions, made_by, what):
    """The checks every new place passes, generated or built: a direction it may go in, a way back, a new id and
    name, a terrain the map knows, a short description. Returns (id, direction, record)."""
    direction = p.get("direction")
    if direction not in directions:
        raise ValueError("%s can only go %s" % (what, " or ".join(directions) if directions else "nowhere from here"))
    back = OPPOSITE.get(direction)
    if not back:
        raise ValueError("no way back is known for direction %r" % direction)
    ident, name = _claim(p, ctx, ids)
    terrain = p.get("terrain") or ctx.terrain_here
    if terrain is not None and terrain not in ctx.terrains:
        raise ValueError("terrain must be one of %s" % ", ".join(ctx.terrains))
    meta = {"name": name, "generated": "yes", "made_by": made_by, "depth": ctx.depth_here + 1, "exits": {back: ctx.location}}
    if terrain:
        meta["terrain"] = terrain
    return ident, direction, {"meta": meta, "body": _text(p, "description", 900)}


def room(p, ctx):
    """A new place off the player's room, through one of the directions the room may grow in."""
    _allowed(ctx, "rooms")
    patch, ids = empty_patch(), set()
    ident, direction, record = _place(p, ctx, ids, ctx.expand, "world", "a new place here")
    _budget(ctx, 1)
    items = [_obj(x, "each of the room's items") for x in _list(p.get("items"), "items")]
    chars = [_obj(x, "each of the room's characters") for x in _list(p.get("characters"), "characters")]
    if len(items) > 2 or len(chars) > 1:
        raise ValueError("a generated room holds at most 2 items and 1 character")
    for it in items:
        item(it, ctx, patch, ids, place=False)
        patch["room_items"].setdefault(ident, []).append(it["id"])
    for ch in chars:
        character(ch, ctx, patch, ids, room=ident)
    patch["rooms"][ident] = record
    patch["exits"][ctx.location] = {direction: ident}
    return patch


def build(p, ctx):
    """A place the player ordered from a builder, at one of this room's build spots. It passes the same checks
    as a generated room but starts empty. It waits, unbuilt, as an order (the record rides in the order) until
    paid for; rpg.py adds it to the world when the work is done. The price comes from balance.json."""
    if p.get("refuse") is not None:
        raise Declined(_text(p, "refuse", 200))
    if not ctx.builder:
        raise ValueError("no order is open: run `world-brief build <builder>` first")
    if p.get("items") or p.get("characters"):
        raise ValueError("a built place starts empty: no items or characters")
    ident, direction, record = _place(p, ctx, set(), list(ctx.build_spots), "player", "it")
    patch = empty_patch()
    patch["commissions"][ident] = {"kind": "room", "maker": ctx.builder, "price": int(ctx.balance["build_price"]),
                                   "status": "ordered", "ordered_at": ctx.moves, "room": ctx.location,
                                   "direction": direction, "record": record}
    return patch


def quest(p, ctx):
    """A small side quest from someone present. Its flags are its own: side_<id>_<word>."""
    _allowed(ctx, "side_quests")
    patch, ids = empty_patch(), set()
    ident, name = _claim(p, ctx, ids)
    giver = p.get("giver")
    if giver not in ctx.characters_here:
        raise ValueError("the giver must be someone in this room: %s" % ", ".join(ctx.characters_here or ["no one"]))
    objectives = [_obj(o, "each objective") for o in _list(p.get("objectives"), "objectives")]
    if not 1 <= len(objectives) <= 4:
        raise ValueError("a side quest has 1 to 4 objectives")
    lines, flags = [], set()
    for o in objectives:
        text = _text(o, "text", 120)
        cond = _text(o, "done_when", 160)
        for term in TERM.findall(cond):
            if term.startswith("side_%s_" % ident):
                flags.add(term)
            elif not term.startswith(("has_", "met_")):
                raise ValueError("objective conditions may only use side_%s_<word>, has_<item> or met_<character> (got %r)"
                                 % (ident, term))
        lines.append("%s (done when %s)" % (text, cond))
    reward = _obj(p.get("reward") or {}, "reward")
    coins = reward.get("coins", 0)
    if not isinstance(coins, int) or not 0 <= coins <= ctx.balance["side_quest_max_coins"]:
        raise ValueError("the reward is 0 to %d coins" % ctx.balance["side_quest_max_coins"])
    gm = ["## GM only",
          "- Generated side quest. Set its flags as the player does each step: %s." % (", ".join(sorted(flags)) or "none"),
          "- It never touches the main quest."]
    pay = ["`coins +%d job`" % coins] if coins else []
    if reward.get("item"):
        item(_obj(reward["item"], "the reward item"), ctx, patch, ids, place=False)
        pay.append("`gain %s`" % reward["item"]["id"])
    gm.append("- When complete, %s gives the reward: %s." % (giver, ", ".join(pay) or "thanks only"))
    last = objectives[-1]
    patch["quests"][ident] = {"meta": {"name": name, "giver": giver, "generated": "yes", "made_by": "world", "objectives": lines,
                                       "completed_by": _text(last, "done_when", 160)},
                              "body": "\n".join(["## Summary", _text(p, "summary", 300)] + gm)}
    _budget(ctx, 1)
    return patch


REUSE_KINDS = {"extra": ("characters", "extras"), "character": ("characters", "characters"),
               "room": ("rooms", "rooms"), "item": ("items", "items")}


def retier(kind, record, balance):
    """A copy of a library record with its stats taken afresh from today's tiers (balance.json `generation`)."""
    rec = copy.deepcopy(record)
    meta = rec["meta"]
    if kind == "items" and meta.get("tier") in balance["item_tiers"]:
        for k in ("weight", "damage", "heal"):
            meta.pop(k, None)
        meta.update(balance["item_tiers"][meta["tier"]])
    if kind == "characters" and meta.get("fights") in balance["foe_tiers"]:
        for k in ("hp", "defense", "attack", "damage"):
            meta.pop(k, None)
        meta.update(balance["foe_tiers"][meta["fights"]])
    meta.pop("carried", None)
    return rec


def reuse(ident, entry, ctx, request, direction=None):
    """A library entry brought back into this run instead of something new (the same dockhand turns up again),
    with what came with it. The same checks as new: where it may go, how much this run may generate, ids and
    names still free. Stats come from today's tiers, never from the old record."""
    if request not in REUSE_KINDS:
        raise ValueError("only people, places and things can be brought back")
    kind, allowed = REUSE_KINDS[request]
    _allowed(ctx, allowed)
    if entry["kind"] != kind or (kind == "characters" and (entry["record"]["meta"].get("extra") == "yes") != (request == "extra")):
        raise ValueError("%s isn't a fitting %s" % (ident, request))
    patch = empty_patch()
    parts = [(kind, ident, entry["record"], True)] + [(b["kind"], b["id"], b["record"], b.get("placed", False))
                                                      for b in entry.get("bundle") or []]
    for k, i, rec, _ in parts:
        if i in ctx.taken_ids or str(rec["meta"].get("name", "")).lower() in ctx.taken_names:
            raise ValueError("%s is already part of this run" % i)
        patch[k][i] = retier(k, rec, ctx.balance)
        patch[k][i]["meta"].update(generated="yes", made_by="world")
    if request == "room":
        if direction not in ctx.expand:
            raise ValueError("a new place here can only go %s" % (" or ".join(ctx.expand) if ctx.expand else "nowhere from here"))
        patch["rooms"][ident]["meta"].update(exits={OPPOSITE[direction]: ctx.location}, depth=ctx.depth_here + 1)
        patch["exits"][ctx.location] = {direction: ident}
        for k, i, _, placed in parts[1:]:
            if k == "characters":
                patch["placements"].setdefault(ident, []).append(i)
            elif placed:
                patch["room_items"].setdefault(ident, []).append(i)
    elif kind == "characters":
        if request == "extra" and ctx.extras_here >= ctx.balance["extras_per_room"]:
            raise ValueError("this room already has as many generated extras as it may")
        patch["placements"].setdefault(ctx.location, []).append(ident)
    else:
        if ctx.items_found_here >= ctx.balance["items_found_per_room"]:
            raise ValueError("this room has already yielded a generated item")
        patch["room_items"].setdefault(ctx.location, []).append(ident)
    _budget(ctx, len(parts))
    return patch


def world_turn(p, ctx):
    """Off-screen life: new rumors, generated people moving between rooms, and major characters' plan steps
    (only ones open now; rpg.py applies them). Nothing mechanical."""
    patch = empty_patch()
    patch["rumors"] = _lines(p, "rumors", 3, 160, required=False)
    for mv in _list(p.get("moves"), "moves"):
        if not isinstance(mv, dict) or mv.get("id") not in ctx.generated_people or mv.get("room") not in ctx.room_ids:
            raise ValueError("moves may only send generated people to rooms that exist")
        patch["moves"].append({"id": mv["id"], "room": mv["room"]})
    for pl in _list(p.get("plans"), "plans"):
        if not isinstance(pl, dict) or pl.get("step") not in ctx.plan_steps.get(pl.get("who"), ()):
            raise ValueError("plans may only pick a step listed as open for that person (%s)" % (
                "; ".join("%s: %s" % (c, ", ".join(s)) for c, s in ctx.plan_steps.items()) or "nobody has one now"))
        if any(x["who"] == pl["who"] for x in patch["plans"]):
            raise ValueError("each person does at most one thing per world turn")
        patch["plans"].append({"who": pl["who"], "step": pl["step"]})
    notes = _list(p.get("notices"), "notices")
    if len(notes) > 1:
        raise ValueError("at most one notice a world turn")
    for n in notes:
        if not isinstance(n, dict) or n.get("room") not in ctx.board_rooms:
            raise ValueError("a notice goes on a board: a room with one (%s)" % (", ".join(ctx.board_rooms) or "there are none"))
        text = " ".join(str(n.get("text") or "").split())
        if not text or len(text) > NOTICE_CHARS:
            raise ValueError("a notice is one short text, at most %d characters" % NOTICE_CHARS)
        patch["notices"].append({"room": n["room"], "text": text})
    arrival = p.get("arrival")
    if arrival is not None:
        if not ctx.arrival_open:
            raise ValueError("no one new arrives on this world turn (only where the world says who may, once a day, "
                             "while the run's limit allows)")
        _obj(arrival, "arrival")
        if arrival.get("room") not in ctx.room_ids:
            raise ValueError("an arrival comes to a room that exists")
        character(arrival, ctx, patch, set(), room=arrival["room"])
        patch["arrival"] = next(iter(patch["characters"]))
    return patch


KINDS = {"extra": extra, "item": item, "character": character, "room": room, "quest": quest, "craft": craft, "build": build}
