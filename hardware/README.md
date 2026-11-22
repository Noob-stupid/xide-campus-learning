# ESP32 座位传感器

## 接线

| HC-SR501 | ESP32 |
|---|---|
| VCC | 5V（不要接 3.3V） |
| GND | GND |
| OUT（前） | GPIO23 → `ir_front` |
| OUT（后） | GPIO27 → `ir_back` |

两块 PIR 都检测到人时才算占用；连续两次无人上报后释放。

> 接线前先断电，确认 5V/3.3V 不混接；PIR 的 OUT 是 3.3V 逻辑，可直接进 ESP32 GPIO。

## 配置

1. 复制 `secrets.h.example` 为 `secrets.h`
2. 填 Wi-Fi、服务地址、设备号
3. `SERVER_BASE` 演示可用 `http://电脑局域网IP:5820`；云端用 `https://你的域名`
4. 用 Arduino IDE / PlatformIO 编译烧录

## 固件流程

```text
WiFi 连接
  → POST /api/sensor/device/register
  → 解析 config.seat_id
  → 每 5 秒读 GPIO23 / GPIO27
  → POST /api/sensor/report {device_id, seat_id, ir_front, ir_back}
```

服务端接口在 `services/devices.py`，前端实时状态在 `/api/seats` 的 `live_status`。

## 联调验证

```bash
curl -X POST http://127.0.0.1:5820/api/sensor/device/register \
  -H 'Content-Type: application/json' \
  -d '{"device_id":"AA:BB:CC:11:22:33"}'
```

遮挡两块 PIR 后，`/api/seats?floor_id=1` 中对应座位应变为 `occupied`；两次无人后恢复 `free`。

## 当前边界

- 仓库提供固件源码和协议，不包含真实板子/烧录结果；
- 真实设备需按现场 Wi-Fi 和服务器地址修改 `secrets.h`；
- AppGallery 上架与硬件接入是两件独立的事。

## 超声波方案（主方案）

代码：`hardware/esp32_ultrasonic_sensor/esp32_ultrasonic_sensor.ino`

| HC-SR04 | ESP32 |
|---|---|
| VCC | 5V |
| GND | GND |
| TRIG | GPIO5 |
| ECHO | GPIO18（必须 1k/2k 分压到 3.3V） |

固件每 3 秒测距，上报：

```json
{"device_id":"US:AA:BB:CC:11:22","seat_id":1,"distance_cm":35.0,"threshold_cm":50.0}
```

服务端 `distance_cm > 0 && <= threshold_cm` 判定有人；连续两次无人后释放。

> ECHO 是 5V 输出，不能直接进 ESP32；先断电接好分压再上电。
