# AQUA EDGE AI — Android 版（MVP）

PC版（Python + Playwright）のテレボート自動投票ロジックを、**Android 単体で動く React Native + WebView アプリ**へ移植したものです。
テレボート操作の中核（ログイン → 場選択 → レース選択 → `BOAT.reg_service.addBet` → 確認 → 投票実行）は
PC版 `ipat_playwright.py` の `_kyoutei_*` を**そのまま JS 注入として移植**しています。

## いまできること（第1弾 MVP）

- 設定画面：認証情報4項目 / 対象会場（最大3）/ 対象レース範囲 / 締切リード秒 / 実投票ON-OFF
- 実行画面：WebViewにテレボートを表示し、テスト発注を**確認画面まで**実行（`submit OFF`）。実投票ONで投票実行まで
- ログ表示

## 動作確認済み（2026-06-29）

Android エミュレータ（Pixel 5 / Android 14 / API 34）で**ビルド・起動・WebView表示まで確認済み**:

- アプリがビルドされ起動（設定/実行タブ、認証情報フォーム、24場リスト描画）
- 実行タブの WebView が**テレボート本番サイト（ib.mbrace.or.jp）のログイン画面を実際に表示**

未確認（サービス時間内＋実口座が必要なため別途）:
- ログイン実行〜場/レース選択〜addBet〜確認画面の一連フロー
- ポップアップ遷移（`setSupportMultipleWindows={false}` の実挙動）

## まだ無いもの（第2弾以降。実機での詰めが必要）

- **締切1分前の自動発火・常駐**（フォアグラウンドサービス＋正確アラーム）← Android省電力対策が必要な領域
- **Discord通知の受信**（PC版の `discord.py` 相当）。signal取得元の実装
- 複数会場の自動巡回スケジューリング

---

## ビルド方法（ローカルにAndroid SDK不要 / クラウドビルド）

開発機に Android Studio は要りません。Expo の **EAS Build** がクラウドでAPKを生成します。

```bash
cd android_app
npm install
npm install -g eas-cli       # 初回のみ
eas login                    # 無料の Expo アカウントでログイン
eas build -p android --profile preview
```

ビルド完了後、コンソールに **APKのダウンロードURL** が出ます。
そのURLをお客様に共有し、Galaxy で開いて**インストール（提供元不明アプリの許可が必要）**してもらいます。

> ローカルにAndroid SDKを入れて `npx expo run:android` でビルドする手もありますが、
> この開発環境には SDK が無いため EAS（クラウド）を前提にしています。

### 動作確認（ローカルのMetroで実機プレビュー）

実機が手元にある場合のみ：

```bash
cd android_app
npm install
npx expo start
# Expo Go ではなく Dev Build / 実APK で確認（WebViewネイティブ依存のため）
```

---

## 使い方

1. **設定タブ**で認証情報・会場・レース範囲を入力 →「設定を保存」
   - `実投票を有効化` は最初は必ず **OFF**（確認画面で停止し、実際の購入はしない）
2. **実行タブ**：WebViewにテレボートのログイン画面が出る
3. テスト発注フォーム（会場 / R / 券種 / 買い目 / 金額）を入れて「実行」
4. ログイン → 場・レース選択 → 買い目投入 → **確認画面で停止**するところまで確認
5. 問題なければ設定で `実投票ON` にして本番

### 認証情報マッピング（PC版と同一）

| アプリ表示 | PC版キー | 用途 |
|---|---|---|
| 加入者番号 | ipat.inet_id | memberNo |
| 暗証番号 | ipat.pars_no | pin |
| 認証用パスワード | ipat.password | authPassword |
| 投票用パスワード | ipat.login_id | votePassword（確認画面） |

---

## 実機でしか確認できない・要調整ポイント（重要）

PC版とAndroid WebViewで挙動が変わり得るため、**実機・実口座での反復検証が必須**です。

1. **ログイン後のポップアップ遷移**
   テレボートはログイン時に別ウィンドウ（ポップアップ）で投票画面を開きます。
   本アプリは `setSupportMultipleWindows={false}`（[RunScreen.js](src/screens/RunScreen.js)）で
   **同一WebViewに読み込む**前提です。実機で遷移しない場合、ここの方式変更が要ります。
2. **公式JS (`window.BOAT...`) の存在タイミング**
   `addBet` 等は投票画面のJSロード後にしか使えません。`waitFor(isBetPageReady)` で待っていますが、
   実機の回線速度次第でタイムアウト調整が必要なことがあります。
3. **特別なお知らせモーダル**：`#newsoverviewdispCloseButton`。文言/IDが変わると閉じられません。
4. **DOM/JS名の変更**：公式サイト更新時は [inject.js](src/telboat/inject.js) のセレクタ調整が必要（PC版と同じ保守前提）。

---

## ソース構成

```
android_app/
├─ App.js                      タブ（設定/実行）
├─ src/storage.js              設定の永続化（AsyncStorage）
├─ src/screens/
│  ├─ ConfigScreen.js          設定UI
│  └─ RunScreen.js             WebView + テスト発注 + ログ
└─ src/telboat/
   ├─ constants.js             場コード/券種コード（PC版から移植）
   ├─ inject.js                注入用JSステップ（_kyoutei_* 移植の中核）
   ├─ bridge.js                WebViewとの非同期JS実行ブリッジ
   └─ driver.js                1レース分の発注オーケストレーション
```

## 既知の制約

- WebView方式のため、公式サイトのDOM/JS更新の影響を受けます（PC版と同じ）。
- 実投票は実口座操作です。必ず `submit OFF` で確認画面まで検証してから本番ONにしてください。
- 自動投票はサイト利用規約との関係が論点になり得ます。提供形態はお客様と合意の上で。
