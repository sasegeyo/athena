#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include "time.h"

// WiFi ayarları
const char* WIFI_SSID = "İSKANOGLU";
const char* WIFI_PASSWORD = "MuzluTirsik";

// Sunucu ayarları
const char* SERVER_URL = "http://192.168.1.102:5000/api/co_data";
const char* API_KEY = " ";

// Cihaz kimliği
const String DEVICE_ID = "DENEYAP_MQ2_SENSOR_001";

// Deneyap Mini pin tanımlamaları
#define MQ2_ANALOG_PIN A0     // MQ-2 analog çıkış (GPIO1)
#define MQ2_DIGITAL_PIN D0    // MQ-2 dijital çıkış (GPIO0)
#define DHT_PIN D8            // DHT22 sıcaklık/nem sensörü (GPIO8)
#define BUZZER_PIN D9         // Buzzer (GPIO9)
#define LED_RED_PIN D12       // Kırmızı LED - Alarm (GPIO12)
#define LED_GREEN_PIN D13     // Yeşil LED - Normal (GPIO13)
#define LED_BLUE_PIN D14      // Mavi LED - WiFi (GPIO14)

// Deneyap Mini'de dahili LED
#define ONBOARD_LED LED_BUILTIN

// Sensör konfigürasyonu
#define DHT_TYPE DHT22
DHT dht(DHT_PIN, DHT_TYPE);

// Zamanlama
unsigned long lastSensorRead = 0;
unsigned long lastDataSend = 0;
unsigned long bootTime = 0;
const unsigned long SENSOR_INTERVAL = 3000;   // 3 saniye
const unsigned long SEND_INTERVAL = 10000;    // 10 saniye

// Sensör verileri
struct SensorData {
  float gas_level_ppm = 0;      // Analog değerden hesaplanan ppm
  bool digital_alarm = false;   // Dijital pin durumu
  int analog_raw = 0;           // Ham analog değer
  float gas_voltage = 0;        // Sensör voltajı
  float temperature = 0;
  float humidity = 0;
  bool alarm_status = false;
  bool system_status = true;
  int wifi_rssi = 0;
  unsigned long uptime = 0;
  float battery_voltage = 0;
};

SensorData currentData;

// Alarm eşikleri
const float GAS_THRESHOLD_PPM = 400.0;  // MQ-2 için gaz eşiği (ppm)
const float TEMP_THRESHOLD = 50.0;
const float VOLTAGE_THRESHOLD = 2.0;    // Voltaj eşiği (alarm için)

// MQ-2 kalibrasyon değerleri
float R0 = 10.0; // Temiz havadaki direnç değeri (kalibrasyonla belirlenecek)
const float RL = 10.0; // Yük direnci (kΩ)

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("🚀 Deneyap Mini MQ-2 Gaz Algılama Sistemi Başlatılıyor...");
  
  bootTime = millis();
  
  // Pin modlarını ayarla
  pinMode(MQ2_DIGITAL_PIN, INPUT);
  pinMode(LED_RED_PIN, OUTPUT);
  pinMode(LED_GREEN_PIN, OUTPUT);
  pinMode(LED_BLUE_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(ONBOARD_LED, OUTPUT);
  
  // Başlangıç LED testi
  testLEDs();
  
  // DHT sensörünü başlat
  dht.begin();
  Serial.println("🌡️ DHT22 sensörü başlatıldı");
  
  // MQ-2 sensörü ısınma süresi
  Serial.println("🔥 MQ-2 sensörü ısınıyor... (30 saniye bekleyiniz)");
  warmUpMQ2Sensor();
  
  // WiFi bağlantısını kur
  connectToWiFi();
  
  // Zaman senkronizasyonu (Türkiye saat dilimi)
  configTime(3 * 3600, 0, "pool.ntp.org", "time.nist.gov");
  
  // MQ-2 kalibrasyonu
  calibrateMQ2();
  
  Serial.println("✅ Sistem hazır!");
  Serial.println("📊 MQ-2 sensör okumaları başlıyor...");
  
  // Sistem durumunu göster
  printSystemStatus();
  
  // İlk test verisi gönder
  delay(2000);
  sendDataToServer();
}

void loop() {
  unsigned long currentTime = millis();
  
  // WiFi bağlantısını kontrol et
  checkWiFiConnection();
  
  // Sensör verilerini oku
  if (currentTime - lastSensorRead >= SENSOR_INTERVAL) {
    readSensors();
    checkAlarms();
    updateLEDs();
    lastSensorRead = currentTime;
  }
  
  // Veriyi sunucuya gönder
  if (currentTime - lastDataSend >= SEND_INTERVAL) {
    sendDataToServer();
    lastDataSend = currentTime;
  }
  
  delay(100);
}

void warmUpMQ2Sensor() {
  // MQ-2 sensörü 30 saniye ısınmalı
  for (int i = 30; i > 0; i--) {
    Serial.printf("⏳ MQ-2 ısınma süresi: %d saniye kaldı\n", i);
    digitalWrite(ONBOARD_LED, i % 2); // LED yanıp sönsün
    delay(1000);
  }
  digitalWrite(ONBOARD_LED, HIGH);
  Serial.println("✅ MQ-2 sensörü hazır!");
}

void connectToWiFi() {
  Serial.print("📡 WiFi'ye bağlanıyor");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    digitalWrite(ONBOARD_LED, !digitalRead(ONBOARD_LED));
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.println("✅ WiFi bağlantısı kuruldu!");
    Serial.print("📍 IP Adresi: ");
    Serial.println(WiFi.localIP());
    Serial.print("📶 Sinyal Gücü: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");
    digitalWrite(LED_BLUE_PIN, HIGH);
    digitalWrite(ONBOARD_LED, HIGH);
  } else {
    Serial.println();
    Serial.println("❌ WiFi bağlantısı kurulamadı!");
    digitalWrite(LED_BLUE_PIN, LOW);
    digitalWrite(ONBOARD_LED, LOW);
  }
}

void checkWiFiConnection() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("⚠️ WiFi bağlantısı kesildi, yeniden bağlanıyor...");
    digitalWrite(LED_BLUE_PIN, LOW);
    connectToWiFi();
  } else {
    digitalWrite(LED_BLUE_PIN, HIGH);
  }
}

void readSensors() {
  // MQ-2 sensörü okuma
  currentData.analog_raw = analogRead(MQ2_ANALOG_PIN);
  currentData.digital_alarm = !digitalRead(MQ2_DIGITAL_PIN); // LOW = Gaz algılandı
  
  // Voltaj hesaplama (Deneyap Mini 12-bit ADC: 0-4095)
  currentData.gas_voltage = (currentData.analog_raw / 4095.0) * 3.3;
  
  // Analog değer (0-4095) → PPM değeri (0-1023)
  currentData.gas_level_ppm = (int)((currentData.analog_raw / 4095.0) * 1023.0);

  // DHT22 - Sıcaklık ve nem
  float temp = dht.readTemperature();
  float hum = dht.readHumidity();
  
  // NaN kontrolü
  if (!isnan(temp)) {
    currentData.temperature = temp;
  }
  if (!isnan(hum)) {
    currentData.humidity = hum;
  }
  
  // Pil voltajı ölçümü
  currentData.battery_voltage = readBatteryVoltage();
  
  // Sistem bilgileri
  currentData.wifi_rssi = WiFi.RSSI();
  currentData.uptime = (millis() - bootTime) / 1000;
  currentData.system_status = true;
  
  // Debug çıktısı
  Serial.println("\n📊 MQ-2 Sensör Okumaları:");
  Serial.printf("   📈 Analog Raw: %d (0-4095)\n", currentData.analog_raw);
  Serial.printf("   ⚡ Voltaj: %.3fV\n", currentData.gas_voltage);
  Serial.printf("   💨 Gaz Seviyesi: %.2f ppm\n", currentData.gas_level_ppm);
  Serial.printf("   🔴 Dijital Alarm: %s\n", currentData.digital_alarm ? "AKTIF" : "NORMAL");
  Serial.printf("   🌡️ Sıcaklık: %.2f°C\n", currentData.temperature);
  Serial.printf("   💧 Nem: %.2f%%\n", currentData.humidity);
}

float calculateGasPPM(int rawValue) {
  // Voltaj hesaplama
  float voltage = (rawValue / 4095.0) * 3.3;
  
  // Direnç hesaplama (voltaj bölücü devresi)
  if (voltage <= 0.01) voltage = 0.01; // Sıfıra bölme hatası önleme
  
  float rs = ((3.3 * RL) / voltage) - RL;
  
  // Rs/R0 oranı
  float ratio = rs / R0;
  
  // MQ-2 için karakteristik eğriye göre ppm hesaplama
  // Bu formül MQ-2'nin LPG/Propan eğrisine dayanır
  float ppm = 613.9 * pow(ratio, -2.074);
  
  // Negatif değerleri engelle
  if (ppm < 0) ppm = 0;
  if (ppm > 10000) ppm = 10000; // Maksimum limit
  
  return ppm;
}

float readBatteryVoltage() {
  // Basit voltaj ölçümü
  return 3.7; // Sabit değer (gerçek projede ADC kullanın)
}

void calibrateMQ2() {
  Serial.println("\n🔧 MQ-2 Sensörü Kalibrasyonu Başlatılıyor...");
  Serial.println("⚠️  Sensörü temiz hava ortamında bulundurun!");
  Serial.println("📏 Kalibrasyon için 10 örnek alınacak...");
  
  delay(2000); // Kullanıcının okuması için bekle
  
  float voltageSum = 0;
  int samples = 10;
  
  for (int i = 0; i < samples; i++) {
    int rawValue = analogRead(MQ2_ANALOG_PIN);
    float voltage = (rawValue / 4095.0) * 3.3;
    voltageSum += voltage;
    
    Serial.printf("📊 Örnek %d/%d - Raw: %d, Voltaj: %.3fV\n", i + 1, samples, rawValue, voltage);
    delay(500);
  }
  
  float avgVoltage = voltageSum / samples;
  
  // R0 hesaplama (temiz havada Rs = R0)
  if (avgVoltage > 0.01) {
    R0 = ((3.3 * RL) / avgVoltage) - RL;
  }
  
  Serial.println("\n📊 Kalibrasyon Sonuçları:");
  Serial.printf("   🔵 Ortalama Voltaj: %.3fV\n", avgVoltage);
  Serial.printf("   🔵 Hesaplanan R0: %.2f kΩ\n", R0);
  
  if (R0 > 0 && R0 < 100) {
    Serial.println("✅ MQ-2 kalibrasyon başarılı!");
  } else {
    Serial.println("⚠️  Kalibrasyon anormal - varsayılan R0 kullanılacak");
    R0 = 10.0; // Varsayılan değer
  }
}

void checkAlarms() {
  bool alarmTriggered = false;
  
  // Dijital pin alarmı (donanım eşiği)
  if (currentData.digital_alarm) {
    Serial.println("🚨 MQ-2 DİJİTAL ALARM! Donanım eşiği aşıldı!");
    alarmTriggered = true;
  }
  
  // Analog değer alarmı (yazılım eşiği)
  if (currentData.gas_level_ppm > GAS_THRESHOLD_PPM) {
    Serial.printf("🚨 MQ-2 GAZ ALARM! Seviye: %.2f ppm (Eşik: %.2f)\n", 
                  currentData.gas_level_ppm, GAS_THRESHOLD_PPM);
    alarmTriggered = true;
  }
  
  // Sıcaklık alarmı
  if (currentData.temperature > TEMP_THRESHOLD) {
    Serial.printf("🚨 SICAKLIK ALARM! Seviye: %.2f°C (Eşik: %.2f)\n", 
                  currentData.temperature, TEMP_THRESHOLD);
    alarmTriggered = true;
  }
  
  currentData.alarm_status = alarmTriggered;
  
  if (alarmTriggered) {
    triggerAlarm();
  }
}

void triggerAlarm() {
  // Buzzer ve LED alarmı
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
    // Alarm durumu - kırmızı LED yanıp sönsün
    digitalWrite(LED_RED_PIN, millis() % 1000 < 500);
    digitalWrite(LED_GREEN_PIN, LOW);
    digitalWrite(ONBOARD_LED, millis() % 500 < 250);
  } else {
    // Normal durum - yeşil LED sabit
    digitalWrite(LED_GREEN_PIN, HIGH);
    digitalWrite(LED_RED_PIN, LOW);
  }
}

void testLEDs() {
  Serial.println("🔍 LED testi yapılıyor...");
  
  // Dahili LED testi
  digitalWrite(ONBOARD_LED, HIGH);
  delay(300);
  digitalWrite(ONBOARD_LED, LOW);
  delay(300);
  
  // Kırmızı LED
  digitalWrite(LED_RED_PIN, HIGH);
  delay(300);
  digitalWrite(LED_RED_PIN, LOW);
  
  // Yeşil LED
  digitalWrite(LED_GREEN_PIN, HIGH);
  delay(300);
  digitalWrite(LED_GREEN_PIN, LOW);
  
  // Mavi LED
  digitalWrite(LED_BLUE_PIN, HIGH);
  delay(300);
  digitalWrite(LED_BLUE_PIN, LOW);
  
  // Buzzer testi
  digitalWrite(BUZZER_PIN, HIGH);
  delay(200);
  digitalWrite(BUZZER_PIN, LOW);
  
  Serial.println("✅ LED testi tamamlandı!");
}

void sendDataToServer() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("❌ WiFi bağlantısı yok");
    return;
  }
  
  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");
  if (strlen(API_KEY) > 1) {
    http.addHeader("Authorization", String("Bearer ") + API_KEY);
  }
  http.setTimeout(15000); // 15 saniye timeout
  
  // JSON verisi oluştur
  DynamicJsonDocument doc(512);
  doc["device_id"] = DEVICE_ID;
  doc["co_level"] = currentData.gas_level_ppm;
  
  // Ek bilgiler
  doc["sensor_type"] = "MQ-2";
  doc["gas_voltage"] = currentData.gas_voltage;
  doc["analog_raw"] = currentData.analog_raw;
  doc["digital_alarm"] = currentData.digital_alarm;
  doc["temperature"] = currentData.temperature;
  doc["humidity"] = currentData.humidity;
  doc["alarm_status"] = currentData.alarm_status;
  doc["wifi_rssi"] = currentData.wifi_rssi;
  doc["uptime"] = currentData.uptime;
  
  String jsonString;
  serializeJson(doc, jsonString);
  
  Serial.println("📤 Sunucuya MQ-2 verisi gönderiliyor...");
  Serial.println("📋 JSON Verisi: " + jsonString);
  Serial.println("🔗 URL: " + String(SERVER_URL));
  
  int httpResponseCode = http.POST(jsonString);
  
  Serial.printf("📡 HTTP Response Code: %d\n", httpResponseCode);
  
  if (httpResponseCode > 0) {
    String response = http.getString();
    Serial.println("📥 Sunucu Yanıtı: " + response);
    
    if (httpResponseCode == 200) {
      Serial.println("✅ Veri başarıyla gönderildi!");
      // Başarı işareti
      digitalWrite(LED_GREEN_PIN, HIGH);
      delay(100);
      digitalWrite(LED_GREEN_PIN, LOW);
      delay(100);
      digitalWrite(LED_GREEN_PIN, HIGH);
    } else {
      Serial.printf("⚠️ HTTP Hatası: %d - %s\n", httpResponseCode, response.c_str());
    }
  } else {
    Serial.printf("❌ Bağlantı Hatası: %d\n", httpResponseCode);
    Serial.println("❌ Possible causes:");
    Serial.println("   - Server not running");
    Serial.println("   - Wrong IP address");
    Serial.println("   - Firewall blocking");
    Serial.println("   - Network connectivity issue");
  }
  
  http.end();
}

String getFormattedTime() {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) {
    Serial.println("⚠️ Zaman bilgisi alınamadı, millis() kullanılıyor");
    return String(millis());
  }
  
  char timeString[50];
  strftime(timeString, sizeof(timeString), "%Y-%m-%d %H:%M:%S", &timeinfo);
  return String(timeString);
}

void printSystemStatus() {
  Serial.println("\n========== DENEYAP MİNİ MQ-2 SİSTEM DURUMU ==========");
  Serial.printf("🔧 Device ID: %s\n", DEVICE_ID.c_str());
  Serial.printf("💻 Board: Deneyap Mini\n");
  Serial.printf("🔍 Sensör: MQ-2 (LPG, CH4, CO, Alkol, Duman)\n");
  Serial.printf("🌐 Server URL: %s\n", SERVER_URL);
  Serial.printf("📡 WiFi SSID: %s\n", WIFI_SSID);
  Serial.printf("📍 IP Address: %s\n", WiFi.localIP().toString().c_str());
  Serial.printf("📶 WiFi RSSI: %d dBm\n", WiFi.RSSI());
  Serial.printf("💾 Free Heap: %d bytes\n", ESP.getFreeHeap());
  Serial.printf("🔧 R0 Kalibrasyon: %.2f kΩ\n", R0);
  Serial.println("=====================================================\n");
}