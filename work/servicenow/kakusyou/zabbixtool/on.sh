#!/bin/bash
# send_zabbix_on.sh

ZABBIX_SERVER="localhost"
KEY="test-hyoka"
VALUE="1"
START=1
END="$1"

if ! [[ "$END" =~ ^[1-9][0-9]*$ ]]; then
    echo "Usage: $0 <end>"
    echo "  <end>: last server number to process (e.g. 3000)"
    exit 1
fi

for i in $(seq -f "%05g" "$START" "$END"); do
    HOST="test-servicenow-monohyouka-${i}"
    zabbix_sender -z "$ZABBIX_SERVER" -s "$HOST" -k "$KEY" -o "$VALUE"
done
