#!/usr/bin/env bash
#
# N-5: TCP セッション枯渇 (sysctl による ephemeral port pool 縮小方式)
#
# OS グローバルの ip_local_port_range を一時的に縮小し、システム全体で
# 新規 outbound 接続に使える ephemeral port を激減させる。
# 縮小後、残った数十ポートを本スクリプトが奪取して保持。
# 結果として MID Server (および他プロセス) は新規 outbound 接続を確立できず、
# 既存接続が切れたタイミングで完全に通信不能になる。
#
# 動作:
#   1. 現在の ip_local_port_range を保存 (/tmp/n5_orig_range)
#   2. sysctl で範囲を狭める (既定 32768 32800 = 33 ポート)
#   3. その範囲のポートを Python で奪取・保持
#   4. DURATION 秒経過 or Ctrl-C で sysctl を元に戻す
#   5. 念のためバックグラウンド guardian がタイムアウトで強制復旧
#
# 必要:
#   sudo (sysctl 変更のため)
#
# 使い方:
#   bash stress_tcp.sh                # 既定 900 秒
#   bash stress_tcp.sh 1800
#   NEW_RANGE="32768 32790" bash stress_tcp.sh 900   # さらに 23 ポートに絞る
#
# 注意:
#   - sysctl 変更中は OS 上の全プロセスが新規 outbound 接続に影響を受ける
#   - 既存接続はそのまま (TCP セッションは一度開いてしまえば動き続ける)
#   - 万一スクリプトが kill -9 された場合は手動で復旧:
#       sudo sysctl -w net.ipv4.ip_local_port_range="$(cat /tmp/n5_orig_range)"
#
set -uo pipefail

DURATION="${1:-900}"
NEW_RANGE="${NEW_RANGE:-32768 32800}"   # 33 ports
LISTEN_PORT="${LISTEN_PORT:-19999}"     # 縮小範囲外を選択
SAVE_FILE="${SAVE_FILE:-/tmp/n5_orig_range}"
PID=
GUARDIAN_PID=

# 縮小範囲の outer guard (DURATION + 60s 経過後に強制復旧する番犬)
spawn_guardian() {
  local restore_after=$(( DURATION + 60 ))
  ( sleep "$restore_after"
    if [ -f "$SAVE_FILE" ]; then
      sudo sysctl -w net.ipv4.ip_local_port_range="$(cat "$SAVE_FILE")" >/dev/null 2>&1 || true
    fi
  ) >/dev/null 2>&1 &
  GUARDIAN_PID=$!
  disown "$GUARDIAN_PID" 2>/dev/null || true
}

cleanup() {
  echo
  echo "Cleaning up..."
  # Python 停止
  if [ -n "${PID:-}" ]; then
    kill -TERM "$PID" 2>/dev/null || true
    sleep 1
    kill -KILL "$PID" 2>/dev/null || true
  fi
  # ip_local_port_range 復元
  if [ -f "$SAVE_FILE" ]; then
    ORIG="$(cat "$SAVE_FILE")"
    echo "Restoring ip_local_port_range to: $ORIG"
    sudo sysctl -w net.ipv4.ip_local_port_range="$ORIG" >/dev/null
    rm -f "$SAVE_FILE"
  fi
  # 番犬停止 (必要なし、自然に終わるが念のため)
  if [ -n "${GUARDIAN_PID:-}" ]; then
    kill "$GUARDIAN_PID" 2>/dev/null || true
  fi
  echo "Done"
}
trap cleanup EXIT INT TERM

echo "N-5 TCP exhaust (sysctl ip_local_port_range shrink)"
echo "  duration    : ${DURATION}s"
echo "  new range   : $NEW_RANGE"
echo "  listen_port : $LISTEN_PORT"
echo

# 事前 sudo 確認
if ! sudo -n true 2>/dev/null; then
  echo "ERROR: sudo がパスワード無しで使えません。事前に sudo -v を実行してください。"
  exit 1
fi

# 1) 現在の範囲を保存
ORIG_RANGE="$(sysctl -n net.ipv4.ip_local_port_range)"
echo "$ORIG_RANGE" > "$SAVE_FILE"
echo "  saved orig  : $ORIG_RANGE (-> $SAVE_FILE)"

# 2) 縮小範囲を適用
sudo sysctl -w net.ipv4.ip_local_port_range="$NEW_RANGE" >/dev/null
echo "  shrunk to   : $(sysctl -n net.ipv4.ip_local_port_range)"
echo

# 3) 番犬を仕掛ける (kill -9 されても DURATION+60s で復旧)
spawn_guardian
echo "  guardian pid: $GUARDIAN_PID  (restores after $((DURATION+60))s)"
echo

# 4) Python で縮小範囲のポートを奪取保持
python3 <<PY &
import os, socket, sys, threading, time

LISTEN_PORT = $LISTEN_PORT
DURATION    = $DURATION

# 1) listener (縮小範囲の外側ポートで起動)
listen_sock = socket.socket()
listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listen_sock.bind(("127.0.0.1", LISTEN_PORT))
listen_sock.listen(1024)
print(f"[N-5] listener on 127.0.0.1:{LISTEN_PORT}", flush=True)

server_conns = []
def acceptor():
    while True:
        try:
            c, _ = listen_sock.accept()
            server_conns.append(c)
        except OSError:
            break
threading.Thread(target=acceptor, daemon=True).start()

clients = []
def try_connect():
    try:
        c = socket.socket()
        c.settimeout(2)
        c.connect(("127.0.0.1", LISTEN_PORT))
        clients.append(c)
        return True
    except OSError:
        return False

# 初回フィル (縮小範囲のポートを総取り)
errs = 0
while errs < 50:
    if try_connect():
        errs = 0
    else:
        errs += 1
        time.sleep(0.005)

print(f"[N-5] initial grabbed = {len(clients)} sockets", flush=True)

# 継続枯渇 (Zabbix の old 接続が切れた瞬間に奪い返す)
start = time.time()
last_log = start
while time.time() - start < DURATION:
    if try_connect():
        pass
    else:
        time.sleep(0.01)
    now = time.time()
    if now - last_log >= 5:
        elapsed = int(now - start)
        print(f"[N-5]   elapsed={elapsed:4}s  clients held={len(clients)}", flush=True)
        last_log = now

# 解放
for c in clients:
    try: c.close()
    except: pass
for c in server_conns:
    try: c.close()
    except: pass
listen_sock.close()
print("[N-5] python finished", flush=True)
PY
PID=$!
echo "  python pid  : $PID"
wait "$PID" 2>/dev/null || true
