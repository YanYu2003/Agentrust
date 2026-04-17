# Agentrust - Agent 身份与权限系统

基于证书链 + 能力令牌的去中心化 Agent 身份与权限管理方案。

## 项目赛道

**飞书 AI 大模型安全赛道 · 课题二：给 AI 发通行证：构建 Agent 身份与权限系统**

## 快速开始

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
│   │   ├── reset.bat/sh     # 初始化脚本
│   │   ├── demo.py          # 演示程序
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
├── 方案书/                   # 设计文档
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

