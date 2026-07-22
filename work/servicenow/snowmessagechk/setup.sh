#!/bin/bash

# このスクリプトは source で実行してください: source ./setup.sh
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "ERROR: このスクリプトは source で実行してください。"
  echo "  正しい実行方法: source ./setup.sh"
  exit 1
fi

. "$(dirname "${BASH_SOURCE[0]}")/.env"

# ベースの一時クレデンシャルを取得
source /Users/bx0815610/githubwork/bin/get_key2.sh "${AWS_TOKEN}"

# big4180-prd-sep プロファイルのロールを明示的に引き受け
# (AWS_ACCESS_KEY_ID 等の環境変数がセットされていると AWS_PROFILE によるロール引き受けが
#  スキップされるため、sts assume-role で明示的に実行する)
_ROLE_ARN=$(aws configure get role_arn --profile big4180-prd-sep)
_ROLE_CREDS=$(aws sts assume-role \
  --role-arn "${_ROLE_ARN}" \
  --role-session-name "setup-session" \
  --output json)

if [ $? -ne 0 ]; then
  echo "ERROR: ロールの引き受けに失敗しました (${_ROLE_ARN})"
  return 1
fi

export AWS_ACCESS_KEY_ID=$(echo "${_ROLE_CREDS}"     | jq -r '.Credentials.AccessKeyId')
export AWS_SECRET_ACCESS_KEY=$(echo "${_ROLE_CREDS}" | jq -r '.Credentials.SecretAccessKey')
export AWS_SESSION_TOKEN=$(echo "${_ROLE_CREDS}"     | jq -r '.Credentials.SessionToken')
unset AWS_PROFILE _ROLE_ARN _ROLE_CREDS

aws sts get-caller-identity
