#!/bin/bash

# GitHub Self-hosted Runnerセットアップスクリプト
# 使用方法: ./setup-runner.sh <GITHUB_TOKEN>

if [ -z "$1" ]; then
    echo "使い方: $0 <GITHUB_TOKEN>"
    echo ""
    echo "GitHubトークンは以下のURLから取得できます："
    echo "https://github.com/Aosy0/AI-Alice/settings/actions/runners/new"
    exit 1
fi

GITHUB_TOKEN=$1
RUNNER_NAME="ai-alice-runner"
RUNNER_DIR="/home/aosy/Docker/github-runner"

echo "=== GitHub Self-hosted Runner セットアップ ==="
echo "Runner名: $RUNNER_NAME"
echo "インストール先: $RUNNER_DIR"
echo ""

# ディレクトリ作成
mkdir -p $RUNNER_DIR
cd $RUNNER_DIR

# 最新のRunnerをダウンロード
echo "1. Runnerのダウンロード..."
curl -o actions-runner-linux-x64-2.319.1.tar.gz -L https://github.com/actions/runner/releases/download/v2.319.1/actions-runner-linux-x64-2.319.1.tar.gz

# 解凍
echo "2. 解凍中..."
tar xzf ./actions-runner-linux-x64-2.319.1.tar.gz

# 設定
echo "3. Runnerの設定..."
./config.sh --url https://github.com/Aosy0/AI-Alice --token $GITHUB_TOKEN --name $RUNNER_NAME --work _work --labels docker,self-hosted,linux --unattended

# サービスとしてインストール
echo "4. サービスとしてインストール..."
sudo ./svc.sh install

# 起動
echo "5. サービス起動..."
sudo ./svc.sh start

echo ""
echo "=== セットアップ完了 ==="
echo "Runner が正常に起動しました！"
echo ""
echo "ステータス確認: sudo ./svc.sh status"
echo "ログ確認: journalctl -u actions.runner.Aosy0-AI-Alice.ai-alice-runner -f"
