#!/bin/bash

# このスクリプトは source で実行してください: source ./setup.sh
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "ERROR: このスクリプトは source で実行してください。"
  echo "  正しい実行方法: source ./setup.sh"
  exit 1
fi

# 引数チェック: 第一引数 servicerid, 第二引数 env (dev/stg/prd)
_SERVICERID="$1"
_ENV="$2"
if [ -z "${_SERVICERID}" ] || [ -z "${_ENV}" ]; then
  echo "ERROR: 引数が不足しています。"
  echo "  使い方: source ./setup.sh <servicerid> <env>"
  echo "  例:     source ./setup.sh big4180 prd"
  unset _SERVICERID _ENV
  return 1
fi
case "${_ENV}" in
  dev|stg|prd) ;;
  *)
    echo "ERROR: env は dev / stg / prd のいずれかを指定してください (指定値: ${_ENV})"
    unset _SERVICERID _ENV
    return 1
    ;;
esac

# 引数からプロファイル名を組み立て (例: big4180-prd-sep)
_PROFILE="${_SERVICERID}-${_ENV}-sep"

. "$(dirname "${BASH_SOURCE[0]}")/.env"

# ベースの一時クレデンシャルを取得
source /Users/bx0815610/src/githubwork/bin/get_key2.sh "${AWS_TOKEN}"

# ${_PROFILE} プロファイルのロールを明示的に引き受け
# (AWS_ACCESS_KEY_ID 等の環境変数がセットされていると AWS_PROFILE によるロール引き受けが
#  スキップされるため、sts assume-role で明示的に実行する)
_ROLE_ARN=$(aws configure get role_arn --profile "${_PROFILE}")
_ROLE_CREDS=$(aws sts assume-role \
  --role-arn "${_ROLE_ARN}" \
  --role-session-name "setup-session" \
  --output json)

if [ $? -ne 0 ]; then
  echo "ERROR: ロールの引き受けに失敗しました (${_ROLE_ARN})"
  unset _SERVICERID _ENV _PROFILE _ROLE_ARN
  return 1
fi

export AWS_ACCESS_KEY_ID=$(echo "${_ROLE_CREDS}"     | jq -r '.Credentials.AccessKeyId')
export AWS_SECRET_ACCESS_KEY=$(echo "${_ROLE_CREDS}" | jq -r '.Credentials.SecretAccessKey')
export AWS_SESSION_TOKEN=$(echo "${_ROLE_CREDS}"     | jq -r '.Credentials.SessionToken')
unset AWS_PROFILE _SERVICERID _ENV _PROFILE _ROLE_ARN _ROLE_CREDS

aws sts get-caller-identity
