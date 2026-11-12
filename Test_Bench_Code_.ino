// This test stand coded by Aiden Ware Bosanko


// Inital Set up
enum SystemState {
  STATE_IDLE,
  STATE_TESTING,
  STATE_STOP
};

SystemState currentstate = STATE_IDLE;
unsigned long LoadCellLastTime = 0;


//System precheck
void setup()
will check to see all sensors connected
if a sensor isnt ocnnected send a message saying not connecteed

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
      char command = Serial.read();
      if (command == 'E'){
        currentstate = STATE_STOP;
      }
    }
    if (millis() - LoadCellLastTime >= 50){
      LoadCellLastTime = millis();

      break;
    case STATE_STOP;
      break;
  }
}



// ESC Check
if currentstate = STATE_TESTING
  E



