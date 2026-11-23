#include <Wire.h>
#include <Adafruit_INA219.h>
#include <LiquidCrystal.h>

// DV POWER MONITOR — código compartido por el autor en la conversación.
// Arduino Mega 2560 + INA219 + LCD 16x2 + indicadores LED.
Adafruit_INA219 ina219(0x40);
LiquidCrystal lcd(7, 8, 9, 10, 11, 12);

const byte LED_AMARILLO_1 = 30;
const byte LED_AMARILLO_2 = 31;
const byte LED_ROJO = 32;
const byte LED_AZUL = 33;
const float UMBRAL_SIN_CARGA_MA = 40.0;
const float UMBRAL_DOS_CARGAS_MA = 247.0;
const unsigned long LECTURA_MS = 500;
const unsigned long CONFIRMACION_MS = 2000;
const unsigned long PANTALLA_MS = 3000;
const unsigned long PARPADEO_AZUL_MS = 250;

enum Estado { SIN_CARGA, UNA_CARGA, DOS_CARGAS };
Estado estadoActual = SIN_CARGA;
Estado estadoCandidato = SIN_CARGA;
unsigned long ultimaLectura = 0;
unsigned long inicioCandidato = 0;
unsigned long ultimoCambioPantalla = 0;
unsigned long ultimoParpadeoAzul = 0;
bool mostrarMensaje = false;
bool enviandoEmail = false;
bool estadoAzul = false;
bool primeraLectura = true;
float voltaje = 0.0;
float corriente_mA = 0.0;
float potencia_mW = 0.0;

const char* nombreEstado(Estado e) {
  switch (e) {
    case DOS_CARGAS: return "NORMAL";
    case UNA_CARGA: return "UNA_CARGA";
    default: return "SIN_CARGA";
  }
}

Estado detectarEstado(float corriente) {
  if (corriente < UMBRAL_SIN_CARGA_MA) {
    return SIN_CARGA;
  }
  if (corriente < UMBRAL_DOS_CARGAS_MA) {
    return UNA_CARGA;
  }
  return DOS_CARGAS;
}

void actualizarLED() {
  switch (estadoActual) {
    case DOS_CARGAS:
      digitalWrite(LED_AMARILLO_1, HIGH);
      digitalWrite(LED_AMARILLO_2, HIGH);
      digitalWrite(LED_ROJO, LOW);
      break;
    case UNA_CARGA:
      digitalWrite(LED_AMARILLO_1, HIGH);
      digitalWrite(LED_AMARILLO_2, LOW);
      digitalWrite(LED_ROJO, HIGH);
      break;
    case SIN_CARGA:
      digitalWrite(LED_AMARILLO_1, LOW);
      digitalWrite(LED_AMARILLO_2, LOW);
      digitalWrite(LED_ROJO, HIGH);
      break;
  }
}

void actualizarLEDAzul(unsigned long ahora) {
  if (!enviandoEmail) {
    estadoAzul = false;
    digitalWrite(LED_AZUL, LOW);
    return;
  }
  if (ahora - ultimoParpadeoAzul >= PARPADEO_AZUL_MS) {
    ultimoParpadeoAzul = ahora;
    estadoAzul = !estadoAzul;
    digitalWrite(LED_AZUL, estadoAzul ? HIGH : LOW);
  }
}

void recibirComandos() {
  if (Serial.available() == 0) {
    return;
  }
  String comando = Serial.readStringUntil('\n');
  comando.trim();
  if (comando == "EMAIL_START") {
    enviandoEmail = true;
    ultimoParpadeoAzul = millis();
    estadoAzul = true;
    digitalWrite(LED_AZUL, HIGH);
  } else if (comando == "EMAIL_DONE" || comando == "EMAIL_ERROR") {
    enviandoEmail = false;
    estadoAzul = false;
    digitalWrite(LED_AZUL, LOW);
  }
}

void escribirLinea(byte fila, const char* mensaje) {
  lcd.setCursor(0, fila);
  byte i = 0;
  while (mensaje[i] != '\0' && i < 16) {
    lcd.print(mensaje[i]);
    i++;
  }
  while (i < 16) {
    lcd.print(' ');
    i++;
  }
}

void mostrarLCD() {
  if (!mostrarMensaje) {
    switch (estadoActual) {
      case DOS_CARGAS: escribirLinea(0, "EQUIPO READY"); break;
      case UNA_CARGA: escribirLinea(0, "ALERTA: EQUIPO"); break;
      case SIN_CARGA: escribirLinea(0, "ALARMA: EQUIPO"); break;
    }
    lcd.setCursor(0, 1);
    lcd.print("                ");
    lcd.setCursor(0, 1);
    lcd.print("V:");
    lcd.print(voltaje, 2);
    lcd.print(" I:");
    lcd.print(corriente_mA / 1000.0, 2);
    lcd.print("A");
  } else {
    switch (estadoActual) {
      case DOS_CARGAS:
        escribirLinea(0, "SISTEMA ESTABLE");
        escribirLinea(1, "2 CARGAS ACTIVAS");
        break;
      case UNA_CARGA:
        escribirLinea(0, "REVISAR EQUIPO");
        escribirLinea(1, "CONSUMO REDUCIDO");
        break;
      case SIN_CARGA:
        escribirLinea(0, "VERIFICAR CARGAS");
        escribirLinea(1, "SIN CONSUMO");
        break;
    }
  }
}

void enviarSerial() {
  Serial.print("{\"voltage\":");
  Serial.print(voltaje, 3);
  Serial.print(",\"current_ma\":");
  Serial.print(corriente_mA, 2);
  Serial.print(",\"power_mw\":");
  Serial.print(potencia_mW, 2);
  Serial.print(",\"state\":\"");
  Serial.print(nombreEstado(estadoActual));
  Serial.println("\"}");
}

void setup() {
  Serial.begin(9600);
  Serial.setTimeout(50);
  Wire.begin();
  pinMode(LED_AMARILLO_1, OUTPUT);
  pinMode(LED_AMARILLO_2, OUTPUT);
  pinMode(LED_ROJO, OUTPUT);
  pinMode(LED_AZUL, OUTPUT);
  digitalWrite(LED_AMARILLO_1, LOW);
  digitalWrite(LED_AMARILLO_2, LOW);
  digitalWrite(LED_ROJO, LOW);
  digitalWrite(LED_AZUL, LOW);
  lcd.begin(16, 2);
  escribirLinea(0, "DV POWER MONITOR");
  escribirLinea(1, "INICIANDO...");
  if (!ina219.begin()) {
    escribirLinea(0, "ERROR INA219");
    escribirLinea(1, "REVISAR CABLES");
    Serial.println("{\"error\":\"INA219_NOT_FOUND\"}");
    while (true) {
      delay(1000);
    }
  }
  ina219.setCalibration_32V_2A();
  delay(1000);
  ultimaLectura = millis();
  inicioCandidato = millis();
  ultimoCambioPantalla = millis();
  lcd.clear();
}

void loop() {
  unsigned long ahora = millis();
  recibirComandos();
  if (ahora - ultimaLectura >= LECTURA_MS) {
    ultimaLectura = ahora;
    float busV = ina219.getBusVoltage_V();
    float shuntmV = ina219.getShuntVoltage_mV();
    voltaje = busV + (shuntmV / 1000.0);
    corriente_mA = ina219.getCurrent_mA();
    potencia_mW = ina219.getPower_mW();
    if (corriente_mA < 0.0) {
      corriente_mA = 0.0;
    }
    Estado detectado = detectarEstado(corriente_mA);
    if (primeraLectura) {
      estadoActual = detectado;
      estadoCandidato = detectado;
      inicioCandidato = ahora;
      primeraLectura = false;
    } else {
      if (detectado != estadoCandidato) {
        estadoCandidato = detectado;
        inicioCandidato = ahora;
      }
      if (estadoCandidato != estadoActual &&
          ahora - inicioCandidato >= CONFIRMACION_MS) {
        estadoActual = estadoCandidato;
        mostrarMensaje = false;
        ultimoCambioPantalla = ahora;
      }
    }
    actualizarLED();
    enviarSerial();
  }
  if (ahora - ultimoCambioPantalla >= PANTALLA_MS) {
    mostrarMensaje = !mostrarMensaje;
    ultimoCambioPantalla = ahora;
  }
  actualizarLEDAzul(ahora);
  mostrarLCD();
}
