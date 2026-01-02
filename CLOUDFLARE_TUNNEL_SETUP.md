# Cloudflare Tunnel経由でGitHub Actionsからデプロイする設定

ポート開放ができない環境でも、Cloudflare Tunnelを使用してGitHub ActionsからSSH接続でデプロイできます。

## 方法1: Cloudflare Tunnel経由でSSHを公開（推奨）

### 1. Cloudflare Tunnelの設定ファイルを編集

Cloudflare Tunnelの設定ファイル（通常は`config.yml`）に以下を追加します：

```yaml
tunnel: <your-tunnel-id>
credentials-file: /etc/cloudflared/<credentials-file>.json

ingress:
  # SSH接続用
  - hostname: ssh.your-domain.com
    service: ssh://localhost:22
  
  # 既存の設定がある場合はここに追加
  # - hostname: example.your-domain.com
  #   service: http://localhost:8080
  
  # 必須: キャッチオールルール
  - service: http_status:404
```

### 2. Cloudflare Dashboardでホスト名を追加

1. [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/) にログイン
2. `Access` → `Tunnels` を開く
3. 使用中のTunnelをクリック
4. `Public Hostname` タブで新しいホスト名を追加：
   - **Subdomain**: `ssh`
   - **Domain**: あなたのドメイン（例: `your-domain.com`）
   - **Service**: `SSH` を選択
   - **URL**: `localhost:22`

### 3. Cloudflareコンテナを再起動

```bash
docker restart cloudflared-tunnel
```

### 4. GitHub Actionsのワークフローを更新

`.github/workflows/deploy.yml` の `SERVER_HOST` を更新：

```yaml
name: Deploy to Server

on:
  push:
    branches:
      - main
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
      - name: Deploy via SSH through Cloudflare Tunnel
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ssh.your-domain.com  # Cloudflare Tunnelのホスト名
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          port: 22
          script: |
            cd /home/aosy/Docker/AI-Alice
            git pull origin main
            docker compose down
            docker compose up -d --build
            echo "Deployment completed at $(date)"
```

### 5. GitHubのSecretsを更新

GitHub Repositoryの Settings → Secrets → Actions で以下を更新：

- **SERVER_HOST**: `ssh.your-domain.com` (Cloudflare Tunnelのホスト名)
- **SERVER_PORT**: `22`
- **SERVER_USER**: `aosy`
- **SSH_PRIVATE_KEY**: (変更なし)

---

## 方法2: Cloudflare Accessを使用（よりセキュア）

SSH接続にCloudflare Accessの認証を追加することで、さらにセキュリティを強化できます。

### 1. Cloudflare Accessアプリケーションを作成

1. Cloudflare Zero Trust Dashboard → `Access` → `Applications`
2. `Add an Application` → `Self-hosted`
3. 設定：
   - **Application name**: `SSH Access`
   - **Session duration**: `24 hours`
   - **Application domain**: `ssh.your-domain.com`

### 2. Accessポリシーを設定

1. `Add a policy`
2. **Policy name**: `Allow GitHub Actions`
3. **Action**: `Allow`
4. **Include**: `Service Auth` → サービストークンを作成
5. サービストークンのClient IDとClient Secretを保存

### 3. GitHub Actionsでcloudflaredを使用

```yaml
name: Deploy to Server

on:
  push:
    branches:
      - main
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
      - name: Install cloudflared
        run: |
          wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
          sudo dpkg -i cloudflared-linux-amd64.deb
      
      - name: Setup SSH config for Cloudflare Tunnel
        run: |
          mkdir -p ~/.ssh
          cat >> ~/.ssh/config << EOF
          Host ssh.your-domain.com
            ProxyCommand cloudflared access ssh --hostname %h
          EOF
          
          echo "${{ secrets.SSH_PRIVATE_KEY }}" > ~/.ssh/deploy_key
          chmod 600 ~/.ssh/deploy_key
      
      - name: Set Cloudflare credentials
        run: |
          export CF_ACCESS_CLIENT_ID="${{ secrets.CF_ACCESS_CLIENT_ID }}"
          export CF_ACCESS_CLIENT_SECRET="${{ secrets.CF_ACCESS_CLIENT_SECRET }}"
      
      - name: Deploy via SSH
        env:
          CF_ACCESS_CLIENT_ID: ${{ secrets.CF_ACCESS_CLIENT_ID }}
          CF_ACCESS_CLIENT_SECRET: ${{ secrets.CF_ACCESS_CLIENT_SECRET }}
        run: |
          ssh -i ~/.ssh/deploy_key -o StrictHostKeyChecking=no ${{ secrets.SERVER_USER }}@ssh.your-domain.com << 'EOF'
            cd /home/aosy/Docker/AI-Alice
            git pull origin main
            docker compose down
            docker compose up -d --build
            echo "Deployment completed at $(date)"
          EOF
```

追加するGitHub Secrets:
- `CF_ACCESS_CLIENT_ID`: Cloudflare AccessのClient ID
- `CF_ACCESS_CLIENT_SECRET`: Cloudflare AccessのClient Secret

---

## 方法3: GitHub Self-hosted Runnerを使用（最もシンプル）

サーバー上でGitHub Runnerを実行すれば、SSH接続が不要になります。

### 1. GitHub Runnerのインストール

```bash
cd /home/aosy/Docker
mkdir github-runner && cd github-runner

# GitHubリポジトリの Settings → Actions → Runners → New self-hosted runner
# 表示されるコマンドを実行
```

### 2. Dockerコンテナとして実行

`compose.yaml`:
```yaml
version: '3.8'

services:
  github-runner:
    image: myoung34/github-runner:latest
    environment:
      - REPO_URL=https://github.com/your-username/AI-Alice
      - RUNNER_NAME=ai-alice-runner
      - ACCESS_TOKEN=${GITHUB_TOKEN}
      - RUNNER_WORKDIR=/tmp/github-runner
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - /home/aosy/Docker/AI-Alice:/home/aosy/Docker/AI-Alice
    restart: unless-stopped
```

### 3. ワークフローを更新

```yaml
name: Deploy to Server

on:
  push:
    branches:
      - main
  workflow_dispatch:

jobs:
  deploy:
    runs-on: self-hosted  # Self-hosted runnerを使用
    
    steps:
      - name: Deploy
        run: |
          cd /home/aosy/Docker/AI-Alice
          git pull origin main
          docker compose down
          docker compose up -d --build
          echo "Deployment completed at $(date)"
```

---

## 推奨される方法

環境に応じて以下を推奨します：

1. **方法1（Cloudflare Tunnel経由でSSH公開）**: シンプルで設定が簡単
2. **方法3（Self-hosted Runner）**: 最もシンプルで、SSH不要
3. **方法2（Cloudflare Access）**: 最もセキュアだが設定が複雑

どの方法を選択されますか？設定のサポートをいたします！
