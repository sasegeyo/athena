#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <NMEAGPS.h>
#include "time.h"
#include <Wire.h>
#include <LiquidCrystal.h>

// LCD paralel bağlantı pinleri (RS, E, D4, D5, D6, D7)
#define LCD_RS 0  // D0
#define LCD_EN 1  // D1
#define LCD_D4 2
#define LCD_D5 3
#define LCD_D6 4
#define LCD_D7 5

LiquidCrystal lcd(LCD_RS, LCD_EN, LCD_D4, LCD_D5, LCD_D6, LCD_D7);

// WiFi ayarları
const char* WIFI_SSID = "İSKANOGLU";
const char* WIFI_PASSWORD = "MuzluTirsik";

// Sunucu ayarları
const char* SERVER_URL = "http://192.168.1.102:5000/api/co_data";
const String DEVICE_ID = "DENEYAP_MQ2_GPS_001";

// Deneyap Mini pin tanımlamaları
#define MQ2_ANALOG_PIN A0     // MQ-2 analog çıkış
#define MQ2_DIGITAL_PIN 0     // MQ-2 dijital çıkış
#define DHT_PIN 8             // DHT22 sıcaklık/nem sensörü
#define BUZZER_PIN 9          // Buzzer
#define LED_RED_PIN 12        // Kırmızı LED - Alarm
#define GPS_RX_PIN 4          // GPS RX
#define GPS_TX_PIN 5          // GPS TX
#define ONBOARD_LED LED_BUILTIN

// Sensör konfigürasyonu
#define DHT_TYPE DHT22
DHT dht(DHT_PIN, DHT_TYPE);

// GPS nesnesi
HardwareSerial gpsSerial(1);
NMEAGPS gps;
gps_fix fix;

// LCD ekran döngüsü
int currentScreen = 0;
const int TOTAL_SCREENS = 4;
unsigned long lastScreenUpdate = 0;
const unsigned long SCREEN_INTERVAL = 3000; // 3 saniye

// Zamanlama
unsigned long lastSensorRead = 0;
unsigned long lastDataSend = 0;
unsigned long lastGPSRead = 0;
unsigned long bootTime = 0;
const unsigned long SENSOR_INTERVAL = 3000;   // 3 saniye
const unsigned long SEND_INTERVAL = 10000;    // 10 saniye
const unsigned long GPS_READ_INTERVAL = 1000; // 1 saniye

// Sensör verileri
struct SensorData {
  float gas_level_ppm = 0;
  bool digital_alarm = false;
  int analog_raw = 0;
  float gas_voltage = 0;
  float temperature = 0;
  float humidity = 0;
  bool alarm_status = false;
  bool system_status = true;
  int wifi_rssi = 0;
  unsigned long uptime = 0;
  float battery_voltage = 0;
  // GPS verileri
  double latitude = 0.0;
  double longitude = 0.0;
  double altitude = 0.0;
  int satellites = 0;
  bool gps_valid = false;
  String gps_time = "";
  String gps_date = "";
  float gps_speed = 0.0;
  float gps_course = 0.0;
  String gps_fix_type = "";
};

SensorData currentData;

// Alarm eşikleri
const float GAS_THRESHOLD_PPM = 400.0;
const float TEMP_THRESHOLD = 50.0;

// MQ-2 kalibrasyon değerleri
float R0 = 10.0;
const float RL = 10.0;

// Özel LCD karakterleri
byte degreeChar[8] = {
  0b00110,
  0b01001,
  0b01001,
  0b00110,
  0b00000,
  0b00000,
  0b00000,
  0b00000
};

byte wifiChar[8] = {
  0b00000,
  0b00000,
  0b00111,
  0b01000,
  0b10110,
  0b00101,
  0b00110,
  0b00000
};

byte gpsChar[8] = {
  0b00100,
  0b01110,
  0b11111,
  0b11111,
  0b01110,
  0b00100,
  0b00000,
  0b00000
};

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("🚀 Deneyap Mini MQ-2 GPS LCD Sistemi Başlatılıyor...");
  
  bootTime = millis();
  
  // LCD başlat
  lcd.begin(20, 4);  // 20x4 LCD
  
  // Özel karakterleri tanımla
  lcd.createChar(0, degreeChar);
  lcd.createChar(1, wifiChar);
  lcd.createChar(2, gpsChar);
  
  // Başlangıç mesajı
  displayStartupMessage();
  
  // Pin modlarını ayarla
  pinMode(MQ2_DIGITAL_PIN, INPUT);
  pinMode(LED_RED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(ONBOARD_LED, OUTPUT);
  
  Serial.println("📱 Sistem pinleri ayarlandı");
  
  // GPS başlat
  gpsSerial.begin(9600, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);
  Serial.println("🛰️ GPS modülü başlatıldı");
  
  // DHT sensörünü başlat
  dht.begin();
  Serial.println("🌡️ DHT22 sensörü başlatıldı");
  
  // MQ-2 sensörü ısınma süresi
  Serial.println("🔥 MQ-2 sensörü ısınıyor...");
  warmUpMQ2Sensor();
  
  // WiFi bağlantısını kur
  connectToWiFi();
  
  // Zaman senkronizasyonu
  configTime(3 * 3600, 0, "pool.ntp.org", "time.nist.gov");
  
  // MQ-2 kalibrasyonu
  calibrateMQ2();
  
  Serial.println("✅ Sistem hazır!");
  printSystemStatus();
  
  delay(2000);
}

void loop() {
  unsigned long currentTime = millis();
  
  // WiFi bağlantısını kontrol et
  checkWiFiConnection();
  
  // GPS verilerini oku
  if (currentTime - lastGPSRead >= GPS_READ_INTERVAL) {
    readGPSData();
    lastGPSRead = currentTime;
  }
  
  // Sensör verilerini oku
  if (currentTime - lastSensorRead >= SENSOR_INTERVAL) {
    readSensors();
    checkAlarms();
    updateLEDs();
    lastSensorRead = currentTime;
  }
  
  // LCD ekranını güncelle
  if (currentTime - lastScreenUpdate >= SCREEN_INTERVAL) {
    updateLCDScreen();
    lastScreenUpdate = currentTime;
  }
  
  // Veriyi sunucuya gönder
  if (currentTime - lastDataSend >= SEND_INTERVAL) {
    sendDataToServer();
    lastDataSend = currentTime;
  }
  
  delay(100);
}

void displayStartupMessage() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("  DENEYAP MINI MQ-2 ");
  lcd.setCursor(0, 1);
  lcd.print("   GPS SISTEM V1.0  ");
  lcd.setCursor(0, 2);
  lcd.print("     LCD EKRAN      ");
  lcd.setCursor(0, 3);
  lcd.print("   Baslatiliyor...  ");
  delay(3000);
}

void updateLCDScreen() {
  lcd.clear();
  
  switch (currentScreen) {
    case 0:
      displayGasScreen();
      break;
    case 1:
      displayTempHumScreen();
      break;
    case 2:
      displayGPSScreen();
      break;
    case 3:
      displaySystemScreen();
      break;
  }
  
  currentScreen = (currentScreen + 1) % TOTAL_SCREENS;
}

void displayGasScreen() {
  lcd.setCursor(0, 0);
  lcd.print("=== GAZ SENSORU ===");
  
  lcd.setCursor(0, 1);
  lcd.print("Gaz: ");
  lcd.print(currentData.gas_level_ppm, 1);
  lcd.print(" ppm");
  
  lcd.setCursor(0, 2);
  lcd.print("Voltaj: ");
  lcd.print(currentData.gas_voltage, 2);
  lcd.print("V");
  
  lcd.setCursor(0, 3);
  if (currentData.alarm_status) {
    lcd.print(">>> ALARM AKTIF! <<<");
  } else if (currentData.digital_alarm) {
    lcd.print(">>> DIJITAL ALARM <<<");
  } else {
    lcd.print("Durum: NORMAL");
  }
}

void displayTempHumScreen() {
  lcd.setCursor(0, 0);
  lcd.print("=== SICAKLIK/NEM ===");
  
  lcd.setCursor(0, 1);
  lcd.print("Sicaklik: ");
  lcd.print(currentData.temperature, 1);
  lcd.write(byte(0)); // Derece karakteri
  lcd.print("C");
  
  lcd.setCursor(0, 2);
  lcd.print("Nem: ");
  lcd.print(currentData.humidity, 1);
  lcd.print("%");
  
  lcd.setCursor(0, 3);
  if (currentData.temperature > TEMP_THRESHOLD) {
    lcd.print(">>> SICAK ALARM! <<<");
  } else {
    lcd.print("DHT22 Sensoru: OK");
  }
}

void displayGPSScreen() {
  lcd.setCursor(0, 0);
  lcd.print("===== GPS DURUM ====");
  
  if (currentData.gps_valid) {
    lcd.setCursor(0, 1);
    lcd.print("Lat:");
    lcd.print(currentData.latitude, 4);
    
    lcd.setCursor(0, 2);
    lcd.print("Lon:");
    lcd.print(currentData.longitude, 4);
    
    lcd.setCursor(0, 3);
    lcd.write(byte(2)); // GPS karakteri
    lcd.print("Sat:");
    lcd.print(currentData.satellites);
    lcd.print(" Hiz:");
    lcd.print(currentData.gps_speed, 0);
    lcd.print("km/h");
  } else {
    lcd.setCursor(0, 1);
    lcd.print("GPS Aranyor...");
    lcd.setCursor(0, 2);
    lcd.print("Konum: Yok");
    lcd.setCursor(0, 3);
    lcd.print("Uydu: 0");
  }
}

void displaySystemScreen() {
  lcd.setCursor(0, 0);
  lcd.print("==== SISTEM INFO ===");
  
  lcd.setCursor(0, 1);
  lcd.write(byte(1)); // WiFi karakteri
  if (WiFi.status() == WL_CONNECTED) {
    lcd.print("WiFi: BAGLLI ");
    lcd.print(WiFi.RSSI());
    lcd.print("dBm");
  } else {
    lcd.print("WiFi: BAGLI DEGIL");
  }
  
  lcd.setCursor(0, 2);
  lcd.print("Uptime: ");
  unsigned long hours = currentData.uptime / 3600;
  unsigned long minutes = (currentData.uptime % 3600) / 60;
  lcd.print(hours);
  lcd.print(":");
  if (minutes < 10) lcd.print("0");
  lcd.print(minutes);
  
  lcd.setCursor(0, 3);
  lcd.print("Pil: ");
  lcd.print(currentData.battery_voltage, 1);
  lcd.print("V ID:");
  lcd.print(DEVICE_ID.substring(DEVICE_ID.length() - 3));
}

void displayAlarmScreen() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("!!!! ALARM !!!!!");
  
  lcd.setCursor(0, 1);
  if (currentData.gas_level_ppm > GAS_THRESHOLD_PPM) {
    lcd.print("GAZ: ");
    lcd.print(currentData.gas_level_ppm, 0);
    lcd.print(" ppm");
  }
  
  lcd.setCursor(0, 2);
  if (currentData.temperature > TEMP_THRESHOLD) {
    lcd.print("SICAKLIK: ");
    lcd.print(currentData.temperature, 1);
    lcd.write(byte(0));
    lcd.print("C");
  }
  
  lcd.setCursor(0, 3);
  lcd.print(">>> DIKKAT! <<<");
}

void warmUpMQ2Sensor() {
  for (int i = 30; i > 0; i--) {
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("MQ-2 SENSORU ISINMA");
    lcd.setCursor(0, 1);
    lcd.print("Lutfen bekleyiniz...");
    lcd.setCursor(0, 2);
    lcd.print("Kalan sure: ");
    lcd.print(i);
    lcd.print(" sn");
    lcd.setCursor(0, 3);
    
    // Progress bar
    int progress = (30 - i) * 20 / 30;
    for (int j = 0; j < progress; j++) {
      lcd.print("=");
    }
    
    Serial.printf("⏳ MQ-2 ısınma süresi: %d saniye kaldı\n", i);
    digitalWrite(ONBOARD_LED, i % 2);
    delay(1000);
  }
  digitalWrite(ONBOARD_LED, HIGH);
  Serial.println("✅ MQ-2 sensörü hazır!");
}

void connectToWiFi() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("WiFi Baglantisi");
  lcd.setCursor(0, 1);
  lcd.print("SSID: ");
  lcd.print(WIFI_SSID);
  
  Serial.print("📡 WiFi'ye bağlanıyor");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    digitalWrite(ONBOARD_LED, !digitalRead(ONBOARD_LED));
    
    lcd.setCursor(0, 2);
    lcd.print("Deneme: ");
    lcd.print(attempts + 1);
    lcd.print("/30");
    
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.println("✅ WiFi bağlantısı kuruldu!");
    Serial.print("📍 IP Adresi: ");
    Serial.println(WiFi.localIP());
    
    lcd.setCursor(0, 3);
    lcd.print("BAGLAN! ");
    String ip = WiFi.localIP().toString();
    lcd.print(ip.substring(ip.lastIndexOf('.') + 1));
    
    digitalWrite(ONBOARD_LED, HIGH);
    delay(2000);
  } else {
    Serial.println();
    Serial.println("❌ WiFi bağlantısı kurulamadı!");
    
    lcd.setCursor(0, 3);
    lcd.print("BAGLI DEGIL!");
    
    digitalWrite(ONBOARD_LED, LOW);
    delay(2000);
  }
}

void checkWiFiConnection() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("⚠️ WiFi bağlantısı kesildi, yeniden bağlanıyor...");
    connectToWiFi();
  }
}

void readGPSData() {
  while (gpsSerial.available()) {
    if (gps.available(gpsSerial)) {
      fix = gps.read();
      
      if (fix.valid.location) {
        currentData.latitude = fix.latitude();
        currentData.longitude = fix.longitude();
        currentData.gps_valid = true;
      }
      
      if (fix.valid.altitude) {
        currentData.altitude = fix.altitude();
      }
      
      if (fix.valid.satellites) {
        currentData.satellites = fix.satellites;
      }
      
      if (fix.valid.speed) {
        currentData.gps_speed = fix.speed_kph();
      }
      
      if (fix.valid.heading) {
        currentData.gps_course = fix.heading();
      }
      
      if (fix.valid.time) {
        char timeStr[20];
        sprintf(timeStr, "%02d:%02d:%02d", 
                fix.dateTime.hours, 
                fix.dateTime.minutes, 
                fix.dateTime.seconds);
        currentData.gps_time = String(timeStr);
      }
      
      if (fix.valid.date) {
        char dateStr[20];
        sprintf(dateStr, "%02d/%02d/%04d", 
                fix.dateTime.date, 
                fix.dateTime.month, 
                fix.dateTime.year);
        currentData.gps_date = String(dateStr);
      }
      
      if (fix.valid.status) {
        switch (fix.status) {
          case gps_fix::STATUS_NONE:
            currentData.gps_fix_type = "NONE";
            break;
          case gps_fix::STATUS_EST:
            currentData.gps_fix_type = "EST";
            break;
          case gps_fix::STATUS_TIME_ONLY:
            currentData.gps_fix_type = "TIME";
            break;
          case gps_fix::STATUS_STD:
            currentData.gps_fix_type = "STD";
            break;
          case gps_fix::STATUS_DGPS:
            currentData.gps_fix_type = "DGPS";
            break;
          default:
            currentData.gps_fix_type = "UNKNOWN";
            break;
        }
      }
      
      if (!fix.valid.location) {
        currentData.gps_valid = false;
      }
    }
  }
}

void readSensors() {
  // MQ-2 sensörü okuma
  currentData.analog_raw = analogRead(MQ2_ANALOG_PIN);
  currentData.digital_alarm = !digitalRead(MQ2_DIGITAL_PIN);
  
  // Voltaj hesaplama
  currentData.gas_voltage = (currentData.analog_raw / 4095.0) * 3.3;
  
  // PPM hesaplama
  currentData.gas_level_ppm = calculateGasPPM(currentData.analog_raw);

  // DHT22 - Sıcaklık ve nem
  float temp = dht.readTemperature();
  float hum = dht.readHumidity();
  
  if (!isnan(temp)) {
    currentData.temperature = temp;
  }
  if (!isnan(hum)) {
    currentData.humidity = hum;
  }
  
  // Pil voltajı
  currentData.battery_voltage = 3.7; // Sabit değer
  
  // Sistem bilgileri
  currentData.wifi_rssi = WiFi.RSSI();
  currentData.uptime = (millis() - bootTime) / 1000;
  currentData.system_status = true;
  
  // Debug çıktısı
  Serial.println("\n📊 Sensör Okumaları:");
  Serial.printf("   📈 Analog Raw: %d (0-4095)\n", currentData.analog_raw);
  Serial.printf("   ⚡ Voltaj: %.3fV\n", currentData.gas_voltage);
  Serial.printf("   💨 Gaz Seviyesi: %.2f ppm\n", currentData.gas_level_ppm);
  Serial.printf("   🔴 Dijital Alarm: %s\n", currentData.digital_alarm ? "AKTIF" : "NORMAL");
  Serial.printf("   🌡️ Sıcaklık: %.2f°C\n", currentData.temperature);
  Serial.printf("   💧 Nem: %.2f%%\n", currentData.humidity);
  Serial.printf("   🛰️ GPS: %s\n", currentData.gps_valid ? "AKTIF" : "ARANYOR");
  if (currentData.gps_valid) {
    Serial.printf("   📍 Konum: %.6f, %.6f\n", currentData.latitude, currentData.longitude);
    Serial.printf("   🛰️ Uydu: %d\n", currentData.satellites);
    Serial.printf("   🚗 Hız: %.2f km/h\n", currentData.gps_speed);
  }
}

float calculateGasPPM(int rawValue) {
  float voltage = (rawValue / 4095.0) * 3.3;
  if (voltage <= 0.01) voltage = 0.01;
  
  float rs = ((3.3 * RL) / voltage) - RL;
  float ratio = rs / R0;
  float ppm = 613.9 * pow(ratio, -2.074);
  
  if (ppm < 0) ppm = 0;
  if (ppm > 10000) ppm = 10000;
  
  return ppm;
}

void calibrateMQ2() {
  Serial.println("\n🔧 MQ-2 Sensörü Kalibrasyonu...");
  
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("MQ-2 KALIBRASYONU");
  lcd.setCursor(0, 1);
  lcd.print("Temiz hava gerekli");
  
  float voltageSum = 0;
  int samples = 10;
  
  for (int i = 0; i < samples; i++) {
    int rawValue = analogRead(MQ2_ANALOG_PIN);
    float voltage = (rawValue / 4095.0) * 3.3;
    voltageSum += voltage;
    
    lcd.setCursor(0, 2);
    lcd.print("Ornek: ");
    lcd.print(i + 1);
    lcd.print("/");
    lcd.print(samples);
    
    lcd.setCursor(0, 3);
    lcd.print("V: ");
    lcd.print(voltage, 3);
    
    Serial.printf("📊 Örnek %d/%d - V: %.3f\n", i + 1, samples, voltage);
    delay(500);
  }
  
  float avgVoltage = voltageSum / samples;
  
  if (avgVoltage > 0.01) {
    R0 = ((3.3 * RL) / avgVoltage) - RL;
  }
  
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("KALIBRASYON TAMAM");
  lcd.setCursor(0, 1);
  lcd.print("Ort. Voltaj:");
  lcd.print(avgVoltage, 3);
  lcd.setCursor(0, 2);
  lcd.print("R0: ");
  lcd.print(R0, 2);
  lcd.print(" kOhm");
  
  if (R0 > 0 && R0 < 100) {
    lcd.setCursor(0, 3);
    lcd.print("Durum: BASARILI");
    Serial.println("✅ MQ-2 kalibrasyon başarılı!");
  } else {
    lcd.setCursor(0, 3);
    lcd.print("Durum: VARSAYILAN");
    Serial.println("⚠️ Varsayılan R0 kullanılacak");
    R0 = 10.0;
  }
  
  delay(3000);
}

void checkAlarms() {
  bool alarmTriggered = false;
  
  if (currentData.digital_alarm) {
    Serial.println("🚨 MQ-2 DİJİTAL ALARM!");
    alarmTriggered = true;
  }
  
  if (currentData.gas_level_ppm > GAS_THRESHOLD_PPM) {
    Serial.printf("🚨 MQ-2 GAZ ALARM! Seviye: %.2f ppm\n", currentData.gas_level_ppm);
    alarmTriggered = true;
  }
  
  if (currentData.temperature > TEMP_THRESHOLD) {
    Serial.printf("🚨 SICAKLIK ALARM! Seviye: %.2f°C\n", currentData.temperature);
    alarmTriggered = true;
  }
  
  currentData.alarm_status = alarmTriggered;
  
  if (alarmTriggered) {
    triggerAlarm();
    displayAlarmScreen();
    delay(2000);
  }
}

void triggerAlarm() {
  for (int i = 0; i < 3; i++) {
    digitalWrite(BUZZER_PIN, HIGH);
    digitalWrite(LED_RED_PIN, HIGH);
    digitalWrite(ONBOARD_LED, LOW);
    delay(200);
    digitalWrite(BUZZER_PIN, LOW);
    digitalWrite(LED_RED_PIN, LOW);
    digitalWrite(ONBOARD_LED, HIGH);
    delay(200);
  }
}

void updateLEDs() {
  if (currentData.alarm_status) {
    digitalWrite(LED_RED_PIN, millis() % 1000 < 500);
    digitalWrite(ONBOARD_LED, millis() % 500 < 250);
  } else {
    digitalWrite(LED_RED_PIN, LOW);
    digitalWrite(ONBOARD_LED, HIGH);
  }
}

void sendDataToServer() {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(SERVER_URL);
    http.addHeader("Content-Type", "application/json");
    
    StaticJsonDocument<512> doc;
    doc["device_id"] = DEVICE_ID;
    doc["gas_level_ppm"] = currentData.gas_level_ppm;
    doc["temperature"] = currentData.temperature;
    doc["humidity"] = currentData.humidity;
    doc["latitude"] = currentData.latitude;
    doc["longitude"] = currentData.longitude;
    doc["battery_voltage"] = currentData.battery_voltage;
    doc["alarm_status"] = currentData.alarm_status;
    
    String jsonData;
    serializeJson(doc, jsonData);
    
    int httpResponseCode = http.POST(jsonData);
    
    if (httpResponseCode > 0) {
      Serial.printf("📡 Veri Gönderildi! HTTP %d\n", httpResponseCode);
    } else {
      Serial.printf("❌ Veri Gönderim Hatası! HTTP %d\n", httpResponseCode);
    }
    
    http.end();
  } else {
    Serial.println("⚠️ WiFi bağlantısı yok, veri gönderilemedi.");
  }
}

void printSystemStatus() {
  Serial.println("\n📋 Sistem Durumu:");
  Serial.printf("   🔧 Cihaz ID: %s\n", DEVICE_ID.c_str());
  Serial.printf("   📡 WiFi: %s\n", WiFi.status() == WL_CONNECTED ? "BAĞLI" : "BAĞLI DEĞİL");
  if (WiFi.status() == WL_CONNECTED) {
     Serial.printf("   📍 IP Adresi: %s\n", WiFi.localIP().toString().c_str());
  }
  Serial.printf("   🛰️ GPS Durumu: %s\n", currentData.gps_valid ? "AKTIF" : "ARANYOR");
  Serial.printf("   🔋 Pil Voltajı: %.2f V\n", currentData.battery_voltage);
  Serial.printf("   ⏱️ Uptime: %lu saniye\n", currentData.uptime);
  Serial.printf("   🔥 MQ-2 Kalibrasyon R0: %.2f\n", R0);
  Serial.println("✅ Sistem Başlatıldı ve Çalışıyor!\n");
}