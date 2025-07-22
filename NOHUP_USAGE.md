# FastAPI Nohup 運行腳本使用指南

## 快速開始

### 1. 基本使用

```bash
# 啟動應用程式（開發模式）
./run-nohup.sh start

# 停止應用程式
./run-nohup.sh stop

# 查看應用程式狀態
./run-nohup.sh status

# 重新啟動應用程式
./run-nohup.sh restart

# 查看即時日誌
./run-nohup.sh logs
```

### 2. 生產環境使用

```bash
# 使用生產模式啟動（預設 4 個 workers）
./run-nohup.sh start --prod

# 使用生產模式 + HTTPS
./run-nohup.sh start --prod --https

# 自定義 worker 數量（例如 8 個）
./run-nohup.sh start --prod --workers 8

# 完整的生產環境啟動命令
./run-nohup.sh start --prod --https --workers 8
```

## 詳細說明

### 啟動選項

| 選項 | 說明 | 範例 |
|------|------|------|
| 無選項 | 開發模式，單一進程 | `./run-nohup.sh start` |
| `--prod` | 生產模式，多進程 | `./run-nohup.sh start --prod` |
| `--https` | 啟用 HTTPS（需要證書） | `./run-nohup.sh start --https` |
| `--workers N` | 設定 worker 數量 | `./run-nohup.sh start --prod --workers 4` |

### 檔案位置

- **PID 檔案**: `meeting-helper-backend.pid`
- **標準日誌**: `logs/meeting-helper-backend.log`
- **錯誤日誌**: `logs/meeting-helper-backend.error.log`

### 實際使用範例

#### 場景 1：開發環境測試

```bash
# 啟動開發模式
./run-nohup.sh start

# 檢查狀態
./run-nohup.sh status

# 查看日誌（按 Ctrl+C 退出）
./run-nohup.sh logs

# 完成測試後停止
./run-nohup.sh stop
```

#### 場景 2：生產環境部署

```bash
# 首先確保有 SSL 證書
make generate-cert

# 使用 HTTPS 和多個 workers 啟動
./run-nohup.sh start --prod --https --workers 8

# 確認服務運行狀態
./run-nohup.sh status

# 訪問服務
# https://localhost:8701
```

#### 場景 3：更新代碼後重啟

```bash
# 拉取最新代碼
git pull

# 重新啟動服務
./run-nohup.sh restart --prod --https

# 檢查新版本是否正常運行
./run-nohup.sh logs
```

### 故障排除

#### 1. 應用程式無法啟動

```bash
# 檢查錯誤日誌
cat logs/meeting-helper-backend.error.log

# 檢查是否有其他進程佔用端口
lsof -i :8701

# 清理並重新啟動
./run-nohup.sh stop
rm -f meeting-helper-backend.pid
./run-nohup.sh start
```

#### 2. HTTPS 模式無法啟動

```bash
# 確認證書存在
ls -la certs/

# 如果沒有證書，生成證書
make generate-cert

# 重新啟動
./run-nohup.sh start --https
```

#### 3. 查看完整日誌

```bash
# 查看所有標準輸出日誌
cat logs/meeting-helper-backend.log

# 查看所有錯誤日誌
cat logs/meeting-helper-backend.error.log

# 使用 less 分頁查看
less logs/meeting-helper-backend.log
```

### 進階使用

#### 自動啟動（使用 crontab）

```bash
# 編輯 crontab
crontab -e

# 添加以下行，在系統啟動時自動運行
@reboot cd /home/will/gitlab/meeting-helper-backend && ./run-nohup.sh start --prod
```

#### 監控腳本

創建一個簡單的監控腳本 `monitor.sh`：

```bash
#!/bin/bash
while true; do
    if ! ./run-nohup.sh status > /dev/null 2>&1; then
        echo "Service is down, restarting..."
        ./run-nohup.sh start --prod
    fi
    sleep 60  # 每分鐘檢查一次
done
```

### 注意事項

1. **端口衝突**：確保 8701 端口沒有被其他服務佔用
2. **權限問題**：確保腳本有執行權限 (`chmod +x run-nohup.sh`)
3. **環境變數**：確保 `.env` 檔案配置正確
4. **日誌管理**：定期清理或輪轉日誌檔案，避免佔用過多磁碟空間

### 常用命令組合

```bash
# 查看服務是否運行並顯示資源使用情況
./run-nohup.sh status

# 快速重啟（保持原有啟動參數）
./run-nohup.sh restart

# 查看最新的錯誤
tail -n 50 logs/meeting-helper-backend.error.log

# 實時監控日誌
tail -f logs/meeting-helper-backend.log

# 查看進程詳細信息
ps aux | grep uvicorn