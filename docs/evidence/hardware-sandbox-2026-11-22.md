# 硬件沙盒端到端测试（2026-11-22）

## 场景

- 插件：`dsh-breadboard`
- 装配：`esp32-seat-sensor` + 2 × `hc-sr501`
- 接线：PIR#1 OUT → GPIO23 / E4；PIR#2 OUT → GPIO27 / E19
- 协议：`zhizuo-sensor`
- 服务端：`http://127.0.0.1:5820`

## 实测结果

```text
register → 绑定 seat_id=1 / A-01
双 PIR 遮挡 → 设备 online，ir_front=true，ir_back=true
/api/seats?floor_id=1 → A-01 occupied
双 PIR 移开 → 连续两次无人上报
/api/seats?floor_id=1 → A-01 free
```

设备统计：

```text
c1 [zhizuo-sensor] online
上报 2 次 / 失败 0 次
绑定座位 1
```

## 结论

- 接线映射、协议注册、双 PIR 占用、连续两次无人释放均已验证；
- 这是虚拟硬件沙盒，不是实物板烧录；
- 实物接入按 `hardware/README.md` 接线并烧录 `hardware/esp32_seat_sensor/esp32_seat_sensor.ino`。
