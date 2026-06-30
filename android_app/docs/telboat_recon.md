# テレボート実地調査メモ（2026-06-29 朝、ログイン実施・購入なし）

実アカウントでログイン成功。本番サイトの構造を確認した結果、**お客様仕様はほぼ全てテレボート純正機能に対応**することが判明。

## サイトの正体

- 投票画面は **jsrender ベースの SPA**（`<script type="text/x-jsrender">` テンプレを JS で動的描画）。
- よって **静的セレクタ（`#raceSelection` 等）は実DOMに常在せず**、`BOAT.*_service` / `BOAT.*_controller` のJS API＋描画ライフサイクルで駆動する必要がある（PC版が `BOAT.reg_service.addBet` を使っているのと同じ方式）。
- **reCAPTCHA あり**（`BOAT.attribute.isRecaptchaEnable`）。自動化の最大リスク。発動条件の確認が必須。

## 仕様 → 純正機能の対応（取得済みセレクタ）

### 仕様7: 資金配分（テンプレ `distamoRender` / `<div id="distribution">`）
> 「どの買い目が的中しても配当金がほぼ同一となるように配分します。資金配分合計を入力して、配分実行ボタンを押してください。」

- 合計入力: `#distamoTotal`（class `inputAmount`）
- 実行ボタン: `#execDistamo`（配分実行）
- **フロー: 買い目を選ぶ → `#distamoTotal` に総額入力 → `#execDistamo` クリック → 各点へ自動配分**。これがお客様の言う「資金配分機能」そのもの。

### 仕様3: 3連単ボックス（テンプレ `boxRender`）
- ボックスは純正の買い方。組番選択（`.combiSel`）→ `#combiCount` ベット数 → `#combiConfirmBtnBox`（組合せ確認）→ `#amount`（購入金額）。
- 3艇選択で6点を**サイト側が生成**。手動6点 addBet（`src/strategy/box.js`）はフォールバックとして温存。

### 仕様6: 締切時刻
- `#nextRaceDeadline`: 「電話投票締切予定時刻まで **{{hatsubaiLeftTime}}分**」= 締切までの残り分。
- レース表に締切列あり。`BOAT.code` の acceptcode に `締切済`/`中止`/`開始前`/`障害中` 等の状態コード。
- → スケジューラの締切判定・発売中判定に使える。

### 仕様4/8: 的中判定・結果
- `hitinformrefRender`（`#hitinformDisp` 的中結果一覧、`<a id="hitinformref">的中結果一覧を見る</a>`）
- `betrefcompRender`（`#voteInquiryResult` 投票照会結果）、`rcptlistRender`（契約一覧）
- → レース確定後の的中/結果はこれらの照会ページから取得。

## 未解決・要追加調査（ライブ最小限で）

1. **SPA のレース選択ナビ**: 今回 `#todayForm` submit → レース選択タブ検出に失敗（タイミング or reCAPTCHA or SPA遷移差）。実際の遷移は `BOAT` のどのコントローラ経由かを特定する。
2. **reCAPTCHA 発動条件**: ログイン/投票時に出るか。出る場合の対処（自動化可否の分水嶺）。
3. **資金配分・ボックスの確定までのJS呼び出し列**: `boxRender`/`distamoRender` を出すコントローラ名。
4. **締切の絶対時刻**: `hatsubaiLeftTime`(残り分)以外に絶対時刻を持つか。

> ⚠️ bot検知回避のため、ライブのログイン試行は最小限に。1回のセッションで複数項目をまとめて取得する方針。

---

## 集中調査の結論（2回目セッション、2026-06-29）

### reCAPTCHA の正体（最重要）
- `isRecaptchaEnable: true` / `grecaptcha` ロード済 / iframe = `recaptcha/enterprise/anchor?...k=6LcTx8ofAAAA`
- **ただし `.g-recaptcha` チェックボックスは0個、チャレンジ(bframe)も非表示** = **不可視のreCAPTCHA Enterprise（スコア型/v3系）**。画像選択やチェックは出ない。
- **無人の自動ログインは成功した** → クリック型CAPTCHAで全自動が止まることはない。
- 残るリスクは**スコア型のサイレント判定**：ヘッドレス自動化は低スコアになりやすく、その場合サイトがナビゲーションを黙って拒否し得る。

### SPA ナビの正体
- ログイン直後の `BOAT` API に **`reg_service`/`betlist_controller`/box/distamo 系コントローラは未ロード**（レース投票ビューに入ると遅延ロードされる）。
- `#todayForm` の form submit では遷移せず（raceUIが出ない）。**現行サイトはajax/JS駆動のSPAで、PC版の form-submit + `#raceSelection` 静的セレクタ方式は現行サイトに合っていない**。
- 有力仮説：**ヘッドレス実行が低reCAPTCHAスコアになり、サイトが投票導線を出さなかった**。PC版が通常（headless=False・実ブラウザ）で動くのと整合。

### 結論（Android方針への影響）
- **クリック型CAPTCHAが無い＝全自動の致命的ブロックは無い**。
- スコア型のため、**実機の本物WebView＋実ユーザーセッションが最も高スコア**になりやすい。つまり「お客様のGalaxy上のWebViewで動かす」という構成は、reCAPTCHA通過の観点でむしろ有利。ヘッドレスのデスクトップ調査は最悪条件だった。
- 次の決定的検証は**エミュレータ/実機の本物WebViewで通しフローを試す**こと（ヘッドレスでなく）。購入導線も SPA のクリック＋純正box/資金配分で駆動する設計に作り替える。
- 付随知見：PC版のkyouteiセレクタも現行SPAに対し**要更新の可能性**（お客様の稼働中PC版での挙動と要照合）。

---

## 実機WebView(CDP)検証の結論（2026-06-29, エミュレータ実WebView）

エミュレータの実WebViewへ **ページ単位CDP**（`websocket-client`, `suppress_origin=True`）で接続し駆動。`navigator.webdriver=false`・本物のAndroid WebView UA＝reCAPTCHA良条件を確認。

### ★ログインの仕組み（最重要・実アプリのブロッカー）
- `#loginButton` は `type=button` で初期 **`disabled`**（フィールド検証通過で有効化）。
- ログインフォーム: `<form id="loginForm" method="post" target="pctablet" action="/tohyo-ap-pctohyo-web/auth/login?...">` = **"pctablet" という別ウィンドウ(ポップアップ)へPOSTする方式**。
- ボタンのクリックハンドラが reCAPTCHA トークン取得 → 別窓へPOST、と推測。
- **現アプリは `setSupportMultipleWindows={false}` で別窓を開けず、ログイン未完了**。
- 別窓を `target=_self` で同一ビューへ強制すると **エラー `ID:00401 処理異常`**（窓ハンドシェイク/トークン不整合）。
- PC版Playwrightは `expect_popup` で**実際の別窓**を開いて成功している＝**ログインは別窓が必須**。

### 実アプリの対策（次の実装）
- react-native-webview を **マルチウィンドウ対応**に変更：`setSupportMultipleWindows={true}` ＋ `onOpenWindow`（または2枚目のWebViewでポップアップを描画）で "pctablet" 窓を開かせ、ボタン本来のハンドラ（トークン取得込み）で認証完了させる。
- 認証後、メイン窓が投票TOPへ遷移 → 以降のSPA操作（場/レース選択・ボックス・資金配分）へ。
- ⚠️ アカウント保護のためライブのログイン連打は中止。次はアプリ改修→エミュレータで再検証。

---

## 購入フロー API マッピング（2026-06-29, ログイン済みSPAを実機WebViewで解析）

### 場選択
- TOP の会場グリッド: `<li id="jyoNN">`（NN=場コード01-24）内の `<a>`。クリック（委譲ハンドラ）で
  `/service/bet/betcom/nextrace/today` の投票ページへ遷移し、**投票系コントローラが遅延ロード**される。
- ロード後の主なAPI: `BOAT.betcom_controller`（統括）, `raceselpanel_*`（レース選択）,
  `reg_service.addBet`（単一）, `box_service.addBet`（ボックス）, `distamo_*`（資金配分）,
  `betlist_*`, `combi_controller.open`, `odds3t_*`(3連単) 他。

### 3連単ボックス（box_controller / box_service）
- UI: `.combiSel` をクリックで艇トグル（`check`クラス, `_arrayBoxCombi`へ）。`#combiCount`に点数。
  `#boxAmountBtn`(+`#amount`) で確定。`#combiConfirmBtnBox`→`combi_controller.open`。
- **直接呼出可**: `BOAT.box_service.addBet(numberOfSheets, kachishiki, [b1,b2,b3], isAlertStop)`。
  内部で `kumiban_generator.generateLive(kachishiki, "3"(=BOX), selectList)` が6点生成→betlistへ。
  kachishiki: 3連単=「6」。

### 資金配分（distamo_controller / distamo_service）★仕様7
- `BOAT.distamo_controller.open()` → `#popupMain` にモーダル描画（現betlistを表示）。
- `#distamoTotal` に合計額入力 → `#execDistamo`(配分実行) = `distamo_service.validate`→`display(total)`で各点へ配分表示。
- `#updateDistamo`(反映) = `distamo_service.modify()`→`betlist_controller.draw()` で betlist に金額確定、モーダル閉じる。
- フロー: ①box_service.addBet で6点追加 → ②distamo_controller.open() → ③#distamoTotal=総額(=マーチン掛金) →
  ④#execDistamo → ⑤#updateDistamo。

### まだ要ライブ確認（次：開催中の1-6Rで）
- **レース選択**: `raceselpanel_service.changeRaceEvent`/`raceselpanel_controller.draw` のタブ/呼出（1R-6R指定）。
- **券種=3連単＋ボックス**の切替: `betcom_controller.openContents`/タブ操作の具体列。
- **最終投票導線**: betlist→投票内容確認→投票用パスワード→投票実行（新SPAのセレクタ。旧 `#betconfForm/#pass/#submitBet` は要再確認）。
- 締切絶対時刻: `#nextRaceDeadline` は「締切まで◯分」表示（`hatsubaiLeftTime`）。
- 全コントローラJSは scratchpad に保存済（box_*.js, distamo_*.js, raceselpanel_*.js, betcom_controller.js）。

---

## 確定: 購入フロー全手順（2026-06-29 実機WebViewで確認画面まで実地検証, submit OFF）

各ステップのクリックは「mousedown/mouseup/click を dispatch」（委譲ハンドラ発火）。

1. **ログイン**: `LOGIN_POPUP_FIX`注入済の状態で #memberNo/#pin/#authPassword を set → #loginButton を enable+click → 投票TOP（/service/bet/top）。✅検証済(アプリ)
2. **場選択**: `#jyo{NN} a`（NN=場コード01-24）をクリック → 投票ページ（/service/bet/...）へ。投票系コントローラが遅延ロード。✅
3. **レース選択**: `#selRaceNo{0N}`（N=1-6, ゼロ詰め）をクリック。現在Rは `betcom_controller.getSelectionRace()`。✅
4. **券種=3連単**: 既定で `getSelKachisiki()==="6"`。違えば3連単タブをクリック。✅(既定6)
5. **ボックス**: `#betway3` をクリック（betway: #betway1=通常/#betway3=box/#betway4=formation）。✅
6. **艇選択**: 出てくる `.combiSel`（textが艇番1-6）から3つクリック → `#combiCount` が「6」。✅検証(6点生成)
7. **ボックス追加**: `#amount` に金額(仮100)を入れ `#boxAmountBtn` をクリック → betlistへ6点追加。または `BOAT.box_service.addBet(amount,"6",[b1,b2,b3],false)`。✅
8. **資金配分**: `.betlistbtn.combi`（=資金配分ボタン）or `BOAT.distamo_controller.open()` → `#distamoTotal` に総額(=マーチン掛金) → `#execDistamo`(配分実行) → `#updateDistamo`(反映)。配分結果は `#betAmount0..5`。✅検証
9. **投票内容確認へ**: `.btnSubmit`（=`#betlist .btnSubmit`）or `BOAT.betlist_controller.betlistSubmit()` → `/service/bet/betconf`。✅検証
10. **投票実行**: 確認画面で `#pass`(投票用パスワード, name=betPassword) を入力（`#amount`は自動）→ `#submitBet a`（「投票する」）をクリック。**※submit OFF時はここを押さない＝確認画面で停止**。`#betconfForm` 健在。⏸（未実行＝検証はここで停止）

→ 確認画面の構造（`#betconfForm`/`#amount`/`#pass`/`#submitBet a`）は**PC版と同一**。SPA化したのはナビ部分のみ。
