# 硬件沙盒联调（2026-10-24）

## 设备

- 硬件沙盒：`dsh-breadboard`
- 型号：`esp32-seat-sensor` + 2× `hc-sr501`
- 协议：`zhizuo-sensor`
- 设备号：`AA:BB:CC:11:22:33`
- 服务端：`http://127.0.0.1:5820`

## 接线映射

```text
PIR#1 OUT → GPIO23 → ir_front
PIR#2 OUT → GPIO27 → ir_back
```

## 实测

1. 硬件沙盒启动后自动注册，服务端返回：

```json
{"registered":true,"config":{"seat_id":1,"seat_code":"A-01","report_interval_ms":5000,"ir_active_high":true}}
```

2. 遮挡两块 PIR：

```text
c2 ir_front = true
c3 ir_back  = true
```

3. 服务端 `/api/seats?floor_id=1`：

```text
A-01 -> occupied
A-02 -> free
```

4. 取消遮挡并连续两次“无人”上报后释放（协议按两块 PIR 同时为 1 才占用）。

## 说明

- 这是硬件沙盒的虚拟 ESP32/PIR 数据，不是真机烧录；
- 服务端已实现 `device/register`、`device_config`、`report` 三个兼容接口；
- 真机接入时只需把 `endpoint` 换成部署地址，并让设备上报同一协议。
