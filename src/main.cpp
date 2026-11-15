#include <Arduino.h>
#include <Servo.h>

// ==========================================
// 1. PIN DEFINITIONS & HARDWARE CONFIG
// ==========================================
const int ESC_PIN       = 2;   // PWM output to ESC signal wire (Teensy 4.1 FlexPWM pin)
const int LED_PIN       = 13;  // Built-in status LED
const int RPM_PIN       = 3;   // Optical / Hall tachometer interrupt pin
const int VOLT_PIN      = A0;  // Voltage divider analog pin
const int CURR_PIN      = A1;  // Current sensor analog pin

// Calibration constants (tune once physical sensors are mounted)
float thrust_tare_offset = 0.0f;
float thrust_scale       = 1.0f;
const float VOLT_SCALE   = 11.0f * (3.3f / 1023.0f); // Example 10:1 divider on 3.3V ADC
const float CURR_SCALE   = 30.0f * (3.3f / 1023.0f); // Example 30A sensor on 3.3V ADC
const int   MOTOR_POLES  = 14;                       // 2806.5 brushless motor = 14 poles (7 pole pairs)

// ==========================================
// 2. STATE MACHINE & TIMING VARIABLES
// ==========================================
enum SystemState {
  STATE_IDLE,
  STATE_TESTING,
  STATE_STOP
};

SystemState currentState = STATE_IDLE;
Servo esc;

int targetThrottle = 1000;
unsigned long lastHeartbeatTime = 0;
const unsigned long FAILSAFE_TIMEOUT_MS = 500;

// Telemetry & LED timers
unsigned long lastTelemetryTime = 0;
const unsigned long TELEMETRY_INTERVAL_MS = 20; // 50 Hz broadcast rate

unsigned long lastBlinkTime = 0;
bool ledState = false;

// RPM interrupt counter
volatile unsigned long rpmPulseCount = 0;
unsigned long lastRpmCalcTime = 0;
int currentRpm = 0;

void rpmISR() {
  rpmPulseCount++;
}

// ==========================================
// 3. SENSOR READ & TARE FUNCTIONS
// ==========================================
float readRawThrust() {
  // TODO: Replace with HX711.get_units() once load cell is wired
  // Simulated response tied to throttle so you can test live USB packets right now
  if (currentState == STATE_TESTING && targetThrottle > 1000) {
    float pct = (targetThrottle - 1000) / 1000.0f;
    return (pct * pct) * 1400.0f;
  }
  return 0.0f;
}

void tareLoadCell() {
  thrust_tare_offset = readRawThrust();
  Serial.println("INFO: Load cell tared");
}

int updateRpm() {
  unsigned long now = millis();
  unsigned long dt = now - lastRpmCalcTime;
  if (dt >= 100) { // Calculate RPM every 100 ms
    noInterrupts();
    unsigned long pulses = rpmPulseCount;
    rpmPulseCount = 0;
    interrupts();

    // If no physical tachometer pulses yet during testing, mirror throttle
    if (pulses == 0 && currentState == STATE_TESTING && targetThrottle > 1000) {
      float pct = (targetThrottle - 1000) / 1000.0f;
      currentRpm = (int)(pct * 18000.0f);
    } else {
      float revs = (float)pulses / (MOTOR_POLES / 2.0f);
      currentRpm = (int)((revs / (dt / 1000.0f)) * 60.0f);
    }
    lastRpmCalcTime = now;
  }
  return currentRpm;
}

// ==========================================
// 4. LED STATUS FEEDBACK
// ==========================================
void updateStatusLED() {
  unsigned long now = millis();
  unsigned long interval = 1000;

  if (currentState == STATE_IDLE) {
    interval = 1000; // Slow heartbeat (1 Hz)
  } else if (currentState == STATE_TESTING) {
    interval = 250;  // Fast active blink (4 Hz)
  } else if (currentState == STATE_STOP) {
    interval = 80;   // Rapid strobe warning (12.5 Hz)
  }

  if (now - lastBlinkTime >= interval) {
    ledState = !ledState;
    digitalWrite(LED_PIN, ledState);
    lastBlinkTime = now;
  }
}

// ==========================================
// 5. SETUP
// ==========================================
void setup() {
  Serial.begin(115200);
  Serial.setTimeout(20); // Critical: prevents parseInt() from tripping 500ms failsafe

  pinMode(LED_PIN, OUTPUT);
  pinMode(RPM_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(RPM_PIN), rpmISR, FALLING);

  esc.attach(ESC_PIN, 1000, 2000);
  esc.writeMicroseconds(1000);

  tareLoadCell();
  Serial.println("STATE: IDLE");
}

// ==========================================
// 6. MAIN REAL-TIME CONTROL LOOP
// ==========================================
void loop() {
  unsigned long now = millis();

  // --- A. PARSE INCOMING SERIAL COMMANDS ---
  while (Serial.available() > 0) {
    char cmd = Serial.read();

    if (cmd == '\n' || cmd == '\r' || cmd == ' ') {
      continue;
    }

    if (cmd == 'E') {
      // Universal E-Stop overrides every state immediately
      targetThrottle = 1000;
      esc.writeMicroseconds(1000);
      currentState = STATE_STOP;
      Serial.println("STATE: STOP");
    }
    else if (cmd == 'Z') {
      // Zero / Tare load cell
      tareLoadCell();
    }
    else if (cmd == 'A') {
      if (currentState == STATE_IDLE) {
        targetThrottle = 1000;
        esc.writeMicroseconds(1000);
        lastHeartbeatTime = now;
        currentState = STATE_TESTING;
        Serial.println("STATE: TESTING");
      }
    }
    else if (cmd == 'I') {
      if (currentState == STATE_TESTING || currentState == STATE_STOP) {
        targetThrottle = 1000;
        esc.writeMicroseconds(1000);
        currentState = STATE_IDLE;
        Serial.println("STATE: IDLE");
      }
    }
    else if (cmd == 'T') {
      int val = Serial.parseInt();
      if (currentState == STATE_TESTING) {
        targetThrottle = constrain(val, 1000, 2000);
        lastHeartbeatTime = now; // Reset 500ms watchdog timer
      }
    }
  }

  // --- B. STATE MACHINE EXECUTION ---
  switch (currentState) {
    case STATE_IDLE:
      targetThrottle = 1000;
      esc.writeMicroseconds(1000);
      break;

    case STATE_TESTING:
      // Watchdog Failsafe Check
      if (now - lastHeartbeatTime > FAILSAFE_TIMEOUT_MS) {
        targetThrottle = 1000;
        esc.writeMicroseconds(1000);
        currentState = STATE_STOP;
        Serial.println("FAILSAFE: HEARTBEAT TIMEOUT");
        Serial.println("STATE: STOP");
      } else {
        esc.writeMicroseconds(targetThrottle);
      }
      break;

    case STATE_STOP:
      targetThrottle = 1000;
      esc.writeMicroseconds(1000);
      break;
  }

  // --- C. 50 HZ TELEMETRY BROADCAST ---
  if (now - lastTelemetryTime >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryTime = now;

    float thrust_g = (readRawThrust() - thrust_tare_offset) * thrust_scale;
    int   rpm      = updateRpm();
    
    // Read analog pins (or provide clean nominal fallback if pins are floating/unwired)
    float voltage  = 16.80f; // Replace with: analogRead(VOLT_PIN) * VOLT_SCALE;
    float current  = (currentState == STATE_TESTING && targetThrottle > 1000) 
                     ? ((targetThrottle - 1000) / 1000.0f) * 25.0f : 0.05f;
                     // Replace with: analogRead(CURR_PIN) * CURR_SCALE;

    // Broadcast CSV packet: DATA,thrust,rpm,volt,curr
    Serial.printf("DATA,%.1f,%d,%.2f,%.2f\n", thrust_g, rpm, voltage, current);
  }

  // --- D. UPDATE VISUAL STATUS LED ---
  updateStatusLED();
}
