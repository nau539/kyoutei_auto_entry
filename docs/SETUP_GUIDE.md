# keirin_auto_entry 導入手順書

## ステータス
- この手順書は競輪版向けに再作成中です。
- 現在のコードは `auto_entry` からのコピー直後のため、競輪固有の接続先・投票手順は未反映です。

## 当面の実行手順（開発者向け）
```bash
cd /home/user/src/keirin/keirin_auto_entry
python3 -m venv .venv
source .venv/bin/activate
pip install playwright discord.py pyinstaller customtkinter
python -m playwright install chromium
python3 main.py
```

## 注意
- 実運用投入前に、競輪向け仕様の実装完了と手順書の正式化が必要です。
