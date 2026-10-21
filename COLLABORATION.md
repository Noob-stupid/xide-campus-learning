# 团队协作指南

> 华为 ICT 大赛创新赛赛题1 — xide-campus-learning 项目

## 仓库地址

- **HTTPS（推荐）**：`https://codehub.devcloud.cn-north-4.huaweicloud.com/a536e0133fe04108987565f2a828822c/xide-campus-learning.git`
- **SSH**：`git@codehub.devcloud.cn-north-4.huaweicloud.com:a536e0133fe04108987565f2a828822c/xide-campus-learning.git`

---

## 一、首次配置（每个队员只做一次）

### 1. 配置 Git 身份

```bash
git config --global user.name "你的名字"
git config --global user.email "你的邮箱"
```

### 2. 配置 HTTPS 密码（推荐，最省事）

1. 登录华为云控制台 → CodeArts DevOps → 进入项目
2. 单击右上角用户名 → **个人设置 → 代码托管 → HTTPS 密码**
3. 设置一个 HTTPS 密码（记住它，clone/push 时要用）

### 3. clone 仓库

```bash
git clone https://codehub.devcloud.cn-north-4.huaweicloud.com/a536e0133fe04108987565f2a828822c/xide-campus-learning.git
cd xide-campus-learning
```

输入华为云用户名和刚才设置的 HTTPS 密码即可。

> 如果用 SSH 方式，需先生成密钥 `ssh-keygen -t rsa`，把 `~/.ssh/id_rsa.pub` 公钥加到 CodeArts「个人设置 → SSH密钥」。

---

## 二、日常开发流程

**核心原则：不要直接往 master 上推！各自开分支，通过合并请求（MR）合并。**

### Step 1：拉最新代码

```bash
git checkout master
git pull origin master
```

### Step 2：建功能分支

分支命名规范：`feature/你的名字-功能描述`

```bash
git checkout -b feature/zhangsan-登录优化
```

### Step 3：写代码

正常开发，改文件、测试。

### Step 4：提交并推送

```bash
git add .
git commit -m "feat: 简要说明你做了什么"
git push origin feature/zhangsan-登录优化
```

提交信息规范：
- `feat:` 新功能
- `fix:` 修 bug
- `docs:` 文档改动
- `refactor:` 重构
- `test:` 测试相关

### Step 5：创建合并请求（MR）

去 CodeArts DevOps 网页操作：

```
仓库页面 → 合并请求 → 新建合并请求
    ↓ 源分支：feature/zhangsan-登录优化
    ↓ 目标分支：master
    ↓ 填标题和描述
    ↓ 指定评审人（其他队友）
    ↓ 提交
```

### Step 6：评审合入

- 评审人看代码，提意见或批准
- 审核通过 → 合入 master
- 合入后，其他人 `git pull origin master` 同步

---

## 三、解决冲突

两人改了同一文件时，合并可能冲突：

```bash
# 在你的功能分支上
git fetch origin
git merge origin/master
# 提示冲突后：
#   1. 打开冲突文件，手动选择保留哪部分（标记 <<<<<<< ======= >>>>>>> 的地方）
#   2. git add <冲突文件>
#   3. git commit -m "merge: 解决冲突"
#   4. git push origin feature/你的分支
```

---

## 四、快速口令（贴在桌面上）

```bash
# 开始干活
git checkout master && git pull origin master
git checkout -b feature/你的名字-功能

# 干完活
git add . && git commit -m "feat: 说明" && git push origin feature/你的名字-功能

# 然后去网页建合并请求，等评审
```

---

## 五、项目结构说明

```
xide-campus-learning/
├── app.py              # Flask 主应用入口
├── config.py           # 配置
├── db.py               # 数据库
├── seed.py             # 数据初始化
├── services/           # 业务逻辑层
│   ├── agents.py       # 智能体服务
│   ├── seats.py        # 座位服务
│   ├── navigation.py   # 导航服务
│   └── ...
├── templates/          # 前端模板（HTML）
├── static/             # 静态资源（CSS/JS）
├── tests/              # 测试
├── docs/               # 项目文档
│   ├── 交接文档.md
│   ├── 项目详细介绍.md
│   └── ...
└── requirements.txt    # Python 依赖
```

## 六、本地运行

```bash
pip install -r requirements.txt
python seed.py      # 初始化数据
python app.py       # 启动服务
```

---

## 七、分工建议

| 角色 | 负责 |
|------|------|
| 队员A | 后端 services / 智能体逻辑 |
| 队员B | 前端 templates / static |
| 队员C | 部署 / 文档 / 测试 / 华为云服务对接 |

各自在自己的分支上开发，通过 MR 合并，互不干扰。
