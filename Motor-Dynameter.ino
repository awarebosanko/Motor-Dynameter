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
unsigned long LoadCellLastTime = 0;
unsigned long LastCommandTime = 0;
Servo esc;

//System precheck
void setup(){
  Serial.begin(115200);
  esc.attach(6);
  esc.writeMicroseconds(1000);
  // will check to see all sensors connected
  // if a sensor isnt ocnnected send a message saying not connecteed
}


// Library of test Functions
void loop(){
  switch (currentstate){
    case STATE_IDLE:
    if (Serial.available() > 0){
      char command = Serial.read();
      if (command == 'A'){
        currentstate = STATE_TESTING;
      }
    }
      break;
    case STATE_TESTING:
    if (Serial.available() > 0){
      if (millis() - LastCommandTime > 50){
        currentstate = STATE_STOP;
      }
      char command = Serial.read();
      if (command == 'E'){
        currentstate = STATE_STOP;
      }
    else if (command == 'T') {
      int throttle = Serial.parseInt(); //Grabs the '1500' part of 'T1500'
      esc.writeMicroseconds(throttle); // Sends 1500 to ESC
      LastCommandTime = millis(); // Reset heartbeat timeout
    }
    if (millis() - LoadCellLastTime >= 50){
      LoadCellLastTime = millis();
    }
      break;
    case STATE_STOP:
    if (Serial.available() > 0){
      char command = Serial.read();
      if (command == 'A'){
        currentstate = STATE_TESTING;
      }
      if (command == 'A'){
        currentstate = STATE_TESTING;
      }
      
    }
      break;
  }
}



