# HTTPS 設定指南 (HTTPS Setup Guide)

本指南將說明如何為您的 FastAPI 應用程式啟用 HTTPS。

## 方法 1: 使用 Uvicorn 直接支援 SSL (開發環境)

### 1.1 生成自簽名證書 (僅供開發使用)

```bash
# 創建證書目錄
mkdir -p certs

# 生成私鑰
openssl genrsa -out certs/key.pem 2048

# 生成自簽名證書
openssl req -new -x509 -key certs/key.pem -out certs/cert.pem -days 365
```

### 1.2 修改 Makefile 以支援 HTTPS

在 Makefile 中添加新的運行命令：

```makefile
.PHONY: run-https
run-https:
	uv run uvicorn src.main:app --host 0.0.0.0 --port 8701 --ssl-keyfile=./certs/key.pem --ssl-certfile=./certs/cert.pem

.PHONY: run-prod-https
run-prod-https:
	uv run uvicorn src.main:app --host 0.0.0.0 --port 8701 --ssl-keyfile=./certs/key.pem --ssl-certfile=./certs/cert.pem --workers 4
```

## 方法 2: 使用 Nginx 作為反向代理 (推薦用於生產環境)

### 2.1 創建 Nginx 配置文件

創建 `nginx/nginx.conf`:

```nginx
events {
    worker_connections 1024;
}

http {
    upstream backend {
        server saywe_backend:8000;
    }

    server {
        listen 80;
        server_name your-domain.com;
        
        # 重定向 HTTP 到 HTTPS
        return 301 https://$server_name$request_uri;
    }

    server {
        listen 443 ssl;
        server_name your-domain.com;

        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;
        
        # SSL 配置
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;
        ssl_prefer_server_ciphers on;

        location / {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
```

### 2.2 更新 docker-compose.yml

創建 `docker-compose.yml`:

```yaml
services:

  saywe_db:
    container_name: saywe_db
    image: postgres:17
    command: postgres -c 'max_connections=250'
    restart: unless-stopped
    env_file:
      - ./env/.env.db
    volumes:
      - ./data/postgresql_data:/var/lib/postgresql/data
    networks:
      - saywe_network 

  saywe_backend:
    container_name: saywe_backend
    build: .
    restart: unless-stopped
    env_file:
      - ./env/.env
    depends_on:
      - saywe_db
    networks:
      - saywe_network

  nginx:
    container_name: saywe_nginx
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
      - ./certs:/etc/nginx/ssl
    depends_on:
      - saywe_backend
    networks:
      - saywe_network

networks:
  saywe_network:
    name: saywe_network
    driver: bridge
```

## 方法 3: 使用 Let's Encrypt 獲取免費 SSL 證書 (生產環境)

### 3.1 使用 Certbot 獲取證書

```bash
# 安裝 Certbot
sudo apt-get update
sudo apt-get install certbot

# 獲取證書 (替換 your-domain.com 為您的域名)
sudo certbot certonly --standalone -d your-domain.com
```

### 3.2 使用 Docker Compose 與 Certbot

創建 `docker-compose.prod.yml`:

```yaml
services:

  saywe_db:
    container_name: saywe_db
    image: postgres:17
    command: postgres -c 'max_connections=250'
    restart: unless-stopped
    env_file:
      - ./env/.env.db
    volumes:
      - ./data/postgresql_data:/var/lib/postgresql/data
    networks:
      - saywe_network 

  saywe_backend:
    container_name: saywe_backend
    build: .
    restart: unless-stopped
    env_file:
      - ./env/.env
    depends_on:
      - saywe_db
    networks:
      - saywe_network

  nginx:
    container_name: saywe_nginx
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
      - /etc/letsencrypt:/etc/letsencrypt
      - ./certbot/www:/var/www/certbot
    depends_on:
      - saywe_backend
    networks:
      - saywe_network

  certbot:
    image: certbot/certbot
    volumes:
      - /etc/letsencrypt:/etc/letsencrypt
      - ./certbot/www:/var/www/certbot
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done;'"

networks:
  saywe_network:
    name: saywe_network
    driver: bridge
```

## 方法 4: 使用 Cloudflare (最簡單的方法)

如果您使用 Cloudflare 作為 DNS 提供商：

1. 在 Cloudflare 儀表板中啟用 SSL/TLS
2. 選擇 "Flexible" 或 "Full" SSL 模式
3. 您的應用程式可以繼續在 HTTP 上運行，Cloudflare 會處理 HTTPS

## 安全建議

1. **生產環境**：永遠不要使用自簽名證書
2. **證書更新**：設置自動更新 Let's Encrypt 證書
3. **安全標頭**：在 Nginx 配置中添加安全標頭：

```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
```

## 快速開始

對於開發環境，最快的方法是：

```bash
# 1. 生成自簽名證書
mkdir -p certs
openssl req -x509 -newkey rsa:4096 -keyout certs/key.pem -out certs/cert.pem -days 365 -nodes

# 2. 運行 HTTPS 服務器
uv run uvicorn src.main:app --host 0.0.0.0 --port 8701 --ssl-keyfile=./certs/key.pem --ssl-certfile=./certs/cert.pem
```

然後訪問 `https://localhost:8701`

## 注意事項

- 瀏覽器會警告自簽名證書不安全，這在開發環境中是正常的
- 生產環境必須使用有效的 SSL 證書
- 記得將證書文件添加到 `.gitignore` 中，不要提交到版本控制系統