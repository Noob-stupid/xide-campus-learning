# 习得 · HarmonyOS 端

HarmonyOS NEXT 工程：原生 ArkUI 主界面 + Web 兜底页。

## 当前结构

- `pages/Index.ets`：启动页，校验持久化 Cookie 后进登录或主界面。
- `pages/Login.ets`：账号密码登录，演示账号 `student / reviewer / admin / teacher`，密码 `123456`。
- `pages/Main.ets`：底部 5 Tab：今日 / 空间 / 学习 / 接力池 / 我的。
- `components/HomeView.ets`：首页数据卡、当前场次、建议、接棒。
- `components/SeatsView.ets`：先选建筑/楼层，再选座位、筛选、推荐、预约。
- `pages/NavPage.ets`：室内 A* 路径（Canvas 绘制）+ 分步指引；入口可切到室外导航。
- `pages/OutdoorPage.ets`：室外步行距离/方向/分钟/步骤，使用后端校门演示坐标。
- `components/LearnView.ets`：学习计时、卡住了辅导、接棒卡、反馈。
- `components/PoolView.ets`：已过审内容卡片；右上角「交棒」走 Web 兜底。
- `components/ProfileView.ets`：学习档案、资料编辑、退出；头像/封面编辑走 Web 兜底。
- `pages/WebShell.ets`：Web 兜底页，支持 `path` 参数，例如：
  - `pages/WebShell?path=/upload`
  - `pages/WebShell?path=/profile`
- `net/Api.ets`：HTTP 客户端、Cookie 持久化、全部业务 API。
- `model/Types.ets`：接口类型。

## 先改地址

打开 `entry/src/main/ets/net/Api.ets`，把：

    export const BASE_URL: string = 'https://xide.example.com';

改成已部署的习得 HTTPS 地址。必须是 HTTPS；WebShell 的 mixedMode 为 None。

## 用 DevEco Studio 打开

1. DevEco Studio 5.0 及以上，HarmonyOS SDK API 12 及以上；
2. Open Project 选择 `mobile-harmony`；
3. 等待 hvigor 同步；
4. File → Project Structure → Signing Configs 配置自动签名；
5. 连接真机或启动模拟器；
6. Run entry。

## 已配置

- bundleName: `site.xide.campus`
- 设备：phone / tablet
- 权限：INTERNET、LOCATION、APPROXIMATELY_LOCATION
- 启动页背景：`#0F2A4A`
- 登录后 Cookie 持久化到 Preferences；启动时先 `Api.init` 再进页面，避免误判未登录。

## 当前边界

- 本机没有 DevEco Studio / HarmonyOS SDK，工程尚未编译、未签名、未真机验证；
- 交棒上传、头像/封面编辑暂时走 WebShell 网页兜底，不是原生表单；
- 室外导航当前用后端校门演示坐标，未接原生定位；
- 本地通知、扫码、震动等原生桥未接；
- 没有 HAP 构建产物。

## 下一步

1. 部署 HTTPS，替换 `BASE_URL`；
2. 用 DevEco 编译、签名、真机跑通；
3. 需要纯原生上传时，再按 `docs/移动端功能交接文档.md` 接 `photoAccessHelper` / `request.uploadFile`。
