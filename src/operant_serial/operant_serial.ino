
int baudRate = 19200; // 9600 seems common though it can probably be increased significantly if needed.
char ioBytes[2];
int ioPort = 0;

void setup()
{
  // start serial port at the specified baud rate
  Serial.begin(baudRate);
  while (!Serial) {
    ; // wait for serial port to connect. Needed for Leonardo only
  }
  Serial.println("Initialized!");
}

void loop()
{
  // All serial communications should be two bytes long
  // The first byte specifies the port to act on
  // The second byte specifies the action to take
  // The actions are:
  // 0: Read the specified input
  // 1: Write the specified output to HIGH
  // 2: Write the specified output to LOW
  // 3: Set the specified pin to OUTPUT
  // 4: Set the specified pin to INPUT
  // 5: Set the specified pin to INPUT_PULLUP
  // if we get a valid serial message, read the request:
  if (Serial.available() >= 2) {
    // get incoming two bytes:
    Serial.readBytes(ioBytes, 2);
    //Serial.println("I received: ");
    //Serial.println(ioBytes[0], DEC);
    //Serial.println(ioBytes[1], DEC);
    // Extract the specified port
    ioPort = (int) ioBytes[0];
    // Switch case on the specified action
    switch ((int) ioBytes[1]) {
      case 0: // Read an input
        Serial.write(digitalRead(ioPort));
        break;
      case 1: // Write an output to HIGH
        digitalWrite(ioPort, HIGH);       
        break;
      case 2: // Write an output to LOW
        digitalWrite(ioPort, LOW);        
        break;
      case 3: // Set a pin to OUTPUT
        pinMode(ioPort, OUTPUT);
        digitalWrite(ioPort, LOW);
        break;
      case 4: // Set a pin to INPUT
        pinMode(ioPort, INPUT);
        break;
      case 5: // Set a pin to INPUT_PULLUP
        pinMode(ioPort, INPUT_PULLUP);
        break;
    }
  }
  //delay(10); // Should probably move to a non-delay based spacing.
}
