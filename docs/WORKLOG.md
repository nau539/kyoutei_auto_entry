# WORKLOG.md
> Codex作業ログ。各タスクで追記する。

## 記録テンプレート
- Date: YYYY-MM-DD
- Task: 作業タイトル
- Summary: 目的を1〜2行
- Changed files: 変更ファイル一覧
- Verification: 実施した確認・結果
- Open items: 未解決事項（なければ `なし`）

## 2026-02-18
- Task: 競輪版プロジェクトの初期コピーとドキュメント初期化
- Summary: `auto_entry` を `keirin_auto_entry` として新規ディレクトリへコピーし、`AGENTS.md` と `docs` を競輪案件向けに初期化した。
- Changed files: `AGENTS.md`, `docs/AGENTS.md`, `docs/PROJECT_CONTEXT.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`, `docs/CHANGELOG_CUSTOMER.md`, `docs/SETUP_GUIDE.md`
- Verification:
  - `rsync` によるコピー完了確認
  - `rg` で旧案件パス/旧履歴の残存を確認
- Open items:
  - 競輪仕様への機能変換（券種・画面遷移・連携先定義）は次タスクで実施

## 2026-02-18
- Task: `keirin_auto_entry` への一括リネーム
- Summary: プロジェクト名・spec名・設定ファイル名・UI表示名・ログファイル名を `keirin_auto_entry` 系へ一括置換し、README/PROJECT_CONTEXT/テスト参照も整合させた。
- Changed files: `README.md`, `auth.py`, `config.py`, `main.py`, `service.py`, `sync_to_windows.sh`, `tests/test_config.py`, `ui/main_window.py`, `auto_entry.spec`(削除), `keirin_auto_entry.spec`(追加), `docs/PROJECT_CONTEXT.md`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`, `VERSION.txt`
- Verification:
  - `python3 -m py_compile config.py main.py auth.py service.py build_release.py ui/main_window.py tests/test_config.py`
  - `python3 -m unittest tests.test_config tests.test_service_review tests.test_service_routing`
  - `rg -n -P "(?<!keirin_)auto_entry"` で旧名残存を確認（コピー元説明の文脈のみ残す）
- Open items:
  - 競輪向け機能仕様（券種/連携先/自動操作導線）の実装は未着手

## 2026-02-18
- Task: 競輪向けセレクタ導入と接続設定UIの置換
- Summary: 競馬向けの中央/地方入力項目を設定画面から外し、競輪のログインURL・認証ID・パスワード・暗証番号へ置換。`keirin.jp` フローのログイン〜投票確定までをデバッグログ付きで実装した。
- Changed files: `config.py`, `ipat_playwright.py`, `tests/test_ipat_playwright.py`, `ui/views/settings_view.py`, `ui/main_window.py`, `README.md`, `docs/PROJECT_CONTEXT.md`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`, `VERSION.txt`
- Verification:
  - `python3 -m py_compile config.py ui/views/settings_view.py ui/main_window.py ipat_playwright.py`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
- Open items:
  - 競輪画面側のDOM変更時は `config.py` の競輪セレクタ群更新が必要
  - 買い目ごとに100円以外を設定する金額編集UI（修正/修正完了）の自動操作は未実装

## 2026-02-18
- Task: Discord受信チャンネルIDの更新
- Summary: 指定チャンネルID `1473307440769400994` を受信対象として `secrets_local.py` に反映し、互換用ローカルルートは空設定に整理した。
- Changed files: `secrets_local.py`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m unittest tests.test_service_routing`
- Open items:
  - なし

## 2026-02-18
- Task: 競輪買い目の金額修正フロー追加
- Summary: 競輪の各買い目セット後に `修正` → 金額入力（既定値クリア）→ `修正完了` を順次実行する処理を追加し、成立予定金額と指示金額の不一致エラーを解消した。
- Changed files: `ipat_playwright.py`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile ipat_playwright.py`
  - `python3 -m unittest tests.test_ipat_playwright tests.test_service_routing`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
- Open items:
  - 競輪画面側で金額編集UIのDOM構造が変わった場合は、買い目グループ検出セレクタの更新が必要

## 2026-02-18
- Task: 競輪買い目グループ照合の再修正
- Summary: 組番抽出が `7-1-7-1` になるケースを吸収するため、グループ照合ロジックを強化し、修正モード遷移後に入力欄が有効化されるまで待機するよう改善した。
- Changed files: `ipat_playwright.py`, `tests/test_ipat_playwright.py`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile ipat_playwright.py tests/test_ipat_playwright.py`
  - `python3 -m unittest tests.test_ipat_playwright tests.test_service_routing`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
- Open items:
  - 競輪画面側で金額編集UIのDOM構造が変わった場合は、買い目グループ検出セレクタの更新が必要

## 2026-02-18
- Task: 競輪フローの速度改善と投票ボタン押下追加
- Summary: 金額修正待機を短縮し、最終確定OFF時でも「投票」ボタンを自動押下して暗証番号入力画面で待機するように変更した。
- Changed files: `ipat_playwright.py`, `tests/test_ipat_playwright.py`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile ipat_playwright.py tests/test_ipat_playwright.py`
  - `python3 -m unittest tests.test_ipat_playwright tests.test_service_routing`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
- Open items:
  - 競輪画面側で金額編集UIのDOM構造が変わった場合は、買い目グループ検出セレクタの更新が必要

## 2026-02-18
- Task: 競輪の資金不足検知とトップ復帰
- Summary: 競輪買い目入力中に購入限度額超過/残高不足の警告を検知したら即エラー化し、実行失敗時に `KEIRIN.JP TOP` へ戻す復帰処理を追加した。
- Changed files: `ipat_playwright.py`, `tests/test_ipat_playwright.py`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile ipat_playwright.py tests/test_ipat_playwright.py`
  - `python3 -m unittest tests.test_ipat_playwright tests.test_service_routing`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
- Open items:
  - 競輪画面側で警告文言が変更された場合は、資金不足判定キーワードの更新が必要

## 2026-02-19
- Task: ログのターゲット表記（中央/地方）削除
- Summary: 競輪運用では中央/地方の区別が不要なため、ログ先頭の `[中央]` / `[地方]` プレフィックス出力を停止した。
- Changed files: `service.py`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile service.py`
  - `python3 -m unittest tests.test_service_review tests.test_service_routing`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
- Open items:
  - なし

## 2026-02-19
- Task: 競輪の未発売/締切レースを見送り扱いに変更
- Summary: 会場は検出できるが指定Rの投票導線が見つからないケースを `unavailable_race` として返し、発注失敗ではなく見送り処理へ変更した。
- Changed files: `ipat_playwright.py`, `tests/test_ipat_playwright.py`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile ipat_playwright.py tests/test_ipat_playwright.py`
  - `python3 -m unittest tests.test_ipat_playwright tests.test_service_routing`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
- Open items:
  - 実サイト側の表示仕様変更時は、未発売/締切判定メッセージの見直しが必要

## 2026-02-19
- Task: 競輪開催一覧の会場優先フォールバック
- Summary: 競輪TOPの一覧が未更新でR表示がずれている場合でも、会場一致なら投票ボタンを押して投票画面へ進むフォールバックを追加した。
- Changed files: `ipat_playwright.py`, `tests/test_ipat_playwright.py`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile ipat_playwright.py tests/test_ipat_playwright.py`
  - `python3 -m unittest tests.test_ipat_playwright tests.test_service_routing`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
- Open items:
  - 投票画面遷移後の対象R切替仕様が変わった場合は、会場優先時の遷移確認条件を見直す

## 2026-03-01
- Task: 資金不足時の確認ダイアログ後トップ復帰を強化
- Summary: 購入限度額超過で失敗した際、`OK` 確認ダイアログの表示タイミングに依存せず `KEIRIN.JP TOP` へ戻るよう復帰処理をリトライ化し、トップ判定も厳密化した。
- Changed files: `ipat_playwright.py`, `tests/test_ipat_playwright.py`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile ipat_playwright.py tests/test_ipat_playwright.py`
  - `python3 -m unittest tests.test_ipat_playwright`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
- Open items:
  - 競輪画面側でトップボタンや確認ダイアログのDOMが変更された場合は、セレクタ再確認が必要

## 2026-03-01
- Task: トップ復帰後の遅延OKダイアログ自動処理
- Summary: 資金不足時にトップ復帰判定後で遅れて表示される確認ダイアログを後処理で再確認し、`OK` 自動押下を追加してトップ待機状態へ確実に戻すよう修正した。
- Changed files: `ipat_playwright.py`, `tests/test_ipat_playwright.py`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile ipat_playwright.py tests/test_ipat_playwright.py`
  - `python3 -m unittest tests.test_ipat_playwright`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
- Open items:
  - 競輪画面側で確認ダイアログの表示仕様が変わった場合は、待機時間や判定条件の再調整が必要

## 2026-03-01
- Task: トップ復帰失敗時の状態デバッグログ追加
- Summary: ユーザー報告の「トップに戻れていない」事象を切り分けるため、`_keirin_return_top` に復帰段階ごとの状態ログ（URL/可視要素/警告文）を追加した。
- Changed files: `ipat_playwright.py`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile ipat_playwright.py tests/test_ipat_playwright.py`
  - `python3 -m unittest tests.test_ipat_playwright`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
- Open items:
  - 実環境ログ取得後、必要に応じてトップ判定条件（URL/DOM）を追加調整する

## 2026-03-01
- Task: racevote画面をトップ誤判定しないよう修正
- Summary: デバッグログで `url=/pc/racevote` なのに `top=1` となっていたため、トップ判定を URL優先に見直し、投票入力UI可視時はトップ扱いしない条件を追加した。
- Changed files: `ipat_playwright.py`, `tests/test_ipat_playwright.py`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile ipat_playwright.py tests/test_ipat_playwright.py`
  - `python3 -m unittest tests.test_ipat_playwright`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
- Open items:
  - 実環境で資金不足ケースを再実行し、`top=0` からトップ復帰へ遷移するログ確認が必要

## 2026-03-01
- Task: トップ復帰デバッグログの通常運用向け削減
- Summary: ユーザー確認で復帰動作が安定したため、`トップ復帰デバッグ` の段階ログを除去し、復帰失敗時のみ最低限のエラーログを残す形へ整理した。
- Changed files: `ipat_playwright.py`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile ipat_playwright.py tests/test_ipat_playwright.py`
  - `python3 -m unittest tests.test_ipat_playwright`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
- Open items:
  - なし

## 2026-03-02
- Task: 競輪（中央）待機維持の10分自動更新を追加
- Summary: 地方のみだったkeepalive処理を中央（競輪）にも拡張し、監視中に10分ごとに `KEIRIN.JP` TOP更新を実行してセッション維持するよう変更した。
- Changed files: `service.py`, `ipat_playwright.py`, `tests/test_service_routing.py`, `tests/test_ipat_playwright.py`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile service.py ipat_playwright.py tests/test_service_routing.py tests/test_ipat_playwright.py`
  - `python3 -m unittest tests.test_service_routing tests.test_ipat_playwright`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
- Open items:
  - 実運用で10分経過時に「待機維持: 10分経過のためKEIRIN.JPを更新しました」が定期出力されることを確認する

## 2026-03-02
- Task: 競輪の固定スケジュール自動開閉を追加
- Summary: 競輪ブラウザを固定時刻で自動開閉する機能を追加し、終了時刻で自動停止・開始時刻帯で自動起動（事前準備実行）できるようにした。開始/終了時刻は設定画面から変更可能にした。
- Changed files: `config.py`, `service.py`, `ui/views/settings_view.py`, `tests/test_config.py`, `tests/test_service_routing.py`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile config.py service.py ipat_playwright.py ui/views/settings_view.py tests/test_service_routing.py tests/test_ipat_playwright.py tests/test_config.py`
  - `python3 -m unittest tests.test_config tests.test_service_routing tests.test_ipat_playwright`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
- Open items:
  - 実運用で `23:30` 停止 / `08:00` 起動ログ（待機スケジュール）を確認する

## 2026-03-02
- Task: 設定JSONフォーマットのテンプレート作成
- Summary: ユーザー提示の設定を基準に、`ID/パスワード/認証ID` を空にした `keirin_auto_entry_config.json` フォーマットを追加した。
- Changed files: `keirin_auto_entry_config.json`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m json.tool keirin_auto_entry_config.json`
- Open items:
  - なし

## 2026-03-02
- Task: 競輪TOP導線検出のセレクタ拡張（大垣1R失敗対応）
- Summary: 競輪TOPの開催一覧・投票ボタン検出セレクタを拡張し、背景色クラス差分や要素種別差分（button/input/a）がある場合でも対象会場の投票導線を検出できるよう修正した。
- Changed files: `config.py`, `ipat_playwright.py`, `tests/test_ipat_playwright.py`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile config.py ipat_playwright.py tests/test_ipat_playwright.py`
  - `python3 -m unittest tests.test_ipat_playwright`
  - `python3 -m unittest tests.test_config tests.test_service_routing tests.test_ipat_playwright`
- Open items:
  - 実運用で大垣など開催行クラス差分のレースに対して投票導線ログが出ることを確認する

## 2026-03-02
- Task: 事前候補JSON（pre_race_candidates）受信の分岐追加
- Summary: `payload_parser` に `message_type=pre_race_candidates` の正規化を追加し、`service` では候補受信ログのみ行って発注キューへ投入しない分岐を実装した。誤発注を防ぎつつ、事前候補の時刻/レース情報を受け取れるようにした。
- Changed files: `payload_parser.py`, `service.py`, `tests/test_payload_parser.py`, `tests/test_service_routing.py`, `README.md`, `docs/PROJECT_CONTEXT.md`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`, `VERSION.txt`
- Verification:
  - `python3 -m py_compile payload_parser.py service.py`
  - `python3 -m unittest tests.test_payload_parser tests.test_service_routing`
- Open items:
  - なし

## 2026-03-02
- Task: 起動時の候補通知（pre_race_candidates）履歴再取得
- Summary: 監視開始時に Discord REST で許可チャンネルの直近履歴を取得し、当日 `pre_race_candidates` を候補ログとして再取り込みできるようにした。投票実行JSONは再処理しないため、再起動時も誤発注しない。
- Changed files: `discord_client.py`, `service.py`, `tests/test_service_routing.py`, `README.md`, `docs/PROJECT_CONTEXT.md`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`, `VERSION.txt`
- Verification:
  - `python3 -m py_compile discord_client.py service.py`
  - `python3 -m unittest tests.test_service_routing`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
- Open items:
  - なし

## 2026-03-04
- Task: 3モード通知（勝負/平均/守り）に対応した受信フィルタを追加
- Summary: Discord買い目payloadの `strategy_name/strategy_code` を受信できるようにし、設定画面へ「受信戦略（勝負/平均/守り/全部）」を追加。`service` 側で戦略不一致payloadを見送り、誤発注を防ぐ動作へ変更した。
- Changed files: `config.py`, `payload_parser.py`, `service.py`, `ui/views/settings_view.py`, `keirin_auto_entry_config.json`, `README.md`, `docs/PROJECT_CONTEXT.md`, `docs/CHANGELOG_CUSTOMER.md`, `VERSION.txt`, `tests/test_config.py`, `tests/test_payload_parser.py`, `tests/test_service_routing.py`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m unittest -q tests.test_config tests.test_payload_parser tests.test_service_routing`
  - `python3 -m py_compile config.py payload_parser.py service.py ui/views/settings_view.py`
- Open items:
  - 実運用で、GUIの受信戦略切替（勝負/平均/守り/全部）ごとの見送りログ・実行ログを確認する。

## 2026-03-04
- Task: 事前候補通知に「オッズ変動で条件不一致になり得る」注記を受信表示
- Summary: `pre_race_candidates` payloadの `is_provisional` / `advisory` を正規化対象に追加し、受信時ログに `候補注記:` を表示するようにした。これにより、朝夕候補通知が直前判定で見送りへ変わる可能性を運用ログで確認しやすくした。
- Changed files: `payload_parser.py`, `service.py`, `tests/test_payload_parser.py`, `tests/test_service_routing.py`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m unittest tests.test_payload_parser tests.test_service_routing`
- Open items:
  - なし

## 2026-03-04
- Task: 受信戦略の「全部」モードを廃止
- Summary: 受信戦略UIから `全部` を削除し、`勝負/平均/守り` の3択へ統一。設定ファイルに残る旧値 `dispatch_mode=all` は自動で `average` に移行するようにして、全エントリーを許す経路をなくした。
- Changed files: `config.py`, `service.py`, `ui/views/settings_view.py`, `tests/test_config.py`, `tests/test_service_routing.py`, `README.md`, `docs/PROJECT_CONTEXT.md`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m unittest tests.test_config tests.test_service_routing`
- Open items:
  - なし

## 2026-03-08
- Task: 受信戦略を6パターン対応へ拡張
- Summary: `keirin_bunseki` 側で予定している `ミッド勝負/ミッド基準/ミッド安定/全帯勝負/全帯基準/全帯安定` の6戦略を `keirin_auto_entry` 側で受け分けできるようにした。旧 `attack/average/defense` は現運用互換としてミッド系へ正規化する。
- Changed files: `strategy_modes.py`, `config.py`, `payload_parser.py`, `service.py`, `ui/views/settings_view.py`, `tests/test_config.py`, `tests/test_payload_parser.py`, `tests/test_service_routing.py`, `README.md`, `docs/PROJECT_CONTEXT.md`, `docs/CHANGELOG_CUSTOMER.md`, `VERSION.txt`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile config.py payload_parser.py service.py ui/views/settings_view.py strategy_modes.py tests/test_config.py tests/test_payload_parser.py tests/test_service_routing.py`
  - `python3 -m unittest tests.test_config tests.test_payload_parser tests.test_service_routing`
- Open items:
  - `keirin_bunseki` 側の実際の6モード `strategy_code` 命名はまだ未確定のため、今回の canonical code は `midnight_* / all_*` で先行定義した。送信側実装時に必要なら alias を追加する。

## 2026-03-09
- Task: GUIの運用画面を簡素化して設定を統合
- Summary: ダッシュボードと設定を `運用` 1画面へまとめ、設定項目を `headless / 1点あたり金額 / エントリー中止金額 / 受信戦略` 中心に整理した。あわせて `LIVE固定・最終確定ON・確認OFF・シミュレーターOFF・固定スケジュール08:00-23:30` を内部既定へ固定し、ログ画面では接続デバッグや待機維持ノイズを非表示にした。
- Changed files: `config.py`, `ui/main_window.py`, `ui/views/dashboard_view.py`, `ui/components/status_bar.py`, `keirin_auto_entry_config.json`, `tests/test_config.py`, `README.md`, `docs/PROJECT_CONTEXT.md`, `docs/CHANGELOG_CUSTOMER.md`, `VERSION.txt`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile config.py ui/main_window.py ui/views/dashboard_view.py ui/components/status_bar.py`
  - `python3 -m unittest tests.test_config tests.test_service_review tests.test_service_routing`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
- Open items:
  - 実機GUIで、保存完了ダイアログのサイズ感とログ非表示対象が運用感覚に合うか確認が必要

## 2026-03-09
- Task: 固定方式を「目標払戻(円)」基準へ修正
- Summary: 前タスクの固定方式解釈を修正し、GUI項目を `1点あたり金額` から `目標払戻(円)` へ変更した。内部既定も `target_payout` 固定へ戻し、固定配当方式で金額計算する前提に合わせた。
- Changed files: `config.py`, `ui/views/dashboard_view.py`, `keirin_auto_entry_config.json`, `tests/test_config.py`, `README.md`, `docs/PROJECT_CONTEXT.md`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`, `VERSION.txt`
- Verification:
  - `python3 -m py_compile config.py ui/views/dashboard_view.py`
  - `python3 -m unittest tests.test_config tests.test_service_review tests.test_service_routing`
- Open items:
  - 実機GUIで、`目標払戻(円)` の文言が運用上誤解なく伝わるか確認が必要

## 2026-03-15
- Task: 時間帯別3モード運用に合わせて受信戦略UIを撤去
- Summary: `keirin_bunseki` 側の実運用が `モーニング収益主軸 / 日中収益主軸 / ミッド収益主軸` の3通知へ整理されたため、`keirin_auto_entry` の戦略絞り込みを廃止した。GUIから受信戦略プルダウンを削除し、サービスは `strategy_name/strategy_code` をログ用に保持しつつ、未知の新コードも含めてすべて受け入れるよう変更した。hidden setting の `dispatch_mode` は `config.py` 側で既定値固定へ寄せた。
- Changed files: `service.py`, `config.py`, `ui/views/dashboard_view.py`, `ui/views/settings_view.py`, `tests/test_service_routing.py`, `tests/test_payload_parser.py`, `tests/test_config.py`, `README.md`, `docs/PROJECT_CONTEXT.md`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`, `VERSION.txt`
- Verification:
  - `python3 -m py_compile config.py payload_parser.py service.py ui/views/dashboard_view.py ui/views/settings_view.py tests/test_config.py tests/test_payload_parser.py tests/test_service_routing.py`
  - `python3 -m unittest tests.test_config tests.test_payload_parser tests.test_service_routing`
- Open items:
  - 実機GUIで、運用画面から `受信戦略` が消えた後の並びと余白の見え方を一度確認したい。

## 2026-03-15
- Task: 空の候補通知を受けて `候補なし` を表示
- Summary: `keirin_bunseki` 側が `candidate_count=0 / candidates=[]` の `pre_race_candidates` を送るようになったため、`keirin_auto_entry` でも空候補 payload を落とさず受理し、ログへ `候補なし` を出すようにした。`payload_parser.py` は空候補 payload を正規化対象に含め、`service.py` は `事前候補受信: ... races=0` のあとに `候補なし` を記録して preview ループへ入らないよう変更した。README / `docs/PROJECT_CONTEXT.md` / `docs/CHANGELOG_CUSTOMER.md` / `VERSION.txt` も更新した。
- Changed files: `payload_parser.py`, `service.py`, `tests/test_payload_parser.py`, `tests/test_service_routing.py`, `README.md`, `docs/PROJECT_CONTEXT.md`, `docs/CHANGELOG_CUSTOMER.md`, `VERSION.txt`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile payload_parser.py service.py tests/test_payload_parser.py tests/test_service_routing.py`
  - `python3 -m unittest tests.test_payload_parser tests.test_service_routing`
  - `python3 - <<'PY' ... extract_payloads_from_text('{\"message_type\":\"pre_race_candidates\",\"date\":\"20260315\",\"candidate_count\":0,\"candidates\":[]}') ... PY`
- Open items:
  - ログ表現は現状 `事前候補受信: ... races=0` の次行に `候補なし` を出す形。将来的に1行へまとめたい場合は、既存ログ検索との整合を見ながら別途調整する。

## 2026-03-15
- Task: 候補通知に連動して競輪ブラウザを自動停止・再起動
- Summary: 08:00 の通常開催候補通知が `候補なし` だった日は、中央ブラウザを停止して無駄な起動を避けるようにした。18:00 のミッドナイト候補通知で候補が見つかった場合は、中央ブラウザを閉じ直して再起動し、夜開催に備えて待機状態へ戻すよう変更した。
- Changed files: `service.py`, `tests/test_service_routing.py`, `README.md`, `docs/PROJECT_CONTEXT.md`, `docs/CHANGELOG_CUSTOMER.md`, `VERSION.txt`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile service.py payload_parser.py tests/test_service_routing.py tests/test_payload_parser.py`
  - `python3 -m unittest tests.test_service_routing tests.test_payload_parser`
- Open items:
  - 実運用で 08:00 の `候補なし` 後にブラウザ停止ログ、18:00 のミッド候補ありでブラウザ再起動ログがそれぞれ出ることを確認する。

## 2026-03-16
- Task: 候補通知後に `Playwright Sync API inside the asyncio loop` で発注が止まる不具合を修正
- Summary: `pre_race_candidates` 受信時のブラウザ停止・再起動処理が Discord の `asyncio` 受信スレッド上で同期版 Playwright を触っていたため、候補通知後の発注で例外化する経路が残っていた。候補通知のブラウザ制御は専用ワーカーコマンドへ積み、実際の Playwright 操作は既存ワーカースレッドでのみ行うよう整理した。候補なし停止/候補あり再起動の既存挙動はテストで維持確認した。
- Changed files: `service.py`, `tests/test_service_routing.py`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile service.py tests/test_service_routing.py`
  - `python3 -m unittest tests.test_service_routing tests.test_service_review`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
- Open items:
  - 実機環境で、候補通知受信後の次回発注がそのまま継続し、`Playwright Sync API inside the asyncio loop` が再発しないことを確認したい。

## 2026-03-18
- Task: `KEIRIN AI ZERO` 商品版UIとプラン別受信制御の追加
- Summary: 商品名を `KEIRIN AI ZERO` へ変更し、`GOLD / SILVER / BRONZE` のプラン別UIを実装した。Discord受信は `モーニング / 日中 / ミッドナイト` の選択枠だけを通すようにし、候補通知のブラウザ停止/再起動も `08:00 / 10:00 / 18:00` の時間帯別へ拡張した。
- Changed files: `product_profile.py`, `config.py`, `payload_parser.py`, `service.py`, `ui/main_window.py`, `ui/views/dashboard_view.py`, `ui/components/status_bar.py`, `ui/theme.py`, `main.py`, `build_release.py`, `keirin_auto_entry.spec`, `discord_client.py`, `keirin_auto_entry_config.json`, `tests/test_config.py`, `tests/test_payload_parser.py`, `tests/test_service_routing.py`, `README.md`, `docs/PROJECT_CONTEXT.md`, `docs/CHANGELOG_CUSTOMER.md`, `VERSION.txt`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile product_profile.py config.py payload_parser.py service.py ui/main_window.py ui/views/dashboard_view.py ui/components/status_bar.py main.py build_release.py discord_client.py`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
- Open items:
  - 実機GUIで、各プラン色とボタン余白、Windows側のEXE名表示 (`KEIRIN AI ZERO_v0.3.0.exe`) を最終確認したい。

## 2026-03-18
- Task: プラン別固定EXEビルドの追加
- Summary: 商品配布を `BRONZE / SILVER / GOLD` の別EXEへ分けるため、ビルド時に固定プランを埋め込む仕組みを追加した。固定版では設定読込とGUIの両方でプランを固定し、README と案件ドキュメントも `--plan` / `--all-plans` に合わせて更新した。
- Changed files: `product_profile.py`, `config.py`, `ui/views/dashboard_view.py`, `build_release.py`, `keirin_auto_entry.spec`, `tests/test_config.py`, `tests/test_build_release.py`, `README.md`, `docs/PROJECT_CONTEXT.md`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`, `VERSION.txt`
- Verification:
  - `python3 -m py_compile product_profile.py config.py build_release.py ui/views/dashboard_view.py keirin_auto_entry.spec`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
  - `python3 build_release.py --spec keirin_auto_entry.spec --all-plans --dry-run`
- Open items:
  - Windows実機で、各固定版EXEのファイル名表示と起動後のプラン固定表示を1回ずつ確認したい。

## 2026-03-18
- Task: 固定版UIの表示崩れとSILVER利用枠切替の修正
- Summary: 固定プラン版でプランカードがすべて同じ名称になる表示崩れを修正し、SILVERで `ミッドナイト` を選んだ後も `モーニング / 日中` の組み合わせへ戻せるように、利用枠のクリック順保持ロジックへ変更した。あわせて、時間帯の補助文言と左上サブタイトルを削って画面を簡潔化した。
- Changed files: `product_profile.py`, `ui/views/dashboard_view.py`, `ui/main_window.py`, `tests/test_product_profile.py`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile product_profile.py ui/views/dashboard_view.py ui/main_window.py tests/test_product_profile.py`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
- Open items:
  - Windows実機で、SILVER固定版を開いて `モーニング / 日中 / ミッドナイト` の切替が意図どおりかを画面上で最終確認したい。

## 2026-03-18
- Task: 旧UIベースの体験版EXE追加
- Summary: 商品版とは別に、お試し配布向けの `trial` EXE を追加した。体験版は旧 `keirin_auto_entry` UI を使い、内部動作は `GOLD` 固定にして全時間帯を受けられるようにした。ビルドスクリプトには `--trial` を追加し、spec の runtime hook で `旧UI + GOLD固定` を注入する方式にした。
- Changed files: `product_profile.py`, `main.py`, `build_release.py`, `keirin_auto_entry.spec`, `ui/main_window.py`, `ui/components/status_bar.py`, `ui/views/classic_dashboard_view.py`, `tests/test_build_release.py`, `tests/test_product_profile.py`, `README.md`, `docs/PROJECT_CONTEXT.md`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`, `VERSION.txt`
- Verification:
  - `python3 -m py_compile product_profile.py main.py build_release.py keirin_auto_entry.spec ui/main_window.py ui/components/status_bar.py ui/views/classic_dashboard_view.py tests/test_build_release.py tests/test_product_profile.py`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
  - `python3 build_release.py --spec keirin_auto_entry.spec --trial --dry-run`
- Open items:
  - Windows実機で、`trial` EXE が旧 `keirin_auto_entry` UI で起動し、全時間帯が有効なまま発注待機に入ることを最終確認したい。

## 2026-03-19
- Task: プラン利用枠を「最大数まで選択」方式へ変更
- Summary: `BRONZE / SILVER / GOLD` の利用枠ルールを固定数前提から上限数前提へ変更し、未選択や任意組み合わせをそのまま保持できるようにした。あわせて README とお客様向け変更履歴の説明も新仕様へそろえた。
- Changed files: `config.py`, `product_profile.py`, `ui/views/dashboard_view.py`, `tests/test_config.py`, `tests/test_product_profile.py`, `README.md`, `docs/PROJECT_CONTEXT.md`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`, `VERSION.txt`
- Verification:
  - `python3 -m py_compile config.py product_profile.py ui/views/dashboard_view.py tests/test_config.py tests/test_product_profile.py`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
- Open items:
  - Windows実機で、固定版EXEの `GOLD / SILVER / BRONZE` それぞれで、利用枠を0件から上限数まで切り替えたときの表示と保存内容を一度確認したい。

## 2026-03-25
- Task: 起動直後の競輪ブラウザ自動起動競合と失敗理由非表示を修正
- Summary: 起動時の `pre_race_candidates` 再取得中は待機スケジュールによる競輪ブラウザ自動起動を保留し、候補連動の再起動とぶつからないようにした。あわせて、待機スケジュール起動失敗と候補連動起動失敗で、画面ログへ具体的な失敗理由を追加した。
- Changed files: `service.py`, `tests/test_service_routing.py`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile service.py tests/test_service_routing.py`
  - `python3 -m unittest tests.test_service_routing tests.test_service_review`
- Open items:
  - Windows実機で、起動直後に `起動時候補再取得` が走るケースでも、待機スケジュールの自動起動失敗が出ず、その後の候補連動または通常待機起動へ素直につながることを確認したい。

## 2026-03-26
- Task: 固定プランEXEに手動発注確認ダイアログを追加
- Summary: `BRONZE / SILVER / GOLD` の固定版EXEだけ、発注前に `auto_entry` 互換の確認ダイアログを表示し、買い目内容を見て `投票する / 見送る` を選べるようにした。`trial` と汎用EXEは従来どおり自動実行のまま維持した。README / 案件コンテキスト / お客様向け変更履歴も新挙動へ更新し、spec / build_release.py は変更なしで整合を確認した。
- Changed files: `product_profile.py`, `ui/main_window.py`, `ui/views/dashboard_view.py`, `tests/test_product_profile.py`, `README.md`, `docs/PROJECT_CONTEXT.md`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`, `VERSION.txt`
- Verification:
  - `python3 -m py_compile product_profile.py ui/main_window.py ui/views/dashboard_view.py tests/test_product_profile.py`
  - `python3 -m unittest tests.test_product_profile tests.test_service_review tests.test_config`
- Open items:
  - Windows実機で、固定版EXEの確認ダイアログが各レースで表示され、`見送る` 選択時に発注されないことを一度確認したい。

## 2026-03-26
- Task: 固定プランEXEの実行方法を自動/手動で選択可能に変更
- Summary: 固定版EXEを「手動確認固定」ではなく、ダッシュボードのラジオボタンで `自動 / 手動` を選べるように変更した。初期値は `手動` のままにしつつ、保存済みの選択結果を次回起動時も維持するよう設定ロードを調整し、README / 案件コンテキスト / 変更履歴も新仕様へそろえた。
- Changed files: `config.py`, `ui/views/dashboard_view.py`, `tests/test_config.py`, `README.md`, `docs/PROJECT_CONTEXT.md`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`, `VERSION.txt`
- Verification:
  - `python3 -m py_compile config.py ui/views/dashboard_view.py tests/test_config.py`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
- Open items:
  - Windows実機で、固定版EXEの `実行方法` ラジオボタンを `自動` にした場合は確認ダイアログなし、`手動` にした場合は確認ダイアログありで動くことを確認したい。

## 2026-03-27
- Task: BRONZE利用枠のワンタップ切替修正
- Summary: `BRONZE` で1枠選択済みの状態でも、別の時間帯ボタンを押したらそのまま新しい時間帯へ切り替わるようにした。従来必要だった「いったんOFFにしてから別枠をONにする」2操作を不要にし、README / 案件コンテキスト / 変更履歴 / 版番号も更新した。
- Changed files: `product_profile.py`, `tests/test_product_profile.py`, `README.md`, `docs/PROJECT_CONTEXT.md`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`, `VERSION.txt`
- Verification:
  - `python3 -m py_compile product_profile.py tests/test_product_profile.py`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
- Open items:
  - Windows実機で、`BRONZE` の `モーニング` 選択中に `日中` や `ミッドナイト` を押したとき、即座に新しい選択へ切り替わることを確認したい。

## 2026-03-30
- Task: 候補なし通知で競輪ブラウザを閉じないよう修正
- Summary: `pre_race_candidates` の 08:00 / 10:00 候補なし通知では、中央ブラウザを実際には閉じず、当日の自動起動停止フラグだけを立てるよう変更した。これにより、候補通知後の発注処理が閉じた `page/context/browser` を参照して落ちるリスクを下げた。README / 案件コンテキスト / お客様向け変更履歴 / 版番号も更新した。
- Changed files: `service.py`, `tests/test_service_routing.py`, `README.md`, `docs/PROJECT_CONTEXT.md`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`, `VERSION.txt`
- Verification:
  - `python3 -m py_compile service.py tests/test_service_routing.py`
  - `python3 -m unittest tests.test_service_routing`
- Open items:
  - Windows実機で、08:00 または 10:00 の候補なし通知後も既存の競輪ブラウザが残り、その後の実発注が継続できることを確認したい。

## 2026-04-04
- Task: 候補件数0件通知でも候補連動再起動へ入る可能性を修正
- Summary: `service.py` の候補連動判定が `candidate_count` ではなく `len(candidates)` を参照していたため、送信側の件数と配列内容がずれた場合に `候補なし` でも再起動経路へ入る可能性があった。候補件数は `candidate_count` 優先へ修正し、0件通知を優先して pause 扱いにする回帰テストと README / 変更履歴も更新した。
- Changed files: `service.py`, `tests/test_service_routing.py`, `README.md`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`, `VERSION.txt`
- Verification:
  - `python3 -m unittest tests.test_service_routing tests.test_payload_parser`
- Open items:
  - Windows実機で、`candidate_count=0` かつ `candidates` 配列内容が残る通知でも、`候補なし` として pause 扱いになることを確認したい。

## 2026-04-04
- Task: Chrome前提を外してブラウザ起動を汎用化
- Summary: Windows既定値が `browser_channel=chrome` になっていたため、Chrome未導入環境で候補連動や待機起動が失敗しやすかった。既定を Playwright Chromium 優先へ変更し、`browser_channel` や `browser_executable_path` を指定していても起動失敗時は Chromium へ自動フォールバックするよう修正した。設定テンプレート、README、変更履歴、版番号、回帰テストも更新した。
- Changed files: `config.py`, `ipat_playwright.py`, `tests/test_config.py`, `tests/test_ipat_playwright.py`, `keirin_auto_entry_config.json`, `README.md`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`, `VERSION.txt`
- Verification:
  - `python -m unittest discover -s tests -p "test_*.py"`
- Open items:
  - Windows実機で、Chrome未導入環境でも既定設定のまま Playwright Chromium で起動することを確認したい。

## 2026-04-05
- Task: 一部Windows利用者でのみ出る Playwright Temp/asyncio エラーの吸収
- Summary: `%TEMP%` 配下の `playwright-artifacts-*` 作成失敗と、同期版 Playwright が `asyncio` ループ上で呼ばれた扱いになる停止を、アプリ側で吸収するよう修正した。Playwright 起動前に書き込み可能な Temp へ自動切替し、実行本体は専用スレッドへ固定した。README / 案件コンテキスト / お客様向け変更履歴 / 版番号も更新した。
- Changed files: `ipat_playwright.py`, `service.py`, `tests/test_ipat_playwright.py`, `README.md`, `docs/PROJECT_CONTEXT.md`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`, `VERSION.txt`
- Verification:
  - `python -m py_compile ipat_playwright.py service.py tests/test_ipat_playwright.py`
  - `python -m unittest discover -s tests -p "test_ipat_playwright.py"`
  - `python -m unittest discover -s tests -p "test_service_routing.py"`
  - `python -m unittest discover -s tests -p "test_service_review.py"`
  - `python -m unittest discover -s tests -p "test_*.py"`
- Open items:
  - 問題が出ていた利用者PCで、新しい EXE に差し替え後、候補連動起動と実発注の両方が継続動作することを確認したい。

## 2026-04-05
- Task: 同梱版EXEで `chrome-headless-shell.exe` 不足になる不具合修正
- Summary: `--bundle-browser` 時の同梱対象が `chromium-*` のみで、既定の `headless` 起動が実際には `chromium_headless_shell-*` を要求していたため、同梱版EXEでも起動失敗することがあった。spec とビルド補助を修正して `chromium_headless_shell` と関連ファイルも同梱し、実行時も同梱 Chromium へフォールバックするよう改善した。README / 案件コンテキスト / お客様向け変更履歴 / 版番号も更新した。
- Changed files: `build_release.py`, `keirin_auto_entry.spec`, `ipat_playwright.py`, `tests/test_build_release.py`, `tests/test_ipat_playwright.py`, `README.md`, `docs/PROJECT_CONTEXT.md`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`, `VERSION.txt`
- Verification:
  - `python -m py_compile build_release.py ipat_playwright.py tests/test_build_release.py tests/test_ipat_playwright.py`
  - `python -m unittest discover -s tests -p "test_build_release.py"`
  - `python -m unittest discover -s tests -p "test_ipat_playwright.py"`
  - `python -m unittest discover -s tests -p "test_*.py"`
- Open items:
  - Windowsで `--bundle-browser` 付きの新しい EXE を再ビルドし、`headlessで起動=ON` のまま候補連動起動できることを確認したい。

## 2026-04-05
- Task: `browser_channel` 空欄時にインストール済み Chrome / Edge を自動利用
- Summary: この方だけ `browser_channel` 空欄設定のため Playwright Chromium 経路へ進み、通常の Chrome 利用者とは異なる例外が表面化していた。Windows では `browser_channel` 未指定でも、まずインストール済み `Chrome`、次に `Edge` を自動で試し、その後に Playwright Chromium へ進むよう改善した。README / 案件コンテキスト / 変更履歴 / 版番号も更新した。
- Changed files: `ipat_playwright.py`, `tests/test_ipat_playwright.py`, `README.md`, `docs/PROJECT_CONTEXT.md`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`, `VERSION.txt`
- Verification:
  - `python -m unittest discover -s tests -p "test_ipat_playwright.py"`
  - `python -m unittest discover -s tests -p "test_*.py"`
- Open items:
  - 問題が出ていた利用者PCで、設定空欄のままでもインストール済み Chrome 起動へ乗ることを確認したい。

## 2026-04-10
- Task: `kyoutei_auto_entry` の新規作成と競艇公式投票フローへの置換
- Summary: `keirin_auto_entry` を土台に `kyoutei_auto_entry` を作成し、中央投票を BOAT RACE 公式サイト向けへ切り替えた。`kyoutei_bunseki` のプレーンテキスト候補通知と最終通知も受信できるようにし、候補通知はログ反映のみ、最終通知は発注キュー投入に分離した。
- Changed files: `config.py`, `product_profile.py`, `payload_parser.py`, `service.py`, `ipat_playwright.py`, `ui/main_window.py`, `ui/views/settings_view.py`, `ui/views/dashboard_view.py`, `ui/views/classic_dashboard_view.py`, `README.md`, `docs/PROJECT_CONTEXT.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`, `tests/test_config.py`, `tests/test_payload_parser.py`, `tests/test_ipat_playwright.py`, `tests/test_service_routing.py`, `kyoutei_auto_entry.spec`
- Verification:
  - `python3 -m unittest tests.test_payload_parser tests.test_config tests.test_product_profile tests.test_ipat_playwright tests.test_service_routing`
- Open items:
  - 実口座を使わない環境では BOAT RACE の実画面遷移を最後まで確認できないため、Windows 実機で `submit_enabled=OFF` の確認画面到達と `submit_enabled=ON` の本番到達を別々に確認したい。

## 2026-04-10
- Task: 競艇接続フォームの表示項目と保存項目を競艇用へ統一
- Summary: `dashboard_view` と `classic_dashboard_view` に旧競輪由来の接続項目が残っており、`投票用パスワード` を入力できず `login_id` が空保存されていた。表示ラベルを `加入者番号 / 暗証番号 / 認証用パスワード / 投票用パスワード` に統一し、両ビューで `login_id` の読込と保存を有効化した。
- Changed files: `ui/views/dashboard_view.py`, `ui/views/classic_dashboard_view.py`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile ui/views/dashboard_view.py ui/views/classic_dashboard_view.py ui/main_window.py ui/views/settings_view.py ipat_playwright.py`
  - `python3 -m unittest tests.test_config tests.test_product_profile tests.test_ipat_playwright tests.test_service_routing`
- Open items:
  - Windows 実機で既存設定を読み込んだ状態の接続フォームに `投票用パスワード` 欄が表示され、保存後に自動開始の未入力警告が消えることを確認したい。

## 2026-04-10
- Task: 中央候補の競技フィルタ追加と重複再起動抑止
- Summary: 競艇側が同一Discord基盤上の競輪候補 payload まで受信し、日中候補の分割通知ごとにブラウザを再ログインし直していた。中央 target で競艇と判定できない payload を見送り、同日同時間帯の同一候補制御 action は一度だけ実行するよう修正した。
- Changed files: `service.py`, `tests/test_service_routing.py`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile service.py tests/test_service_routing.py`
  - `python3 -m unittest tests.test_service_routing tests.test_payload_parser tests.test_ipat_playwright tests.test_config tests.test_product_profile`
- Open items:
  - Windows 実機で、競輪候補が `見送り: 競技不一致: keirin` になり、競艇候補だけで 1 回だけ事前ログインすることを確認したい。

## 2026-04-10
- Task: 競艇 Discord チャンネルIDを実運用値へ修正
- Summary: `kyoutei_auto_entry` の `secrets_local.py` にコピー元の競輪中央チャンネルIDが残っていたため、起動時候補再取得で競輪チャンネル履歴を読んでいた。競艇の実運用チャンネルID `1490297331839664290` へ差し替え、コメント表記も競艇向けに修正した。
- Changed files: `secrets_local.py`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile secrets_local.py service.py`
- Open items:
  - 更新版で再起動後、起動ログの `連携設定: 中央ch=1490297331839664290` と、競輪候補の `起動時候補見送り` が出なくなることを確認したい。

## 2026-04-10
- Task: 競艇確認画面の入力耐性を強化
- Summary: BOAT RACE の確認画面まで到達しているのに、`#pass` への `fill()` が通らず `selector missing or not fillable: kyoutei_confirm_pass_input` で止まっていた。確認画面の金額欄と投票用パスワード欄は `fill()` だけでなく、クリック、キー操作、JS 代入まで順に試すようにし、投票ボタンも `#submitBet a` を優先して押すよう修正した。
- Changed files: `ipat_playwright.py`, `tests/test_ipat_playwright.py`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile ipat_playwright.py tests/test_ipat_playwright.py`
  - `python3 -m unittest tests.test_ipat_playwright`
- Open items:
  - Windows 実機で、確認画面 `#amount` と `#pass` へ実値が入り、そのまま `投票する` 押下まで進むことを確認したい。

## 2026-04-10
- Task: 競艇確認画面エラー文言を実態に合わせて明確化
- Summary: `#pass` 要素が見えているのに `selector missing or not fillable` と出ると原因誤認につながるため、入力欄が見つかったが埋められない場合は `input not fillable`、要素自体が無い場合だけ `selector missing` を返すように分離した。
- Changed files: `ipat_playwright.py`, `tests/test_ipat_playwright.py`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile ipat_playwright.py tests/test_ipat_playwright.py`
  - `python3 -m unittest tests.test_ipat_playwright`
- Open items:
  - Windows 実機で、再現時のエラー表示が `selector missing` ではなく `input not fillable` へ変わることを確認したい。

## 2026-04-10
- Task: 競艇確認画面の非表示入力欄も入力対象に拡張
- Summary: 実機では `#amount` は埋められる一方で `#pass` だけ `selector missing` になっており、確認画面の投票用パスワード欄が DOM 上は存在しても `is_visible()` 判定から外れている可能性があった。入力欄探索では可視要素優先の後に DOM へ付いている要素も対象にするよう広げた。
- Changed files: `ipat_playwright.py`, `tests/test_ipat_playwright.py`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile ipat_playwright.py tests/test_ipat_playwright.py`
  - `python3 -m unittest tests.test_ipat_playwright`
- Open items:
  - Windows 実機で、同じ確認画面の `#pass` が可視判定外でも入力されることを確認したい。

## 2026-04-10
- Task: 競艇確認画面の入力欄探索に `querySelector` フォールバックを追加
- Summary: 実機HTMLでは `#pass` が明確に存在するのに `selector missing` が続いたため、Playwright locator ベース探索が空振りした場合でも `document.querySelector(...)` で DOM 直接取得して値を入れる最終フォールバックを追加した。
- Changed files: `ipat_playwright.py`, `tests/test_ipat_playwright.py`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile ipat_playwright.py tests/test_ipat_playwright.py`
  - `python3 -m unittest tests.test_ipat_playwright`
- Open items:
  - Windows 実機で、確認画面HTMLに `#pass` があるケースで `selector missing` が再発しないことを確認したい。

## 2026-04-10
- Task: 起動ログへ実行バージョンを表示
- Summary: Windows 側で古い EXE を実行しているか判別しづらかったため、起動時に `起動バージョン: vX.Y.Z` をログへ出すようにした。EXE 実行時はファイル名、ソース実行時は `VERSION.txt` から判定する。
- Changed files: `main.py`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile main.py`
- Open items:
  - Windows 実機の起動ログに `起動バージョン: v0.3.15` が出ることを確認したい。

## 2026-04-10
- Task: 競艇確認画面の失敗解析ログを強化
- Summary: 実機の `ipat_error.html` には `#pass` が存在しているのに `selector missing` で落ちていたため、入力欄探索に `query_selector` 経路を追加し、失敗時には `ipat_error_context.json` へ selector ごとの探索結果、`betconfForm` 抜粋、`confirmationArea` 抜粋を保存するようにした。
- Changed files: `ipat_playwright.py`, `tests/test_ipat_playwright.py`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile main.py ipat_playwright.py tests/test_ipat_playwright.py`
  - `python3 -m unittest tests.test_ipat_playwright`
- Open items:
  - Windows 実機で再度失敗した場合、`runtime_logs/debug/<stamp>/ipat_error_context.json` に selector probe が保存されることを確認したい。

## 2026-05-03
- Task: BOAT RACE 三連複対応確認と補強
- Summary: 公式 JS 投入側には `3連複=7` の変換があり、三連複の組番も順不同として正規化される状態だった。一方で競艇券種判定の明示リストに三連複が無かったため、競艇対応券種へ三連単と三連複を追加し、三連複通知の受信、中央キュー投入、公式 JS への `kachishiki=7` 受け渡しをテストで固定した。
- Changed files: `ipat_playwright.py`, `service.py`, `tests/test_payload_parser.py`, `tests/test_ipat_playwright.py`, `tests/test_service_routing.py`, `tests/test_build_release.py`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/PROJECT_CONTEXT.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m unittest tests.test_payload_parser tests.test_ipat_playwright tests.test_service_routing`
  - `python3 -m unittest tests.test_payload_parser tests.test_config tests.test_product_profile tests.test_ipat_playwright tests.test_service_routing`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
  - `python3 build_release.py --spec kyoutei_auto_entry.spec --clean --dry-run`
- Open items:
  - 実機ログイン確認は未実施。三連複の実発注前に、最終確定OFFで確認画面まで進むことを1回確認したい。

## 2026-05-03
- Task: `ev` と上位確率付き三連複通知の受信確認
- Summary: ユーザー提示の `[競艇通知] 宮島 12R` サンプルを実測し、`ev=2.90` と `上位確率 ...` は余分な情報として無視され、`3連複 1-3-4`、3,100円、オッズ3.3を抽出できることを確認した。受信枠を絞った商品版では `tool_slot` 空欄だと見送りになるため、最終通知の締切時刻から `morning/daytime/midnight` を補完するよう修正した。
- Changed files: `payload_parser.py`, `tests/test_payload_parser.py`, `tests/test_service_routing.py`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/PROJECT_CONTEXT.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m unittest tests.test_payload_parser tests.test_service_routing`
  - `python3 -m unittest tests.test_payload_parser tests.test_config tests.test_product_profile tests.test_ipat_playwright tests.test_service_routing`
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
- Open items:
  - 実機ログイン確認は未実施。日中枠選択時に該当通知が実ブラウザの確認画面まで進むことを確認したい。

## 2026-05-11
- Task: BOAT RACE サービス時間外のブラウザ常駐を避ける。
- Summary: 中央投票ブラウザの自動起動時間を `10:00-21:00` に変更し、時間外は起動済みブラウザを閉じるようにした。事前準備、候補連動再起動、発注 payload の各経路でも時間外のブラウザ新規起動を抑止する。
- Changed files: `config.py`, `service.py`, `ui/views/settings_view.py`, `ui/views/dashboard_view.py`, `ui/views/classic_dashboard_view.py`, `README.md`, `docs/PROJECT_CONTEXT.md`, `tests/test_config.py`, `tests/test_service_routing.py`, `tests/test_service_review.py`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python3 -m py_compile config.py service.py ui/views/settings_view.py ui/views/dashboard_view.py ui/views/classic_dashboard_view.py tests/test_config.py tests/test_service_routing.py tests/test_service_review.py`
  - `python3 -m unittest tests.test_config tests.test_service_routing -q`
  - `python3 -m unittest discover -s tests -p 'test_*.py' -q`
  - `bash ./sync_to_windows.sh /home/user/src/kyoutei/kyoutei_auto_entry/ /mnt/c/pleiades/2023-03/workspace/kyoutei/kyoutei_auto_entry/`
  - Windows側 `python .\build_release.py --spec kyoutei_auto_entry.spec --clean`
- Open items:
  - Windows 実機で v0.3.19 の起動ログと `10:00-21:00` 外の自動停止を確認したい。

## 2026-05-12
- Task: 候補連動ログイン時の `ERR_CERT_AUTHORITY_INVALID` 対応
- Summary: `keirin.jp` への事前ログインで `Page.goto: net::ERR_CERT_AUTHORITY_INVALID` が出て候補連動のブラウザ起動が止まっていた。通常は従来どおり接続し、証明書エラーを検知した時だけ Playwright context を `ignore_https_errors=True` で作り直して同じ URL を再試行するようにした。
- Changed files: `ipat_playwright.py`, `tests/test_ipat_playwright.py`, `VERSION.txt`, `docs/CHANGELOG_CUSTOMER.md`, `docs/WORKLOG.md`, `docs/LEARNINGS.md`
- Verification:
  - `python -m py_compile ipat_playwright.py tests/test_ipat_playwright.py`
  - `python -m unittest discover -s tests -p test_ipat_playwright.py -q`
  - `python -m unittest discover -s tests -p "test_*.py" -q`
  - `wsl -d Ubuntu -- bash -lc "cd /home/user/src/kyoutei/kyoutei_auto_entry && python3 -m unittest discover -s tests -p 'test_*.py' -q"`
- Open items:
  - Windows 実機で v0.3.20 の起動ログ後、候補連動の事前ログインが同じ証明書エラーで停止しないことを確認したい。
