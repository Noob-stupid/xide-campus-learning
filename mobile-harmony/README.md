# 习得 · HarmonyOS Web 壳

把习得 Web 应用套壳成 HarmonyOS NEXT 的 HAP。

## 它是什么

- 一个 Stage 模型的 HarmonyOS 工程；
- 一个 Web 组件加载习得的 HTTPS 页面；
- 不是把 Flask 页面打进 HAP，也不是原生重写；
- 定位、文件选择、Cookie、返回键由 WebView + 系统能力负责。

## 先改地址

打开 entry/src/main/ets/pages/Index.ets，把：

    private readonly webUrl: string = 'https://xide.example.com';

改成你部署好的习得 HTTPS 地址。必须是 HTTPS，当前 mixedMode 为 None。

## 用 DevEco Studio 打开

1. DevEco Studio 5.0 及以上，HarmonyOS SDK API 12 及以上；
2. Open Project 选择 mobile-harmony；
3. 等待 hvigor 同步；
4. File → Project Structure → Signing Configs 配置自动签名；
5. 连接真机或启动模拟器；
6. Run entry。

## 已配置

- bundleName: site.xide.campus
- 设备：phone / tablet
- 权限：INTERNET、LOCATION、APPROXIMATELY_LOCATION
- WebView：DOM storage、文件选择、定位、缩放、返回键
- 启动页背景：#0F2A4A

## 当前边界

- 没有原生桥 javaScriptProxy；首版只依赖 Web 自身能力；
- 通知、扫码、震动、外部地图跳转还没接原生；
- 高德/华为地图 Key 未配置；
- 页面必须 HTTPS 部署后才能加载；
- 没有真机/DevEco 环境时无法在这里编译 HAP。

## 下一步

- 部署 HTTPS 后替换 webUrl；
- 用 DevEco 签名打包 HAP；
- 需要原生通知/扫码时，再按 docs/移动端功能交接文档.md 加 javaScriptProxy 桥。
