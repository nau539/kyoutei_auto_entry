# AQUA EDGE AI

AQUA EDGE AI は、Discord の競艇通知を監視し、Playwright 経由で BOAT RACE 公式投票サイトへ自動入力する GUI ツールです。

現在の中央投票フローは https://ib.mbrace.or.jp/ を対象にしています。朝 8:00 の候補一覧通知と、締切 1 分前の最終通知の両方を受信できます。

## 対応している入力

- JSON の entry_tickets
- JSON の pre_race_candidates
- kyoutei_bunseki が現在送っているプレーンテキスト通知
- 競艇候補 20260410 ...
- 競艇通知 大村 1R ...

候補通知はログ表示とブラウザ起動制御だけに使い、発注キューには入れません。最終通知だけが発注対象です。

## 必要な認証情報

設定画面の中央接続には次の 4 項目を入力します。

- 加入者番号
- 暗証番号
- 認証用パスワード
- 投票用パスワード

内部の設定マッピングは以下です。

- ipat.inet_id = 加入者番号
- ipat.pars_no = 暗証番号
- ipat.password = 認証用パスワード
- ipat.login_id = 投票用パスワード

設定ファイル名は kyoutei_auto_entry_config.json です。

## セットアップ

1. cd /home/user/src/kyoutei/kyoutei_auto_entry
2. python3 -m venv .venv
3. source .venv/bin/activate
4. pip install playwright discord.py pyinstaller customtkinter
5. python3 -m playwright install chromium

## 実行

1. cd /home/user/src/kyoutei/kyoutei_auto_entry
2. python3 main.py

## テスト

1. cd /home/user/src/kyoutei/kyoutei_auto_entry
2. python3 -m unittest tests.test_payload_parser tests.test_config tests.test_product_profile tests.test_ipat_playwright tests.test_service_routing

## Discord 連携の前提

secrets_local.py に少なくとも以下を設定します。

- DISCORD_BOT_TOKEN
- DISCORD_CENTRAL_CHANNEL_IDS
- DISCORD_LOCAL_CHANNEL_IDS
- DISCORD_ALLOWED_GUILD_IDS

## 競艇の中央投票フロー

現在の実装は次の順で動きます。

1. https://ib.mbrace.or.jp/ のログイン画面へアクセス
2. 加入者番号、暗証番号、認証用パスワードを入力
3. ログインボタン押下で開く公式ポップアップ画面へ遷移
4. TOP 画面で対象場を選択
5. 対象レースを選択
6. 公式 JS の BOAT.reg_service.addBet で買い目を追加
7. 投票内容確認画面へ進む
8. 金額と投票用パスワードを入力
9. 投票実行

券種コードは公式 JS の定義に合わせています。

- 単勝 = 1
- 複勝 = 2
- 2連単 = 3
- 2連複 = 4
- 拡連複 = 5
- 3連単 = 6
- 3連複 = 7

## ビルド

配布はクリアイズム様向け3本と、通常向け1本を作る。製品ライン、エディション、認証先はビルド時のruntime hookで固定するため、EXE名だけに依存しない。

- クリアイズム様向け GOLD: python build_release.py --spec kyoutei_auto_entry.spec --line clearism --edition GOLD --auth-module auth_clear --app-name "AQUA EDGE AI_GOLD" --clean
- クリアイズム様向け SILVER: python build_release.py --spec kyoutei_auto_entry.spec --line clearism --edition SILVER --auth-module auth_clear --app-name "AQUA EDGE AI_SILVER" --clean
- クリアイズム様向け BRONZE: python build_release.py --spec kyoutei_auto_entry.spec --line clearism --edition BRONZE --auth-module auth_clear --app-name "AQUA EDGE AI_BRONZE" --clean
- 通常向け: python build_release.py --spec kyoutei_auto_entry.spec --line aqua --edition BRONZE --auth-module auth_master --app-name kyoutei_auto_trade --no-version-suffix --clean

4本まとめてビルドする場合は bash build_all_lines.sh を実行する。

- クリアイズム様向けは、GOLD/SILVER/BRONZEごとに選べる日区分（モーニング/日中/ナイター）の上限が変わる。
- 通常向けは、auth_masterを使う固定名の kyoutei_auto_trade.exe として作成する。
- 開発時に手元で挙動を切り替えるには環境変数 APP_LINE、APP_EDITION、APP_AUTH_MODULE を指定する。

### 送信側（kyoutei_bunseki）
- 通知は `aqua3` 戦略（ナイター・信頼度0.86・2連複/3連複/3連単を同時通知・100円固定）を使う。
- cron は `dispatch-pick --strategy aqua3 ...` / `dispatch-watch --strategy aqua3 ...`。投資額は受信側で調整する前提で100円固定で送る。

## 現状の注意点

- 公式サイトの DOM と公式 JS 名に依存するため、サイト更新が入ると config.py と ipat_playwright.py の調整が必要です。
- 実口座を使う処理なので、初回は submit_enabled=OFF で確認画面まで動くことを先に確認する前提です。
- BOAT RACE 公式サイトのサービス時間外を避けるため、中央投票ブラウザは標準で 10:00-21:00 の間だけ起動し、時間外は閉じます。
- 受信側はプレーンテキスト通知も読めますが、将来的には JSON へ寄せた方が保守しやすいです。
