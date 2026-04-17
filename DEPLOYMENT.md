# Agentrust 部署指南

本文档提供 Agentrust 系统的部署说明。

## 系统要求

- Python 3.10+
- SQLite 3
- 至少 512MB RAM
- Linux/macOS/Windows

## 部署模式

### 开发模式

```bash
cd backend
pip install -r requirements.txt
python scripts/init_db.py
uvicorn main:app --reload --port 8000
```

### 生产模式

#### 1. 使用 Gunicorn + Uvicorn Workers

```bash
pip install gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

#### 2. 使用 Docker

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

RUN mkdir -p data

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

构建并运行：

```bash
docker build -t agentrust .
docker run -p 8000:8000 -v $(pwd)/data:/app/data agentrust
```

#### 3. 使用 Docker Compose

```yaml
version: '3.8'

services:
  agentrust:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
    environment:
      - DATABASE_URL=sqlite+aiosqlite:///data/agentrust.db
      - SESSION_SECRET=your-secret-key-at-least-32-bytes
      - CA_KEY_PASSWORD=your-ca-password
      - LOG_LEVEL=INFO
    restart: unless-stopped
```

## 前端部署

### 构建前端

```bash
cd dashboard
npm install
npm run build
```

构建产物在 `dashboard/dist/` 目录。

### 使用 Nginx 托管

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # 前端静态文件
    location / {
        root /path/to/dashboard/dist;
        try_files $uri $uri/ /index.html;
    }

    # API 代理
    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 环境变量

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `DATABASE_URL` | Yes | `sqlite+aiosqlite:///data/agentrust.db` | 数据库连接 URL |
| `SESSION_SECRET` | Yes | - | Session Token 签名密钥（至少 32 字节） |
| `CA_KEY_PASSWORD` | Yes | - | CA 根密钥加密密码 |
| `LOG_LEVEL` | No | `INFO` | 日志级别: DEBUG, INFO, WARNING, ERROR |

## 数据库

SQLite 数据库文件存储在 `data/agentrust.db`。

### 备份

```bash
cp data/agentrust.db data/agentrust.db.backup
```

### 恢复

```bash
cp data/agentrust.db.backup data/agentrust.db
```

## 安全注意事项

1. **私钥保护**: CA 私钥使用 AES-256 加密存储，确保 `CA_KEY_PASSWORD` 足够复杂
2. **Session Secret**: 确保 `SESSION_SECRET` 足够随机，不要在代码中硬编码
3. **CORS**: 生产环境中在 `main.py` 中指定具体的 allowed origins
4. **网络**: 生产环境建议使用 HTTPS
5. **定期更新**: 定期更新依赖包以修复安全漏洞

## 监控

建议监控以下指标：

- API 响应时间
- 认证失败率
- 证书吊销频率
- 审计日志写入速率

## 故障排查

### 数据库锁定

如果遇到数据库锁定错误，检查：
- 是否有多个进程同时写入数据库
- SQLite 是否支持 WAL 模式

### 签名验证失败

确保 canonical_json 实现一致，签名和验签使用相同的序列化方式。

### 证书过期

证书过期后需要重新注册 Agent。定期检查证书有效期。

## 扩展

### 切换到 PostgreSQL

```python
# 在生产环境中，可以使用 PostgreSQL
DATABASE_URL=postgresql+asyncpg://user:password@localhost/agentrust
```

### 添加缓存

可以使用 Redis 缓存 CRL 和会话信息：

```python
# 使用 Redis 缓存 CRL（TTL = 60s）
```

## 许可证

MIT License
