"""The camera deck: varied moves, no neighbour repeats, the once-a-film move mid-film, deterministic."""
from factory import camera_deck as D


def test_a_deck_never_repeats_a_move_and_keeps_the_big_one_for_midfilm():
    for tempo in D.TEMPOS:
        for seed in ("a", "b", "001-aselsan", "x"):
            deck = D.deal(9, tempo, seed=seed)
            assert len(deck) == 9 and D.problems(deck) == []
            moves = [d["move"] for d in deck]
            assert all(moves[i] != moves[i - 1] for i in range(1, len(moves)))
            for once in D.ONCE:
                assert moves.count(once) <= 1
            big = [i for i, d in enumerate(deck) if d["big"]]
            assert len(big) <= 1
            if big:
                assert 0.45 <= (big[0] + 1) / len(deck) <= 0.85     # the turn, not the opening


def test_the_same_idea_deals_the_same_deck_and_another_idea_does_not():
    assert D.deal(7, "standard", seed="p1") == D.deal(7, "standard", seed="p1")
    assert [d["move"] for d in D.deal(7, "standard", seed="p1")] != \
           [d["move"] for d in D.deal(7, "standard", seed="p2")]


def test_tempo_changes_the_rhythm():
    fast = [d["move"] for d in D.deal(8, "energetic", seed="s")]
    slow = [d["move"] for d in D.deal(8, "contemplative", seed="s")]
    assert fast != slow
    assert slow.count("hold") + slow.count("pull_out") >= fast.count("hold") + fast.count("pull_out")
    assert D.deal(8, "contemplative")[0]["seconds"] > D.deal(8, "energetic")[0]["seconds"]


def test_a_move_the_last_films_used_is_pushed_back():
    plain = [d["move"] for d in D.deal(6, "standard", seed="s")]
    aware = [d["move"] for d in D.deal(6, "standard", seed="s", memory=("push_in", "hold"))]
    assert aware.count("push_in") <= plain.count("push_in")


def test_three_shots_still_get_a_deck_and_no_big_move():
    deck = D.deal(3, "standard", seed="s")
    assert len(deck) == 3 and not any(d["big"] for d in deck)
    assert D.deal(0) == [] and D.deal(2, "standard")[0]["shot"] == 1


def test_the_deck_is_summarised_for_the_creator():
    assert "sahne" in D.summary(D.deal(4, "standard", seed="s"), "tr")
    assert "shots" in D.summary(D.deal(4, "standard", seed="s"), "en")
