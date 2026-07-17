#!/bin/bash

# TICKET はソースにハードコードせず、環境変数 or gitignore 対象のローカルファイルから取得する
# 優先順位: 1) 既存の環境変数 TICKET  2) スクリプトと同ディレクトリの ticket.local (TICKET=xxxx を記載)
if [ -z "${TICKET}" ] && [ -f "$(dirname "${BASH_SOURCE[0]}")/ticket.local" ]; then
  . "$(dirname "${BASH_SOURCE[0]}")/ticket.local"
fi
if [ -z "${TICKET}" ]; then
  echo "環境変数 TICKET が未設定です。'export TICKET=xxxx' するか bin/ticket.local に TICKET=xxxx を記載してください。"
  return 1 2>/dev/null || exit 1
fi

ISSUE_KEY_URL="https://api.ticket.aws.biglobe.net/key"
JQ=jq

type ${JQ} > /dev/null 2>&1
if [ $? -ne 0 ]; then
  echo "Not found ${JQ} commad."
  echo "Please install ${JQ} commad."
  return 255
fi

KEY_URL="${ISSUE_KEY_URL}?ticket=${TICKET}"

CREDENTIAL=`curl -fs ${KEY_URL}`
if [ $? -ne 0 ]; then
  echo "Failed to get credential."
  return 1
fi

KEYS=(`echo ${CREDENTIAL} | ${JQ} -r '.AccessKeyId, .SecretAccessKey, .SessionToken'`)
if [ ${#KEYS[@]} -ne 3 ]; then
  echo "Failed to parse credential."
  return 2
fi

index=1
for item in ${KEYS[@]};
do
	if [ $index -eq 1 ]; then
		AWS_ACCESS_KEY_ID=$item
		export AWS_ACCESS_KEY_ID
		echo AWS_ACCESS_KEY=${AWS_ACCESS_KEY_ID}
		# echo $item
		
	elif [ $index -eq 2 ]; then		
		AWS_SECRET_ACCESS_KEY=$item
		export AWS_SECRET_ACCESS_KEY
		echo AWS_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
		# echo $item

	elif [ $index -eq 3 ]; then
		AWS_SESSION_TOKEN=$item
		export AWS_SESSION_TOKEN
		echo AWS_SESION_TOKEN=${AWS_SESSION_TOKEN}
		# echo $item
	fi
	index=$(expr $index + 1)
done
