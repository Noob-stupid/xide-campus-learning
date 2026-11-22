/*
 * 习得 KeepLit · ESP32 + HC-SR04 超声波座位传感器
 * 接线：VCC 5V, GND, TRIG GPIO5, ECHO GPIO18（ECHO 需 1k/2k 分压到 3.3V）
 * 协议：register -> report {distance_cm}；服务端阈值默认 50cm
 */
#include <WiFi.h>
#include <HTTPClient.h>
#include "secrets.h"

const char* SERVER = SERVER_BASE;
const char* DEVICE_ID = SEAT_DEVICE_ID;
const int PIN_TRIG = 5;
const int PIN_ECHO = 18;
const float THRESHOLD_CM = 50.0;
const unsigned long REPORT_MS = 3000;

int seatId = -1;

static int extractInt(const String& body, const char* key) {
  int p = body.indexOf(key);
  if (p < 0) return -1;
  p = body.indexOf(':', p);
  if (p < 0) return -1;
  p++;
  while (p < (int)body.length() && (body[p] == ' ' || body[p] == '"')) p++;
  int start = p;
  while (p < (int)body.length() && body[p] >= '0' && body[p] <= '9') p++;
  if (p == start) return -1;
  return body.substring(start, p).toInt();
}

static bool postJson(const String& path, const String& payload, String& response) {
  if (WiFi.status() != WL_CONNECTED) return false;
  HTTPClient http;
  http.begin(String(SERVER) + path);
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(payload);
  response = http.getString();
  http.end();
  return code >= 200 && code < 300;
}

static void registerDevice() {
  String resp;
  String payload = String("{\"device_id\":\"") + DEVICE_ID + "\"}";
  if (postJson("/api/sensor/device/register", payload, resp)) {
    seatId = extractInt(resp, "seat_id");
    Serial.printf("register: %s, seat_id=%d\n", resp.c_str(), seatId);
  } else {
    Serial.printf("register failed: %s\n", resp.c_str());
  }
}

static float readDistanceCm() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(5);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  unsigned long us = pulseIn(PIN_ECHO, HIGH, 30000UL);
  if (us == 0) return 0;
  return (us * 0.0343) / 2.0;
}

static void report() {
  if (seatId < 0) { registerDevice(); return; }
  float distance = readDistanceCm();
  String payload = String("{\"device_id\":\"") + DEVICE_ID +
                   "\",\"seat_id\":" + String(seatId) +
                   ",\"distance_cm\":" + String(distance, 1) +
                   ",\"threshold_cm\":" + String(THRESHOLD_CM, 1) + "}";
  String resp;
  if (postJson("/api/sensor/report", payload, resp)) {
    Serial.printf("distance=%.1fcm: %s\n", distance, resp.c_str());
  } else {
    Serial.printf("report failed: %s\n", resp.c_str());
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  digitalWrite(PIN_TRIG, LOW);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("WiFi connecting");
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.printf("\nWiFi connected: %s\n", WiFi.localIP().toString().c_str());
  registerDevice();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) { WiFi.reconnect(); delay(2000); return; }
  report();
  delay(REPORT_MS);
}
