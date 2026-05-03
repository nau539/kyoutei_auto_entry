# PROJECT_CONTEXT.md

このファイルは `kyoutei_auto_entry` 案件の固有情報です。

## 目的

- `kyoutei_bunseki` から流れる競艇通知を受信する
- BOAT RACE 公式投票サイト `https://ib.mbrace.or.jp/` へ Playwright で自動入力する
- 朝 8:00 の候補通知と、締切 1 分前の最終通知を同じ Discord チャンネルから処理できるようにする

## 現在の状態

- リポジトリ構成は `keirin_auto_entry` を土台にコピーして作成した
- 中央投票の主対象は競艇へ置き換え済み
- 受信側は JSON だけでなく、`kyoutei_bunseki` のプレーンテキスト通知も読める
- 候補通知は `pre_race_candidates` として扱い、ログ反映とブラウザ起動制御だけを行う
- 最終通知は `entry_tickets` として扱い、中央発注キューへ投入する
- 公式サイト操作は、ログイン、場選択、レース選択、`BOAT.reg_service.addBet(...)`、確認画面、投票実行まで実装済み

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

```bash
cd /home/user/src/kyoutei/kyoutei_auto_entry
python3 build_release.py --spec kyoutei_auto_entry.spec --clean
```

## Distribution Profile

- Distribution Required: yes
- Package Type: python-exe
- Version Source: `VERSION.txt`
- Artifact Naming: `NAME_vX.Y.Z.exe`
- Spec: `kyoutei_auto_entry.spec`
- Build Script: `build_release.py`

## 注意点

- 公式サイトの画面更新に追従するため、`config.py` と `ipat_playwright.py` のセレクタと公式 JS 呼び出しの整合確認が継続的に必要
- `submit_enabled=OFF` では確認画面まで進み、最終確定は行わない
- 候補通知は朝 8:00 運用を前提に `tool_slot=morning` として正規化している
