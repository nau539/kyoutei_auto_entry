# CODEX_PROMPTS.md

このファイルは「人間がチャットへ貼り付ける依頼文」を管理します。
Codexが自動実行するものではありません。必要時に手動で使います。

注意:
- `WORKLOG / LEARNINGS / CHANGELOG_CUSTOMER` の追記は手動不要です。
- これらは AGENTS ルールに従って Codex が作業完了時に更新します。
- 毎タスクの実装条件は AGENTS の `Default Task Contract` が自動適用されます。

## 初回調査テンプレート（新規案件）
```text
AGENTS.mdは変更せず、まずリポジトリを調査してください。
案件固有情報を docs/PROJECT_CONTEXT.md に作成してください。
内容:
- 目的
- ディレクトリ構成
- 主要モジュール
- 依存関係
- 実行/ビルド手順
- Git運用（正本パス、同期手順）
- Distribution Profile（配布要否、パッケージ種別、spec要否、バージョン規則）
- READMEの対象パス（README.md 優先、既存READMEがあればそれを採用）
- 要確認事項
その後 docs/LEARNINGS.md と docs/WORKLOG.md を初期化してください。
```

## Codex依頼テンプレート（毎タスク・任意）
```text
このタスクを実装してください。
必須条件:
- 変更は最小限
- docs/PROJECT_CONTEXT.md と docs/LEARNINGS.md を先に読む
- 初回調査時は docs/CHANGELOG_CUSTOMER.md を案件用に初期化（他案件履歴があれば削除）
- docs/WORKLOG.md に作業メモを追記
- docs/LEARNINGS.md に学びを追記（追記のみ）
- 依存/実行/ビルド/同期手順を変えた場合は README を更新
- お客様影響がある場合は docs/CHANGELOG_CUSTOMER.md を更新
- Distribution Profile が python-exe の場合は、spec/バージョン付き成果物/変更履歴を整合させる
- Distribution Profile が python-exe の場合は、`.spec` と `build_release.py` を常に整合させる（どちらか変更時はもう一方も確認・修正）
- Distribution Profile が python-exe の場合は、`.spec` / `build_release.py` が無ければ Codex が新規作成する（事前配置不要）
- 別案件名（例: `SYSTElVl`）が `.spec` / `build_release.py` / ビルド手順に混入していたら、現案件名へ修正する
- `build_release.py` は案件名をハードコードせず、原則 `.spec` から自動判定する（複数specは `--spec` 指定）
- ユーザー停止指示がない限り、修正完了後は Codex が `git add -A` / `git commit` / `git push` まで実施する
- 完了後は変更内容・検証結果・未解決事項を報告
```

上記テンプレートは「追加で明示したいときのみ」使います。通常は貼り付け不要です。
