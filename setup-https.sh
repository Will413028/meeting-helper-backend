#!/bin/bash

echo "🔐 FastAPI HTTPS 設置腳本"
echo "========================"

# 檢查是否已經有證書
if [ -d "certs" ] && [ -f "certs/cert.pem" ] && [ -f "certs/key.pem" ]; then
    echo "✅ 證書已存在於 ./certs/ 目錄"
    echo ""
    echo "要重新生成證書嗎？(y/N)"
    read -r response
    if [[ ! "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo "保留現有證書。"
    else
        rm -rf certs
        make generate-cert
    fi
else
    echo "📝 生成自簽名證書..."
    make generate-cert
fi

echo ""
echo "🚀 啟動選項："
echo "1) 開發模式 HTTPS (單一進程)"
echo "2) 生產模式 HTTPS (多進程)"
echo "3) 只生成證書，不啟動服務"
echo ""
echo "請選擇 (1-3):"
read -r choice

case $choice in
    1)
        echo "啟動開發模式 HTTPS 服務器..."
        make run-https
        ;;
    2)
        echo "啟動生產模式 HTTPS 服務器..."
        make run-prod-https
        ;;
    3)
        echo "證書已準備就緒！"
        echo ""
        echo "您可以使用以下命令啟動 HTTPS 服務器："
        echo "  開發模式: make run-https"
        echo "  生產模式: make run-prod-https"
        ;;
    *)
        echo "無效的選擇"
        exit 1
        ;;
esac