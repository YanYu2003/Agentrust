# Agentrust - Agent 身份与权限系统

基于证书链 + 能力令牌的去中心化 Agent 身份与权限管理方案。

## 快速开始

### 方式 A：一键演示（推荐）

**前置：** Python 3.10+；建议先在后端目录执行 `scripts\setup.bat` 安装依赖并 `init_db`。Dashboard 需本机已安装 **Node.js / npm**。

**Windows**

```batch
cd backend\scripts
run_demo.bat
```

**Linux / macOS**

```bash
cd backend/scripts
bash run_demo.sh
```

脚本将依次：启动 IAM（8000）并等待 `/health` → 启动三个场景 Agent（8001/8002/8003）→ 启动 Dashboard（5173）→ 运行 `demo_cycle4_normal.py` 与 `demo_cycle4_abnormal.py` → 打开浏览器。控制台会打印 **`task_id`、`agent_id`、`session_token`**，用于 Dashboard「演示 Session Token」登录或 Swagger `GET /api/v1/audit/trace/{task_id}`。

详细步骤与截图占位说明见根目录 **`演示Demo-评委导读.md`**。

仅启动服务、暂不跑 Python 演示：`set SKIP_DEMOS=1` 后执行 `run_demo.bat`。

### 方式 B：经典 Demo 脚本（委托链长流程）

### 1. 进入后端目录

```bash
cd backend
```

### 2. 初始化系统（Windows 用户）

```bash
scripts\reset.bat
```

Linux/macOS 用户：
```bash
bash scripts/reset.sh
```

### 3. 运行演示

```bash
python scripts/demo.py
```

或者使用：
```bash
python -X utf8 scripts/demo.py   # Windows 中文环境
```

## 项目结构

```
Agentrust/
├── backend/                 # 后端服务 (Python/FastAPI)
│   ├── app/                 # 应用代码
│   │   ├── api/             # API 路由
│   │   ├── services/        # 业务逻辑
│   │   └── crypto/          # 密码学工具
│   ├── scripts/
│   │   ├── reset.bat/sh     # 清空 DB + init_db
│   │   ├── setup.bat        # venv + pip + init_db
│   │   ├── run_demo.bat/sh  # 第四周期一键演示（IAM + Agents + Dashboard + Cycle4 脚本）
│   │   ├── spawn_uvicorn.bat # 子进程启动 uvicorn（规避 Windows start 与 main:app）
│   │   ├── demo_cycle4_*.py # 正常 / 异常演示脚本
│   │   ├── demo.py          # 经典委托链长流程演示
│   │   └── init_db.py       # 数据库初始化
│   ├── tests/               # 测试代码
│   ├── data/                # 数据库文件目录
│   └── requirements.txt     # Python 依赖
│
├── agentrust-sdk/           # Agent SDK (Python)
│   ├── agentrust/           # SDK 核心代码
│   ├── examples/            # 示例代码
│   └── README.md            # SDK 说明
│
├── dashboard/               # Web 管理面板 (React/TypeScript)
│   ├── src/                 # 源代码
│   ├── public/              # 静态资源
│   └── README.md            # Dashboard 说明
│
├── 演示Demo-评委导读.md      # 演示说明文档
├── Agentrust-Demo-Judges.docx # （可选）python backend/scripts/build_demo_word_doc.py 生成
└── DEPLOYMENT.md            # 部署指南
```

## 功能演示

运行 `demo.py` 可以看到以下场景：

1. **Agent 注册与证书签发** - 三个 Agent 完成注册
2. **挑战-响应认证** - ECDSA P-256 签名验证
3. **带衰减的委托授权** - 限制字段、行数、委托深度
4. **被委托者操作** - 使用委托令牌执行操作
5. **越权拦截** - 能力、资源、深度超限被拒绝
6. **证书吊销** - 吊销后整条委托链失效

## 技术栈

| 组件 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| 数据库 | SQLite (aiosqlite) |
| 密码学 | ECDSA P-256, AES-256-GCM |
| SDK | Python 3.10+ |
| 前端 | React 18 + TypeScript + Ant Design |

## 运行测试

```bash
cd backend
python -m pytest tests/ -v
```

## Dashboard 登录（演示）

1. 运行 `run_demo.bat` 后，在正常演示完成输出中复制 **`session_token`** 与同次的 **`agent_id`**。  
2. 打开 http://localhost:5173/login ，将 Token 粘贴到 **「演示 Session Token」**，填写 **Agent ID**，登录（成功后整页跳转进入仪表盘）。  
3. 侧边栏 **「任务链路」** 中输入控制台打印的 **`task_id`** 查询。

