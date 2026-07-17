source .env
[ -z "$ZABBIX_TOKEN" ] && echo "ZABBIX_TOKEN is empty!" || \
curl -sk -X POST -H "Content-Type: application/json-rpc" \
  -d '{"jsonrpc":"2.0","method":"event.get","params":{"output":["eventid","name","clock","severity"],"sortfield":"eventid","sortorder":"DESC","limit":1},"auth":"'"$ZABBIX_TOKEN"'","id":1}' \
  "$ZABBIX_URL" | jq .
