/*
 * 习得 KeepLit · ESP32 座位占位传感器
 * 硬件：ESP32 DevKit + 2 × HC-SR501 PIR
 * 接线：PIR VCC -> 5V, GND -> GND, OUT1 -> GPIO23(ir_front), OUT2 -> GPIO27(ir_back)
 * 协议：register -> config -> report（与 services/devices.py 对齐）
 */
#include <WiFi.h>
#include <HTTPClient.h>
#include "secrets.h"

const char* SERVER = SERVER_BASE;
const char* DEVICE_ID = SEAT_DEVICE_ID;
const int PIN_FRONT = 23;
const int PIN_BACK = 27;
const unsigned long REPORT_MS = 5000;

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
  String url = String(SERVER) + path;
  http.begin(url);
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

static void report() {
  if (seatId < 0) { registerDevice(); return; }
  int front = digitalRead(PIN_FRONT) == HIGH ? 1 : 0;
  int back = digitalRead(PIN_BACK) == HIGH ? 1 : 0;
  String payload = String("{\"device_id\":\"") + DEVICE_ID +
                   "\",\"seat_id\":" + String(seatId) +
                   ",\"ir_front\":" + String(front) +
                   ",\"ir_back\":" + String(back) + "}";
  String resp;
  if (postJson("/api/sensor/report", payload, resp)) {
    Serial.printf("report front=%d back=%d: %s\n", front, back, resp.c_str());
  } else {
    Serial.printf("report failed: %s\n", resp.c_str());
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_FRONT, INPUT);
  pinMode(PIN_BACK, INPUT);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("WiFi connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\nWiFi connected: %s\n", WiFi.localIP().toString().c_str());
  registerDevice();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.reconnect();
    delay(2000);
    return;
  }
  report();
  delay(REPORT_MS);
}
