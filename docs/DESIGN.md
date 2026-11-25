# Beat-Draw Showdown - design notes

How the game works in detail: rules for each level, the hardware, the Bluetooth protocol, the timing model and the gesture detectors.

## 1. What we are building
A 2-player duel game in **3 levels** (one match ≈ 3 minutes). Each player holds a 3D-printed **wand**
with a TinyScreen+ stack inside. The laptop is the referee and the big screen.

### Level 1 — Cowboy (best of 3 draws, ties replayed, max 5 rounds)
| Stage | Where | What happens |
|---|---|---|
| 1 Lobby | laptop + wands | Laptop connects to `BDS-1` and `BDS-2`, measures Bluetooth latency (10 pings). |
| 2 Air-drum | both | 4-beat count-in, then **16 beats @90 BPM** (v5.7, was 8 @120). Pattern of **arrows**: flick the wand TIP `U` up / `D` down / `L` left / `R` right, `-` = rest; **8 notes**, beat 1 never a rest, never 4 notes or 4 rests in a row. Round 1 = up + down only, round 2 = + one or two left/right, round 3+ = all 4 (`random_pattern(rng, round_no)`). Each on-beat correct arrow loads 1 bullet (max 6, so 2 misses are free). **Arena (v5.7): a 4-lane note highway per player (L D U R, like DDR): arrows fall onto a hit line exactly on their beat, beat lines scroll with the music (bright on each bar), receptors light up on a hit, PERFECT (≤ `PERFECT_MS` 60 ms) / GOOD (≤ 150 ms) / MISS popups + a COMBO counter; a note that passes unhit = MISS.** Plus the BIG arrow for the current beat (and "next") in the middle. **Sound (v5.7): a generated Wild-West play-along groove (`sounds.groove(bpm, beats)`: sticks + hats in the count-in, then kick/snare/hats, boom-chick bass and off-beat strums over Am-G-F-E), built for the exact tempo and played as ONE sound so it can't drift; `western` is silent during it.** Wand: 8 boxes of its strip at a time (beats 1-8, then 9-16) + a big arrow, PERFECT / GOOD / MISS text. |
| 3 Holster | both | 1.5 s to lower the wand to your side. |
| 4 Standoff | wands judge | Random 1.5–4.5 s. Moving more than 0.35 g from your holster pose = **FOUL (JAMMED)**. |
| 5 DRAW! | wands time it | Laptop sends `G` and plays the DRAW sound. Wand times the flick with `micros()`. |
| 6 Result | laptop decides | `effective = reaction_ms − bullets × 25 ms`. Lower wins. Sent back to both wands. |
**Cowboy tutorial (v5.4, before Level 1, no timer — `CTUT` state):** (1) ARROWS: each player at their own pace
flicks U, D, L, R twice each (wand mode `O1` reports every flick as `d<dir>`; card = big arrow + animated flick
demo + tip + progress, "That was LEFT - flick UP"); (2) PRACTICE BEAT: both play one slow 70 BPM `U-D-L-R-` round
(normal `R` packet, doesn't count, shows x/4; v5.7: 70 BPM on the note highway); (3) HOLSTER: each player freezes for 3 s at their own pace (wand
mode `O3` = standoff that never fouls and streams `s<0-20>` every 100 ms, 10 = the foul line; live 20-block
stillness meter, moving past the line resets the timer); (4) DRAW: `O3` again, then a shared practice `G`,
shows each reaction time and "you moved before DRAW" if they did. Then the match intro (or round 1 in Level 1
practice). SKIP button / SPACE skips, SETTINGS > COWBOY TUTORIAL or `--no-cowboy-tutorial` turns it off; a
drop-out during it goes straight on to the match.
A second spike within the hit window of a beat that is already loaded = wrist rebound: the wand ignores it
(no packet). The arena never turns a green (loaded) beat red. Level 1 winner starts Level 2 with **+1 HP** (6 instead of 5).

### Level 2 — Spellcaster (60 s, real-time)
* **Spell tutorial first (v5.1, no timer):** laptop sends `w`; spells are free (no mana, no cooldown) and each
  one is reported with `C<s>0`. Each player goes at their OWN pace through Lightning → Water → Fire
  (`Tutorial` in game_logic.py), landing each one 2× (`TUTORIAL_REPEATS`). Each player's card shows the big
  element symbol, an animated pixel wand doing the move with a trail + dotted guide path (`Art.move_demo()`),
  a one-line tip (`SPELL_TIPS`), progress squares and feedback ("GOOD! 1 more", "That was FIRE - try a ZIG-ZAG",
  FIZZLE hints). The duel starts 1.5 s after BOTH have finished. SPACE = operator skip. Turn it off in
  SETTINGS or with `--no-warmup`. A drop-out during the tutorial resumes it with progress kept.
* **FIZZLE hints (v5):** a failed gesture is scored against each spell rule (`closestSpell()`); the wand shows
  "thrust harder!" / "rounder circle!" / "zig-zag faster!" / "bigger move!" (too short) and sends `f<c>`; the
  arena shows "FIZZLE - almost FIRE: thrust harder!". Works in the duel, the warm-up, Level 3 and offline practice.
* **Charge pose (mana, no buttons):** point the wand straight at the sky. Every 0.8 s in the pose = +1 mana
  (max 3, start 1). The pose is checked on the lightly smoothed RAW accelerometer (total ≈ 1 g and mostly along
  the wand), so it starts ~60 ms after the wand is up and a trembling hand still counts; a wobble shorter than
  0.4 s only pauses the bar. It's a pose, not a movement, so it can't be mistaken for a spell; a gesture
  that ENDS with the wand pointing up is ignored (that was the raise), and a FIZZLE right after charging is hidden.
  Settings: `CHARGE_UP_SIGN`, `CHARGE_TILT_G`, `CHARGE_STILL_G`, `CHARGE_MS`, `CHARGE_SETTLE_MS`, `CHARGE_GRACE_MS`.
* **Cast:** move: **zig-zag = Lightning (L)**, **circle = Water (W)**, **forward thrust = Fire (F)**.
  Costs 1 mana, then 1.5 s cooldown. The wand recognises the gesture itself.
* Counter cycle: **Lightning > Water > Fire > Lightning**.
* A spell takes 2.0 s to cross the arena. Spells **collide in mid-air**: where a P1 spell meets a P2 spell,
  the one that beats the other destroys it and keeps flying; same element = both vanish (clash). Who cast
  first doesn't matter. A spell that lands = −1 HP. The target's wand warns "! FIRE !" for 2 s.
* Ends at 0 HP or after 60 s (more HP wins; equal = draw).

### Level 3 — Combo Clash (no shaking — rounds until the beam reaches an end)
* The clash point runs 0–100 (P1's view). Start = 50 + 5 × (P1 HP − P2 HP after Level 2), capped ±15.
* Each round: **ROUND n** (1.5 s) → **SHOW**: the combo flashes one spell at a time on the arena and the wands
  (0.9 s each in round 1, faster each round down to 0.5 s; never the same combo twice in a row)
  → **WAIT** 2 s (combo hidden) → **GO**: both players cast it back from memory → **SCORE**.
* **Combos (v5.1):** round 1 = 3 DIFFERENT spells (e.g. FWL); rounds 2–5 = 3 spells where one REPEATS (e.g.
  WFW, FLL); the **FINAL round (6) and sudden death = 5 spells** (e.g. WFWLF), 0.6 s each, "FINAL ROUND - 5 SPELLS!".
  Never the same spell 3× in a row (`combo_ok()`). Input time = 7 s + 1.8 s per extra spell (5 spells = 10.6 s).
* Score = spells right AND in the right place (0–n). More right wins the round; equal → whoever finished first;
  0 vs 0 = no push. Winner pushes the beam `10 + 10 × (their right − rival's right)` (3 vs 0 = 40, 5 vs 0 = 60).
* Beam reaches an end = **CHAMPION**. After 6 rounds whoever is ahead wins; exactly level → up to 3
  sudden-death rounds.
* **Hype (laptop only):** arcade `battle` music (→ `battle_fast` near an end or in the last rounds), ducked
  while the combo flashes; each flashed spell plays its sound; announcer "Two, one… GO!" (+ soft clicks) in the wait; surge on GO;
  recorded crowd loop + `cheer.ogg` on round wins / overpowering; drumroll for sudden death.
* Shaking was removed in v4 (it was the likely cause of loose batteries / disconnects).

### Reliability (v5)
* **Watchdog:** the SAMD21 hardware watchdog (2 s, `USE_WATCHDOG` in config.h) restarts a frozen wand.
  `loop()` and `waitMs()` feed it. The reset cause (`P` power, `W` watchdog, `B` brown-out, `R` reset button,
  `S` software) is the 4th field of `V` and shows on the wand lobby ("restarted: froze / low batt").
* **Pause + resume:** a wand dropping out during a match → `PAUSED` (both wands get `L`, music stops). When both
  are back and re-measured (+1.5 s) the arena carries on: Level 1 replays the interrupted round; Level 2 resends
  `M2` with the same HP and the time that was left (min 15 s, spells in the air are cleared); Level 3 resends `M3`
  with the same beam and replays the interrupted round (a finished round still counts). BACKSPACE = give up → lobby.
* **Drop log:** `pc/disconnects.csv` (time, player, disconnect / reconnect / restart cause, level, state, battery %,
  seconds offline). The lobby shows "dropped Nx this session".
* **Faster reconnect:** BleLink remembers each wand's address and reconnects to it directly (no 4 s scan).
  A failed write is only a warning now (it used to look like a disconnect).

### Main menu (v5.1, `menu.py`, shown in the LOBBY state)
PLAY FULL MATCH · PRACTICE A LEVEL (1/2/3) · HOW TO PLAY (4 illustrated pages, LEFT/RIGHT) · PLAYERS & WANDS
(names, connection, battery, Bluetooth delay, firmware, last restart, drop-outs, re-measure) · HALL OF FAME
(10 fastest draws + most titles + latest champions, `pc/hall_of_fame.json`) · SETTINGS (music / effects /
announcer volume 0–10, cowboy tutorial on/off, spell tutorial on/off, difficulty EASY 75 / NORMAL 90 / HARD 110 BPM (v5.7), `pc/settings.json`;
`--bpm` on the command line wins) · QUIT. Keys: UP/DOWN, ENTER/SPACE, LEFT/RIGHT, ESC/BACKSPACE = back
(ESC on the main page = quit). **Mouse (v5.2):** hover = highlight, left-click = select, right-click = back
(never quits), wheel = move / flip pages, clickable `<` `>` on settings and how-to pages, BACK buttons; clickable
PLAY AGAIN / MAIN MENU after a match or practice level, SKIP in the spell tutorial. Hit areas live in
`menu.py` (`item_rect`, `setting_arrow`, `HOWTO_ARROWS`, `BACK_BUTTONS`) and `END_BUTTONS` / `SKIP_BUTTON` in
arena_referee.py, shared by drawing and clicking. PLAY needs both wands ready, otherwise a red hint points to PLAYERS & WANDS.
After a match: SPACE = again, BACKSPACE/ESC = menu. **Keyboard + mouse only (v5.6):** wand menu control
(tilt / flick, `m` packets, `MENU_NAV`) was removed because it was too unreliable.

### Fun + report extras (v5)
* **Names:** press `1` / `2` in the lobby (or `--players Fadil Aisyah`), type, ENTER. Names show on every
  screen, the leaderboard, the banners and the CSVs. Announcer still says "Player one".
* **Draw replay:** after each draw two bars race (light = reaction time, solid = minus bullets); RESULT is 4 s.
* **Match stats** at MATCH_END: draws won, best draw, beat accuracy, fouls, spells cast/landed/blocked, combo
  accuracy, perfect combos, fizzles.
* **Demo / filming:** `--demo` = sim + bots + auto, no key hints; add `--fullscreen`. **`--winner 1|2` (v5.7):** that
  player's bot plays sharp (no misses, fast draw, always counters, perfect memory) and the other sloppy, so the
  chosen player wins the match (for filming the story). In Level 3 both bots then remember every combo, so the
  match always reaches the 5-spell FINAL round (the loser takes rounds 2 and 4). `--demo` with `--matches` holds
  the champion + match stats for 9 s before quitting.
* **`bench.py`:** latency (200 pings), gesture accuracy (prompted casts in warm-up mode, confusion matrix),
  battery drain (%/hour). Prints a Markdown row for `docs/TEST_LOG.md` + CSV in `pc/bench_results/`.

### Look and sound (laptop)
* **Pixel art** (`pixel_art.py`): the scene is painted on a 160×90 canvas and scaled 8× (hard edges). Level 1 =
  desert sunset with two cowboys (idle / aim + muzzle flash / shot down, bullet row above each head, tumbleweed).
  Levels 2–3 = night castle with two wizards (idle / cast / charge with sparkles / hurt / down), pixel spells,
  collision bursts, crackling beams, Level 3 combo slots, confetti for the champion. Text = small font scaled up without smoothing.
* **Window (v5.5):** the game always draws on a 1280×720 surface that `present()` scales (hard edges) into a
  RESIZABLE window, with black bars if it isn't 16:9 — so the maximise button works. F11 / `--fullscreen` =
  desktop-resolution fullscreen on the monitor the window is on. Mouse positions are mapped back with `to_game()`.
* **Music:** Level 1 + lobby = `western.ogg` (quiet during the air-drum beat and the standoff), Level 2 =
  generated `arcane` loop, Level 3 = generated arcade `battle` loops + crowd.
* **Announcer** (v4.2, `announcer.py`): Street-Fighter-style voice on its own reserved mixer channel (a new line
  cuts the old one). Lines are recorded once with the built-in Windows voice (SAPI via PowerShell) on the first
  arena start and processed (deeper, saturated, stadium echo) into `pc/sounds/announcer/ann_*.wav`; a
  teammate's recording with the same name wins. Calls: match intro "Level one. Cowboy showdown! ... Round one!"
  → count-in "4, 3, 2, 1" (on the clicks) → "Holster!" → "Draw!" (with the DRAW sound) → "Foul!" / "Player N
  wins!" / "Tie!" → "Round n!" / "Final round!" before the next round. Level 2/3 intro: "Level two/three…" then
  "3, 2, 1" (+ "Fight!" for L2); L2 end "K.O.!" or "Time!" + winner. L3: "Round n!" / "Final round!" /
  "Sudden death!", wait "Two, one", "GO!", "Perfect!" for a 3/3 round win, end "K.O.!" (beam reached an end) or
  "Time!" + "Player N… is the champion!". `V` toggles it, `--no-voice` starts without it. v5 adds "Warm up! Try every spell!", "Pause!" and "Resume!".

## 2. Hardware (per wand)
TinyScreen+ ASM2022 (SAMD21, 96×64 OLED, 4 buttons) + ST BLE TinyShield ASD2116-R (BlueNRG-MS, SPI pins
CS 10 / IRQ 2 / RST 9) + Accelerometer TinyShield ASD2511-R-A (Bosch BMA250, I²C 0x18/0x19) + 150 mAh LiPo.
Optional: Wireling Adapter TinyShield ASD2022 + Buzzer Wireling AST1035 on port 0 (pin `A0`), enabled with
`USE_BUZZER 1`. Wireling power pin is 4 (handled by `Wireling.begin()`).

Accelerometer runs at ±8 g, 64 LSB/g, sampled every 2 ms.

**Battery %:** `getVCC()` / `getBattVoltage()` from TinyCircuits' TinyScreen+ battery tutorial (VBATT on `A4`
through a ½ divider, ADC reference from the 1.1 V bandgap), smoothed, then mapped to % with a LiPo curve
(4.2 V = 100 %, 3.7 V ≈ 25 %, 3.3 V = 0 %). Reads ~100 % while charging on USB. Shown on the wand lobby
(`BDS-1  87%`) and next to each player's name on the arena; ≤ `BATT_LOW_PCT` (20 %) = red + blinking +
"Charge P1 - battery low!" in the lobby.

## 3. BLE protocol (ASCII, ≤ 20 bytes per packet, no newline)
Service `6E400001-B5A3-F393-E0A9-E50E24DCCA9E`.
Laptop **writes** to `6E400002…` (write-without-response). Wand **notifies** on `6E400003…`.

| Laptop → Wand | Meaning |
|---|---|
| `P` | ping (reply `Q`) |
| `V` | version (reply `V5.7,BDS-1,<buzzer 0/1>,<reset cause P/W/B/R/S>`, then a `%` battery packet) |
| `L` | go to lobby |
| `R<3-digit bpm><pattern>` | start air-drum, e.g. `R090U-DU--D-UD--U-D-` (v5.7: 16 arrows/rests = exactly 20 bytes; the tutorial sends 8); the old `R120,UDL-RDU-` still works; wand's beat 0 = arrival + 4 beats |
| `W` | start standoff (learn holster pose for 300 ms, then watch for fouls) |
| `G` | DRAW cue |
| `E<o><ms>` | result: `o` = `W` win, `L` lose, `F` foul, `X` tie; `ms` = your effective time |
| `O1` / `O3` | L1 tutorial: `O1` = free arrow flicks (each reported with `d<dir>`); `O3` = holster practice (standoff that never fouls, streams `s<n>`; `G` still starts the draw) (v5.4) |
| `w` | L2 warm-up: free spells, each reported with `C<s>0` (v5) |
| `M2,<bpm>,<hp>,<opp>` | start Level 2 after a 5 s intro, e.g. `M2,120,6,5` (bpm is unused since v3) |
| `U<hp>,<opp>,<e>` | L2 HP update; `e` = `H` I got hit, `D` I hit them, `B` I blocked, `-` none |
| `I<s>` | L2 warning: spell `s` (`L`/`W`/`F`) is flying at you |
| `M3,<pos>` | start Level 3 after a 5 s intro; `pos` = my beam position (100 = I win) |
| `Z<combo><f>` | L3 show a 3–5 spell combo (e.g. `ZFLW8`, `ZWFWLF6`), each spell flashes `f` × 100 ms |
| `K` | L3 GO: cast the combo now (wand starts a `micros()` stopwatch, records up to 3 spells) |
| `J` | L3 round over (wand back to the beam bar) |
| `b<pos>` | L3 beam position after each round (wand: bar + buzzer pitch) |
| `Y<o><lvl>` | level result, `o` = `W`/`L`/`X`, e.g. `YW3` = you are champion |

| Wand → Laptop | Meaning |
|---|---|
| `Q` | pong |
| `H<k><g><ok><err>` | hit on beat k (0-15), arrow g (`U`/`D`/`L`/`R`), ok `1`/`0`, timing error ms, e.g. `H3U1+12`, `H14L0-140` |
| `B<n>` | bullets loaded after the drum phase |
| `F` | foul during standoff |
| `T<us>` | draw time in microseconds since `G` arrived |
| `N` | no draw within 3 s |
| `A<n>` | L2 mana is now n (after a finished charge pose) |
| `C<s><n>` | L2 cast spell `s`, `n` mana left, e.g. `CL2` |
| `X<s><us>` | L3 one combo spell `s`, µs from `K` (GO) arrival to the end of the gesture (max = combo length) |
| `d<g>` | L1 tutorial: a free arrow flick `U`/`D`/`L`/`R` (v5.4) |
| `s<n>` | L1 tutorial holster: movement in the last 100 ms, 0–20, 10 = `FOUL_THRESHOLD_G` (v5.4) |
| `f<c>` | FIZZLE; `c` = closest spell `L`/`W`/`F`, or `s` = move too short (v5) |
| `%<n>` | battery level 0–100 % (after `V`, then every 10 s; measured every 5 s, never during a timed moment) |

## 4. Timing model (why it is fair)
* Wands judge hits and draws **locally** — Bluetooth delay never touches the stopwatch.
* Laptop measures one-way latency per wand (median ping / 2).
* Laptop delays its own count-in and DRAW sound by the **mean** latency so audio lines up with the wands.
* Reaction time = `T/1000 + (my_latency − mean_latency)`. Under 100 ms = guessed = foul.
* Level 3 combo times use the same correction (`X` time + my latency − mean); a first spell under 150 ms after GO is ignored.
* Level 2 is real-time with 2.0 s spell travel, so ~20 ms Bluetooth delay doesn't matter there.

## 5. Arrow detector (firmware `hitDetector()`, v5.3)
A hit = dynamic accel above `HIT_THRESHOLD_G`; the peak is searched for 25 ms. **Axis** = the bigger of the
up/down (`SNARE_AXIS`) and left/right (`HIHAT_AXIS`) values at the peak. **Direction** = the sign on that axis at
the FIRST sample (the start of the flick), because the peak is often the wrist stopping the wand (pointing back).
Signs: `DRUM_UP_SIGN`, `DRUM_RIGHT_SIGN`. A rebound right after a loaded beat is ignored as before.

## 6. Gesture recogniser (firmware `spellDetector()` / `classifySpell()`)
Accelerometer only (no gyro), so spells are **motion patterns**, not drawn shapes.
A gesture = motion above 1.0 g until 150 ms of quiet. While recording, per axis (side / up-down / forward):
*lobes* (pushes above 0.8 g that change direction), energy share, peak.
1. **Fire**: forward peak ≥ 2.0 g and forward energy > 45 %.
2. **Water**: side lobes ≥ 2 AND up-down lobes ≥ 2, both energies > 25 %.
3. **Lightning**: side lobes ≥ 3 and side energy > 55 %.
4. otherwise **FIZZLE**: `closestSpell()` scores each rule 0–1 and the wand sends `f<closest>` (v5).
Axes: `SIDE_AXIS`/`UPDOWN_AXIS`/`FORWARD_AXIS` in config.h. With the Serial Monitor open, every gesture
prints its numbers (`SPELL_DEBUG 1`) — use these to tune.

## 7. Tuning checklist (do with real players)
| Symptom | Change |
|---|---|
| Drum hits not detected | lower `HIT_THRESHOLD_G` (1.2 → 1.0) |
| Double hits | raise `HIT_REFRACTORY_MS` (140 → 180) |
| Up/down arrows read as left/right | swap / fix `SNARE_AXIS` (up/down) and `HIHAT_AXIS` (left/right) |
| UP shows as DOWN (or LEFT as RIGHT) | flip `DRUM_UP_SIGN` (or `DRUM_RIGHT_SIGN`) to -1 — cowboy practice shows what the wand saw |
| Fouls when standing still | raise `FOUL_THRESHOLD_G` (0.35 → 0.5) |
| Draw triggers too late | lower `DRAW_THRESHOLD_G` (2.0 → 1.6) |
| Too hard to hit on beat | raise `HIT_WINDOW_MS` in **both** config.h and game_logic.py |
| Zig-zag shows FIZZLE | lower `ZIGZAG_LOBES` (3 → 2 is too low: a plain sweep would count) or `LOBE_G` (0.8 → 0.6) |
| Circle detected as Lightning | draw a rounder, bigger circle; or lower the 25 % energy limits in `classifySpell()` |
| Thrust not detected | lower `THRUST_G` (2.0 → 1.6); check `FORWARD_AXIS` |
| Random spells while standing | raise `GESTURE_START_G` (1.0 → 1.3) |
| Charge pose never charges | check `CHARGE_UP_SIGN` with accel debug (wand pointing up: FORWARD column ≈ +1 → 1, ≈ −1 → −1); lower `CHARGE_TILT_G` (0.75 → 0.65) |
| Charges while just holding the wand | raise `CHARGE_TILT_G` (0.75 → 0.9) |
| Counters impossible in time | raise `SPELL_TRAVEL_S` in game_logic.py (2.0 → 2.5) and the 2000 ms warning in the firmware `I` handler |
| Combos too hard / easy | change `COMBO_FLASH_S` (flash time per round) or `COMBO_WAIT_S` in game_logic.py |
| Level 3 too long / short | change `COMBO_WIN_PUSH` / `COMBO_POINT_PUSH` or `L3_MAX_ROUNDS` in game_logic.py |
