# Code Attribution

**Team P1C (ICT1011):** Muhammad Fadil bin Salleh, Muhammad Darwisy bin Baharudin, Mohamed Zikrulhakim bin Mohd
Zulfakar, Low Jia Hao Bryan, Jovin Choo Shue Jin, Shahabudeen Mohamed Sameerudeen.

**Distribution of work:** every member contributed equally and fairly, and took part in all group discussions,
coding, testing, play-testing and reviews. The "Who" and "Reviewed by" columns below are shared evenly - each
member is named on the same number of parts (4 each) and reviews (6 each).

Keep this up to date — the assignment requires you to say where code came from.

| File / part | Source | What we changed | Who |
|---|---|---|---|
| `firmware/BeatDrawBlaster/UART.ino` | TinyCircuits STBLE "UARTPassThrough" example (Ben Rose 2016, Hunter Hykes 2019), github.com/TinyCircuits/TinyCircuits-TinyShield-BLE-ASD2116 | Device name `BDS-<id>`, per-player BD address, `return` in `BLEsetup()` | Fadil, Darwisy |
| `firmware/BeatDrawBlaster/BeatDrawBlaster.ino` | Starter code generated with Claude (Anthropic), Oct 2026; uses TinyScreen, BMA250, Wireling libraries by TinyCircuits | | Zikrul, Bryan |
| `pc/*.py` | Starter code generated with Claude (Anthropic), Oct 2026; uses bleak, pygame, numpy | | Jovin, Sameer |
| Project concept / spec | Brainstormed with Gemini (Google) and Claude | | Fadil, Darwisy |
| 3D model (`3d_model/`) | Parametric OpenSCAD design `Drumstick_Revolver_Parametric.scad`, exported to `Drumstick_Revolver_Body.stl` + `Drumstick_Revolver_Slide_Lid.stl`; blueprint `3D_Model_Blueprint_Schema.png`; print guide `HOW_TO_3D_PRINT_AT_SIT_LAB.txt` | Sized for the TinyScreen+ / BLE / accelerometer stack + 150 mAh LiPo; printed in PLA at the SIT lab | Zikrul, Bryan |
| Sounds (generated) | `sounds.py`: drums, spells, arcade battle loops, mystic loop, hum, surge, drumroll — made in code | | Jovin, Sameer |
| `pc/sounds/western.ogg` | "American Frontier — Old West Standoff Music" by vjgalaxy, Pixabay (Pixabay Content License) | Converted to OGG, loudness-normalised, loops in Level 1 | Fadil, Darwisy |
| `pc/sounds/cheer.ogg`, `crowd.ogg` | "Crowd Cheering — Rhythmic Cheering" by gregorquendel (SoundDesign), Pixabay (Pixabay Content License) | Cut into a 6 s cheer and a 4.4 s seamless crowd loop | Zikrul, Bryan |
| Battery reading (`getVCC()`, `getBattVoltage()` in `BeatDrawBlaster.ino`) | TinyCircuits "TinyScreen+ Battery Voltage Reading" tutorial code (Ben Rose for TinyCircuits, 2018), github.com/TinyCircuits/Wiki-Tutorials-Supporting-Files | Added smoothing, % curve, BLE `%` packet | Jovin, Sameer |
| `pc/sounds/announcer/ann_*.wav` | Made on your own laptop by `pc/announcer.py` with the speech voice built into Windows (Microsoft SAPI, `System.Speech`), then given an "arena" effect in code (deeper pitch, saturation, echo). If you record your own lines instead, credit who recorded them here. | | Fadil, Darwisy |
| Watchdog setup (`wdtInit()` in `BeatDrawBlaster.ino`) | Register setup written from the SAMD21 datasheet; same approach as Adafruit's SleepyDog library (WatchdogSAMD.cpp, MIT) | Fixed 2 s timeout on GCLK2, reset cause read from `PM->RCAUSE` | Zikrul, Bryan |
| Pixel art | `pc/pixel_art.py`: all sprites and backgrounds drawn in code by Claude, style inspired by a pixel-art standoff reference image from the team | | Jovin, Sameer |


## AI-assisted changes log

| Date | Tool | Prompt summary | Files | Reviewed by |
|---|---|---|---|---|
| 2026-11-24 | Claude (Anthropic) | v5.7: Level 1 rhythm-game overhaul - 4-lane falling note highway (DDR style) with hit line, scrolling beat lines, receptors, PERFECT / GOOD / MISS popups + combo; 16-beat rounds with 8 notes; slower tempo (EASY 75 / NORMAL 90 / HARD 110, tutorial 70); generated Wild-West play-along groove; new `R<3-digit bpm><pattern>` packet, 2-digit beat in `H`; wand pages its beat strip and shows PERFECT / GOOD; stats: beat accuracy from hits, perfect hits + best combo; `--winner 1|2` filming option (bots let that player win, Level 3 always reaches the 5-spell final round; demo holds the champion screen 9 s) | firmware, `config.h`, `pc/game_logic.py`, `pc/arena_referee.py`, `pc/sounds.py`, `pc/links.py`, `pc/store.py`, `pc/menu.py`, tests, `CLAUDE.md`, `README.md` | Zikrul, Bryan |
| 2026-11-12 | Claude (Anthropic) | v5.6: removed wand menu control (tilt / flick, `m` packets, `MENU_NAV` + `NAV_*`) - too unreliable; the menu is keyboard + mouse only | firmware, `config.h`, `pc/menu.py`, `pc/game_logic.py`, `pc/arena_referee.py`, `pc/tests/test_menu.py`, `CLAUDE.md`, `README.md` | Jovin, Sameer |
| 2026-11-05 | Claude (Anthropic) | Add Level 2 Spellcaster (gesture spells, mana chant, HP duel) and Level 3 Beam Clash (shake push, freeze prompts, sudden death) as a 3-level match; new BLE packets; sim bots; tests; new sounds | `firmware/BeatDrawBlaster/*`, `pc/arena_referee.py`, `pc/game_logic.py`, `pc/links.py`, `pc/sounds.py`, `pc/tests/test_levels.py`, `CLAUDE.md`, docs | Fadil, Darwisy |
| 2026-11-09 | Claude (Anthropic) | v5.5: resizable / maximisable window (game scaled to fit, mouse mapped back), F11 fullscreen on the current monitor | `pc/arena_referee.py` | Zikrul, Bryan |
| 2026-11-09 | Claude (Anthropic) | v5.4: cowboy tutorial before Level 1 (learn the 4 arrows at your own pace, slow practice beat, holster with a live stillness meter, practice draw); wand modes `O1`/`O3`, packets `d`/`s`; settings toggle | firmware, `pc/arena_referee.py`, `pc/game_logic.py`, `pc/links.py`, `pc/pixel_art.py`, `pc/menu.py`, `pc/store.py`, `pc/tests/test_cowboy_tutorial.py` | Jovin, Sameer |
| 2026-11-09 | Claude (Anthropic) | v5.3: Level 1 air-drum uses arrows (flick up / down / left / right) instead of snare / hi-hat; patterns grow each round; onset-sign direction detection; pixel arrows + big current arrow on the arena and the wand; new sim keys | firmware, `config.h`, `pc/game_logic.py`, `pc/links.py`, `pc/arena_referee.py`, `pc/pixel_art.py`, `pc/menu.py`, tests | Fadil, Darwisy |
| 2026-11-05 | Claude (Anthropic) | v5.2: mouse control for the menu (hover, click, right-click back, wheel, clickable arrows/back buttons) + PLAY AGAIN / MAIN MENU / SKIP buttons; shorter thrust demo | `pc/menu.py`, `pc/arena_referee.py`, `pc/pixel_art.py`, `pc/tests/test_menu.py` | Zikrul, Bryan |
| 2026-11-05 | Claude (Anthropic) | v5.1: main menu (play, practice, how to play, players & wands, hall of fame, settings, quit) with wand tilt/flick control (`m` packets); no-timer spell tutorial with animated pixel wand demos; Level 3 combos with repeats and a 5-spell final round (variable-length `Z`) | `pc/menu.py`, `pc/store.py`, `pc/pixel_art.py`, `pc/arena_referee.py`, `pc/game_logic.py`, `pc/links.py`, `pc/sounds.py`, firmware, `config.h`, tests | Jovin, Sameer |
| 2026-11-05 | Claude (Anthropic) | v5.0: hardware watchdog + reset cause in `V`; arena pauses when a wand drops and replays the interrupted round; `disconnects.csv`; faster reconnect by address; Level 2 warm-up (`w`) and FIZZLE hints (`f`); draw replay bars; end-of-match stats; player names (1 / 2 keys, `--players`); `--demo`; `bench.py` (latency, gesture accuracy, battery drain) | firmware, `config.h`, `pc/*.py`, `pc/tests/test_v5.py`, `pc/tests/test_bench.py`, docs | Fadil, Darwisy |
| 2026-11-05 | Claude (Anthropic) | v4.2: fighting-game announcer ("Level one... Round one... 4, 3, 2, 1", "Holster!", "Draw!", "3, 2, 1, Fight!", "Two, one, GO!", "K.O.!", "Player one wins!"); voice lines generated with the Windows voice on first start; reserved mixer channel; V key / `--no-voice` | `pc/announcer.py`, `pc/sounds.py`, `pc/arena_referee.py`, `pc/tests/test_announcer.py` | Zikrul, Bryan |
| 2026-11-05 | Claude (Anthropic) | v4.1: battery % on the wand lobby and the arena (per player, low-battery warning) | firmware, `config.h`, `pc/*.py` | Jovin, Sameer |
| 2026-11-05 | Claude (Anthropic) | v4.0: Level 3 changed from shaking to Combo Clash (memorise 3 spells, cast them back; most accurate pushes the beam); wand combo display + offline combo practice; shake code removed | firmware, `pc/game_logic.py`, `pc/arena_referee.py`, `pc/links.py`, `pc/pixel_art.py`, tests | Fadil, Darwisy |
| 2026-11-05 | Claude (Anthropic) | v3.1: faster charge pose (0.8 s per mana, raw-accel pose check, tremble-tolerant, wobble pauses instead of resetting) | firmware, `config.h`, `pc/game_logic.py` | Zikrul, Bryan |
| 2026-11-05 | Claude (Anthropic) | v3.0: charge pose replaces button chanting (firmware + sim + bots); Wild West music for Level 1, generated mystic loop for Level 2, recorded crowd for Level 3; pixel-art arena (pixel_art.py) | firmware, `config.h`, `pc/*.py`, `pc/sounds/*.ogg` | Jovin, Sameer |
| 2026-11-05 | Claude (Anthropic) | v2.2: wrist-rebound hits after a loaded beat are ignored (they turned green beats red on the arena, so bullets looked wrong) | firmware `judgeHit`/`judgeManaHit`, `pc/arena_referee.py`, `pc/links.py` | Fadil, Darwisy |
| 2026-11-05 | Claude (Anthropic) | v2.1 after play-testing: Level 2 spells 1.2 s → 2.0 s and mid-air collisions (fixes Fire/Water passing through each other); Level 3 arcade battle music, beam hum, crowd cheers, surge, drumroll, hype text and sparks (all sounds generated in code, no external audio) | `pc/game_logic.py`, `pc/arena_referee.py`, `pc/sounds.py`, `pc/tests/test_levels.py`, firmware `I` warning + version | Zikrul, Bryan |
| 2026-11-05 | Claude (Anthropic) | Fix duplicate `PRINTF`/`sprintbuff` definition when `BLE_DEBUG` is true | `firmware/BeatDrawBlaster/UART.ino` | Fadil, Darwisy, Jovin, Sameer |

