# CLAUDE.md

このファイルは Claude Code (claude.ai/code) が本リポジトリで作業する際の指針を提供する。

## リポジトリ概要

ServiceNow 統合管理コンソール導入の **性能・可用性・非正常系試験** 関連の試験コード・スクリプト・ドキュメント一式。

- 対象 ServiceNow バージョン: **Zurich**
- 対象インスタンス: **`biglobedev`** (2026/8/14 以降の再測定。2026/5〜6 の初回は nonprod 主体)
- 試験項目数: 34 (出荷条件 33 + 参考値 1)
- 初回試験 (2026/5〜6): 出荷条件 33 件すべて OK

### 進行中: 再測定 (2026/7〜)

システム全体見直し (イベントルール KDI 版 → 改版) に伴い **13 件を再測定中**。
詳細は `再測定_実行計画.md`。

| 状態 | 要件 |
|---|---|
| 完了・合格 | 1-1 / 1-2 / 1-3 / 1-4 / 2-1 / 3-1 / M-1 / **2-2** |
| 実施中 | 2-2 の追加検証 (コネクタのポーリング間隔 30s → 15s の効果測定) |
| 未実施 | M-2 / M-3 / 2-3 / 2-4-5 / 2-6 |

### 環境差分 (重要)

| | dev (現在) | dev (2026/8/19 まで) | nonprod |
|---|---|---|---|
| MID インスタンス | **t3.large** (7 GiB) | t3.small (2 GiB) | t3.large (8 GiB) |
| MID Java ヒープ | **4096 MB** | 1024 MB | 4096 MB |
| MID 台数 | `mid-server-zabbix` の 1 台のみ Up | 同左 | 3 AZ 構成 (stg-1 / stg-2 / stg-3) |

**dev は Excel の前提条件「3AZ 全ての MID サーバが稼働中」を満たさない (1 台構成)。**
高負荷系 (2-2 / M-x) の結果を製品の処理能力として報告する際は、この差分を必ず注記する。

## ディレクトリ構成

```
kakusyou/
├── CLAUDE.md                                 ← 本ファイル
├── README.md                                 セットアップ・実行方法
├── 性能・可用性・非正常系テスト計画書.xlsx       テスト計画書 (旧: 非機能要件テスト計画書)
├── 性能・可用性・非正常系試験_評価報告書.pptx     評価報告書 (slide deck)
├── 性能・可用性・非正常系試験_評価報告書.pdf      評価報告書 PDF 版
│
├── 再測定_実行計画.md              再測定 13 件の計画・経緯・作業ログ
├── 動作確認_書き込み系.md          書き込みを伴う試験のスモーク手順
│
├── _common/                       Python 共通モジュール
│   ├── config.py                  環境設定 (.env 読込)
│   ├── servicenow_auth.py         OAuth Client Credentials 認証 (一部試験用)
│   ├── snow_client.py             ServiceNow REST API クライアント (一部試験用)
│   ├── playwright_helpers.py      Playwright 計測ヘルパー (iframe / measure / summarize)
│   ├── save_auth_state.py         Google SSO + MFA storage_state 保存 (永続プロファイル方式)
│   ├── check_form_login.py        SNOW_USER/SNOW_PASSWORD でフォームログイン疎通確認
│   ├── check_zabbix_connector.py  em_connector_instance の状態確認・継続モニタ
│   ├── preflight_check.py         ★実測前の一括チェック (env/tools/auth/oauth/snow/mid/zabbix)
│   └── fetch_oauth_from_secrets.py ★Secrets Manager から OAuth を取得し jmeter.properties へ反映
│
├── N-common/                      非正常系試験 共通モジュール
│   ├── verify_continuity.py       em_event 到達継続性 検証 (手元実行)
│   └── verify_mid_status.py       ecc_agent.status 変化検出 (手元実行)
│
├── conftest.py                    pytest 共通フィクスチャ (auth.json 自動読込)
├── pytest.ini                     pytest 設定
├── requirements.txt               Python 依存パッケージ
├── jmeter.properties              JMeter プロパティ (秘匿情報)
├── jmeter.properties.example      JMeter テンプレート
├── auth.json                      Playwright storage_state (gitignore)
├── .env                           環境変数 (秘匿情報)
├── .env.example                   .env テンプレート
├── .playwright-profile/           Chromium 永続プロファイル (gitignore)
│
├── 1-1/ … 4-1/                    性能 要件 (サービスデスク / アラームビューワー / ワークフロー / 構成情報)
├── 7-1/ … 9-2/                    可用性・災害対策 要件
├── M-1/ … M-9/                    MID サーバ 性能・可用性 要件
├── M10/                           外部試験成果物 (Trap 送信)
├── M11/                           外部試験成果物 (メール通知 ※参考値)
├── N-1/ … N-5/                    MID サーバ 非正常系 (新設)
│
├── 2-2/                           アラーム処理性能
│   ├── 実行ガイド.md               ★2-2 の手順書 (前提確認〜判定)
│   ├── zabbix_load.py             Mac から script.execute で投入 (旧方式・低速)
│   ├── watch_em_event.py          ★em_event 到達件数の定期モニタ
│   ├── analyze_arrival.py         ★到達分析 (投入 window / 遅延 / 重複)
│   └── count_zabbix_events.py     ★Zabbix 側のイベント生成数カウント (欠損の切り分け)
│
└── zabbixtool/                    Zabbix 操作ツール
    ├── zabbix_bulk_copy_1.py      ホスト大量コピー (アイテム・トリガーごと)
    ├── on.py / on.sh / off.sh     旧・イベント投入 (1 件ごとに zabbix_sender 起動)
    └── send_bulk.py               ★新・一括投入 (zabbix_sender -i / 50 件/秒を達成)
```

## 試験項目マトリクス

### 性能 (15 件)

| カテゴリ | 要件 | 主なツール |
|---|---|---|
| サービスデスク | 1-1, 1-2, 1-3, 1-4 | Playwright + JMeter |
| アラームビューワー | 2-1, 2-2, 2-3, 2-4/5, 2-6 | Playwright + Zabbix 外部投入 |
| ワークフロー | 3-1 | JMeter (incident 並列起票) |
| 構成情報 | 4-1 | 専用スクリプト |

### 可用性・災害対策 (7 件)

ServiceNow 社方針により実機試験不可。**Trust Center / SLA 資料によるドキュメントレビュー方式** で代替: 7-1, 7-2, 7-3, 7-4, 7-5/6/7, 9-1, 9-2 すべて OK。

### MID サーバ 性能 (5 件 + 参考 1 件)

| 要件 | 内容 | 補足 |
|---|---|---|
| M-1〜M-3 | イベント転送スループット系 | Zabbix 外部負荷投入 |
| M-4 | リソース使用率 | `monitor_local.sh` ローカル実行 |
| M-10 | Trap 送信テスト | 外部試験 |
| **M-11** | **メール通知送信機能** | **参考値・出荷条件外** (メール経由の全機器障害通知は設計想定外) |

### MID サーバ 可用性 (5 件)

M-5〜M-9: AZ 停止系試験。

### MID サーバ 非正常系 (5 件・新設)

N-1〜N-5: Disk I/O / CPU / メモリ / Disk Full / TCP 枯渇。各 MID 上でローカル負荷スクリプト + 手元から継続性検証。

## 認証パターン

### REST API 呼び出し
- **方式**: `auth.json` の cookie + `X-UserToken` (`window.g_ck`) ヘッダ
- OAuth Client Credentials / AWS Secrets Manager は **不要**
- 関連: `N-common/verify_continuity.py` / `2-3/test_2_3_alarm_render.py` 等

### Playwright 画面操作
- 既存 `auth.json` を `storage_state` として読み込む (`conftest.py`)
- Google SSO + MFA で取得: `python3 _common/save_auth_state.py`
- `.playwright-profile/` を永続化、2 回目以降 MFA スキップ
- セッション有効期間: 約 8 時間

### JMeter
- OAuth Client Credentials Grant (`/oauth_token.do`)
- `jmeter.properties` の `snow.client_id` / `snow.client_secret`
- setUp Thread Group で取得した token を `${snow.token}` 変数に展開

## 共通的な実行パターン

### pytest (Playwright) 試験

```bash
cd /Users/bx0815610/githubwork/work/servicenow/kakusyou
pytest 2-3/ -v -s          # -s は input() プロンプト表示のため必須
```

### JMeter 試験

```bash
jmeter -n -t 1-2/1-2_concurrent_165.jmx -q jmeter.properties \
  -l 1-2/result.jtl -e -o 1-2/report/
# パラメタ上書き
jmeter -n -t 1-2/...jmx -Jthreads=165 -Jramp_up=30 ...
```

### 非正常系 (3 端末構成)

```bash
# 端末 A (手元)
python3 N-common/verify_continuity.py --label N-1 --duration 600 --max-gap 60 --output N-1/result.json

# 端末 B (MID Server stg-1)
bash /tmp/stress_disk_io.sh 600

# 端末 C (Zabbix 側) - 既存運用イベントで十分なケース多
```

`Enter で計測開始 >` プロンプトで両端末同期。

## 試験ごとの結果ファイル規約

| ファイル | 役割 |
|---|---|
| `<要件>/result*.json` | 生データ・統計 (テストごとに自動生成) |
| `<要件>/RESULT.md` | 判定サマリ・観察事項・実施情報 (人手で書く) |
| `<要件>/result_run<N>.json` | 過去 Run の保管 (やり直し時に rename) |

## Excel テスト計画書の規約

`性能・可用性・非正常系テスト計画書.xlsx` を Python で更新する際の規約:

- 日付列 (実施日): **文字列で `YYYY/M/D` 形式** (例: `2026/6/5`、ゼロ埋めなし、スラッシュ区切り)
- 結果列: `OK` / `NG` / `△` / `参考` / `未実施`
- M-x / N-x を追加するときは `insert_rows()` の後、凡例行のマージ (`A<R>:L<R>`) を unmerge → 再 merge する必要あり
- スタイルは M-9 行を template にコピー (`copy_style()` ヘルパー参照)

## 重要な学び (Learnings)

これらは過去にハマったポイント。同じ問題に当たったら参照する:

### 1. REST API の認証
- ServiceNow Zurich の REST API は **cookie だけでは 401** を返す
- `X-UserToken` ヘッダに `window.g_ck` の値を載せる必要あり
- `Referer` ヘッダも `em_event_list.do` 等の正規 URL に設定

### 2. 高負荷時の em_event 検知
- `ORDERBYsys_created_on` (昇順) でポーリングすると、新着順表示のビューワー 1 ページ目から押し出され DOM で見つからない
- **降順 `ORDERBYDESC` + 計測済 sys_id 除外** で安定

### 3. N-3 メモリ試験で MID Java を温存
- 単純に MemTotal × 80% を確保すると MID Java の Max ヒープ (4096MB) を奪い GC 飢餓で停止
- 既定計算式は **`MemTotal − MID_MAX_MB(4096) − OS_BUFFER_MB(512)`**

### 4. N-5 TCP 枯渇は sysctl 方式
- `ulimit -n` は systemd 起動の MID daemon に効かない
- OS グローバルの `ip_local_port_range` を sysctl で 32768-32800 (33 ポート) に縮小する方式に切替
- 復旧用 `/tmp/n5_orig_range` + 番犬プロセスで kill -9 でも自動復帰

### 5. M-11 メール通知は参考値
- メール経由の全機器障害通知は設計想定外
- 5,000 件処理に約 53 分かかるが **出荷条件には含めず参考値** として記録

### 6. Excel のシート構造
- 「非機能要件テスト計画」シートは **R3 がヘッダ** (R1 タイトル、R2 メタ)
- 「MIDサーバ テスト計画」シートは **R4 がヘッダ** (R1 タイトル、R2 メタ、R3 構成説明)
- `find_cols()` 系ユーティリティで `要件No` 列を検出してから操作する

### 7. Zabbix コネクタ バースト時取りこぼし (制限事項)
- ServiceNow サポート確認済の既知事象
- 発生条件: Zabbix の性能限界レベルの負荷 (ローカルからのバースト性能)
- 発生率: 0.02%
- 通常運用 (50 障害/秒以下) では再現せず
- 取りこぼしは Zabbix 側に残るため再送・運用回避可能
- **次回製品修正までの暫定制限事項**

### 8. JMeter の `-p` は既定 properties を「置き換える」
- `-p jmeter.properties` は指定ファイルを**既定の jmeter.properties の代わりに**読み込む
- リポジトリの `jmeter.properties` は 15 行しかないため、`summariser.name` 等の既定が全部失われ、
  実行中の `summary = ...` 進捗が出なくなる
- **追加読み込みは `-q`（`--addprop`）を使う。全コマンドを `-q` に統一済み (2026/7/31)**
- あわせて `jmeter.properties` のグローバル値 (`ramp_up` / `loop.count` / `threads.normal`) が
  全 JMX の `__P()` 既定を上書きするため、**条件は必ず `-J` で明示指定する**

### 9. em_event / incident への POST は 201 を返す
- Response Assertion を `200` のみにしていると**全件エラー判定**になる
- M-1 がこの状態だった (2026/8/14 に修正)。M-3 はそもそもアサーションが無かった
- 現在は M-1 / M-2 / M-3 とも `201` で統一

### 10. HeaderManager の Authorization 重複で 400
- M-2 / M-3 の JMX に `Authorization: Bearer ...` が **2 行**入っており、
  ServiceNow 前段 (`snow_adc`) が重複ヘッダを **400 Bad Request** で拒否していた
- curl では再現しないので JMeter 側のヘッダを疑うこと
- レスポンス本文の採取:
  `-Jjmeter.save.saveservice.output_format=xml -Jjmeter.save.saveservice.response_data=true`

### 11. 1-4 は iframe 経由でないとフォームを操作できない
- Classic UI のコンテンツは `iframe#gsft_main` の中。トップレベル `page` に `fill()` しても見つからない
- `_common/playwright_helpers.snow_goto_and_wait()` が返すコンテンツロケーター経由で操作する

### 12. 1-4 は「保存して留まる」を使うと 4〜5 件で UI が停止する
- `sysverb_insert_and_stay` はレコードを開いたまま次へ進むため、セッション側にリソースが溜まり、
  **4〜5 件で `page.goto` すら 30 秒タイムアウトするようになる**。再ログインで一時回復するだけ
- **通常の Submit (`sysverb_insert`) に変えると 1,000 件を連続実行できる** (2026/8/19 実証)
- Submit 方式では保存後に一覧へ戻るため、フォームから番号を取得できない。
  `short_description` に `[run=<tag>]` を埋め込み、**実行後に REST で突合**する方式にしている
- `#output_messages` は常時 DOM に存在し普段は `outputmsg_hide` で非表示。可視待ちは不安定

### 13. Zabbix `host.get` の前方一致は `startSearch`
- `searchWildcardsEnabled: true` を付けると `*` を明示しない限り**完全一致**になる
- 前方一致は `{"search": {"host": prefix}, "startSearch": True}`
- これを誤って「Zabbix の負荷用ホストが 0 件」と誤検知した (2026/8/14)。実際は 30,002 件存在

### 14. Zabbix は OK→PROBLEM の遷移でしかイベントを生成しない
- すでに PROBLEM のトリガーに再度 `value=1` を送っても**イベントは発生しない**
- 連続して負荷試験を行う場合、**毎回、事前に復旧させる**こと
  ```bash
  python3 send_bulk.py --count 30000 --rate 50 --value 0   # 復旧
  python3 send_bulk.py --count 30000 --rate 50             # 投入
  ```

### 15. `on.py` では要件レートが出ない → `send_bulk.py` を使う
- `on.py` は 1 イベントごとに `zabbix_sender` プロセスを起動するため、`sleep(0.02)` を入れても
  **実効 12.5 件/秒**しか出ない (30,000 件で約 40 分)
- `send_bulk.py` は `zabbix_sender -i -` で 1 秒ごとに 50 件を一括送信し、
  **30,000 件 / 600 秒 / 50.0 件/秒 / 失敗 0** を達成 (2026/8/19 実測)
- 前回 nonprod で記録した「実効 17.6 rps・880 件失敗」も投入方式の問題だった可能性が高い

### 16. `time_of_event` は Zabbix 側の発生時刻ではない
- ServiceNow が登録時に上書きするため `sys_created_on` とほぼ同値 (差 0〜1 秒)
- **投入側と ServiceNow 側の律速を切り分ける用途には使えない**
- 切り分けには `2-2/count_zabbix_events.py` で Zabbix 側の生成数を数えて突合する

### 17. dev の MID は t3.small で本番相当ではない
- dev: t3.small (2 GiB) × Up 1 台 / nonprod: t3.large (8 GiB) × 3AZ
- MID Java の Max ヒープ 4096MB (学び 3) は **2 GiB のマシンでは成立しない**
- t3 は burstable。ベースライン (t3.small は 40%) を超える負荷が続くとクレジット枯渇で絞られる
- 2026/8/19 の 2-2 で「13,500 件到達後 46 分間まったく進まない」という**停止**が発生。
  性能不足ではなく処理系の停止を示す挙動で、OOM またはクレジット枯渇が疑われる
- **高負荷系の結果を製品の限界として報告しないこと。環境差分の注記が必須**

### 18. MID の Java ヒープが処理能力を直接左右する（2026/8/20 実証）
- EC2 のインスタンスタイプを変えても **`wrapper.java.maxmemory` は自動で変わらない**
- dev は t3.large 化後も **1024 MB のまま**で、2-2 の 30,000 件投入に対し
  **13,500 件（54.8% 欠損）で処理が停止**していた
- **4096 MB に変更しただけで 30,000 件すべて到達・欠損ゼロ**になった
- 設定は `wrapper.conf` ではなく **`conf/wrapper-override.conf`** に書く
  （`wrapper.conf` は MID のアップグレードで上書きされる）
  ```
  wrapper.java.maxmemory=4096
  ```
- 反映確認: `ps aux | grep "[j]ava.*mid" | grep -o "Xmx[0-9]*[mMgG]"`

### 19. MID の conf ディレクトリに他ユーザ所有のファイルを置かない
- 起動時の `FileSystemPermissionsTest` が conf 配下を全走査し、
  **読めないファイルが 1 つでもあると `StartupSequencer: test failure` で起動しない**
- root で `cp` / `sed -i` すると root 所有になり、MID (`mid-server` ユーザ) が読めなくなる
- 2026/8/20 に `conf/wrapper-override.conf.bak_*` を置いて MID が起動不能になった
- **バックアップは `/root` や `/tmp` など conf の外に取る**
- 復旧: `find /opt/midserver/agent/conf -name "*.bak_*" -exec mv {} /root/ \;` +
  `chown -R mid-server:mid-server /opt/midserver/agent/conf`

### 20. `gs.dateGenerate()` はセッションのタイムゾーンで解釈される
- `sysparm_query` で `sys_created_on>=javascript:gs.dateGenerate('YYYY-MM-DD','HH:MM:SS')`
  を使う場合、**JST セッションなら JST の値をそのまま渡す**
- UTC に変換して渡すと 9 時間ずれる（2026/8/20 に `analyze_arrival.py` で発生）
- API のレスポンス (`sys_created_on`) は UTC なので、そちらと混同しないこと

### 21. 長時間の投入は nohup / screen で走らせる
- `send_bulk.py` を前面実行していて **セッション断で 12,600 件（4.2 分）で停止**した
  （2026/8/20。Zabbix 側の性能問題ではなく単なるプロセス終了）
- 10 分の投入でも切れるときは切れる
  ```bash
  nohup python3 -u send_bulk.py --count 30000 --rate 50 > /tmp/send.log 2>&1 &
  tail -f /tmp/send.log
  ```
- **`-u` を付けないと Python の stdout がバッファされ、ログに何も出ない**
- 二重投入を防ぐため、再実行前に必ず `ps aux | grep "[s]end_bulk"` で確認する

### 22. 2-2 の再測定は「復旧 → 待ち → 投入」の 3 段構え
1. `send_bulk.py --value 0` で全トリガーを復旧（10 分）
2. `count_zabbix_events.py --show-problems` で **PROBLEM が 0 件**を確認
3. **復旧イベント 30,000 件が ServiceNow に流れ切るまで待つ（30〜40 分）**
   `watch_em_event.py --once` を数分おきに実行し、件数が動かなくなるまで
4. その値をベースラインにして投入

3 を省くと復旧イベントが今回分に混ざり、到達数が読めなくなる。

## 環境変数 (.env)

```
SNOW_INSTANCE=biglobenonprod
SNOW_BASE_URL=https://biglobenonprod.service-now.com
SNOW_USER=mono                   # ローカルユーザ (フォームログイン用、MFA 有効)
SNOW_PASSWORD=...
ZABBIX_URL=https://10.249.73.66/zabbix/api_jsonrpc.php
ZABBIX_USER=mono
ZABBIX_PASSWORD=...
ZABBIX_TOKEN=...
ZABBIX_SCRIPT_ID=4               # script.execute 用 ID
ZABBIX_VERIFY_TLS=false
MID_HOSTS=mid-a.example.com,mid-b.example.com,mid-c.example.com
```

## 評価報告書の更新フロー

評価報告書 pptx は Node.js + pptxgenjs で生成:

```bash
# ローカル
node build_report.js 性能・可用性・非正常系試験_評価報告書.pptx

# PDF 化
soffice --headless --convert-to pdf 性能・可用性・非正常系試験_評価報告書.pptx
```

`build_report.js` 本体は別途管理。配色テーマは Midnight Executive (`#1E2761` navy + `#CADCFC` ice + `#FFC857` accent)。

## 注意・避けるべきこと

- 旧名 `非機能要件テスト計画書.xlsx` / `非機能要件_評価報告書.*` は削除済み。再生成時は新名 `性能・可用性・非正常系...` を使う
- `auth.json` / `jmeter.properties` / `.env` は gitignore 対象。コミットしない
- `.playwright-profile/` も gitignore。永続プロファイルなので機密 cookie を含む
- N-* の負荷スクリプトは MID 本番には絶対実行しない (stg-1 に限定)
- N-4 は既定で 100% Disk Full にする。`/tmp` と MID ログ FS が同じ場合は `TARGET=/var/tmp/n4.bin` で切替
- N-5 は sudo 必須、別経路 (コンソール or 別 SSH) を事前確保

## 作業終了時のルーティン

リポジトリは git 管理 (githubwork)。以下の順:

1. テスト結果が含まれる場合: `result*.json` は gitignore 対象なのでコミットしない
2. RESULT.md / README.md / Excel / pptx は git 管理 (履歴を残す)
3. コミットメッセージは `[要件No] 動作概要` 形式を推奨
4. `git push origin <branch>` でアップ

---

## クイックリファレンス

| やりたいこと | コマンド |
|---|---|
| 実測前の一括チェック | `python3 _common/preflight_check.py` |
| OAuth を Secrets Manager から反映 | `source setup.sh big4180 prd` → `python3 _common/fetch_oauth_from_secrets.py --write` |
| auth.json 取り直し | `python3 _common/save_auth_state.py` |
| auth.json 生存確認 | `python3 2-3/api_probe.py` |
| Zabbix へイベント投入 (サーバ上) | `python3 send_bulk.py --count 30000 --rate 50` (事前に `--value 0` で復旧) |
| em_event 到達モニタ | `python3 2-2/watch_em_event.py --baseline <N> --interval 30` |
| 到達分析 | `python3 2-2/analyze_arrival.py --since "HH:MM" --json 2-2/result_2_2.json` |
| Zabbix 側の生成数確認 | `python3 2-2/count_zabbix_events.py --from "HH:MM" --to "HH:MM" --show-problems` |
| 1-4 の 1,000 件起票 | `PERF_SUBMIT_MODE=submit pytest 1-4/ -v -s` |
| 非正常系試験 N-1 | `python3 N-common/verify_continuity.py --label N-1 ...` + MID で `bash N-1/stress_disk_io.sh 600` |
| Zabbix コネクタ確認 | `python3 N-common/check_zabbix_connector.py --name zabbix` |
| Excel に試験結果書き込み | M-9 行をテンプレに copy_style + 実施日は `YYYY/M/D` 文字列 |
| 評価報告書再生成 | `node build_report.js ...` + `soffice --headless --convert-to pdf` |
