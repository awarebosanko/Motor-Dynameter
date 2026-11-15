# Propeller Dyna Pro

**Modular Static Thrust & Propulsion Dynamometer**  
*Developed by Aiden Ware Bosanko — Mechanical Engineering, Texas A&M University*

Propeller Dyna Pro is an instrumented static thrust dynamometer and real-time data acquisition (DAQ) suite engineered to experimentally characterize brushless motor and propeller combinations. It replaces theoretical eCalc estimates with empirical aerodynamic coefficients (Ct, Cp), motor constants (Kv, Kt), and propulsion efficiency curves (g/W).

---

## System Wiring & Architecture

![Propeller Dyna Pro Wiring Diagram](hardware/schematics/Dyna%20Test%20Bench%20Wire%20Diagram.png)

### Repository Layout
- **firmware/** — Teensy 4.1 C++ real-time state machine & DAQ (src/main.cpp, platformio.ini)
- **software/** — Python mission-control telemetry HUD & step-sweep logger (dashboard.py, requirements.txt)
- **analysis/** — MATLAB aerodynamic & motor curve-fitting post-processor (analyze_dyno.m)
- **hardware/cad/** — SolidWorks parts/assemblies & 3D-printed ABS mounts (Planned)
- **hardware/schematics/** — System pinout & wiring harness diagrams
- **hardware/BOM.md** — Complete hardware bill of materials
- **docs/PRELIMINARY_SCOPE.md** — Engineering requirements & project scope
- **logs/** — Recorded test-run & step-sweep CSV exports

---

## Hardware Pinout & Sensor Interface

| Subsystem | Sensor / Actuator | Teensy 4.1 Pin | Protocol / Notes |
| :--- | :--- | :--- | :--- |
| **Throttle Output** | Brushless ESC | Pin 2 (FlexPWM) | 1000-2000 us @ 50 Hz |
| **Thrust Force** | Load Cell + HX711 | Pin 4 (DOUT), Pin 5 (SCK) | 24-bit ADC; live tare via Z command |
| **Rotor Speed** | TCRT5000 Optical IR | Pin 3 (Hardware ISR) | Falling-edge pulse counter (14-pole motor) |
| **Motor Temp** | MLX90614 IR Sensor | Pin 18 (SDA), Pin 19 (SCL) | Non-contact I2C thermal monitoring |
| **Bus Electrical** | Voltage / Current | A0 (Volt), A1 (Curr) | Scaled 4S LiPo voltage & current sensing |
| **Fault Indicator** | Onboard LED | Pin 13 | 1 Hz Idle, 4 Hz Armed, 12.5 Hz Fault |

---

## Quick Start

1. **Flash Firmware:** Open firmware/ in VS Code with PlatformIO and upload to the Teensy 4.1 (115200 baud).
2. **Launch Control Station:** Run pip install -r software/requirements.txt and python software/dashboard.py (Esc = E-Stop, Space = Idle).
3. **Run MATLAB Analysis:** Open analysis/analyze_dyno.m, set D_inch, and run to auto-load the latest sweep CSV from logs/.

---

## Project Progress & Development Timeline (~50% Complete)

### Completed
- [x] **Milestone 1 — Embedded State Machine & Failsafe Firmware:** Deterministic IDLE, TESTING, and STOP states on Teensy 4.1 with 500 ms heartbeat watchdog, 20 ms serial timeout, and 50 Hz DATA packet streaming.
- [x] **Milestone 2 — Host Telemetry HUD & Step-Sweep Engine:** Python control station with hardware-confirmed state tracking, blitted 30 s strip charts, anti-aliased radial gauges, manual CSV capture, and automated staircase sweep.
- [x] **Milestone 3 — MATLAB Propulsion Characterization Pipeline:** Curve-fitting script for quadratic PWM response, T vs. RPM^2 scaling, Ct, Cp, loaded Kv, Kt, and g/W efficiency.

### Remaining
- [ ] **Milestone 4 — SolidWorks CAD & 3D-Printed Mounts:** Design motor thrust sled, load cell mounting blocks, and optical tachometer shroud in SolidWorks; print structural brackets in ABS.
- [ ] **Milestone 5 — 2020 Extrusion Assembly & Harness Integration:** Assemble 2020 T-slot aluminum frame, mount HX711, TCRT5000, and MLX90614 sensors, and finalize wiring harness.
- [ ] **Milestone 6 — Dead-Weight Calibration & Low-Throttle Spin Tests:** Integrate physical HX711 and MLX90614 libraries into firmware/src/main.cpp, calibrate load cell scale factor with known masses, and run prop-clamped sweeps capped at 1100-1400 us.
- [ ] **Milestone 7 — Full-Envelope Prop Mapping:** Run full 1100-2000 us sweeps across candidate propellers to generate empirical propulsion lookup tables.
