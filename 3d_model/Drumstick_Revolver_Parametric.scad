// ============================================================================
// Beat-Draw Showdown: Parametric "Drumstick Revolver" 3D Print Model (OpenSCAD)
// Units: millimeters (mm)
// Fits: TinyScreen+ (ASM2022) + ST BLE (ASD2116-R) + Accel (ASD2511-R-A)
//       + 150mAh LiPo Battery (+ optional Wireling Adapter ASD2022)
// ============================================================================

$fn = 48;

// --- Editable Tolerances (tweak if your printer runs tight) ---
pcb_width_x       = 27.0;  // 25.8mm TinyScreen+ PCB + 1.2mm total clearance
pcb_length_y      = 26.2;  // 25.0mm TinyScreen+ PCB + 1.2mm total clearance
cavity_depth_z    = 22.7;  // Fits 3-to-4 board stack + 150mAh LiPo battery
oled_win_x        = 21.6;  // Visible 96x64 OLED active area window width
oled_win_y        = 15.2;  // Visible 96x64 OLED active area window height
top_bezel_z       = 1.8;   // Lip thickness holding TinyScreen+ top face

module rounded_box(sx, sy, sz, r) {
    hull() {
        for (dx = [-sx/2 + r, sx/2 - r])
            for (dy = [-sy/2 + r, sy/2 - r])
                translate([dx, dy, 0])
                    cylinder(r=r, h=sz, center=false);
    }
}

module revolver_body() {
    difference() {
        union() {
            // 1. Scope Head Housing (Y = +12 to +52 mm)
            translate([0, 32, 0])
                rounded_box(35.0, 40.0, 28.0, 3.0);
            
            // 2. Ergonomic Drumstick Grip (Y = -65 to +16 mm)
            translate([0, -24.5, 0])
                rounded_box(27.0, 81.0, 24.0, 4.5);
            
            // 3. Flared Revolver Pommel (Y = -70 to -56 mm)
            translate([0, -63.0, 0])
                rounded_box(32.0, 14.0, 24.0, 3.5);
            
            // 4. Revolver Barrel Nose & Front Sight (Y = +50 to +68 mm)
            translate([0, 50.0, 15.0])
                rotate([-90, 0, 0])
                    cylinder(r=9.0, h=18.0);
            translate([-2.0, 59.0, 22.0])
                cube([4.0, 8.0, 5.0]);
        }

        // A. TinyScreen+ Stack & Battery Cavity (loads from bottom)
        translate([-pcb_width_x/2, 32 - pcb_length_y/2, 0.0])
            cube([pcb_width_x, pcb_length_y, 28.0 - top_bezel_z]);

        // B. Slide-On Lid Grooves near bottom (Z = 0.7 to 2.9 mm)
        translate([-14.8, 7.5, 0.7])
            cube([29.6, 45.0, 2.2]);
        translate([-13.5, 7.5, -0.1])
            cube([27.0, 45.0, 1.5]);

        // C. Top OLED Scope Window
        translate([-oled_win_x/2, 32 - oled_win_y/2, 25.0])
            cube([oled_win_x, oled_win_y, 6.0]);

        // D. Left & Right Button + Power Switch Cutouts
        translate([-20.0, 21.0, 17.0])
            cube([40.0, 22.0, 8.4]);

        // E. Micro-USB Programming / Charging Access + Barrel Bore
        translate([-8.0, 42.0, 14.0])
            cube([16.0, 12.0, 9.0]);
        translate([0, 44.0, 15.0])
            rotate([-90, 0, 0])
                cylinder(r=5.5, h=28.0);

        // F. Handle Weight-Reduction Core & Lanyard Hole
        translate([0, -47.0, 12.0])
            rotate([-90, 0, 0])
                cylinder(r=6.5, h=64.0);
        translate([0, -63.0, -1.0])
            cylinder(r=4.0, h=30.0);
    }
}

module slide_lid() {
    difference() {
        union() {
            translate([-14.45, -19.5, 0])
                cube([28.9, 39.0, 1.8]);
            translate([-12.4, -10.0, 1.8])
                cube([24.8, 24.0, 1.7]);
        }
        translate([0, -15.5, -1.0])
            cylinder(r=3.5, h=6.0);
    }
}

// Render Body and Lid side-by-side for printing
revolver_body();
translate([40, 20, 0]) slide_lid();
