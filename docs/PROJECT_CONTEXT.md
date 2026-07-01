# PROJECT_CONTEXT.md

このファイルは `kyoutei_auto_entry` 案件の固有情報です。

## 目的

- `kyoutei_bunseki` から流れる競艇通知を受信する
- BOAT RACE 公式投票サイト `https://ib.mbrace.or.jp/` へ Playwright で自動入力する
- 朝 8:00 の候補通知と、締切 1 分前の最終通知を同じ Discord チャンネルから処理できるようにする

## 現在の状態

- リポジトリ構成は `keirin_auto_entry` を土台にコピーして作成した
- 通常向けの商品名は kyoutei_auto_trade、クリアイズム様向けの商品名は AQUA EDGE AI
- BRONZE、SILVER、GOLD などのプラン区分や利用枠選択は使わない
- 中央投票の主対象は競艇へ置き換え済み
- 利用者ID認証は、クリアイズム様向けが auth_clear.py、通常向けが auth_master.py を使う
- 受信側は JSON だけでなく、`kyoutei_bunseki` のプレーンテキスト通知も読める
- 候補通知は `pre_race_candidates` として扱い、ログ反映とブラウザ起動制御だけを行う
- 最終通知は `entry_tickets` として扱い、中央発注キューへ投入する
- Discord 定型文の最終通知では、本文の投資額を発注準備後も維持し、自動投票側の目標払戻設定では再計算しない
- 公式サイト操作は、ログイン、場選択、レース選択、`BOAT.reg_service.addBet(...)`、確認画面、投票実行まで実装済み
- 最終通知は `締切 HH:MM` から `tool_slot` を補完する（10時前は morning、18時前は daytime、18時以降は midnight）
- BOAT RACE 公式サイトのサービス時間外を避けるため、中央投票ブラウザの自動起動は `10:00-21:00` に固定する。時間外は起動済みブラウザも閉じる。

## 中央投票サイトの認証項目

- `ipat.inet_id` = 加入者番号
- `ipat.pars_no` = 暗証番号
- `ipat.password` = 認証用パスワード
- `ipat.login_id` = 投票用パスワード

## ディレクトリ構成

```text
.
├── AGENTS.md
├── README.md
├── VERSION.txt
├── main.py
├── app.py
├── config.py
├── discord_client.py
├── payload_parser.py
├── ipat_playwright.py
├── service.py
├── kyoutei_auto_entry.spec
├── build_release.py
├── tests/
└── docs/
```

## 実行手順

```bash
cd /home/user/src/kyoutei/kyoutei_auto_entry
python3 -m venv .venv
source .venv/bin/activate
pip install playwright discord.py pyinstaller customtkinter
python3 -m playwright install chromium
python3 main.py
```

## テスト

```bash
cd /home/user/src/kyoutei/kyoutei_auto_entry
python3 -m unittest tests.test_payload_parser tests.test_config tests.test_product_profile tests.test_ipat_playwright tests.test_service_routing
```

## ビルド

クリアイズム様向けは、AQUA EDGE AI_GOLD / AQUA EDGE AI_SILVER / AQUA EDGE AI_BRONZE の3本を作る。通常向けは3券種対応でグレード表示なしの kyoutei_auto_trade.exe を作る。

まとめて作る場合は、bash build_all_lines.sh を実行する。

## Distribution Profile

- Distribution Required: yes
- Package Type: python-exe
- Version Source: `VERSION.txt`
- Artifact Naming: クリアイズム様向けは NAME_vX.Y.Z.exe、通常向けは kyoutei_auto_trade.exe
- Spec: `kyoutei_auto_entry.spec`
- Build Script: `build_release.py`

## 注意点

- 公式サイトの画面更新に追従するため、`config.py` と `ipat_playwright.py` のセレクタと公式 JS 呼び出しの整合確認が継続的に必要
- `submit_enabled=OFF` では確認画面まで進み、最終確定は行わない
- 候補通知は朝 8:00 運用を前提に `tool_slot=morning` として正規化している
- 中央投票サイトの開始・終了対象レースはおおむね `10:30-20:30` のため、事前ログイン枠は `10:00-21:00` とする
