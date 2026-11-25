"""Tests for v5.1: main menu, settings, hall of fame, keyboard / mouse only menu.

Run:  python tests/test_menu.py      (or)   python -m pytest tests
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import arena_referee  # noqa: E402
from game_logic import parse_message  # noqa: E402
from store import HallOfFame, Settings  # noqa: E402


def _ref(ready=True):
    args = arena_referee.parse_args(["--sim", "--bots", "--fast", "--seed", "1"])
    ref = arena_referee.run_fast(args, max_virtual_s=3.0)          # lobby, both wands connected + measured
    assert ref.state == "LOBBY" and ref.ready() == True            # noqa: E712
    if not ready:
        ref.latency = [None, None]
    return ref


def test_menu_moves_and_wraps():
    ref = _ref()
    m = ref.menu
    assert m.page == "main" and m.sel["main"] == 0
    ref.on_key("up", 0)
    assert m.sel["main"] == 6                                       # wraps to QUIT
    ref.on_key("down", 0)
    ref.on_key("down", 0)
    ref.on_key("return", 0)
    assert m.page == "practice"
    ref.on_key("escape", 0)
    assert m.page == "main" and not ref.want_quit                   # ESC on a sub-page = back
    ref.on_key("escape", 0)
    assert ref.want_quit                                             # ESC on the main menu = quit


def test_play_needs_ready_wands():
    ref = _ref(ready=False)
    ref.on_key("return", 0)                                          # PLAY FULL MATCH
    assert ref.state == "LOBBY" and "PLAYERS & WANDS" in ref.menu.msg[1]
    ref = _ref()
    ref.on_key("return", 0)
    assert ref.state == "CTUT" and ref.level == 1 and ref.only_level == 0       # cowboy tutorial first


def test_practice_level_from_menu():
    ref = _ref()
    for k in ("down", "return", "down", "return"):                   # PRACTICE > LEVEL 2
        ref.on_key(k, 0)
    assert ref.only_level == 2 and ref.state == "WARMUP"


def test_wand_does_not_control_the_menu():
    assert parse_message("mU")["type"] != "menu"                     # v5.6: keyboard / mouse only
    ref = _ref()
    ref.handle_msg(0, "mD", 0, 0)
    assert ref.menu.page == "main" and ref.menu.sel["main"] == 0


def _center(rect):
    x, y, w, h = rect
    return (x + w // 2, y + h // 2)


def test_mouse_hover_click_back_wheel():
    ref = _ref()
    m = ref.menu
    ref.on_mouse("move", _center(m.item_rect(2)), 0)                   # hover HOW TO PLAY
    assert m.sel["main"] == 2 and m.page == "main"
    ref.on_mouse("click", _center(m.item_rect(2)), 0)
    assert m.page == "howto" and m.howto == 0
    from menu import BACK_BUTTONS, HOWTO_ARROWS
    ref.on_mouse("click", _center(HOWTO_ARROWS[1]), 0)                  # > arrow
    assert m.howto == 1
    ref.on_mouse("wheel", (0, 0), 0, -1)                                # wheel down = next page
    assert m.howto == 2
    ref.on_mouse("click", _center(BACK_BUTTONS["howto"]), 0)            # BACK button
    assert m.page == "main"
    ref.on_mouse("wheel", (0, 0), 0, -1)                                # wheel down = next item
    assert m.sel["main"] == 3
    ref.on_mouse("click", _center(m.item_rect(5)), 0)                   # SETTINGS
    assert m.page == "settings"
    before = ref.settings["music"]
    ref.on_mouse("click", _center(m.setting_arrow(0, -1)), 0)           # music <
    assert ref.settings["music"] == before - 1 and m.sel["settings"] == 0
    ref.on_mouse("back", (0, 0), 0)                                     # right-click = back
    assert m.page == "main" and not ref.want_quit
    ref.on_mouse("back", (0, 0), 0)                                     # never quits from the main page
    assert not ref.want_quit
    ref.on_mouse("click", (5, 5), 0)                                    # empty space: nothing
    assert m.page == "main"
    ref.on_mouse("click", _center(m.item_rect(0)), 0)                   # PLAY FULL MATCH
    assert ref.state == "CTUT"


def test_mouse_end_screen_buttons():
    args = arena_referee.parse_args(["--sim", "--bots", "--auto", "--fast", "--seed", "7", "--matches", "1"])
    ref = arena_referee.run_fast(args)
    assert ref.state == "MATCH_END" and ref.end_screen()
    ref.on_mouse("click", _center(arena_referee.END_BUTTONS["menu"]), 0)
    assert ref.state == "LOBBY"
    ref.state = "MATCH_END"
    ref.on_mouse("click", _center(arena_referee.END_BUTTONS["again"]), 0)
    assert ref.state == "CTUT"


def test_settings_change_and_save():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "settings.json")
        st = Settings(path=p)
        assert st["music"] == 8 and st.bpm == 90
        st.change("music", -3)
        st.change("difficulty", 1)
        st.change("tutorial", 1)
        st.change("effects", 5)                                      # capped at 10
        again = Settings(path=p)
        assert again["music"] == 5 and again["difficulty"] == "HARD" and again.bpm == 110
        assert again["tutorial"] is False and again["effects"] == 10
    ref = _ref()
    ref.settings.change("difficulty", -1)                            # EASY
    ref.apply_settings()
    assert ref.bpm == 75


def test_tutorial_off_in_settings():
    ref = _ref()
    ref.settings.change("tutorial", 1)
    ref.start_level2(0)
    assert ref.state == "INTRO"                                      # straight to the duel


def test_hall_of_fame():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "hof.json")
        h = HallOfFame(path=p)
        for k in range(12):
            h.add_draw(f"p{k}", 300 - k)
        h.add_champion("Fadil", "Zul")
        h.add_champion("fadil", "Aisyah")
        h.add_champion("Zul", "Fadil")
        again = HallOfFame(path=p)
        assert len(again.data["draws"]) == 10 and again.fastest(1)[0]["name"] == "p11"
        assert again.most_titles()[0] == ("Fadil", 2) and again.recent(1)[0]["name"] == "Zul"


def test_full_match_records_hall_of_fame():
    args = arena_referee.parse_args(["--sim", "--bots", "--auto", "--fast", "--seed", "7", "--matches", "1",
                                     "--players", "Fadil", "Zul"])
    ref = arena_referee.run_fast(args)
    assert ref.hof.fastest(1) and ref.hof.data["champions"][0]["name"] in ("Fadil", "Zul")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
