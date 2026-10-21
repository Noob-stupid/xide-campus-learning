# 队友 Onboarding 一键清单

> 华为 ICT 大赛创新赛赛题1 · 习得项目
> 方案：GitHub 协作开发 → 华为云 CodeArts 定时同步（仓库只读镜像）

---

## 〇、你要准备什么

- [ ] GitHub 账号（没有就注册一个）
- [ ] Python 3.10+ 装好
- [ ] 华为云账号（已实名认证）
- [ ] 码道 CodeArts 客户端（必选智能体，赛题要求）

---

## 一、接受 GitHub 协作邀请（1 分钟）

队长会在 GitHub 仓库 `Noob-stupid/xide-campus-learning` 把你加为 Collaborator。

1. 查收 GitHub 邮件邀请 → 点 **Accept Invite**
2. 或直接打开：`https://github.com/Noob-stupid/xide-campus-learning`
3. 确认能看到 Code 标签页 → 成功

---

## 二、用 CodeArts（智能体）clone GitHub 仓库（2 分钟）

### 方式 A：在 CodeArts 里直接 clone（推荐）

1. 打开码道 CodeArts（`codearts.huaweicloud.com`）
2. 新建工作区 / 打开终端
3. 执行：

```bash
git clone https://github.com/Noob-stupid/xide-campus-learning.git
cd xide-campus-learning
```

4. 首次 push 会弹 GitHub 登录框 → 授权 → 以后自动记住

### 方式 B：本地终端 clone，再用 CodeArts 打开文件夹

```bash
git clone https://github.com/Noob-stupid/xide-campus-learning.git
```

然后在 CodeArts 里 `Open Folder` 打开这个目录。

---

## 三、配置 Git 身份（只做一次）

```bash
git config --global user.name "你的名字"
git config --global user.email "你的GitHub邮箱"
```

---

## 四、本地能跑起来（验证环境 OK）

```bash
cd xide-campus-learning
python -m pip install -r requirements.txt
python seed.py --reset      # 初始化演示数据
python app.py               # 启动 → 浏览器打开 http://127.0.0.1:5820
```

演示账号（密码均 `123456`）：

| 账号 | 角色 |
|------|------|
| `student` | 学生 林晓 |
| `reviewer` | 审核员 周老师 |
| `admin` | 管理员 |
| `teacher` | 教师 陈老师 |

跑测试：

```bash
python -m pytest -q
# 应看到 78 passed
```

---

## 五、日常开发流程（贴在桌面）

### 开始干活

```bash
git checkout master
git pull origin master
git checkout -b feature/你的名字-功能描述
```

### 干完活

```bash
git add .
git commit -m "feat: 简要说明"
git push origin feature/你的名字-功能描述
```

### 发 Pull Request

去 GitHub 网页：
```
Pull requests → New pull request
  源分支：feature/你的名字-功能描述
  目标分支：master
  填标题描述 → 指定队友评审 → Create
```

评审通过后合入 master，华为云 CodeArts 仓库自动同步。

---

## 六、分工建议

| 队员 | 负责 | 建议分支 |
|------|------|----------|
| A | 后端 services / 智能体逻辑 / RDS·Redis 对接 | `feature/A-backend` |
| B | 前端 templates / static / UI 打磨 | `feature/B-frontend` |
| C | 部署 / 文档 / 测试 / 华为云服务 / CodeArts 证据 | `feature/C-deploy` |

---

## 七、项目结构速览

```
xide-campus-learning/
├── app.py              # Flask 主应用（30KB，所有路由）
├── config.py           # 配置（环境变量驱动）
├── db.py               # SQLite 访问层（待迁 RDS）
├── seed.py             # 演示数据（79座位/4用户/5内容）
├── services/           # 业务逻辑
│   ├── agents.py       # 智能体意图路由
│   ├── seats.py        # 座位/预约/签到
│   ├── navigation.py   # A* 室内导航
│   ├── content.py      # 抽帧/AI初筛/复核
│   ├── relay.py        # 接棒推送
│   ├── tutor.py        # 苏格拉底辅导
│   ├── flow.py         # 工作流引擎
│   ├── outdoor.py      # 室外导航
│   └── devices.py      # ESP32 设备
├── templates/          # 14 个页面模板
├── static/             # CSS/JS
├── tests/              # 78 条测试
└── docs/               # 产品/架构/UI/华为云文档
```

---

## 八、华为云 CodeArts 仓库（只读，不用碰）

- 地址：`https://codehub.devcloud.cn-north-4.huaweicloud.com/a536e0133fe04108987565f2a828822c/xide-campus-learning.git`
- 已开启定时同步，自动从 GitHub 拉取最新代码
- **你不需要直接连这个仓库**，只管 GitHub 开发即可
- 提交作品时，华为云仓库会自动有最新代码

---

## 九、遇到问题

| 问题 | 解决 |
|------|------|
| clone 慢/超时 | 用代理：`git clone https://ghproxy.net/https://github.com/Noob-stupid/xide-campus-learning.git` |
| push 被拒 | 先 `git pull origin master` 同步再推 |
| 冲突 | 看到标记 `<<<<<<< ======= >>>>>>>` 手动选保留哪段，再 add+commit |
| 测试失败 | `python -m pytest -q` 看哪个挂了，贴给队长 |
| Python 依赖装不上 | `python -m pip install --upgrade pip` 再试 |

---

**就这些。clone 完 → 跑起来 → 开分支 → 干活 → PR。**
