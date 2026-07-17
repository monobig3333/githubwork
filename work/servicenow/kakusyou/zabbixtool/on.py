#!/usr/bin/env python3
# send_zabbix_on.py

import subprocess
import sys
import time
import re

ZABBIX_SERVER = "localhost"
KEY = "test-hyoka"
VALUE = "1"
START = 1
# 秒間50実行: 1/50 = 0.02秒
SLEEP_INTERVAL = 1 / 50


def main():
    if len(sys.argv) != 2 or not re.match(r'^[1-9][0-9]*$', sys.argv[1]):
        print(f"Usage: {sys.argv[0]} <end>")
        print("  <end>: last server number to process (e.g. 3000)")
        sys.exit(1)

    end = int(sys.argv[1])

    for i in range(START, end + 1):
        host = f"test-servicenow-monohyouka-{i:05d}"
        subprocess.run(
            ["zabbix_sender", "-z", ZABBIX_SERVER, "-s", host, "-k", KEY, "-o", VALUE]
        )
        time.sleep(SLEEP_INTERVAL)


if __name__ == "__main__":
    main()
