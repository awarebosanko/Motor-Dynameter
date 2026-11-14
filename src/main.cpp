// This test stand coded by Aiden Ware Bosanko
#include <Arduino.h>
#include <Servo.h>

// Inital Set up
enum SystemState {
  STATE_IDLE,
  STATE_TESTING,
  STATE_STOP
};

SystemState currentstate = STATE_IDLE;
SystemState previousstate = STATE_IDLE; // Tracks changes so we don't flood the serial monitor

unsigned long LoadCellLastTime = 0;
unsigned long LastCommandTime = 0;
Servo esc;

// LED state status
const int ledPin = 13; // Teensy 4.1 led
unsigned long LedLastTime = 0;
bool ledState = false;

// Helper function to print state changes cleanly
void printStateChange(SystemState newState) {
  if (newState == STATE_IDLE) Serial.println("\n>>> STATE: IDLE (Awaiting 'A' to Arm)");
  else if (newState == STATE_TESTING) Serial.println("\n>>> STATE: TESTING (Motor Armed)");
  else if (newState == STATE_STOP) Serial.println("\n>>> STATE: STOP (Motor Killed)");
}

//System precheck
void setup(){
  Serial.begin(115200);
  pinMode(ledPin, OUTPUT); 
  esc.attach(6);
  esc.writeMicroseconds(1000);

  // Give the serial monitor a second to open, then print the starting state
  delay(1000);
  Serial.println("System Initialized.");
  printStateChange(currentstate);
}

void loop(){
  // 1. STATE CHANGE DETECTOR
  // If the state just changed, print the new state, then update the tracker
  if (currentstate != previousstate) {
    printStateChange(currentstate);
    previousstate = currentstate;
  }

  // 2. THE STATE MACHINE
  switch (currentstate){
    
    case STATE_IDLE:
      // Slow blink
      if (millis() - LedLastTime >= 1000){
        LedLastTime = millis();
        ledState = !ledState;
        digitalWrite(ledPin, ledState);
      }
      if (Serial.available() > 0){
        char command = Serial.read();
        if (command == 'A'){
          currentstate = STATE_TESTING;
          LastCommandTime = millis(); 
        }
      }
      break;

    case STATE_TESTING:
      // Fast led blink
      if (millis() - LedLastTime >= 100){
        LedLastTime = millis();
        ledState = !ledState;
        digitalWrite(ledPin, ledState);
      }

      // 1. The Failsafe (Outside the Serial block, set to 500ms)
      if (millis() - LastCommandTime > 500){
        Serial.println("FAILSAFE TRIGGERED: No heartbeat received in 500ms!");
        currentstate = STATE_STOP;
      }
      
      // 2. USB Command Parser
      if (Serial.available() > 0){
        char command = Serial.read();
        if (command == 'E'){
          Serial.println("E-STOP TRIGGERED via USB Command!");
          currentstate = STATE_STOP;
        }
        else if (command == 'T') {
          int throttle = Serial.parseInt(); 
          esc.writeMicroseconds(throttle);  
          LastCommandTime = millis();       
        }
      } 

      // 3. Load cell timer
      if (millis() - LoadCellLastTime >= 50){
        LoadCellLastTime = millis();
      }
      break;

    case STATE_STOP:
      // 1. Solid Light
      digitalWrite(ledPin, HIGH);

      // 2. KILL THE MOTOR
      esc.writeMicroseconds(1000);
      
      // 3. Route to other modes
      if (Serial.available() > 0) {
        char command = Serial.read();
        
        if (command == 'A') {
          // Re-arm directly to testing
          currentstate = STATE_TESTING;
          LastCommandTime = millis(); 
        }
        else if (command == 'I') {
          // Fall back to idle mode safely
          currentstate = STATE_IDLE;
          digitalWrite(ledPin, LOW); 
        }
      }
      break;
  }
}
