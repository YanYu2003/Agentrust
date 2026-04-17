# Agentrust Dashboard

Agentrust 系统的 Web 管理面板。

## 技术栈

- React 18 + TypeScript
- Vite 5
- Ant Design 5.x
- ECharts 5
- React Query (TanStack Query)
- Axios

## 快速开始

### 前提条件

Dashboard 需要后端服务运行在 `http://localhost:8000`。

后端启动方式：
```bash
cd backend
python -X utf8 -m uvicorn main:app --port 8000
```

### 安装依赖

```bash
cd dashboard
npm install
```

### 启动开发服务器

```bash
npm run dev
```

访问 http://localhost:5173

### 构建生产版本

```bash
npm run build
```

构建产物在 `dist/` 目录。

## 功能模块

### 1. 登录页面
- 输入 Agent ID、证书 ID 和私钥文件路径
- Demo 模式下跳过实际签名验证

### 2. 证书管理 (CertView)
- 展示所有 Agent 的证书列表
- 显示状态（有效/过期/已吊销）、过期时间、信任等级
- 支持手动吊销证书
- 证书详情弹窗

### 3. 委托链可视化 (DelegationGraph)
- 使用 ECharts Force Graph 展示委托关系
- 节点大小按 trust_level 映射
- 边颜色按能力类型区分
- 点击边查看衰减参数详情

### 4. 审计日志 (AuditView)
- 按时间倒序展示审计日志
- 支持按 Agent、操作类型、结果状态过滤
- DENIED 记录红色高亮显示
- ERROR 记录橙色高亮显示
- 点击查看完整 token_chain 和请求上下文

## API 代理

开发模式下，Vite 配置了代理将 `/api` 请求转发到 `http://localhost:8000`（后端服务）。

确保后端服务已启动在 8000 端口。

## 与后端集成

Dashboard 需要后端提供以下 API：

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/v1/ca/auth/challenge` | POST | 获取认证挑战 |
| `/api/v1/ca/auth/verify` | POST | 验证签名 |
| `/api/v1/ca/revoke` | POST | 吊销证书 |
| `/api/v1/ca/crl` | GET | 获取 CRL |
| `/api/v1/agents/{agent_id}` | GET | 获取 Agent 信息 |
| `/api/v1/audit/logs` | GET | 查询审计日志 |
| `/api/v1/audit/logs/{log_id}` | GET | 获取日志详情 |
| `/api/v1/audit/delegation-graph` | GET | 获取委托关系图 |
