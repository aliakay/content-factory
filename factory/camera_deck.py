"""The camera deck: which move each scene gets, dealt deterministically so a film never repeats itself.

A scene plan that names its camera per scene still drifts into one move (the designer's favourite) or spends the
disorienting moves in the first ten seconds. This deals the moves like cards instead of choosing them one by one:

- every move has a weight per tempo, so a contemplative film holds and a fast one pushes and cuts;
- the previous shot's move, size and transition are taken out of the deck, so no two neighbours match;
- a move marked ONCE (the big ones: orbit, dolly_zoom) appears at most once, and it is placed at 55–75 % of the film,
  where a big move lands as a turn rather than as an opening flourish;
- the same idea text always deals the same deck (seeded by the project id + tempo), and moves the last films opened
  or signed with are pushed back by a weight factor (`memory`), so a series does not open the same way twice.

The deck is advice, not a rule: `camera.problems()` still refuses a plan that ignores the vocabulary. The scene plan
receives the deck in its design pass (`factory/hat/shortplan.py`), so the designers draw *against* a varied deck.
"""
import hashlib

WEIGHTS = {
    # move: (energetic, standard, contemplative)
    "hold": (0.5, 2.0, 4.0),
    "push_in": (3.0, 2.5, 1.5),
    "pull_out": (1.5, 1.5, 1.5),
    "pan_left": (2.0, 1.5, 1.0),
    "pan_right": (2.0, 1.5, 1.0),
    "tilt_up": (1.0, 1.0, 1.0),
    "tilt_down": (1.0, 1.0, 1.0),
    "zoom_to": (2.5, 1.5, 0.8),
    "follow": (3.0, 1.2, 0.5),
    "rack_focus": (1.2, 1.0, 1.0),
    "orbit": (3.0, 2.0, 1.0),
    "dolly_zoom": (3.0, 1.0, 0.0),
}
TEMPOS = ("energetic", "standard", "contemplative")
ONCE = ("orbit", "dolly_zoom")                 # the disorienting moves: once per film, mid-film
BIG_AT = (0.55, 0.75)                         # where the one big move sits (share of the scenes)
MEMORY_FACTOR = 0.3                            # a move the last films opened with is pushed back to 30 % weight
SECONDS = {"energetic": 2.5, "standard": 3.5, "contemplative": 5.0}
EASING = {"hold": "linear", "orbit": "inertia", "dolly_zoom": "ease_in_out"}


def _seed(text):
    return int(hashlib.sha1(str(text).encode()).hexdigest()[:8], 16)


def _weight(move, tempo, memory):
    w = WEIGHTS.get(move, (1.0, 1.0, 1.0))[TEMPOS.index(tempo)]
    return w * (MEMORY_FACTOR if move in (memory or ()) else 1.0)


def deal(shots, tempo="standard", seed="", memory=(), easings=None):
    """-> [{shot, move, seconds, easing, big}] one entry per shot (an int count or a list of shot ids).

    `memory`: moves the recent films opened or signed with (e.g. from `factory.memory`), pushed back in weight.
    `easings`: optional per-move easing override {move: name from camera.EASINGS}."""
    tempo = tempo if tempo in TEMPOS else "standard"
    ids = list(shots) if not isinstance(shots, int) else list(range(1, shots + 1))
    n = len(ids)
    if not n:
        return []
    rng, seen = _seed(f"{seed}|{tempo}|{n}"), []
    deck = []
    big_slot = None
    if n >= 4 and _weight("orbit", tempo, memory) + _weight("dolly_zoom", tempo, memory) > 0:
        big_slot = max(1, min(n - 2, round(n * (BIG_AT[0] + (BIG_AT[1] - BIG_AT[0]) * ((rng % 100) / 100.0)))))
    for i in range(n):
        pool = {m: _weight(m, tempo, memory) for m in WEIGHTS}
        pool = {m: w for m, w in pool.items() if w > 0}
        for once in ONCE:                          # a once-a-film move only ever comes from the big slot
            pool.pop(once, None)
        if seen:                                   # never the move before
            pool.pop(seen[-1], None)
        if i == big_slot and big_slot is not None:
            free = [m for m in ONCE if m not in seen and _weight(m, tempo, memory) > 0]
            if free:                               # a once-a-film move is only dealt when it is still in the deck
                big = max(free, key=lambda m: _weight(m, tempo, memory))
                pool = {big: 1.0}
        if not pool:
            pool = {m: 1.0 for m in ("push_in", "pan_left", "tilt_up")}
        rng = (rng * 1103515245 + 12345) & 0x7FFFFFFF
        total, pick, acc = sum(pool.values()), None, (rng % 1000) / 1000.0 * sum(pool.values())
        for m, w in sorted(pool.items()):
            acc -= w
            if acc <= 0:
                pick = m
                break
        pick = pick or sorted(pool)[0]
        seen.append(pick)
        deck.append({"shot": ids[i], "move": pick, "seconds": SECONDS[tempo],
                     "easing": (easings or {}).get(pick) or EASING.get(pick) or "ease_out",
                     "big": pick in ONCE})
    return deck


def summary(deck, lang="tr"):
    """One line for the creator: the rhythm of moves and where the big one sits."""
    moves = [d["move"] for d in deck]
    big = next((i + 1 for i, d in enumerate(deck) if d["big"]), None)
    if lang == "tr":
        return (f"{len(deck)} sahne: {' · '.join(moves)}"
                + (f" · büyük hareket {big}. sahnede" if big else ""))
    return f"{len(deck)} shots: {' · '.join(moves)}" + (f" · big move at shot {big}" if big else "")


def problems(deck):
    """What a drawn deck must never do (a deck we hand a designer is checked like a plan)."""
    out = []
    moves = [d["move"] for d in deck or []]
    for i in range(1, len(moves)):
        if moves[i] == moves[i - 1]:
            out.append(f"shot {i + 1}: the same move as the shot before it ({moves[i]})")
    for once in ONCE:
        if moves.count(once) > 1:
            out.append(f"'{once}' is dealt {moves.count(once)} times; it is a once-a-film move")
    return out
