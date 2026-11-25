// =====================================================================
//  config.h  —  Beat-Draw Showdown wand settings
//  Change these per board BEFORE uploading. Everything else can stay.
// =====================================================================
#pragma once

// ---- 1. Which wand is this? ------------------------------------------
// 1 = Player 1, 2 = Player 2. Spare boards: 3, 4, 5, 6.
// The board advertises over Bluetooth as "BDS-<PLAYER_ID>" (e.g. BDS-1).
#define PLAYER_ID 1

// ---- 2. Audio option -----------------------------------------------
// 0 = laptop speakers only (zero loan parts)
// 1 = ALSO beep on the wand using a Buzzer Wireling (SN 15)
//     plugged into the Wireling Adapter TinyShield (SN 24).
#define USE_BUZZER 0
#define BUZZER_PORT 0          // Wireling port the buzzer is plugged into (0-3)

// ---- 3. Gesture axes (depends on how the board sits in your 3D print)
// 0 = X, 1 = Y, 2 = Z. Use the Serial Monitor "accel debug" (press the
// lower-right button in the lobby) to see which axis spikes for each move.
#define SNARE_AXIS 2           // up/down axis   (Level 1 UP / DOWN arrows; the name is from the old "snare" move)
#define HIHAT_AXIS 1           // left/right axis (Level 1 LEFT / RIGHT arrows; old "hi-hat" move)
#define FORWARD_AXIS 0         // along the wand, pointing at your rival (Fire thrust)
#define SIDE_AXIS   HIHAT_AXIS // Lightning zig-zag + Water circle
#define UPDOWN_AXIS SNARE_AXIS // Water circle

// ---- 3b. Level 1 arrow directions (v5.3) -----------------------------
// Flick the wand TIP up / down / left / right on the beat. Check with cowboy practice (upper-left button):
// the big arrow on the wand shows what it saw. If UP shows as DOWN, change DRUM_UP_SIGN to -1;
// if LEFT shows as RIGHT, change DRUM_RIGHT_SIGN to -1.
#define DRUM_UP_SIGN        1
#define DRUM_RIGHT_SIGN     1

// ---- 4. Level 1 thresholds (in g). Tune during play-testing. --------
#define HIT_THRESHOLD_G     1.20f   // air-drum hit: dynamic accel above this
#define FOUL_THRESHOLD_G    0.35f   // standoff: moving this much = JAMMED
#define DRAW_THRESHOLD_G    2.00f   // quick-draw flick detection
#define HIT_WINDOW_MS       150     // +/- ms around a beat that counts as "on beat"
#define HIT_REFRACTORY_MS   140     // ignore new hits this soon after one
#define DRAW_TIMEOUT_MS     3000    // no flick within this = "no draw"

// ---- 5. Level 1 game constants (keep in sync with pc/game_logic.py) ---
#define BEATS_PER_ROUND     16      // MAX beats in a round (v5.7: 16; the R packet may send fewer)
#define PERFECT_MS          60      // |timing error| up to this = PERFECT (v5.7)
#define COUNT_IN_BEATS      4
#define MAX_BULLETS         6
#define BULLET_BONUS_MS     25      // each bullet shaves 25 ms off your time

// ---- 6. Level 2 — Spellcaster (keep in sync with pc/game_logic.py) ----
#define LEVEL_INTRO_MS      5000    // "LEVEL 2" intro screen before the level starts
#define MAX_MANA            3
#define START_MANA          1
#define CAST_COOLDOWN_MS    1500    // wait this long between two spells
// CHARGE POSE: point the wand straight at the sky and hold it still = +1 mana every CHARGE_MS.
// Check the sign with accel debug (lower-right button in the lobby): point the wand up.
// If the FORWARD_AXIS column shows about +1.0 keep 1; if it shows about -1.0 set -1.
#define CHARGE_UP_SIGN      1
#define CHARGE_TILT_G       0.75f   // 1.0 = perfectly vertical; lower = a sloppier pose still counts
#define CHARGE_STILL_G      0.45f   // swinging more than this pauses the charge (a trembling hand is fine)
#define CHARGE_MS           800     // time in the pose for +1 mana (keep in sync with pc/game_logic.py)
#define CHARGE_SETTLE_MS    60      // pose must hold this long before charging starts
#define CHARGE_GRACE_MS     400     // a wobble shorter than this only pauses the bar, it doesn't reset it

// Spell gesture detector (tune with the "spell practice" mode + Serial Monitor)
#define GESTURE_START_G     1.00f   // a gesture starts when motion goes above this
#define GESTURE_END_G       0.50f   // ...and ends when it stays below this
#define GESTURE_QUIET_MS    150     //    for this long
#define GESTURE_MIN_MS      120     // shorter than this = just a bump, ignored
#define GESTURE_MAX_MS      1500    // longest gesture we record
#define GESTURE_GAP_MS      250     // ignore the wobble right after a spell
#define LOBE_G              0.80f   // a push in one direction counts if above this
#define ZIGZAG_LOBES        3       // Lightning: at least this many left/right pushes
#define CIRCLE_LOBES        2       // Water: at least this many on BOTH side and up/down
#define THRUST_G            2.00f   // Fire: forward peak must be at least this
#define SPELL_DEBUG         1       // 1 = print gesture numbers to the Serial Monitor

// ---- 7. Level 3 — Combo Clash --------------------------------------------
// No settings: it uses the same spell detector as Level 2. Timings live in pc/game_logic.py.

// ---- 8. Battery ----------------------------------------------------
#define BATT_READ_MS        5000    // measure the battery this often
#define BATT_SEND_MS        10000   // tell the laptop this often (also right after it connects)
#define BATT_LOW_PCT        20      // at or below this: red warning (lobby + arena)

// ---- 9. Watchdog (v5) ------------------------------------------------
// 1 = if the wand ever freezes, it restarts itself after 2 s and the laptop reconnects
//     (the arena pauses the match and logs it in pc/disconnects.csv). Keep this on.
// 0 = off (only for debugging with a debugger attached).
#define USE_WATCHDOG 1

// ---- 10. Debug -----------------------------------------------------
// true prints BLE stack messages to the Serial Monitor (slower).
#define BLE_DEBUG false
