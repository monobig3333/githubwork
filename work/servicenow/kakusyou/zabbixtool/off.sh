#!/bin/bash
# send_zabbix.sh

ZABBIX_SERVER="localhost"
KEY="test-hyoka"
VALUE="0"
START=1
END="$1"
INTERVAL="$2"

if ! [[ "$END" =~ ^[1-9][0-9]*$ ]] || ! [[ "$INTERVAL" =~ ^[1-9][0-9]*$ ]]; then
    echo "Usage: $0 <end> <interval>"
    echo "  <end>: last server number to process (e.g. 3000)"
    echo "  <interval>: process this many servers before sending trigger signal"
    exit 1
fi

PROCESSED=0

for i in $(seq -f "%05g" "$START" "$END"); do
    HOST="test-servicenow-monohyouka-${i}"
    zabbix_sender -z "$ZABBIX_SERVER" -s "$HOST" -k "$KEY" -o "$VALUE"

    PROCESSED=$((PROCESSED + 1))
    if (( PROCESSED % INTERVAL == 0 )); then
        zabbix_sender -z localhost -s "test-servicenow-monohyouka-1" -k "test-hyoka" -o 1
        sleep 1
        zabbix_sender -z localhost -s "test-servicenow-monohyouka-1" -k "test-hyoka" -o 0
    fi
done