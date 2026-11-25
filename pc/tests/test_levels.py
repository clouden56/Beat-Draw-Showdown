"""Tests for Level 2 (Spellcaster), Level 3 (Beam Clash) and the full 3-level match.

Run:  python tests/test_levels.py      (or)   python -m pytest tests
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import random  # noqa: E402

from game_logic import (BEATS, COMBO_POINT_PUSH, COMBO_WIN_PUSH, L2_START_HP, SPELL_TRAVEL_S,  # noqa: E402
                        BeamClash, ComboEntry, SpellDuel, beam_start_pos, combo_correct, combo_input_s, combo_len,
                        combo_ok, counter_of, flash_s,
                        hp_packet, level1_bonus, level1_done, level_packet, my_beam_pos, parse_message,
                        random_combo)


# ---------------- match glue ----------------
def test_level1_bonus_and_done():
    assert level1_bonus([2, 1]) == 0 and level1_bonus([0, 2]) == 1 and level1_bonus([1, 1]) is None
    assert level1_done([2, 0], 2) and not level1_done([1, 1], 2) and level1_done([1, 1], 5)


# ---------------- Level 2 ----------------
def test_counter_cycle():
    assert BEATS == {"L": "W", "W": "F", "F": "L"}
    assert counter_of("W") == "L" and counter_of("F") == "W" and counter_of("L") == "F"


def test_spell_hits_after_travel_time():
    d = SpellDuel(t_start=0)
    assert d.cast(0, "F", 1.0) == [("launch", 0, "F")]
    assert d.update(1.0 + SPELL_TRAVEL_S - 0.01) == []
    assert d.update(1.0 + SPELL_TRAVEL_S) == [("hit", 1, "F")]
    assert d.hp == [L2_START_HP, L2_START_HP - 1]


def test_counter_blocks_and_keeps_flying():
    d = SpellDuel(t_start=0)
    d.cast(0, "F", 1.0)                       # fire at P2
    assert d.cast(1, "W", 1.5) == [("launch", 1, "W")]
    meet = (1.0 + 1.5 + SPELL_TRAVEL_S) / 2
    assert d.update(meet - 0.01) == []
    ev = d.update(meet)
    assert ev[0][:3] == ("block", 1, "F")     # water put the fire out mid-air
    assert 0 < ev[0][3] < 1
    d.update(10)
    assert d.hp == [L2_START_HP - 1, L2_START_HP]   # only P2's water landed


def test_simultaneous_fire_and_water_no_longer_pass_through():
    d = SpellDuel(t_start=0)
    d.cast(1, "W", 2.00)                      # water arrives at the laptop a moment first
    d.cast(0, "F", 2.01)
    evs = d.update(10)
    assert [e[0] for e in evs] == ["block", "hit"]
    assert d.hp == [L2_START_HP - 1, L2_START_HP]   # only the fire caster is hurt


def test_same_element_clash_and_losing_counter():
    d = SpellDuel(t_start=0)
    d.cast(0, "L", 1.0)
    d.cast(1, "L", 1.2)
    assert [e[:3] for e in d.update(5)] == [("clash", None, "L")]
    assert d.flying == [] and d.hp == [L2_START_HP, L2_START_HP]
    d.cast(0, "F", 6.0)
    d.cast(1, "L", 6.2)                       # lightning loses to fire: lightning destroyed
    evs = d.update(20)
    assert evs[0][:3] == ("block", 0, "L") and evs[1] == ("hit", 1, "F")
    assert d.hp == [L2_START_HP, L2_START_HP - 1]


def test_spell_that_already_landed_cannot_be_blocked():
    d = SpellDuel(t_start=0)
    d.cast(0, "F", 0.0)
    d.cast(1, "W", SPELL_TRAVEL_S + 0.1)      # too late: fire already hit
    evs = d.update(20)
    assert evs[0] == ("hit", 1, "F") and evs[1] == ("hit", 0, "W")


def test_duel_ends_at_zero_hp_or_time():
    d = SpellDuel(hp=(1, 2), t_start=0, duration_s=60)
    d.cast(1, "W", 0)
    d.update(2)
    assert d.done(2) and d.winner() == 1
    d2 = SpellDuel(t_start=0, duration_s=60)
    assert not d2.done(59.9) and d2.done(60) and d2.winner() is None
    assert d2.cast(0, "F", 61) == []          # no casting after time is up


def test_hp_packet():
    d = SpellDuel(hp=(6, 5))
    assert hp_packet(d, 0, "H") == "U6,5,H" and hp_packet(d, 1) == "U5,6,-"


# ---------------- Level 3 (combo clash) ----------------
def test_beam_start_from_hp():
    assert beam_start_pos([5, 5]) == 50
    assert beam_start_pos([4, 2]) == 60          # P1 ahead by 2 HP -> clash point nearer P2
    assert beam_start_pos([0, 6]) == 35          # capped at 15
    assert my_beam_pos(60, 0) == 60 and my_beam_pos(60, 1) == 40


def test_random_combo_round1_different_then_mixed():
    rng = random.Random(1)
    for _ in range(50):
        c = random_combo(rng)                                      # round 1: all different
        assert len(c) == 3 and sorted(c) == sorted("LWF")
        m = random_combo(rng, 3, mixed=True)                       # later rounds: a spell repeats (e.g. WFW)
        assert len(m) == 3 and len(set(m)) == 2 and combo_ok(m, True)
        f = random_combo(rng, 5, mixed=True)                       # final round: 5 spells
        assert len(f) == 5 and set(f) <= set("LWF") and combo_ok(f, True)
        assert not any(f[k] == f[k - 1] == f[k - 2] for k in range(2, 5))   # never 3 the same in a row
    assert not combo_ok("FFF", True) and not combo_ok("FLW", True) and combo_ok("WFW", True)
    assert combo_len(1) == 3 and combo_len(5) == 3 and combo_len(6) == 5 and combo_len(8) == 5
    assert flash_s(1) > flash_s(3) > flash_s(5) - 1e-9 and flash_s(6) == 0.6
    assert combo_input_s(3) == 7.0 and abs(combo_input_s(5) - 10.6) < 1e-9


def test_five_spell_round_scoring():
    b = BeamClash(50)
    e1 = ComboEntry(5)
    for k, sp in enumerate("WFWLF"):
        assert e1.add(sp, 500 + 900 * k)
    assert e1.done and not e1.add("L", 9000)
    e2 = ComboEntry(5)
    for k, sp in enumerate("WFL"):
        e2.add(sp, 400 + 800 * k)
    w, push, correct = b.resolve_combo("WFWLF", [e1, e2])
    assert (w, correct) == (0, [5, 2]) and push == COMBO_WIN_PUSH + 3 * COMBO_POINT_PUSH and b.perfect == [1, 0]


def _entry(spells, times):
    e = ComboEntry()
    for sp, t in zip(spells, times):
        e.add(sp, t)
    return e


def test_combo_accuracy_wins_and_push():
    assert combo_correct("FLW", "FLW") == 3 and combo_correct("FLW", "LFW") == 1 and combo_correct("FLW", "F") == 1
    b = BeamClash(50)
    w, push, correct = b.resolve_combo("FLW", [_entry("FLW", [900, 1800, 2700]), _entry("FWL", [500, 900, 1300])])
    assert (w, correct) == (0, [3, 1])                       # accuracy beats speed
    assert push == COMBO_WIN_PUSH + 2 * COMBO_POINT_PUSH and b.pos == 50 + push


def test_combo_tie_goes_to_faster_and_zero_zero_is_no_push():
    b = BeamClash(50)
    w, push, _ = b.resolve_combo("WLF", [_entry("WLF", [800, 1600, 2600]), _entry("WLF", [700, 1500, 2400])])
    assert w == 1 and push == COMBO_WIN_PUSH and b.pos == 40
    w, push, _ = b.resolve_combo("WLF", [_entry("LWL", [800, 1600, 2600]), _entry("", [])])
    assert w is None and push == 0 and b.pos == 40


def test_combo_entry_limits():
    e = ComboEntry()
    assert not e.add("F", 50)                                # cast before GO = ignored
    assert e.add("F", 400) and e.add("L", 900) and e.add("W", 1300)
    assert e.done and not e.add("F", 2000) and e.finish_ms == 1300


def test_beam_win_and_leader():
    b = BeamClash(95)
    b.resolve_combo("FLW", [_entry("FLW", [500, 900, 1300]), _entry("", [])])
    assert b.pos == 100 and b.winner() == 0
    assert BeamClash(50).leader() is None and BeamClash(52).leader() == 0


def test_new_packets_parse_and_fit():
    assert parse_message("A3") == {"type": "mana", "n": 3}
    assert parse_message("%87") == {"type": "battery", "pct": 87}
    assert parse_message("CL2") == {"type": "cast", "spell": "L", "mana": 2}
    assert parse_message("XW812345") == {"type": "answer", "spell": "W", "us": 812345}
    assert parse_message("CZ1")["type"] == "?"
    assert level_packet(True, 2) == "YW2" and level_packet(None, 3) == "YX3"
    for pk in ("M2,140,6,5", "M3,100", "U10,10,B", "XL12345678", "ZFLW9", "K", "J", "b100", "%100"):
        assert len(pk) <= 20


# ---------------- whole match, simulated, fake clock ----------------
def test_full_matches_with_bots():
    import arena_referee
    ref = arena_referee.main(["--sim", "--bots", "--auto", "--fast", "--matches", "2", "--seed", "7"])
    assert ref.matches_played == 2
    assert ref.state == "MATCH_END"
    assert ref.l1_rounds >= 2 and ref.duel is not None and ref.beam is not None


def test_single_levels_with_bots():
    import arena_referee
    for lvl in (2, 3):
        ref = arena_referee.main(["--sim", "--bots", "--auto", "--fast", "--level", str(lvl),
                                  "--matches", "2", "--seed", "11"])
        assert ref.levels_played == 2 and ref.state == "LEVEL_RESULT"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
