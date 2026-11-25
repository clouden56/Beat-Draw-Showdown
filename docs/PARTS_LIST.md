# Parts List — Beat-Draw Showdown

Levels 2 and 3 (Spellcaster, Combo Clash) need **no extra parts** — the accelerometer does all the gesture detection.

## A. From your 6 base kits (no loan needed)
| Part | Code | Use | Qty |
|---|---|---|---|
| TinyScreen+ | ASM2022 | Brain + OLED "scope" + buttons | 2 in play + 2 spare (+2 for dev) |
| Accelerometer TinyShield | ASD2511-R-A | Air-drum hits, draw flick, spell gestures, charge pose | same as above |
| ST BLE TinyShield | ASD2116-R | Talk to the laptop (Bluetooth, no Wi-Fi needed) | same as above |
| 150 mAh Li-Po battery | ASR0003 | Wireless play | 2 + spares |

Use the 4 extra kits as: 2 hot spares on demo day (flash them as BDS-3/BDS-4), 2 for teammates coding in parallel.

## B. Loan parts — only for the buzzer option (`USE_BUZZER 1`)
| Part | SN / Code | Use | Qty |
|---|---|---|---|
| Wireling Adapter TinyShield | SN 24 / ASD2022 | Plug Wirelings into the stack | 2 |
| Buzzer Wireling | SN 15 / AST1035 | Beeps on the wand (count-in, spells, beam pitch) | 2 |
| Wireling cable (usually included) | — | Connect buzzer to adapter port 0 | 2 |

SN 24 is the most fought-over loan item. If you can't get it, use laptop audio (`USE_BUZZER 0`) — the game is complete without it.

## C. Other things you need
| Item | Why |
|---|---|
| Windows laptop with Bluetooth 4.0+ | Runs `arena_referee.py` |
| Micro-USB **data** cables ×2 | Uploading firmware (charge-only cables won't work) |
| Speaker (optional) | Louder DRAW! for the live demo |
| 3D printer filament (PLA) ~60–80 g | 2 revolver grips + test prints |
| M2 screws or double-sided foam tape | Hold the stack in the grip |
| 2 cowboy hats + 2 wizard hats (optional, cheap) | YouTube video vibes — swap hats between levels |
| Wrist straps ×2 | Snaps, draws and spells are fast moves; stops flying wands |

## D. Optional extras (only if they're still on the shelf)
| Part | SN | Idea |
|---|---|---|
| Hall Sensor Wireling + magnet | SN 8/9 | Magnetic belt holster check |
| Servo TinyShield + Servo | SN 29/30 | Physical target that falls over |
| Microphone Wireling | SN 4 | Shout the spell name for a bonus push in Level 3 |
| Large Button Wireling | SN 11 | Real trigger for the Level 1 quick-draw |
