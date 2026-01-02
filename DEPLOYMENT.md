# GitHub Actions 自動デプロイ設定手順

このドキュメントは、GitHub上のコードが変更されたときに自動的にサーバーにデプロイする設定手順を説明します。

## 1. 生成されたSSH鍵

SSH鍵ペアは既に生成済みです：
- 秘密鍵: `/tmp/github_deploy_key`
- 公開鍵: `/tmp/github_deploy_key.pub`

公開鍵は既にサーバーの `~/.ssh/authorized_keys` に追加されています。

## 2. GitHubリポジトリにSecretsを設定

以下の手順でGitHubリポジトリにSecretsを追加してください：

1. GitHubリポジトリのページを開く
2. `Settings` タブをクリック
3. 左サイドバーの `Secrets and variables` → `Actions` をクリック
4. `New repository secret` ボタンをクリック

以下の4つのSecretsを追加してください：

### SECRET 1: SSH_PRIVATE_KEY
- Name: `SSH_PRIVATE_KEY`
- Value: 以下のコマンドで表示される秘密鍵の内容をコピー＆ペースト
```bash
cat /tmp/github_deploy_key
```

### SECRET 2: SERVER_HOST
- Name: `SERVER_HOST`
- Value: サーバーのIPアドレスまたはドメイン名
  - ローカルネットワーク: `10.13.49.18`
  - または外部からアクセス可能なIPアドレス/ドメイン名

### SECRET 3: SERVER_USER
- Name: `SERVER_USER`
- Value: `aosy`

### SECRET 4: SERVER_PORT
- Name: `SERVER_PORT`
- Value: `22` (SSH接続のポート番号、デフォルトは22)

## 3. ワークフローファイルの確認

GitHub Actionsのワークフローファイルは `.github/workflows/deploy.yml` に作成されています。

このワークフローは以下のタイミングで実行されます：
- `main` ブランチにプッシュされたとき
- GitHubの Actions タブから手動実行したとき

## 4. デプロイフロー

1. コードを変更してGitHubにプッシュ
   ```bash
   git add .
   git commit -m "Update code"
   git push origin main
   ```

2. GitHub Actionsが自動的に実行される

3. サーバー上で以下のコマンドが実行される：
   - `git pull origin main` - 最新のコードを取得
   - `docker compose down` - 既存のコンテナを停止
   - `docker compose up -d --build` - 新しいイメージをビルドして起動

## 5. デプロイの確認

1. GitHubリポジトリの `Actions` タブで実行状況を確認
2. 緑色のチェックマークが表示されれば成功
3. エラーが発生した場合は、ログを確認して問題を解決

## 6. セキュリティに関する注意事項

- 秘密鍵 (`/tmp/github_deploy_key`) は安全に保管してください
- GitHubのSecretsに追加したら、ローカルの秘密鍵は削除することを推奨します：
  ```bash
  rm /tmp/github_deploy_key /tmp/github_deploy_key.pub
  ```
- `.env` ファイルは `.gitignore` に含まれているため、GitHubにプッシュされません

## 7. トラブルシューティング

### SSH接続エラー
- サーバーのファイアウォール設定を確認
- GitHub Actionsからサーバーへのアクセスが許可されているか確認
- Secretsの値が正しいか確認

### Dockerコンテナ起動エラー
- `compose.yaml` の設定を確認
- サーバー上で手動でビルドして問題を特定

### 環境変数の問題
- `.env` ファイルがサーバー上に存在するか確認
- 必要な環境変数がすべて設定されているか確認
