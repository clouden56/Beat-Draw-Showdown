# 3D Printing Plan — the wand

The same print is used for all 3 levels (revolver in Level 1, magic wand in Levels 2–3).

## What to print (per player)
* **Grip body** ~140 mm long × 35 mm wide, hollow.
* **Top window** about 16 × 12 mm so the OLED faces the player like a gun scope (the 0.6" OLED's visible area is roughly 13 × 9 mm — measure yours with calipers).
* **Button slots** on both sides — TinyScreen+ has 2 buttons on each side.
* **Battery bay** under the stack for the 150 mAh LiPo.
* **USB slot** or a **slide-off back lid** so you can re-upload code.
* **Lanyard hole** at the bottom — people swing hard on the draw and the spells; a wrist strap stops flying wands.
* **Battery clip or foam** so the LiPo cannot rattle loose (a loose battery = random disconnects).

## Step by step
1. **Measure** your stack (TinyScreen+ + BLE + accel [+ Wireling adapter]) with calipers — height changes with each shield. Add 0.4 mm clearance each side.
2. **Model in Tinkercad** (free, browser): start with a box, add a cylinder "barrel", subtract (hole) the stack cavity, window, button slots, USB slot. Export **STL**.
   *Shortcut:* search Thingiverse/Printables for "TinyScreen+ case" and remix a case into a handle. Credit the original designer in CODE_ATTRIBUTION.md.
3. **Slice in UltiMaker Cura** — pick your lab's printer (ask the technician).
   * Layer height 0.2 mm · Infill 20–30 % (gyroid) · Supports ON for overhangs · Brim ON.
4. **Test print one** first (aim < 2 h). Check fit, buttons, window, battery.
5. Fix the model, then print the second one.
6. **Mount:** foam tape or M2 screws. Make sure the board can't rotate — the accelerometer axes must stay fixed relative to the grip.
7. After mounting, re-check `SNARE_AXIS` / `HIHAT_AXIS` / `FORWARD_AXIS` with the accel debug mode (axes change with orientation!), then re-test the spells in spell practice and combo practice.

## Tips
* Print the grip in two halves (left/right) if supports get messy.
* Different colours for P1 (red/orange) and P2 (blue) — matches the arena screen.
* Bring spare tape on demo day.
* Glue or screw the lid shut for the demo — a press-fit lid can pop open on a hard draw.
