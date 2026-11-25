// =====================================================================
//  Beat-Draw Showdown — wand firmware for TinyScreen+
//  ICT1011 Team Exploration Project
//
//  One wand, three levels:
//    Level 1  COWBOY       air-drum the arrows (flick up/down/left/right) to load bullets, holster, quick-draw
//    Level 2  SPELLCASTER  point the wand at the sky = mana; zig-zag / circle / thrust = spells
//    Level 3  COMBO CLASH  watch 3 spells flash, wait 2 s, cast the combo back from memory
//
//  Hardware stack (bottom -> top):
//    TinyScreen+ (ASM2022)  +  ST BLE TinyShield (ASD2116-R)
//    + Accelerometer TinyShield (ASD2511-R-A, Bosch BMA250)
//    [+ Wireling Adapter TinyShield (ASD2022) + Buzzer Wireling (AST1035)
//       only if USE_BUZZER is 1 in config.h]
//
//  Libraries (Arduino IDE > Library Manager or TinyCircuits GitHub):
//    TinyScreen, STBLE, TinyCircuits BMA250, Wireling (buzzer build only)
//
//  The wand judges its own hits, gestures and draw times with millis()/micros(),
//  so Bluetooth delay never touches the measurements. The laptop
//  (pc/arena_referee.py) is the referee: it starts levels, plays the music,
//  tracks HP / the beam and decides the winner.
//
//  BLE protocol (ASCII, max 20 bytes per packet) — see docs/DESIGN.md (BLE protocol)
//    Laptop -> Wand:  P V L R W G E  |  w M2 U I  |  M3 b Z K J  |  Y
//    Wand -> Laptop:  Q V H B F T N  |  A C f    |  X  |  %
// =====================================================================

#include <Wire.h>
#include <SPI.h>
#include <TinyScreen.h>
#include <STBLE.h>
#include <BMA250.h>
#include "config.h"
#if USE_BUZZER
#include <Wireling.h>
#endif

#if defined(ARDUINO_ARCH_SAMD)
#define SerialMonitorInterface SerialUSB
#else
#define SerialMonitorInterface Serial
#endif

#if BLE_DEBUG
#include <stdio.h>
char sprintbuff[100];
#define PRINTF(...) {sprintf(sprintbuff, __VA_ARGS__); SerialMonitorInterface.print(sprintbuff);}
#else
#define PRINTF(...)
#endif

// ---- Globals required by UART.ino (TinyCircuits BLE example) --------
uint8_t ble_rx_buffer[21];
uint8_t ble_rx_buffer_len = 0;
uint8_t ble_connection_state = false;
#define PIPE_UART_OVER_BTLE_UART_TX_TX 0

#define FIRMWARE_VERSION "5.7"

TinyScreen display = TinyScreen(TinyScreenPlus);
BMA250 accel;

// ---- Game state ------------------------------------------------------
enum GameState {
  ST_LOBBY,        // waiting for laptop (or button for offline practice)
  ST_AIR_DRUM,     // L1: count-in + 8 beats of air drumming
  ST_HOLSTER,      // L1: "HOLSTER!" — get your hand down
  ST_STANDOFF,     // L1: stay still... foul if you move
  ST_DRAW_ACTIVE,  // L1: DRAW! — timing the flick
  ST_RESULT,       // showing a result (any level)
  ST_INTRO,        // "LEVEL 2/3" intro screen
  ST_SPELL,        // L2: spell duel (charge pose + cast)
  ST_BEAM,         // L3: between rounds (beam bar)
  ST_COMBO_SHOW,   // L3: the combo flashes, then "WAIT"
  ST_PROMPT,       // L3: GO! cast the 3 spells
  ST_TUT_ARROWS    // L1 tutorial: free arrow flicks, each one reported with d<U/D/L/R>
};
GameState state = ST_LOBBY;
GameState introNext = ST_SPELL;

bool offlineMode = false;          // practice mode without a laptop
bool warmup = false;               // Level 2 warm-up sent by the laptop (free spells, reported with C)
char resetCause = 'P';             // why the wand last started: P power, B brown-out, W watchdog, R reset, S software
char fizzleWhy = 0;                // closest spell when a gesture FIZZLEs ('L'/'W'/'F', 's' = too short)
uint32_t hintUntilMs = 0;

// Accelerometer (all values in g)
const float LSB_PER_G = 64.0f;     // BMA250 at +/-8 g, 10-bit
float ax = 0, ay = 0, az = 0;      // latest sample
float gx = 0, gy = 0, gz = 1;      // slow gravity estimate
bool accelOk = false;
uint32_t lastSampleUs = 0;
const uint32_t SAMPLE_PERIOD_US = 2000;   // 500 Hz loop sampling

// ---- Level 1: air-drum + quick-draw ----------------------------------
char pattern[BEATS_PER_ROUND + 1] = "DUD-UDU-";   // U D L R = arrows, - = rest
uint8_t roundBeats = 8;            // beats in this round (v5.7: up to 16, = length of the R pattern)
uint16_t beatMs = 667;             // 90 BPM
uint32_t drumT0 = 0;               // millis() of beat 0 (after count-in)
bool beatHit[BEATS_PER_ROUND];
uint8_t bullets = 0;
bool inHit = false;
uint32_t hitStartMs = 0, lastHitMs = 0;
float peakX = 0, peakY = 0, peakZ = 0, peakMag = 0;
float startX = 0, startY = 0, startZ = 0;   // first sample of a hit: which way the flick STARTED
int8_t lastBeatShown = -99;
bool needRedraw = false;
int8_t feedback = 0;               // 1 = HIT, -1 = MISS, 0 = none

float refX = 0, refY = 0, refZ = 0;      // holster pose
float refSumX = 0, refSumY = 0, refSumZ = 0;
uint16_t refCount = 0;
bool refReady = false;
bool tutStill = false;             // L1 tutorial holster (O3): never fouls, streams s<0-20> instead
float stillPeak = 0;               // biggest move in the last 100 ms (g)
uint32_t lastStillSendMs = 0;
char lastArrow = 0;
uint32_t stateStartMs = 0;
uint32_t standoffDelayMs = 0;      // offline mode only
uint32_t cueUs = 0;
uint32_t drawUs = 0;

// ---- Level 2: spellcaster --------------------------------------------
uint8_t mana = START_MANA;
int8_t myHp = 5, oppHp = 5;
uint32_t lastCastMs = 0;
bool castOnce = false;
uint32_t spellT0 = 0;              // millis() when Level 2 starts (after the intro)
bool charging = false;             // wand held pointing at the sky = charging mana
uint32_t lastPoseMs = 0, chargeEndMs = 0, lastChargeDrawMs = 0;
uint32_t poseRunStart = 0;         // when the wand entered the pose (0 = not in pose)
uint32_t chargeAccum = 0;          // ms charged towards the next +1 mana (pauses during a short wobble)
uint32_t chargeTickMs = 0;
float pfx = 0, pfy = 0, pfz = 1;   // lightly smoothed raw accel (ignores hand tremble) for the pose check
char statusText[14] = "";
uint8_t statusColor = TS_8b_White;
uint32_t statusUntilMs = 0;
char incomingSpell = 0;
uint32_t incomingUntilMs = 0;
uint32_t introUntilMs = 0;
int8_t introShown = -1;
uint8_t introLevel = 2;
uint32_t lastActivityMs = 0;       // offline practice auto-exit

// gesture recorder (shared by Level 2 casting and Level 3 prompts)
bool inGesture = false;
uint32_t gStartMs = 0, gLastMotionMs = 0, gLastMotionUs = 0, lastGestureEndMs = 0;
uint8_t lobeCount[3];              // [side, updown, forward]
int8_t lobeSign[3];
float gEnergy[3], gPeak[3];

// ---- Level 3: beam clash -----------------------------------------------
uint8_t myPos = 50;                // 100 = I win, 0 = I lose
#define MAX_COMBO 5                // Level 3: 3 spells per round, 5 in the final round
char comboStr[MAX_COMBO + 1] = "LWF";   // the combo to remember
uint8_t comboLen = 3;
uint16_t flashMs = 800;            // how long each spell of the combo flashes
uint32_t showStartMs = 0;
int8_t shownK = -1;                // last combo slot drawn
char castStr[MAX_COMBO + 1] = "";  // what I cast after GO
uint8_t castCount = 0;
uint32_t promptUs = 0;             // micros() when GO (K) arrived
uint32_t inputStartMs = 0;
uint8_t practiceRound = 0;         // offline combo practice
uint32_t nextComboMs = 0;

// ---- Battery -------------------------------------------------------------
float battV = 0;                   // smoothed battery voltage
int8_t battPct = -1;               // -1 = not measured yet
uint32_t lastBattReadMs = 0, lastBattSendMs = 0;

uint8_t lastButtons = 0;
uint8_t buttonsNow = 0;
uint8_t lastConnState = 2;         // force first lobby draw
bool accelDebug = false;

// =====================================================================
//  Small helpers
// =====================================================================
static inline float absf(float v) { return v < 0 ? -v : v; }
static inline float axisVal(uint8_t axis, float x, float y, float z) {
  return axis == 0 ? x : (axis == 1 ? y : z);
}

void bleSend(const char *msg) {
  if (offlineMode || !ble_connection_state) return;
  uint8_t len = strlen(msg);
  if (len > 20) len = 20;            // BLE packet limit
  Write_UART_TX((char *)msg, len);
}

// ---- Watchdog ----------------------------------------------------------
// If the wand ever hangs (e.g. an I2C read or the Bluetooth chip stops answering), the SAMD21's
// hardware watchdog restarts it after ~2 s instead of leaving a frozen screen. The laptop then
// reconnects, sees reset cause 'W' in the V packet and logs it. Uses generic clock 2 (free on the
// TinyScreen+ core; the same setup as Adafruit's SleepyDog library).
void wdtInit() {
  GCLK->GENDIV.reg = GCLK_GENDIV_ID(2) | GCLK_GENDIV_DIV(4);              // 32768 Hz / 2^(4+1) = 1024 Hz
  GCLK->GENCTRL.reg = GCLK_GENCTRL_ID(2) | GCLK_GENCTRL_GENEN | GCLK_GENCTRL_SRC_OSCULP32K | GCLK_GENCTRL_DIVSEL;
  while (GCLK->STATUS.bit.SYNCBUSY);
  GCLK->CLKCTRL.reg = GCLK_CLKCTRL_ID_WDT | GCLK_CLKCTRL_CLKEN | GCLK_CLKCTRL_GEN_GCLK2;
  WDT->CTRL.reg = 0;
  while (WDT->STATUS.bit.SYNCBUSY);
  WDT->CONFIG.reg = WDT_CONFIG_PER_2K;                                   // 2048 ticks at 1024 Hz = 2 s
  WDT->CTRL.reg = WDT_CTRL_ENABLE;
  while (WDT->STATUS.bit.SYNCBUSY);
}
void wdtFeed() {                                                          // "I'm still alive"
  if (!WDT->STATUS.bit.SYNCBUSY) WDT->CLEAR.reg = WDT_CLEAR_CLEAR_KEY;
}
char readResetCause() {
  uint8_t r = PM->RCAUSE.reg;
  if (r & PM_RCAUSE_WDT) return 'W';
  if (r & (PM_RCAUSE_BOD12 | PM_RCAUSE_BOD33)) return 'B';
  if (r & PM_RCAUSE_SYST) return 'S';
  if (r & PM_RCAUSE_EXT) return 'R';
  return 'P';
}

// Keeps Bluetooth alive while we wait (never use plain delay() > 5 ms)
void waitMs(uint32_t ms) {
  uint32_t start = millis();
  while (millis() - start < ms) { aci_loop(); wdtFeed(); }
}

// ---- Buzzer (optional) -----------------------------------------------
#if USE_BUZZER
const uint8_t BUZZER_PIN = A0 + BUZZER_PORT;
void beep(uint16_t freq, uint16_t ms) { tone(BUZZER_PIN, freq, ms); }
#else
void beep(uint16_t, uint16_t) {}
#endif

const char *spellName(char s) {
  if (s == 'L') return "ZAP!";
  if (s == 'W') return "SPLASH!";
  if (s == 'F') return "FIRE!";
  return "FIZZLE";
}
const char *spellMove(char s) {
  if (s == 'L') return "ZIG-ZAG";
  if (s == 'W') return "CIRCLE";
  return "THRUST";
}
// What to do better after a FIZZLE (fits the 96 px screen)
const char *fizzleHint(char c) {
  if (c == 'L') return "zig-zag faster!";
  if (c == 'W') return "rounder circle!";
  if (c == 'F') return "thrust harder!";
  return "bigger move!";
}
uint8_t spellColor(char s) {
  if (s == 'L') return TS_8b_Yellow;
  if (s == 'W') return TS_8b_Blue;
  if (s == 'F') return TS_8b_Red;
  return TS_8b_Gray;
}
void spellBeep(char s) {
  if (s == 'L') { beep(3000, 40); }
  else if (s == 'W') { beep(700, 120); }
  else if (s == 'F') { beep(250, 150); }
}

// =====================================================================
//  Battery level
//  getVCC() and getBattVoltage() are from TinyCircuits' "TinyScreen+ Battery Voltage
//  Reading" tutorial (Ben Rose for TinyCircuits, 2018): VBATT is on pin A4 through a 1/2
//  divider, and the ADC reference is worked out from the chip's internal 1.1 V bandgap.
// =====================================================================
float getVCC() {
  SYSCTRL->VREF.reg |= SYSCTRL_VREF_BGOUTEN;
  while (ADC->STATUS.bit.SYNCBUSY == 1);
  ADC->SAMPCTRL.bit.SAMPLEN = 0x1;
  while (ADC->STATUS.bit.SYNCBUSY == 1);
  ADC->INPUTCTRL.bit.MUXPOS = 0x19;         // Internal bandgap input
  while (ADC->STATUS.bit.SYNCBUSY == 1);
  ADC->CTRLA.bit.ENABLE = 0x01;             // Enable ADC
  while (ADC->STATUS.bit.SYNCBUSY == 1);
  ADC->SWTRIG.bit.START = 1;                // Start conversion
  ADC->INTFLAG.bit.RESRDY = 1;              // Clear the Data Ready flag
  while (ADC->STATUS.bit.SYNCBUSY == 1);
  ADC->SWTRIG.bit.START = 1;                // Start again to throw out the first value
  while (ADC->INTFLAG.bit.RESRDY == 0);     // Wait for the conversion
  uint32_t valueRead = ADC->RESULT.reg;
  while (ADC->STATUS.bit.SYNCBUSY == 1);
  ADC->CTRLA.bit.ENABLE = 0x00;             // Disable ADC
  while (ADC->STATUS.bit.SYNCBUSY == 1);
  SYSCTRL->VREF.reg &= ~SYSCTRL_VREF_BGOUTEN;
  return (1.1 * 1023.0) / valueRead;
}

float getBattVoltage() {
  const int VBATTpin = A4;
  float VCC = getVCC();
  float reading = analogRead(VBATTpin);
  reading = analogRead(VBATTpin);           // throw out the first value
  return VCC * reading / 1023.0 / 0.5;      // 1/2 resistor divider
}

// LiPo voltage -> rough % (resting voltage; reads ~100% while charging on USB)
int8_t voltsToPct(float v) {
  const float V[] = {3.30f, 3.50f, 3.60f, 3.65f, 3.70f, 3.75f, 3.80f, 3.90f, 4.00f, 4.10f, 4.20f};
  const int8_t P[] = {0, 3, 8, 15, 25, 35, 45, 62, 78, 90, 100};
  if (v <= V[0]) return 0;
  for (uint8_t k = 1; k < 11; k++) {
    if (v <= V[k]) return P[k - 1] + (int8_t)((v - V[k - 1]) / (V[k] - V[k - 1]) * (P[k] - P[k - 1]));
  }
  return 100;
}

// Measure every BATT_READ_MS (never during a timed moment) and tell the laptop every BATT_SEND_MS
void updateBattery(uint32_t now, bool force) {
  bool busy = state == ST_AIR_DRUM || state == ST_STANDOFF || state == ST_DRAW_ACTIVE || state == ST_PROMPT
              || inGesture || inHit;
  if (!force && (busy || now - lastBattReadMs < BATT_READ_MS)) return;
  lastBattReadMs = now;
  float v = getBattVoltage();
  if (v < 2.5f || v > 5.5f) return;          // nonsense reading
  battV = (battPct < 0) ? v : battV + (v - battV) * 0.3f;
  int8_t p = voltsToPct(battV);
  bool changed = p != battPct;
  battPct = p;
  if (force || now - lastBattSendMs >= BATT_SEND_MS) {
    lastBattSendMs = now;
    char msg[8];
    sprintf(msg, "%%%d", battPct);
    bleSend(msg);
  }
  if (changed && state == ST_LOBBY) lastConnState = 2;   // redraw the lobby with the new %
}

// =====================================================================
//  Drawing (96 x 64 OLED)
// =====================================================================
void centerText(const char *s, uint8_t y, const FONT_INFO &font, uint8_t fg, uint8_t bg) {
  display.setFont(font);
  display.fontColor(fg, bg);
  uint8_t w = display.getPrintWidth((char *)s);
  display.setCursor(w < 96 ? (96 - w) / 2 : 0, y);
  display.print(s);
}

// Revolver cylinder: 6 chambers around (cx, cy)
void drawCylinder(uint8_t cx, uint8_t cy, uint8_t loaded) {
  const int8_t ox[6] = {0, 10, 10, 0, -10, -10};
  const int8_t oy[6] = {-11, -5, 6, 11, 6, -5};
  for (uint8_t i = 0; i < MAX_BULLETS; i++) {
    uint8_t x = cx + ox[i] - 3, y = cy + oy[i] - 3;
    display.drawRect(x, y, 7, 7, TSRectangleFilled, TS_8b_Black);
    if (i < loaded) display.drawRect(x, y, 7, 7, TSRectangleFilled, TS_8b_Yellow);
    else            display.drawRect(x, y, 7, 7, TSRectangleNoFill, TS_8b_Gray);
  }
  display.drawRect(cx - 2, cy - 2, 5, 5, TSRectangleFilled, TS_8b_Gray);   // pin
}

void drawLobby() {
  display.clearScreen();
  centerText("BEAT-DRAW", 0, liberationSans_10ptFontInfo, TS_8b_Yellow, TS_8b_Black);
  centerText("SHOWDOWN", 13, liberationSans_10ptFontInfo, TS_8b_Yellow, TS_8b_Black);
  char name[20];
  if (battPct >= 0) sprintf(name, "BDS-%d  %d%%", PLAYER_ID, battPct);
  else sprintf(name, "BDS-%d", PLAYER_ID);
  centerText(name, 27, liberationSans_8ptFontInfo,
             (battPct >= 0 && battPct <= BATT_LOW_PCT) ? TS_8b_Red : TS_8b_White, TS_8b_Black);
  if (!accelOk) {
    centerText("NO ACCEL!", 44, liberationSans_8ptFontInfo, TS_8b_Red, TS_8b_Black);
  } else if (ble_connection_state) {
    centerText("Laptop linked", 40, liberationSans_8ptFontInfo, TS_8b_Green, TS_8b_Black);
    if (resetCause == 'W' || resetCause == 'B')        // tells you WHY the wand restarted last time
      centerText(resetCause == 'W' ? "(restarted: froze)" : "(restarted: low batt)", 52,
                 liberationSans_8ptFontInfo, TS_8b_Gray, TS_8b_Black);
  } else {
    // practice menu: one button per level
    centerText("UL draw  UR spell", 40, liberationSans_8ptFontInfo, TS_8b_Gray, TS_8b_Black);
    centerText("LL combo LR debug", 52, liberationSans_8ptFontInfo, TS_8b_Gray, TS_8b_Black);
  }
}

// ---- Level 1 screens ---------------------------------------------------
// A filled arrow (head + stem) pointing U / D / L / R, about 2r pixels tall, drawn with lines.
void drawArrow(int16_t cx, int16_t cy, int16_t r, char dir, uint8_t color) {
  for (int16_t i = 0; i <= r; i++) {                       // head: rows getting wider
    int16_t y = -r + i, w = i;
    if (dir == 'U') display.drawLine(cx - w, cy + y, cx + w, cy + y, color);
    else if (dir == 'D') display.drawLine(cx - w, cy - y, cx + w, cy - y, color);
    else if (dir == 'L') display.drawLine(cx + y, cy - w, cx + y, cy + w, color);
    else display.drawLine(cx - y, cy - w, cx - y, cy + w, color);
  }
  int16_t sw = r / 3 > 0 ? r / 3 : 1;                      // stem
  for (int16_t y = 1; y <= r; y++) {
    if (dir == 'U') display.drawLine(cx - sw, cy + y, cx + sw, cy + y, color);
    else if (dir == 'D') display.drawLine(cx - sw, cy - y, cx + sw, cy - y, color);
    else if (dir == 'L') display.drawLine(cx + y, cy - sw, cx + y, cy + sw, color);
    else display.drawLine(cx - y, cy - sw, cx - y, cy + sw, color);
  }
}
uint8_t arrowColor(char d) {
  if (d == 'U') return TS_8b_Green;
  if (d == 'D') return TS_8b_Blue;
  if (d == 'L') return TS_8b_Yellow;
  return TS_8b_Red;
}

void drawBeatStrip(int8_t current) {
  // 8 boxes fit the screen: show beats 1-8, then 9-16 (v5.7)
  uint8_t page = (current >= 8 && roundBeats > 8) ? 8 : 0;
  display.clearWindow(0, 0, 96, 13);
  for (uint8_t k = page; k < page + 8 && k < roundBeats; k++) {
    uint8_t x = (k - page) * 12, y = 0;
    uint8_t col = TS_8b_DarkBlue;
    if (pattern[k] == '-') col = TS_8b_Black;
    if (beatHit[k]) col = TS_8b_Green;
    else if (current > (int8_t)k && pattern[k] != '-') col = TS_8b_DarkRed;   // missed
    display.drawRect(x, y, 11, 12, TSRectangleFilled, col);
    display.drawRect(x, y, 11, 12, TSRectangleNoFill, (current == (int8_t)k) ? TS_8b_White : TS_8b_Gray);
    if (pattern[k] != '-') drawArrow(x + 5, y + 6, 4, pattern[k], TS_8b_White);
  }
}

void drawDrumScreen(int8_t currentBeat, int8_t countIn) {
  drawBeatStrip(currentBeat);
  display.clearWindow(0, 14, 96, 50);
  drawCylinder(22, 38, bullets);
  if (countIn > 0) {
    char s[4];
    sprintf(s, "%d", countIn);
    centerText(s, 18, liberationSans_22ptFontInfo, TS_8b_White, TS_8b_Black);
    if (pattern[0] != '-') drawArrow(72, 52, 6, pattern[0], arrowColor(pattern[0]));   // the first move
  } else {
    // BIG arrow for this beat on the right (what to flick now)
    char c = (currentBeat >= 0 && currentBeat < roundBeats) ? pattern[currentBeat] : '-';
    if (c != '-') {
      drawArrow(70, 34, 14, c, beatHit[currentBeat] ? TS_8b_Green : arrowColor(c));
    } else {
      display.setFont(liberationSans_8ptFontInfo);
      display.fontColor(TS_8b_Gray, TS_8b_Black);
      display.setCursor(58, 28);
      display.print("rest");
    }
    if (feedback != 0) {
      display.setFont(liberationSans_8ptFontInfo);
      display.fontColor(feedback == 2 ? TS_8b_Yellow : (feedback > 0 ? TS_8b_Green : TS_8b_Red), TS_8b_Black);
      display.setCursor(feedback == 2 ? 50 : (feedback > 0 ? 56 : 56), 52);
      display.print(feedback == 2 ? "PERFECT" : (feedback > 0 ? "GOOD" : "MISS"));
    }
  }
}

void drawHolster() {
  display.clearScreen();
  drawCylinder(48, 22, bullets);
  centerText("HOLSTER!", 44, liberationSans_12ptFontInfo, TS_8b_Yellow, TS_8b_Black);
}

void drawStandoff() {
  display.drawRect(0, 0, 96, 64, TSRectangleFilled, TS_8b_DarkRed);
  centerText(tutStill ? "FREEZE..." : "STEADY...", 24, liberationSans_10ptFontInfo, TS_8b_White, TS_8b_DarkRed);
  if (tutStill) centerText("practice", 46, liberationSans_8ptFontInfo, TS_8b_Gray, TS_8b_DarkRed);
}

// L1 tutorial: the last arrow the wand saw, big
void drawTutArrows() {
  display.clearScreen();
  centerText("FLICK THE TIP", 0, liberationSans_8ptFontInfo, TS_8b_Yellow, TS_8b_Black);
  if (lastArrow) drawArrow(48, 36, 16, lastArrow, arrowColor(lastArrow));
  else centerText("follow big screen", 30, liberationSans_8ptFontInfo, TS_8b_Gray, TS_8b_Black);
}

void drawDrawCue() {
  display.drawRect(0, 0, 96, 64, TSRectangleFilled, TS_8b_Green);
  centerText("DRAW!", 18, liberationSans_22ptFontInfo, TS_8b_Black, TS_8b_Green);
}

void drawMuzzleFlash() {
  display.clearScreen();
  const uint8_t cx = 48, cy = 22;
  const int8_t dx[8] = {30, 22, 0, -22, -30, -22, 0, 22};
  const int8_t dy[8] = {0, 14, 20, 14, 0, -14, -20, -14};
  for (uint8_t i = 0; i < 8; i++) {
    display.drawLine(cx, cy, cx + dx[i], cy + dy[i], i % 2 ? TS_8b_Red : TS_8b_Yellow);
    waitMs(15);
  }
  display.drawRect(cx - 5, cy - 5, 11, 11, TSRectangleFilled, TS_8b_White);
}

void drawShatter() {
  display.clearScreen();
  const uint8_t hx = 60, hy = 24;    // bullet hole
  const int8_t ex[9] = {-60, -40, -10, 30, 35, 20, -25, -55, 5};
  const int8_t ey[9] = {-10, -24, -24, -20, 10, 39, 39, 20, 39};
  for (uint8_t i = 0; i < 9; i++) {
    int16_t x2 = hx + ex[i], y2 = hy + ey[i];
    x2 = constrain(x2, 0, 95);
    y2 = constrain(y2, 0, 63);
    display.drawLine(hx, hy, x2, y2, TS_8b_White);
    waitMs(20);
  }
  display.drawRect(hx - 4, hy - 4, 9, 9, TSRectangleFilled, TS_8b_Gray);
  display.drawRect(hx - 2, hy - 2, 5, 5, TSRectangleFilled, TS_8b_Black);
}

void showResult(char outcome, int32_t ms) {
  state = ST_RESULT;
  stateStartMs = millis();
  char line[28];
  if (outcome == 'W') {
    drawMuzzleFlash();
    beep(1800, 80);
    centerText("YOU WIN!", 40, liberationSans_10ptFontInfo, TS_8b_Yellow, TS_8b_Black);
    sprintf(line, "%ld ms", (long)ms);
    centerText(line, 54, liberationSans_8ptFontInfo, TS_8b_White, TS_8b_Black);
  } else if (outcome == 'L') {
    drawShatter();
    beep(200, 400);
    centerText("BANG! YOU LOSE", 46, liberationSans_8ptFontInfo, TS_8b_Red, TS_8b_Black);
    if (ms > 0) {
      sprintf(line, "%ld ms", (long)ms);
      display.setFont(liberationSans_8ptFontInfo);
      display.fontColor(TS_8b_White, TS_8b_Black);
      display.setCursor(2, 2);
      display.print(line);
    }
  } else if (outcome == 'F') {
    display.drawRect(0, 0, 96, 64, TSRectangleFilled, TS_8b_Red);
    centerText("JAMMED!", 14, liberationSans_14ptFontInfo, TS_8b_White, TS_8b_Red);
    centerText("FOUL - too early", 42, liberationSans_8ptFontInfo, TS_8b_White, TS_8b_Red);
    beep(150, 500);
  } else if (outcome == 'P') {       // offline practice result
    display.clearScreen();
    centerText("PRACTICE", 2, liberationSans_8ptFontInfo, TS_8b_Gray, TS_8b_Black);
    if (ms >= 0) {
      sprintf(line, "%ld ms", (long)ms);
      centerText(line, 16, liberationSans_14ptFontInfo, TS_8b_Yellow, TS_8b_Black);
      sprintf(line, "bullets %d -> %ld", bullets, (long)(ms - bullets * BULLET_BONUS_MS));
      centerText(line, 40, liberationSans_8ptFontInfo, TS_8b_White, TS_8b_Black);
    } else {
      centerText("NO DRAW", 20, liberationSans_14ptFontInfo, TS_8b_Red, TS_8b_Black);
    }
    centerText("Btn = lobby", 52, liberationSans_8ptFontInfo, TS_8b_Gray, TS_8b_Black);
  } else {                           // 'X' tie / no contest
    display.clearScreen();
    centerText("TIE", 16, liberationSans_14ptFontInfo, TS_8b_White, TS_8b_Black);
    centerText("No winner", 42, liberationSans_8ptFontInfo, TS_8b_Gray, TS_8b_Black);
  }
}

// ---- Level 2/3 screens -------------------------------------------------
void drawIntro(uint8_t lvl, uint8_t secondsLeft) {
  display.clearScreen();
  centerText(lvl == 2 ? "LEVEL 2" : "LEVEL 3", 0, liberationSans_10ptFontInfo, TS_8b_Yellow, TS_8b_Black);
  centerText(lvl == 2 ? "SPELLCASTER" : "BEAM CLASH", 13, liberationSans_10ptFontInfo, TS_8b_White, TS_8b_Black);
  char s[4];
  sprintf(s, "%d", secondsLeft);
  centerText(s, 30, liberationSans_22ptFontInfo, TS_8b_White, TS_8b_Black);
}

void setStatus(const char *txt, uint8_t color, uint16_t ms) {
  strncpy(statusText, txt, sizeof(statusText) - 1);
  statusText[sizeof(statusText) - 1] = '\0';
  statusColor = color;
  statusUntilMs = millis() + ms;
  needRedraw = true;
}

// HP squares (top), mana orbs, big status line, warning line
void drawSpellScreen() {
  display.clearScreen();
  for (int8_t k = 0; k < myHp && k < 8; k++)        // my HP: red squares from the left
    display.drawRect(1 + k * 7, 1, 5, 5, TSRectangleFilled, TS_8b_Red);
  for (int8_t k = 0; k < oppHp && k < 8; k++)       // rival HP: gray squares from the right
    display.drawRect(90 - k * 7, 1, 5, 5, TSRectangleFilled, TS_8b_Gray);
  for (uint8_t k = 0; k < MAX_MANA; k++) {          // mana orbs
    if (offlineMode || warmup || k < mana) display.drawRect(1 + k * 11, 10, 9, 9, TSRectangleFilled, TS_8b_Blue);
    else                         display.drawRect(1 + k * 11, 10, 9, 9, TSRectangleNoFill, TS_8b_DarkBlue);
  }
  display.setFont(liberationSans_8ptFontInfo);
  display.fontColor(TS_8b_Gray, TS_8b_Black);
  display.setCursor(38, 10);
  display.print(warmup ? "WARM UP" : (offlineMode ? "PRACTICE" : "mana"));

  uint32_t now = millis();
  if (now < statusUntilMs && statusText[0]) {
    centerText(statusText, 26, liberationSans_14ptFontInfo, statusColor, TS_8b_Black);
  } else if (charging) {
    centerText("CHARGING", 26, liberationSans_14ptFontInfo, TS_8b_Blue, TS_8b_Black);
  } else if (!offlineMode && !warmup && mana == 0) {
    centerText("NO MANA", 26, liberationSans_14ptFontInfo, TS_8b_DarkRed, TS_8b_Black);
  } else if (!offlineMode && !warmup && castOnce && now - lastCastMs < CAST_COOLDOWN_MS) {
    centerText("wait...", 26, liberationSans_14ptFontInfo, TS_8b_Gray, TS_8b_Black);
  } else {
    centerText("CAST!", 26, liberationSans_14ptFontInfo, TS_8b_Green, TS_8b_Black);
  }
  if (now < hintUntilMs && fizzleWhy) {               // how to fix the last FIZZLE
    centerText(fizzleHint(fizzleWhy), 52, liberationSans_8ptFontInfo, TS_8b_White, TS_8b_Black);
  } else if (now < incomingUntilMs && incomingSpell) {
    char w[16];
    sprintf(w, "! %s !", incomingSpell == 'L' ? "LIGHTNING" : (incomingSpell == 'W' ? "WATER" : "FIRE"));
    centerText(w, 52, liberationSans_8ptFontInfo, spellColor(incomingSpell), TS_8b_Black);
  } else if (warmup) {
    centerText("follow big screen", 52, liberationSans_8ptFontInfo, TS_8b_Gray, TS_8b_Black);
  } else {
    centerText("point up = charge", 52, liberationSans_8ptFontInfo, TS_8b_Gray, TS_8b_Black);
  }
}

// Charge progress bar under the status text (only while charging)
void drawChargeBar() {
  uint32_t el = chargeAccum;
  uint8_t w = el >= CHARGE_MS ? 94 : (uint8_t)(el * 94UL / CHARGE_MS);
  display.drawRect(1, 45, 94, 4, TSRectangleNoFill, TS_8b_DarkBlue);
  if (w > 0) display.drawRect(1, 45, w, 4, TSRectangleFilled, TS_8b_Blue);
}

void drawBeamBar() {
  uint8_t w = (uint16_t)myPos * 96 / 100;
  if (w > 0)  display.drawRect(0, 24, w, 14, TSRectangleFilled, TS_8b_Yellow);
  if (w < 96) display.drawRect(w, 24, 96 - w, 14, TSRectangleFilled, TS_8b_Red);
  uint8_t mx = w < 2 ? 0 : (w > 94 ? 94 : w - 1);
  display.drawRect(mx, 22, 2, 18, TSRectangleFilled, TS_8b_White);
}

void drawBeamScreen() {
  display.clearScreen();
  centerText(offlineMode ? "COMBO PRACTICE" : "COMBO CLASH", 2, liberationSans_8ptFontInfo, TS_8b_Yellow, TS_8b_Black);
  if (!offlineMode) drawBeamBar();
  centerText(offlineMode ? "get ready..." : "watch the screen", 48, liberationSans_8ptFontInfo, TS_8b_Gray, TS_8b_Black);
}

// One combo slot: k = 0..2. s = spell letter, '?' = hidden, ' ' = empty. border = outline colour.
// Combo slots: 3 big ones (24 px) or, in the final round, 5 smaller ones (15 px) across the 96 px screen
void drawComboSlot(uint8_t k, char s, uint8_t border) {
  uint8_t step = comboLen <= 3 ? 28 : 19, sz = step - 4;
  uint8_t x = (96 - (comboLen * step - 4)) / 2 + k * step, y = comboLen <= 3 ? 20 : 24;
  display.drawRect(x, y, sz, sz, TSRectangleFilled, (s == 'L' || s == 'W' || s == 'F') ? spellColor(s) : TS_8b_Black);
  display.drawRect(x, y, sz, sz, TSRectangleNoFill, border);
  if (s != ' ') {
    char t[2] = {s, 0};
    display.setFont(comboLen <= 3 ? liberationSans_10ptFontInfo : liberationSans_8ptFontInfo);
    display.fontColor(s == 'L' ? TS_8b_Black : TS_8b_White, (s == 'L' || s == 'W' || s == 'F') ? spellColor(s) : TS_8b_Black);
    display.setCursor(x + (comboLen <= 3 ? 8 : 4), y + (comboLen <= 3 ? 6 : 3));
    display.print(t);
  }
}

void drawComboTitle(const char *t, uint8_t color) {
  display.drawRect(0, 0, 96, 16, TSRectangleFilled, TS_8b_Black);
  centerText(t, 2, liberationSans_10ptFontInfo, color, TS_8b_Black);
}

void showLevelResult(char o, uint8_t lvl) {
  state = ST_RESULT;
  stateStartMs = millis();
  display.clearScreen();
  centerText(lvl == 3 ? "FINAL" : (lvl == 2 ? "LEVEL 2" : "LEVEL 1"), 2, liberationSans_8ptFontInfo,
             TS_8b_Gray, TS_8b_Black);
  if (o == 'W') {
    centerText(lvl == 3 ? "CHAMPION!" : "YOU WIN!", 20, liberationSans_14ptFontInfo, TS_8b_Yellow, TS_8b_Black);
    beep(1500, 80); waitMs(100); beep(2000, 80); waitMs(100); beep(2500, 150);
  } else if (o == 'L') {
    centerText(lvl == 3 ? "DEFEATED" : "YOU LOSE", 20, liberationSans_14ptFontInfo, TS_8b_Red, TS_8b_Black);
    beep(300, 400);
  } else {
    centerText("DRAW", 20, liberationSans_14ptFontInfo, TS_8b_White, TS_8b_Black);
  }
  if (offlineMode) centerText("Btn = lobby", 52, liberationSans_8ptFontInfo, TS_8b_Gray, TS_8b_Black);
}

// =====================================================================
//  State transitions
// =====================================================================
void goLobby() {
  state = ST_LOBBY;
  offlineMode = false;
  tutStill = false;
  warmup = false;
  inGesture = false;
  inHit = false;
  lastConnState = 2;                 // forces lobby redraw
}

void startDrum(uint16_t bpm, const char *pat) {
  if (bpm < 60) bpm = 60;
  if (bpm > 200) bpm = 200;
  beatMs = 60000UL / bpm;
  roundBeats = 0;
  while (roundBeats < BEATS_PER_ROUND && pat[roundBeats] != '\0') roundBeats++;   // 8 or 16 (v5.7)
  if (roundBeats == 0) roundBeats = 1;
  for (uint8_t k = 0; k < BEATS_PER_ROUND; k++) {
    char c = (k < roundBeats) ? pat[k] : '-';
    pattern[k] = (c == 'U' || c == 'D' || c == 'L' || c == 'R') ? c : '-';
    beatHit[k] = false;
  }
  pattern[roundBeats] = '\0';
  bullets = 0;
  feedback = 0;
  inHit = false;
  lastHitMs = 0;
  lastBeatShown = -99;
  drumT0 = millis() + (uint32_t)COUNT_IN_BEATS * beatMs;
  state = ST_AIR_DRUM;
  display.clearScreen();
}

void startStandoff() {
  state = ST_STANDOFF;
  tutStill = false;
  stateStartMs = millis();
  refSumX = refSumY = refSumZ = 0;
  refCount = 0;
  refReady = false;
  drawStandoff();
}

void drawCue() {
  if (state != ST_STANDOFF) return;   // fouled or not ready: ignore
  drawDrawCue();
  beep(2500, 250);
  cueUs = micros();
  drawUs = 0;
  if (!refReady && refCount > 0) {    // very early cue: use what we have
    refX = refSumX / refCount; refY = refSumY / refCount; refZ = refSumZ / refCount;
    refReady = true;
  }
  state = ST_DRAW_ACTIVE;
}

void startIntro(uint8_t lvl, GameState next, uint32_t ms) {
  introLevel = lvl;
  introNext = next;
  introUntilMs = millis() + ms;
  introShown = -1;
  inGesture = false;
  inHit = false;
  state = ST_INTRO;
}

// Level 2: M2,<bpm>,<hp>,<opp>
void startSpellLevel(uint16_t bpm, int8_t hp, int8_t opp, bool practice) {
  offlineMode = practice;
  warmup = false;
  if (bpm < 60) bpm = 60;
  if (bpm > 200) bpm = 200;
  beatMs = 60000UL / bpm;
  myHp = hp; oppHp = opp;
  mana = START_MANA;
  castOnce = false;
  charging = false;
  chargeAccum = 0;
  poseRunStart = 0;
  incomingSpell = 0;
  statusText[0] = '\0';
  uint32_t introMs = practice ? 1500 : LEVEL_INTRO_MS;
  spellT0 = millis() + introMs;      // the duel starts when the intro ends
  lastActivityMs = spellT0;
  startIntro(2, ST_SPELL, introMs);
}

// Level 3: M3,<my pos>   (practice = offline combo practice, LL button in the lobby)
void startBeamLevel(uint8_t pos, bool practice) {
  offlineMode = practice;
  warmup = false;
  myPos = pos;
  practiceRound = 0;
  uint32_t introMs = practice ? 1500 : LEVEL_INTRO_MS;
  nextComboMs = millis() + introMs + 800;
  startIntro(3, ST_BEAM, introMs);
}

// w<seconds>: Level 2 warm-up sent by the laptop. Spells are free (no mana, no cooldown) and each one
// is still reported with C so the arena can tick it off; FIZZLEs are reported with f<closest>.
void startWarmup() {
  startSpellLevel(120, 0, 0, false);      // hp 0,0 = no HP squares on the screen
  warmup = true;
  introUntilMs = millis();                // no intro: straight into casting
  spellT0 = millis();
}

void enterIntroNext() {
  state = introNext;
  if (state == ST_SPELL) { needRedraw = true; }
  else if (state == ST_BEAM) { drawBeamScreen(); }
}

// Z<combo><flash x 100 ms>: show the spells one by one (e.g. ZFLW8, final round ZWFWLF6).
// Spells can repeat (WFW) from round 2 on; the combo is 3 to 5 letters long.
void startComboShow(const char *combo, uint16_t fl) {
  comboLen = 0;
  while (comboLen < MAX_COMBO && (combo[comboLen] == 'L' || combo[comboLen] == 'W' || combo[comboLen] == 'F')) {
    comboStr[comboLen] = combo[comboLen];
    comboLen++;
  }
  if (comboLen == 0) { comboStr[0] = 'L'; comboLen = 1; }
  comboStr[comboLen] = 0;
  flashMs = fl < 200 ? 200 : fl;
  showStartMs = millis();
  shownK = -1;
  state = ST_COMBO_SHOW;
  display.clearScreen();
  drawComboTitle(comboLen > 3 ? "FINAL - WATCH!" : "WATCH!", TS_8b_Yellow);
  for (uint8_t k = 0; k < comboLen; k++) drawComboSlot(k, ' ', TS_8b_Gray);
}

// Same rules as random_combo() in pc/game_logic.py: never 3 of the same in a row; round 1 = all different,
// later 3-spell rounds must repeat a spell (e.g. WFW)
bool comboOk(const char *c, uint8_t n, bool mixed) {
  for (uint8_t k = 2; k < n; k++) if (c[k] == c[k - 1] && c[k] == c[k - 2]) return false;
  bool allDifferent = (n == 3 && c[0] != c[1] && c[1] != c[2] && c[0] != c[2]);
  if (n == 3) return mixed ? !allDifferent : allDifferent;
  return true;
}

// K: GO! record up to comboLen spells
void startComboInput() {
  castCount = 0;
  castStr[0] = 0;
  promptUs = micros();
  inputStartMs = millis();
  inGesture = false;                  // start fresh from GO
  lastGestureEndMs = millis() - GESTURE_GAP_MS;
  state = ST_PROMPT;
  display.clearScreen();
  char t[12];
  sprintf(t, "GO!  0/%d", comboLen);
  drawComboTitle(t, TS_8b_Green);
  for (uint8_t k = 0; k < comboLen; k++) drawComboSlot(k, ' ', TS_8b_White);
  beep(2200, 80);
}

// Offline practice: show how many were right, then the next round
void practiceScore() {
  uint8_t right = 0;
  for (uint8_t k = 0; k < comboLen; k++) if (k < castCount && castStr[k] == comboStr[k]) right++;
  char t[16];
  sprintf(t, "%d/%d RIGHT", right, comboLen);
  drawComboTitle(t, right == comboLen ? TS_8b_Green : TS_8b_White);
  for (uint8_t k = 0; k < comboLen; k++)
    drawComboSlot(k, comboStr[k], (k < castCount && castStr[k] == comboStr[k]) ? TS_8b_Green : TS_8b_Red);
  centerText("(right answer)", 50, liberationSans_8ptFontInfo, TS_8b_Gray, TS_8b_Black);
  beep(right == comboLen ? 2000 : 300, 120);
  practiceRound++;
  state = ST_BEAM;
  nextComboMs = millis() + 2800;
}

// =====================================================================
//  Motion detectors
// =====================================================================
// Air-drum style hit: a spike above HIT_THRESHOLD_G, peak found within 25 ms.
// Returns true once per hit with its start time and gesture (S = down, H = side).
bool hitDetector(float dx, float dy, float dz, uint32_t nowMs, uint32_t *tHit, char *g) {
  float mag = sqrtf(dx * dx + dy * dy + dz * dz);
  if (!inHit) {
    if (mag > HIT_THRESHOLD_G && nowMs - lastHitMs > HIT_REFRACTORY_MS) {
      inHit = true; hitStartMs = nowMs;
      peakX = dx; peakY = dy; peakZ = dz; peakMag = mag;
      startX = dx; startY = dy; startZ = dz;
    }
    return false;
  }
  if (mag > peakMag) { peakX = dx; peakY = dy; peakZ = dz; peakMag = mag; }
  if (nowMs - hitStartMs < 25) return false;          // 25 ms to find the peak
  inHit = false;
  lastHitMs = hitStartMs;
  // Which axis: the bigger one at the peak. Which way: the sign when the flick STARTED (the peak can be
  // the wrist stopping the wand, which pushes the other way).
  float pu = axisVal(SNARE_AXIS, peakX, peakY, peakZ), ps = axisVal(HIHAT_AXIS, peakX, peakY, peakZ);
  bool vertical = absf(pu) >= absf(ps);
  float on = axisVal(vertical ? SNARE_AXIS : HIHAT_AXIS, startX, startY, startZ);
  float v = absf(on) > 0.3f ? on : (vertical ? pu : ps);
  *tHit = hitStartMs;
  if (vertical) *g = (v * DRUM_UP_SIGN > 0) ? 'U' : 'D';
  else          *g = (v * DRUM_RIGHT_SIGN > 0) ? 'R' : 'L';
  return true;
}

// Count "lobes": pushes above LOBE_G that alternate direction on one axis.
void addLobe(uint8_t a, float v) {
  if (v > LOBE_G && lobeSign[a] != 1)       { lobeSign[a] = 1;  lobeCount[a]++; }
  else if (v < -LOBE_G && lobeSign[a] != -1) { lobeSign[a] = -1; lobeCount[a]++; }
}

char classifySpell() {
  float eS = gEnergy[0], eU = gEnergy[1], eF = gEnergy[2];
  float eTot = eS + eU + eF + 0.0001f;
  char s = '?';
  if (gPeak[2] >= THRUST_G && eF > 0.45f * eTot) s = 'F';                        // one hard push forward
  else if (lobeCount[0] >= CIRCLE_LOBES && lobeCount[1] >= CIRCLE_LOBES &&
           eS > 0.25f * eTot && eU > 0.25f * eTot) s = 'W';                       // side AND up-down = circle
  else if (lobeCount[0] >= ZIGZAG_LOBES && eS > 0.55f * eTot) s = 'L';            // many left-right pushes
#if SPELL_DEBUG
  if (SerialMonitorInterface) {         // never blocks: only prints when the Serial Monitor is open
    SerialMonitorInterface.print("gesture ms="); SerialMonitorInterface.print(gLastMotionMs - gStartMs);
    SerialMonitorInterface.print(" lobes side="); SerialMonitorInterface.print(lobeCount[0]);
    SerialMonitorInterface.print(" up="); SerialMonitorInterface.print(lobeCount[1]);
    SerialMonitorInterface.print(" fwd="); SerialMonitorInterface.print(lobeCount[2]);
    SerialMonitorInterface.print(" | energy% side="); SerialMonitorInterface.print((int)(100 * eS / eTot));
    SerialMonitorInterface.print(" up="); SerialMonitorInterface.print((int)(100 * eU / eTot));
    SerialMonitorInterface.print(" fwd="); SerialMonitorInterface.print((int)(100 * eF / eTot));
    SerialMonitorInterface.print(" | peak fwd="); SerialMonitorInterface.print(gPeak[2]);
    SerialMonitorInterface.print(" -> "); SerialMonitorInterface.println(s);
  }
#endif
  return s;
}

// After a FIZZLE: which spell was the move closest to? Each rule is scored 0..1 (1 = it would have passed).
static inline float part(float have, float need) { return have >= need ? 1.0f : (have <= 0 ? 0 : have / need); }
char closestSpell() {
  float eTot = gEnergy[0] + gEnergy[1] + gEnergy[2] + 0.0001f;
  float sS = gEnergy[0] / eTot, sU = gEnergy[1] / eTot, sF = gEnergy[2] / eTot;
  float fire  = part(gPeak[2], THRUST_G) * part(sF, 0.45f);
  float water = part(lobeCount[0], CIRCLE_LOBES) * part(lobeCount[1], CIRCLE_LOBES) * part(sS, 0.25f) * part(sU, 0.25f);
  float light = part(lobeCount[0], ZIGZAG_LOBES) * part(sS, 0.55f);
  if (fire >= water && fire >= light) return 'F';
  return water >= light ? 'W' : 'L';
}

// Records one gesture (motion start -> 150 ms of quiet) and classifies it.
// Returns 'L' / 'W' / 'F' / '?' when a gesture ends, 0 while nothing finished.
char spellDetector(float dx, float dy, float dz, uint32_t nowMs) {
  float v[3] = {axisVal(SIDE_AXIS, dx, dy, dz), axisVal(UPDOWN_AXIS, dx, dy, dz), axisVal(FORWARD_AXIS, dx, dy, dz)};
  float mag = sqrtf(dx * dx + dy * dy + dz * dz);
  if (!inGesture) {
    if (mag <= GESTURE_START_G || nowMs - lastGestureEndMs < GESTURE_GAP_MS) return 0;
    inGesture = true;
    gStartMs = gLastMotionMs = nowMs;
    gLastMotionUs = micros();
    for (uint8_t a = 0; a < 3; a++) { lobeCount[a] = 0; lobeSign[a] = 0; gEnergy[a] = 0; gPeak[a] = 0; }
  }
  for (uint8_t a = 0; a < 3; a++) {
    addLobe(a, v[a]);
    gEnergy[a] += v[a] * v[a];
    if (absf(v[a]) > gPeak[a]) gPeak[a] = absf(v[a]);
  }
  if (mag > GESTURE_END_G) { gLastMotionMs = nowMs; gLastMotionUs = micros(); }
  if (nowMs - gLastMotionMs < GESTURE_QUIET_MS && nowMs - gStartMs < GESTURE_MAX_MS) return 0;
  inGesture = false;
  lastGestureEndMs = nowMs;
  if (gLastMotionMs - gStartMs < GESTURE_MIN_MS) { fizzleWhy = 's'; return '?'; }
  char s = classifySpell();
  if (s == '?') fizzleWhy = closestSpell();
  return s;
}

// =====================================================================
//  Judging
// =====================================================================
// Level 1: judge an air-drum hit (arrow U/D/L/R) against this board's own beat grid
void judgeHit(uint32_t tHit, char gesture) {
  int32_t rel = (int32_t)(tHit - drumT0);
  int32_t half = beatMs / 2;
  int32_t k = (rel >= -half) ? (rel + half) / (int32_t)beatMs : -1;
  if (k < 0 || k >= roundBeats) return;               // outside this round's beats
  int32_t err = rel - k * (int32_t)beatMs;
  // A second spike on a beat we already loaded = the wrist bouncing back after the hit.
  // Ignore it completely (no MISS, no packet) so it can't turn a good hit red on the arena.
  if (beatHit[k] && absf((float)err) <= HIT_WINDOW_MS + 100) return;
  bool ok = (absf((float)err) <= HIT_WINDOW_MS) && pattern[k] == gesture && !beatHit[k];
  if (ok) {
    beatHit[k] = true;
    if (bullets < MAX_BULLETS) bullets++;
    feedback = (absf((float)err) <= PERFECT_MS) ? 2 : 1;   // PERFECT / GOOD (v5.7)
    beep(gesture == 'U' ? 1600 : (gesture == 'D' ? 1000 : (gesture == 'L' ? 2400 : 3200)), 25);
  } else {
    feedback = -1;
  }
  char msg[20];
  sprintf(msg, "H%ld%c%d%+ld", (long)k, gesture, ok ? 1 : 0, (long)err);
  bleSend(msg);
  needRedraw = true;
}

// Level 2: is the wand pointing at the sky and (roughly) still?
// Uses the raw accelerometer, lightly smoothed, so it reacts at once (no waiting for the slow
// gravity estimate) and a trembling hand still counts: total ~1 g = not swinging, mostly along the wand = up.
bool inChargePose() {
  float up = axisVal(FORWARD_AXIS, pfx, pfy, pfz) * CHARGE_UP_SIGN;
  float mag = sqrtf(pfx * pfx + pfy * pfy + pfz * pfz);
  return up >= CHARGE_TILT_G && absf(mag - 1.0f) < CHARGE_STILL_G;
}

// Level 2: every CHARGE_MS in the charge pose = +1 mana
void addMana() {
  lastActivityMs = millis();
  if (mana < MAX_MANA) mana++;
  char msg[8];
  sprintf(msg, "A%d", mana);
  bleSend(msg);
  beep(1400, 40);
  setStatus(mana >= MAX_MANA ? "MANA FULL" : "+MANA", TS_8b_Blue, 400);
}

// Level 2: a gesture was recognised
void onSpellGesture(char s, uint32_t nowMs) {
  lastActivityMs = nowMs;
  if (s == '?') {
    if (nowMs - chargeEndMs < 800) return;          // just lowering the wand after charging: not a spell
    setStatus("FIZZLE", TS_8b_Gray, 700);
    hintUntilMs = nowMs + 1500;                        // bottom line: "thrust harder!" etc.
    char f[4] = {'f', fizzleWhy ? fizzleWhy : 's', 0, 0};
    bleSend(f);                                        // the arena shows the hint too
    return;
  }
  if (offlineMode || warmup) {       // practice / warm-up: unlimited mana, no cooldown
    spellBeep(s);
    setStatus(spellName(s), spellColor(s), 900);
    if (warmup) { char m[4] = {'C', s, '0', 0}; bleSend(m); }
    return;
  }
  if (mana == 0) { setStatus("NO MANA", TS_8b_DarkRed, 600); beep(150, 80); return; }
  if (castOnce && nowMs - lastCastMs < CAST_COOLDOWN_MS) { setStatus("wait...", TS_8b_Gray, 400); return; }
  mana--;
  lastCastMs = nowMs;
  castOnce = true;
  char msg[8];
  sprintf(msg, "C%c%d", s, mana);
  bleSend(msg);
  spellBeep(s);
  setStatus(spellName(s), spellColor(s), 900);
}

// Level 3: one spell of the combo (time = end of the gesture since GO arrived)
void comboCast(char s) {
  if (castCount >= comboLen) return;
  uint32_t us = gLastMotionUs - promptUs;
  if ((int32_t)us < 0) us = 0;
  castStr[castCount] = s;
  castStr[castCount + 1] = 0;
  drawComboSlot(castCount, s, TS_8b_White);
  castCount++;
  char msg[20];
  sprintf(msg, "X%c%lu", s, (unsigned long)us);
  bleSend(msg);
  spellBeep(s);
  char t[12];
  if (castCount >= comboLen) strcpy(t, "DONE!");
  else sprintf(t, "GO!  %d/%d", castCount, comboLen);
  drawComboTitle(t, castCount >= comboLen ? TS_8b_Yellow : TS_8b_Green);
}

// =====================================================================
//  Sensor processing — called every 2 ms
// =====================================================================
void processSample() {
  accel.read();
  if (accel.X == -1 && accel.Y == -1 && accel.Z == -1) { accelOk = false; return; }
  accelOk = true;
  ax = accel.X / LSB_PER_G;
  ay = accel.Y / LSB_PER_G;
  az = accel.Z / LSB_PER_G;
  uint32_t nowMs = millis();

  // gravity estimate (frozen during a hit / gesture so spikes don't pollute it)
  if (!inHit && !inGesture && nowMs - lastHitMs > 100) {
    gx += (ax - gx) * 0.02f; gy += (ay - gy) * 0.02f; gz += (az - gz) * 0.02f;
  }
  float dx = ax - gx, dy = ay - gy, dz = az - gz;    // motion without gravity

  if (accelDebug && state == ST_LOBBY) {
    static uint32_t lastPrint = 0;
    if (nowMs - lastPrint > 50) {
      lastPrint = nowMs;
      SerialMonitorInterface.print(ax); SerialMonitorInterface.print('\t');
      SerialMonitorInterface.print(ay); SerialMonitorInterface.print('\t');
      SerialMonitorInterface.println(az);
    }
  }

  switch (state) {
    case ST_AIR_DRUM: {
      uint32_t tHit; char g;
      if (hitDetector(dx, dy, dz, nowMs, &tHit, &g)) judgeHit(tHit, g);
      break;
    }
    case ST_STANDOFF: {
      if (!refReady) {                                // learn holster pose (300 ms)
        refSumX += ax; refSumY += ay; refSumZ += az; refCount++;
        if (nowMs - stateStartMs >= 300) {
          refX = refSumX / refCount; refY = refSumY / refCount; refZ = refSumZ / refCount;
          refReady = true;
        }
      } else {
        float ex = ax - refX, ey = ay - refY, ez = az - refZ;
        float moved = sqrtf(ex * ex + ey * ey + ez * ez);
        if (tutStill) {                                // tutorial: report how still you are, never foul
          if (moved > stillPeak) stillPeak = moved;
          if (nowMs - lastStillSendMs >= 100) {
            int n = (int)(stillPeak * 10.0f / FOUL_THRESHOLD_G + 0.5f);   // 10 = the foul line
            char msg[6];
            sprintf(msg, "s%d", n > 20 ? 20 : n);
            bleSend(msg);
            stillPeak = 0;
            lastStillSendMs = nowMs;
          }
        } else if (moved > FOUL_THRESHOLD_G) {
          bleSend("F");
          showResult('F', 0);
        }
      }
      break;
    }
    case ST_DRAW_ACTIVE: {
      float ex = ax - refX, ey = ay - refY, ez = az - refZ;
      if (sqrtf(ex * ex + ey * ey + ez * ez) > DRAW_THRESHOLD_G) {
        drawUs = micros() - cueUs;
        char msg[20];
        sprintf(msg, "T%lu", (unsigned long)drawUs);
        bleSend(msg);
        if (offlineMode) {
          showResult('P', drawUs / 1000);
        } else {
          state = ST_RESULT;                          // wait for laptop verdict
          stateStartMs = nowMs;
          display.clearScreen();
          char s[12];
          sprintf(s, "%lu ms", (unsigned long)(drawUs / 1000));
          centerText("BANG!", 10, liberationSans_14ptFontInfo, TS_8b_Yellow, TS_8b_Black);
          centerText(s, 40, liberationSans_10ptFontInfo, TS_8b_White, TS_8b_Black);
        }
      } else if (micros() - cueUs > (uint32_t)DRAW_TIMEOUT_MS * 1000UL) {
        bleSend("N");
        if (offlineMode) showResult('P', -1);
        else {
          state = ST_RESULT; stateStartMs = nowMs;
          display.clearScreen();
          centerText("TOO SLOW", 24, liberationSans_10ptFontInfo, TS_8b_Red, TS_8b_Black);
        }
      }
      break;
    }
    case ST_SPELL: {
      // 1) charge pose: wand pointing at the sky -> +1 mana every CHARGE_MS
      pfx += (ax - pfx) * 0.1f; pfy += (ay - pfy) * 0.1f; pfz += (az - pfz) * 0.1f;   // ~20 ms smoothing
      bool pose = inChargePose();
      if (pose) {
        if (!poseRunStart) poseRunStart = nowMs;
        lastPoseMs = nowMs;
      } else {
        poseRunStart = 0;
      }
      if (pose && nowMs - poseRunStart >= CHARGE_SETTLE_MS) {
        if (inGesture) { inGesture = false; lastGestureEndMs = nowMs; }   // that "gesture" was the raise
        if (!charging) {
          charging = true; needRedraw = true;
          beep(900, 15);                                  // tick: charge started
        } else {
          chargeAccum += nowMs - chargeTickMs;            // only time IN the pose counts
          if (chargeAccum >= CHARGE_MS) { chargeAccum -= CHARGE_MS; addMana(); }
          if (mana >= MAX_MANA && !offlineMode) chargeAccum = 0;
        }
        chargeTickMs = nowMs;
      } else if (charging) {
        chargeTickMs = nowMs;                             // pause, don't count the wobble
        if (nowMs - lastPoseMs > CHARGE_GRACE_MS) {       // really left the pose
          charging = false; chargeAccum = 0; chargeEndMs = nowMs; needRedraw = true;
        }
      }
      if (charging) break;                                // no spells while charging
      // 2) spells: a gesture that ends with the wand pointing up was just raising it to charge
      char s = spellDetector(dx, dy, dz, nowMs);
      if (s) {
        float up = axisVal(FORWARD_AXIS, ax, ay, az) * CHARGE_UP_SIGN;
        if (up >= CHARGE_TILT_G) s = 0;
      }
      if (s) onSpellGesture(s, nowMs);
      break;
    }
    case ST_TUT_ARROWS: {                           // L1 tutorial: report every flick right away
      uint32_t tHit; char g;
      if (hitDetector(dx, dy, dz, nowMs, &tHit, &g)) {
        char msg[4] = {'d', g, 0, 0};
        bleSend(msg);
        lastArrow = g;
        beep(g == 'U' ? 1600 : (g == 'D' ? 1000 : (g == 'L' ? 2400 : 3200)), 25);
        needRedraw = true;
      }
      break;
    }
    case ST_PROMPT: {
      char s = spellDetector(dx, dy, dz, nowMs);
      if (s && s != '?') comboCast(s);
      else if (s == '?' && castCount < comboLen) {
        display.drawRect(0, 50, 96, 14, TSRectangleFilled, TS_8b_Black);
        centerText(fizzleHint(fizzleWhy), 50, liberationSans_8ptFontInfo, TS_8b_Gray, TS_8b_Black);
        char f[4] = {'f', fizzleWhy ? fizzleWhy : 's', 0, 0};
        bleSend(f);
      }
      break;
    }
    default: break;
  }
}

// =====================================================================
//  Commands from the laptop
// =====================================================================
void handleCommand(char *cmd, uint8_t len) {
  if (len == 0) return;
  offlineMode = false;
  switch (cmd[0]) {
    case 'P': bleSend("Q"); break;                         // ping -> pong
    case 'V': {
      char v[20];
      sprintf(v, "V%s,BDS-%d,%d,%c", FIRMWARE_VERSION, PLAYER_ID, USE_BUZZER, resetCause);
      bleSend(v);
      updateBattery(millis(), true);                       // and the battery level right away
      break;
    }
    case 'L': goLobby(); break;
    case 'w': startWarmup(); break;                        // Level 2 warm-up (free spells)
    case 'O':                                              // Level 1 tutorial: O1 = free arrows, O3 = holster practice
      if (cmd[1] == '1') {
        state = ST_TUT_ARROWS; lastArrow = 0; inHit = false; lastHitMs = 0; needRedraw = true;
      } else if (cmd[1] == '3') {
        startStandoff();
        tutStill = true; stillPeak = 0; lastStillSendMs = millis();
        drawStandoff();
      }
      break;
    case 'R': {                                            // v5.7: R090U-DU--D-UD--U-D-  (3-digit bpm + arrows)
      char *comma = strchr(cmd, ',');                      // (old format R120,UDL-RDU- still works)
      if (comma) {
        startDrum(atoi(cmd + 1), comma + 1);
      } else if (len >= 5) {
        char b[4] = {cmd[1], cmd[2], cmd[3], '\0'};
        startDrum(atoi(b), cmd + 4);
      }
      break;
    }
    case 'W': startStandoff(); break;
    case 'G': drawCue(); break;
    case 'E': if (len >= 2) showResult(cmd[1], atol(cmd + 2)); break;
    case 'M': {                                            // M2,120,6,5  or  M3,60
      if (cmd[1] == '2') {
        int bpm = 120, hp = 5, opp = 5;
        sscanf(cmd + 3, "%d,%d,%d", &bpm, &hp, &opp);
        startSpellLevel(bpm, hp, opp, false);
      } else if (cmd[1] == '3') {
        startBeamLevel(atoi(cmd + 3), false);
      }
      break;
    }
    case 'U': {                                            // U5,4,H  (my hp, rival hp, event)
      int hp = myHp, opp = oppHp;
      char ev = '-';
      sscanf(cmd + 1, "%d,%d,%c", &hp, &opp, &ev);
      myHp = hp; oppHp = opp;
      if (ev == 'H')      { setStatus("OUCH!", TS_8b_Red, 700); beep(200, 150); }
      else if (ev == 'D') { setStatus("HIT THEM!", TS_8b_Green, 700); beep(1600, 60); }
      else if (ev == 'B') { setStatus("BLOCKED!", TS_8b_White, 700); beep(2000, 60); }
      needRedraw = true;
      break;
    }
    case 'I':                                              // IF = fire is flying at you
      incomingSpell = cmd[1];
      incomingUntilMs = millis() + 2000;           // = SPELL_TRAVEL_S in game_logic.py
      beep(3200, 30);
      needRedraw = true;
      break;
    case 'b': {                                            // b62 = beam position (100 = I win)
      int p = atoi(cmd + 1);
      myPos = constrain(p, 0, 100);
      if (state == ST_BEAM) {
        drawBeamBar();
        beep(300 + (100 - myPos) * 25, 60);                // higher pitch = beam closer to you
      }
      break;
    }
    case 'Z': {                                            // ZFLW8 = Fire, Lightning, Water, 0.8 s each (3-5 spells)
      uint8_t n = 0;
      while (n < MAX_COMBO && (cmd[1 + n] == 'L' || cmd[1 + n] == 'W' || cmd[1 + n] == 'F')) n++;
      if (n >= 1) startComboShow(cmd + 1, (1 + n < len && cmd[1 + n] >= '0' && cmd[1 + n] <= '9') ? (cmd[1 + n] - '0') * 100 : 800);
      break;
    }
    case 'K': if (state == ST_COMBO_SHOW || state == ST_BEAM) startComboInput(); break;   // GO!
    case 'J':                                              // round over: back to the beam bar
      if (state == ST_PROMPT || state == ST_COMBO_SHOW) { state = ST_BEAM; drawBeamScreen(); }
      break;
    case 'Y': if (len >= 3) showLevelResult(cmd[1], cmd[2] - '0'); break;   // YW3
    default: break;
  }
}

// =====================================================================
//  Arduino setup / loop
// =====================================================================
void setup() {
  resetCause = readResetCause();    // read first: why did we (re)start?
  SerialMonitorInterface.begin(115200);
  // NOTE: no "while(!SerialMonitorInterface)" here — that line from the
  // TinyCircuits example freezes the board when it runs on battery!
  Wire.begin();
#if USE_BUZZER
  Wireling.begin();                 // powers the Wireling ports
  pinMode(BUZZER_PIN, OUTPUT);
#endif
  display.begin();
  display.setBrightness(12);
  display.setFlip(false);
  accelOk = (accel.begin(BMA250_range_8g, BMA250_update_time_2ms) == 0);
  BLEsetup();
  randomSeed(analogRead(A1) ^ micros());
  updateBattery(millis(), true);
  drawLobby();
#if USE_WATCHDOG
  wdtInit();                        // from now on loop() must run at least every 2 s
#endif
}

void loop() {
  wdtFeed();                        // watchdog: a hang anywhere below restarts the wand after 2 s
  aci_loop();                       // keep Bluetooth alive — must run often

  if (ble_rx_buffer_len) {
    char cmd[21];
    uint8_t n = ble_rx_buffer_len > 20 ? 20 : ble_rx_buffer_len;
    memcpy(cmd, ble_rx_buffer, n);
    cmd[n] = '\0';
    ble_rx_buffer_len = 0;
    handleCommand(cmd, n);
  }

  uint32_t nowUs = micros();
  if (nowUs - lastSampleUs >= SAMPLE_PERIOD_US) {
    lastSampleUs = nowUs;
    processSample();
  }

  uint32_t now = millis();
  updateBattery(now, false);
  // Laptop disconnected in the middle of an online round -> back to lobby
  if (!offlineMode && state != ST_LOBBY && !ble_connection_state) goLobby();

  buttonsNow = display.getButtons();
  uint8_t pressed = buttonsNow & ~lastButtons;
  lastButtons = buttonsNow;

  switch (state) {
    case ST_LOBBY:
      if (lastConnState != ble_connection_state) {
        lastConnState = ble_connection_state;
        drawLobby();
      }
      if (pressed & TSButtonLowerRight) {
        accelDebug = !accelDebug;   // stream X/Y/Z to Serial Monitor for tuning
      } else if (pressed && !ble_connection_state) {
        randomSeed(micros());
        if (pressed & TSButtonUpperRight)     startSpellLevel(120, 5, 5, true);   // spell practice
        else if (pressed & TSButtonLowerLeft) startBeamLevel(50, true);           // combo practice
        else { offlineMode = true; startDrum(90, "U-DU--L-UD--R-D-"); }          // cowboy practice: all 4 arrows
      }
      break;

    case ST_AIR_DRUM: {
      int32_t rel = (int32_t)(now - drumT0);
      int8_t countIn = 0, beat = -1;
      if (rel < 0) countIn = (-rel + beatMs - 1) / beatMs;   // 4,3,2,1
      else beat = rel / beatMs;
      int8_t key = (countIn > 0) ? -countIn : beat;
      if (key != lastBeatShown) {                      // a new beat started
        lastBeatShown = key;
        if (countIn > 0) beep(900, 40);
        else if (beat < roundBeats) { feedback = 0; beep(600, 15); }
        needRedraw = true;
      }
      if (needRedraw) {
        needRedraw = false;
        drawDrumScreen(beat, countIn);
      }
      if (rel > (int32_t)(roundBeats * beatMs + HIT_WINDOW_MS)) {
        char msg[8];
        sprintf(msg, "B%d", bullets);
        bleSend(msg);
        state = ST_HOLSTER;
        stateStartMs = now;
        drawHolster();
      }
      break;
    }

    case ST_HOLSTER:
      // Online: the laptop sends "W" when the standoff starts.
      if (offlineMode && now - stateStartMs > 1500) {
        startStandoff();
        standoffDelayMs = random(1500, 4500);
      }
      break;

    case ST_STANDOFF:
      if (offlineMode && now - stateStartMs > standoffDelayMs) drawCue();
      break;

    case ST_INTRO: {
      if ((int32_t)(now - introUntilMs) >= 0) { enterIntroNext(); break; }
      int8_t secs = (introUntilMs - now + 999) / 1000;
      if (secs != introShown) { introShown = secs; drawIntro(introLevel, secs); }
      break;
    }

    case ST_SPELL: {
      if (charging) lastActivityMs = now;
      if (statusUntilMs && now >= statusUntilMs) { statusUntilMs = 0; needRedraw = true; }
      if (incomingUntilMs && now >= incomingUntilMs) { incomingUntilMs = 0; needRedraw = true; }
      if (hintUntilMs && now >= hintUntilMs) { hintUntilMs = 0; needRedraw = true; }
      if (needRedraw && !inGesture && !inHit) {        // never redraw in the middle of a move
        needRedraw = false;
        drawSpellScreen();
        if (charging) drawChargeBar();
      } else if (charging && now - lastChargeDrawMs > 80) {
        lastChargeDrawMs = now;
        drawChargeBar();
      }
      if (offlineMode && now - lastActivityMs > 30000) { goLobby(); }   // practice auto-exit
      break;
    }

    case ST_BEAM:                                          // offline practice drives its own rounds
      if (offlineMode && (int32_t)(now - nextComboMs) >= 0) {
        if (practiceRound >= 5) {
          state = ST_RESULT; stateStartMs = now;
          display.clearScreen();
          centerText("PRACTICE", 10, liberationSans_10ptFontInfo, TS_8b_Yellow, TS_8b_Black);
          centerText("done!", 28, liberationSans_10ptFontInfo, TS_8b_White, TS_8b_Black);
          centerText("Btn = lobby", 52, liberationSans_8ptFontInfo, TS_8b_Gray, TS_8b_Black);
        } else {
          // practice like the real thing: round 1 = 3 different spells, then repeats allowed, round 5 = 5 spells
          char c[MAX_COMBO + 1];
          uint8_t n = practiceRound >= 4 ? 5 : 3;
          do {
            for (uint8_t k = 0; k < n; k++) c[k] = "LWF"[random(0, 3)];
            c[n] = 0;
          } while (!comboOk(c, n, practiceRound > 0));
          startComboShow(c, n > 3 ? 700 : 800);
        }
      }
      break;

    case ST_COMBO_SHOW: {                                  // reveal the combo one spell at a time
      int32_t k = (int32_t)(now - showStartMs) / (int32_t)flashMs;
      if (k != shownK) {
        if (shownK >= 0 && shownK < comboLen) drawComboSlot(shownK, '?', TS_8b_Gray);   // hide the previous one
        shownK = k;
        if (k < comboLen) { drawComboSlot(k, comboStr[k], TS_8b_White); spellBeep(comboStr[k]); }
        else if (k == comboLen) drawComboTitle("WAIT...", TS_8b_White);
      }
      if (offlineMode && now - showStartMs >= (uint32_t)comboLen * flashMs + 2000) startComboInput();
      break;
    }

    case ST_PROMPT:
      if (offlineMode && (castCount >= comboLen || now - inputStartMs > 4000UL + 1500UL * comboLen)) practiceScore();
      break;

    case ST_RESULT:
      if (offlineMode && pressed && now - stateStartMs > 500) goLobby();
      break;

    case ST_TUT_ARROWS:
      if (needRedraw && !inHit) { needRedraw = false; drawTutArrows(); }
      break;

    default: break;
  }
}
