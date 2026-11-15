# Preliminary Engineering Scope — Propeller Dyna Pro

> *Paste your preliminary scope text, requirements matrix, and target performance envelope below.*

## 1. Problem Statement & Motivation
Commercial propulsion calculators (e.g., eCalc) rely on generalized motor and propeller aerodynamic models that diverge from real-world static thrust, voltage sag, and thermal derating under load. This test stand provides repeatable empirical propulsion data for Vertical Flight Design aircraft sizing.

## 2. Design Requirements
- **Thrust Measurement Range:** 0 - 2,000 g (configurable via load cell rating)
- **DAQ Sampling Rate:** 50 Hz deterministic USB telemetry stream
- **Safety Architecture:** Hardware-enforced 500 ms heartbeat watchdog + instant 1000 us E-Stop cutoff
- **Primary Outputs:** Thrust vs. PWM, T vs. RPM^2 linearity, Ct, Cp, loaded Kv, torque constant Kt, and specific thrust (g/W)
