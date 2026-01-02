#!/bin/bash
set -e

echo "=== AI-Alice Auto Deploy Script ==="
echo "Started at: $(date)"
echo ""

# プロジェクトディレクトリに移動
cd /home/aosy/Docker/AI-Alice

# 最新のコードを取得
echo "📥 Pulling latest changes from GitHub..."
git pull origin main

# Dockerコンテナを再構築
echo "🐳 Rebuilding Docker containers..."
docker compose down
docker compose up -d --build

# 状態確認
echo ""
echo "✅ Deployment completed!"
echo "📊 Container status:"
docker compose ps

echo ""
echo "Finished at: $(date)"
