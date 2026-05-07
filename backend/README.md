# Agentrust Backend

Agent 身份与权限系统的后端服务。

## 技术栈

- Python 3.10+
- FastAPI - Web 框架
- SQLite - 数据库
- ECDSA P-256 - 密码学签名
- SQLAlchemy (async) - ORM

## 快速开始（推荐评委使用）

### Windows 用户

```batch
cd backend
scripts\reset.bat
python -X utf8 scripts\demo.py
```

### Linux/macOS 用户

```bash
cd backend
bash scripts/reset.sh
PYTHONIOENCODING=utf-8 python scripts/demo.py
```

---

## 完整安装步骤

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 初始化数据库

```bash
python scripts/init_db.py
```

### 3. 启动服务器

```bash
uvicorn main:app --reload --port 8000
```

服务器启动后访问:
- API 文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/health

## 一键启动脚本（第四周期）

**Windows（推荐评委）：** 在 `backend` 目录执行 `scripts\run_demo.bat` — 拉起 IAM（8000）、三个 Agent（8001/8002/8003）、Dashboard（5173，需 npm）、探活通过后运行 `demo_cycle4_normal.py` 与 `demo_cycle4_abnormal.py`。详见仓库根目录 **`演示Demo-评委导读.md`**。

**Linux/macOS：** `bash scripts/run_demo.sh`

- **仅起服务不跑演示：** `SKIP_DEMOS=1 bash scripts/run_demo.sh`（Windows：`set SKIP_DEMOS=1` 再运行 bat）。
- **子进程启动：** `spawn_uvicorn.bat` 通过环境变量 `UVICORN_APP` / `UVICORN_PORT` 传入模块与端口，避免在 Windows `start` 下传入 `main:app` 触发路径解析错误。

### 经典启动（单 IAM 进程）

### Linux/macOS

```bash
# 首次设置
./scripts/setup.sh

# 启动服务器
./scripts/start_server.sh
```

### Windows

```batch
REM 首次设置
scripts\setup.bat

REM 启动 IAM 单服务
scripts\start_server.bat
```

## 项目结构

```
backend/
├── app/
│   ├── api/              # API 路由
│   ├── config.py         # 配置管理
│   ├── crypto/           # 密码学工具
│   ├── database.py       # 数据库初始化
│   ├── middleware/       # 中间件
│   ├── models/           # 数据模型
│   ├── schemas/          # Pydantic 模型
│   ├── services/         # 业务逻辑
│   └── utils/            # 工具函数
├── scripts/
│   ├── init_db.py              # 数据库初始化
│   ├── demo.py                 # 经典委托链长流程演示
│   ├── demo_cycle4_normal.py   # 第四周期正常链路
│   ├── demo_cycle4_abnormal.py # 第四周期异常 / 越权
│   ├── run_demo.bat / run_demo.sh
│   ├── spawn_uvicorn.bat
│   └── wait_health.py
├── tests/
│   ├── conftest.py       # 测试配置
│   ├── test_crypto.py    # 密码学测试
│   ├── test_ca_service.py # CA 服务测试
│   ├── test_token_verifier.py # 令牌验证测试
│   ├── test_delegation.py # 委托测试
│   └── integration/      # 集成测试
├── data/                  # 数据库文件目录
├── main.py               # FastAPI 入口
└── requirements.txt       # 依赖
```

## 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行集成测试
pytest tests/integration/ -v

# 查看测试覆盖率
pytest tests/ --cov=app --cov-report=html
```

## API 端点

### CA Service

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/v1/ca/register` | POST | 注册 Agent 并签发证书 |
| `/api/v1/ca/auth/challenge` | POST | 获取认证挑战 |
| `/api/v1/ca/auth/verify` | POST | 验证签名完成认证 |
| `/api/v1/ca/revoke` | POST | 吊销证书 |
| `/api/v1/ca/crl` | GET | 获取 CRL |

### 资源操作

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/v1/resources/execute` | POST | 执行受保护操作 |

### 委托

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/v1/delegate` | POST | 创建委托令牌 |
| `/api/v1/agents/{agent_id}/tokens` | GET | 查询 Agent 的令牌 |

### 审计

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/v1/audit/logs` | GET | 查询审计日志（支持 task_id 等筛选） |
| `/api/v1/audit/logs/{log_id}` | GET | 获取日志详情 |
| `/api/v1/audit/trace/{task_id}` | GET | 按 task_id 聚合任务链路 |
| `/api/v1/audit/tasks/recent` | GET | 近期带 task_id 的任务摘要 |
| `/api/v1/audit/delegation-graph` | GET | 获取委托关系图 |
| `/api/v1/audit/alert-status` | GET | 获取告警状态 |

## Demo 演示

### 经典脚本 `demo.py`

```bash
python scripts/demo.py
```

场景概要：Analyst 注册与读表 → 委托 Reporter → 越权拦截 → 吊销。

### 第四周期脚本（需 IAM 已运行在 8000，或由 `run_demo` 一并启动）

```bash
python scripts/demo_cycle4_normal.py
python scripts/demo_cycle4_abnormal.py
```

控制台将打印 **`task_id`、`agent_id`、`session_token`**，供 Dashboard「演示 Session Token」登录或 Swagger **`GET /api/v1/audit/trace/{task_id}`**。

## 配置

环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `sqlite+aiosqlite:///data/agentrust.db` | 数据库 URL |
| `SESSION_SECRET` | (必需) | Session Token 签名密钥 |
| `CA_KEY_PASSWORD` | (必需) | CA 私钥加密密码 |
| `LOG_LEVEL` | `INFO` | 日志级别 |

## API 文档

服务器启动后访问:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
