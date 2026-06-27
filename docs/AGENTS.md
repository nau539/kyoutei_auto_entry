# Project Agent Guide (Generic)

この `AGENTS.md` は汎用運用ルールです。案件固有の情報は `docs/PROJECT_CONTEXT.md` に記載します。

## Rule Separation
- `AGENTS.md`: 全案件共通ルール（原則固定）
- `docs/AGENTS.md`: 参照用ミラー（正本はルート `AGENTS.md`）
- `docs/PROJECT_CONTEXT.md`: 案件固有情報（目的/構成/依存/実行手順）
- `docs/CODEX_PROMPTS.md`: 手動で貼り付ける依頼テンプレート集（初回調査/毎タスク）
- `README.md` または `README.txt`: 人間向けの最短手順（起動/ビルド/同期）
- `docs/WORKLOG.md`: 作業ログ（毎タスク追記）
- `docs/LEARNINGS.md`: 学び（毎タスク追記、上書き禁止）
- `docs/CHANGELOG_CUSTOMER.md`: お客様向け変更履歴

## Scope (In / Out)
### In scope
- 既存機能のバグ修正
- テスト追加
- 小さめの機能追加
- ドキュメント整備（運用に必要な範囲）

### Out of scope
- 大規模リファクタリング（事前合意なし）
- 依存関係の大幅更新（事前合意なし）
- 公開APIの破壊的変更（事前合意なし）

## Non-negotiables (必ず守る)
- 変更は最小限にする（必要以上に触らない）
- 既存APIの互換性を優先する（破壊的変更は事前合意）
- バグ修正は「再現確認 → 修正 → 検証」の順で進める
- 既存の設計・命名・実装方針を優先し、新流儀を持ち込まない
- 作業開始時に `docs/PROJECT_CONTEXT.md` と `docs/LEARNINGS.md` を読む
- パッケージを勝手にインストールしない（提案のみ可）
- `print()` デバッグを残さない（`logging` を使う）
- お客様向け文面では内部実装前提の表現（例: 「ソースコード」）を避ける
- `docs/LEARNINGS.md` は追記のみ（削除・上書き禁止）
- `docs/WORKLOG.md` は毎タスク追記（目的/変更点/検証/未解決事項）
- 初回セットアップ時は README（`README.md` 優先、既存が `README.txt` の場合はそれ）を整備する
- 依存/実行/ビルド/同期手順に変更があった場合は README を更新する
- 配布物がある案件では、必要に応じてバージョンと変更履歴を更新する
- 初回調査時は `docs/CHANGELOG_CUSTOMER.md` を案件用に初期化し、他案件の履歴を残さない
- `docs/CHANGELOG_CUSTOMER.md` は `Unreleased` を使わず、`## vX.Y.Z - YYYY-MM-DD` 形式で追記する
- Git操作は「正本ワークスペース」のみで行う（正本は `docs/PROJECT_CONTEXT.md` で定義）
- ユーザーから停止指示がない限り、修正完了後はCodexが `git add` / `commit` / `push` まで実施する

## Conditional Distribution Policy
- このポリシーの適用可否は `docs/PROJECT_CONTEXT.md` の「Distribution Profile」で判定する
- `Distribution Required: yes` かつ `Package Type: python-exe` の場合:
  - Codexは `.spec` を用意/更新してビルド手順を維持する
  - Codexは `build_release.py` を用意/更新し、`.spec` と常に整合させる
  - `build_release.py` の案件名はハードコードせず、原則 `.spec` から自動判定する（複数spec時は明示指定）
  - `.spec` / `build_release.py` が存在しない場合は、Codexが新規作成する（人間の事前配置は不要）
  - `.spec` または `build_release.py` のどちらかを変更した場合、もう一方も必要に応じて自動修正する
  - 配布ファイル名を `NAME_vX.Y.Z` 形式にする（例: `keirin_auto_entry_v1.0.0.exe`）
  - `VERSION.txt` と `docs/CHANGELOG_CUSTOMER.md` を更新対象に含める
- 非Python案件または配布不要案件は、この配布ポリシーを `N/A` として扱う

## Required Docs
- `AGENTS.md`:
  - 共通ルールの正本
- `docs/AGENTS.md`:
  - docs配下から参照するためのミラー（内容はルート `AGENTS.md` に準拠）
- `docs/PROJECT_CONTEXT.md`:
  - 案件目的、ディレクトリ構成、主要モジュール、依存関係、実行/ビルド手順、Git運用
  - Distribution Profile（配布要否、パッケージ種別、バージョン/成果物命名規則）
  - 初回に存在しない場合は、コードを調査して作成する
- `docs/CODEX_PROMPTS.md`:
  - 初回調査依頼と毎タスク依頼のコピペ文（人間が入力）
  - 必要時に人間がチャットへ貼り付けて使う
- `README.md` または `README.txt`:
  - 人間向けの最短手順（依存導入、実行、同期、ビルド）
  - 手順変更時は更新する
- `docs/WORKLOG.md`:
  - 各タスクごとに追記（時系列）
- `docs/LEARNINGS.md`:
  - 再発防止の学びを1〜3行で追記
- `docs/CHANGELOG_CUSTOMER.md`:
  - お客様影響のある変更時に更新

## Definition of Done (完了条件)
- [ ] 受け入れ条件を満たす
- [ ] 影響範囲に応じた検証を実施した
- [ ] 既存機能の回帰がないことを確認した
- [ ] `docs/WORKLOG.md` に作業メモを追記した
- [ ] `docs/LEARNINGS.md` に学びを追記した
- [ ] 必要に応じて `docs/PROJECT_CONTEXT.md` を更新した
- [ ] 依存/実行/ビルド/同期手順に変更がある場合、READMEを更新した
- [ ] お客様影響がある場合、`docs/CHANGELOG_CUSTOMER.md` を更新した
- [ ] `Distribution Profile` が `python-exe` の場合、バージョン/成果物名/変更履歴の整合を確認した
- [ ] `Distribution Profile` が `python-exe` の場合、`.spec` と `build_release.py` の整合を確認した
- [ ] ユーザー停止指示がない場合、正本ワークスペースで `commit` / `push` まで完了した

## Workflow (進め方の型)
1. `docs/PROJECT_CONTEXT.md` と `docs/LEARNINGS.md` を読む
2. Task Brief（目的/制約/受け入れ条件）を短く整理する
3. 関連ファイルを列挙してから読む
4. `Distribution Profile`（python-exe / N/A）を確認する
5. 実装方針と検証方針を決める
6. 実装（最小限の変更）
7. Verify（テスト/再現手順/動作確認）
8. `docs/WORKLOG.md` に作業メモを追記する
9. `docs/LEARNINGS.md` に学びを追記する
10. 必要に応じて `docs/PROJECT_CONTEXT.md` / README / `docs/CHANGELOG_CUSTOMER.md` を更新する
11. ユーザー停止指示がない場合、正本ワークスペースで `git add` / `commit` / `push` を実施する

## Default Task Contract (Auto Applied)
- 毎タスクで以下をCodexが自動適用する（人間の貼り付け不要）
- 変更は最小限
- `docs/PROJECT_CONTEXT.md` と `docs/LEARNINGS.md` を先に読む
- `docs/WORKLOG.md` に作業メモを追記
- `docs/LEARNINGS.md` に学びを追記（追記のみ）
- 初回調査時は `docs/CHANGELOG_CUSTOMER.md` を案件用に初期化（他案件履歴があれば削除）
- 依存/実行/ビルド/同期手順を変えた場合は README を更新
- お客様影響がある場合は `docs/CHANGELOG_CUSTOMER.md` を更新
- `docs/CHANGELOG_CUSTOMER.md` はリリース見出し（`vX.Y.Z - YYYY-MM-DD`）で記録する
- `Distribution Profile` が `python-exe` の場合は、spec/バージョン付き成果物/変更履歴を整合させる
- `Distribution Profile` が `python-exe` の場合は、`.spec` と `build_release.py` を常に整合させる（片方変更時はもう片方も確認・修正）
- ユーザー停止指示がない限り、修正後は正本ワークスペースで `git add` / `commit` / `push` を実施する
- 完了後は変更内容・検証結果・未解決事項を報告

## Version-Origin Bug Guideline（バージョン起因バグ調査ガイドライン）
### 適用条件
- 以下のいずれかに該当する場合は本ガイドラインを適用する
- 「最新版にしたら動かなくなった」「バージョンアップ後にエラー」などの報告がある
- 外部ライブラリ呼び出しで `Invalid request` / `Unnamed arguments not allowed` / `TypeError` などが出る
- レスポンスのフィールドが全てゼロ・空文字・デフォルト値になる
- コード未変更なのに、ライブラリ更新後から失敗し始めた

### 原則ルール
1. ラッパー関数を最優先で疑う
   - 共通ラッパー内で引数変形（`request=` 付与、型変換、並べ替え等）がないかを最初に確認する
   - 「ラッパー経由」と「ライブラリ直接呼び出し」を比較し、差異があればラッパー起因と判断する
2. 引数渡し方式を全パターン試す
   - 失敗時は以下を必ず比較する
```python
# A: 位置引数（dict）
result_a = lib.func(req)

# B: キーワード引数（request=dict）
result_b = lib.func(request=req)

# C: dict展開（**dict）
result_c = lib.func(**req)
```
   - 1つでも成功パターンがあれば、その方式に合わせて修正する
3. 全ゼロレスポンスは「引数未到達」のサインとして扱う
   - パラメータ値以前に、呼び出し方式不一致の可能性を優先して調べる
4. 1回の変更で1仮説のみ検証する
   - 一度に複数箇所を直さず、効果判定可能な順で進める

### デバッグ手順（順序固定）
1. エラーコードの意味を公式ドキュメントで確認する
2. 送信直前のリクエスト全フィールドをログに出す
```python
logger.debug("request: %s", req)
```
3. レスポンス全フィールド（`request` を含む）をログに出す
```python
logger.debug("response: retcode=%s comment=%s request=%s", res.retcode, res.comment, res.request)
```
4. 事前検証関数（例: `*_check`）があれば送信前に実行する
5. ラッパーを迂回して直接呼び出しの3パターンを比較する
```python
try:
    r1 = lib.func(req)
except Exception as e:
    logger.debug("pattern A failed: %s", e)

try:
    r2 = lib.func(request=req)
except Exception as e:
    logger.debug("pattern B failed: %s", e)

try:
    r3 = lib.func(**req)
except Exception as e:
    logger.debug("pattern C failed: %s", e)
```
6. 成功パターンに統一して修正し、同じラッパー利用箇所へ横展開する

### よくある破壊的変更パターン
- `Unnamed arguments not allowed`
  - 原因候補: 位置引数/キーワード引数の受理条件変更
  - 対処: `dict` 直渡し / `request=` / `**dict` の実測結果で方式を決める
- `Invalid request` + 全ゼロレスポンス
  - 原因候補: リクエストがライブラリまで届いていない
  - 対処: 呼び出し方式とラッパー変換ロジックを見直す
- `TypeError: unexpected keyword ...`
  - 原因候補: 引数名の変更・廃止
  - 対処: 公式ドキュメントで新シグネチャを確認する
- 特定パラメータ値だけ失敗する
  - 原因候補: enum値・デフォルト値・制約の変更
  - 対処: 検証関数で有効値を段階的に試して確定する

### 実装時の注意
- 検証用ログは原因特定まで残し、解決後は必要最小限に整理する
- 互換ハックは恒久化せず、実測で有効だった最小ロジックだけ残す
- 再発防止のため、判明した「有効な呼び出し方式」を `docs/LEARNINGS.md` に追記する

## Prompt Templates
- 依頼テンプレートは `docs/CODEX_PROMPTS.md` に分離管理する
- `初回調査テンプレート` は新規案件の開始時に人間が貼り付けて使う
- `毎タスクテンプレート` は任意（通常は貼り付け不要。`Default Task Contract` を自動適用）
- `WORKLOG / LEARNINGS / CHANGELOG` の記載は Codex が自動で実施する（人間の手動入力は不要）
