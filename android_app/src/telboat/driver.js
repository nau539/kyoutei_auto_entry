// 1レース分の発注オーケストレーション。
// PC版 _execute_kyoutei / _kyoutei_open_target_race / _kyoutei_submit の流れを移植。

import { venueCode, kachishikiCode } from "./constants";
import * as J from "./inject";

export class EntryError extends Error {}

// entry: { venueName, raceNum, tickets:[{market, numbers:[int], betYen}] }
// cfg:   storage の設定（votePassword, submitEnabled 等）
// log:   (string) => void  進捗表示
export async function runEntry(bridge, cfg, entry, log = () => {}) {
  const jyoCode = venueCode(entry.venueName);
  if (!jyoCode) throw new EntryError(`競艇場コードを解決できません: ${entry.venueName}`);
  if (!(entry.raceNum >= 1)) throw new EntryError("レース番号が不正です");

  // 合計金額と各買い目の検証
  let totalYen = 0;
  const tickets = [];
  for (const t of entry.tickets) {
    const kachishiki = kachishikiCode(t.market);
    if (!kachishiki) throw new EntryError(`未対応券種: ${t.market}`);
    const betYen = Number(t.betYen) || 0;
    if (betYen <= 0 || betYen % 100 !== 0)
      throw new EntryError(`買い目金額は100円単位が必要: ${betYen}`);
    totalYen += betYen;
    tickets.push({
      market: t.market,
      numberOfSheets: Math.floor(betYen / 100),
      kachishiki,
      selectList: t.numbers.map((n) => String(parseInt(n, 10))),
      betYen,
    });
  }

  await ensureLoggedIn(bridge, cfg, log);

  log(`場選択: ${entry.venueName} (${jyoCode})`);
  await dismissNotice(bridge);
  await bridge.evalAsync(J.selectVenue(jyoCode));
  await bridge.waitFor(J.isRaceTabsReady(), { timeoutMs: 12000 });

  log(`レース選択: ${entry.raceNum}R`);
  const sel = await bridge.evalAsync(J.selectRace(entry.raceNum));
  if (!sel || !sel.ok) throw new EntryError(`対象レースのタブが見つかりません: ${entry.raceNum}R`);
  await bridge.waitFor(J.isBetPageReady(), { timeoutMs: 12000 });

  await bridge.evalAsync(J.clearBets());

  for (const t of tickets) {
    log(`買い目入力: ${t.market} ${t.selectList.join("-")} ${t.betYen.toLocaleString()}円`);
    const r = await bridge.evalAsync(J.addBet(t));
    if (!r || r.error) throw new EntryError(`買い目追加に失敗: ${(r && r.error) || "?"}`);
    if (r.isErrorDisp)
      throw new EntryError(`買い目追加エラー code=${r.errorCode || "-"} detail=${r.errorReplaceString || "-"}`);
  }

  log("投票内容確認へ");
  const mv = await bridge.evalAsync(J.moveToConfirm());
  if (!mv || !mv.ok) throw new EntryError("確認画面への導線を押せません");
  await bridge.waitFor(J.isConfirmReady(), { timeoutMs: 12000 });

  log(`金額・投票用パスワード入力 (合計 ${totalYen.toLocaleString()}円)`);
  const fc = await bridge.evalAsync(J.fillConfirm(totalYen, cfg.votePassword));
  if (!fc || !fc.ok) throw new EntryError("確認画面の入力に失敗（金額/パスワード欄）");

  if (!cfg.submitEnabled) {
    log("submit OFF: 確認画面で停止しました（実投票なし）");
    return { status: "prepared", ticketCount: tickets.length, totalYen };
  }

  log("投票実行");
  const sb = await bridge.evalAsync(J.clickSubmit());
  if (!sb || !sb.ok) throw new EntryError("投票実行ボタンを押せません");
  await bridge.evalAsync(J.dismissPopup()).catch(() => {});
  await bridge.waitFor(J.isComplete(), { timeoutMs: 12000 });
  log("投票完了を確認しました");
  return { status: "submitted", ticketCount: tickets.length, totalYen };
}

async function dismissNotice(bridge) {
  try {
    await bridge.evalAsync(J.dismissSpecialNotice());
  } catch (e) {
    /* best effort */
  }
}

async function ensureLoggedIn(bridge, cfg, log) {
  // 既にTOP/ログイン後ならスキップ
  try {
    const top = await bridge.evalAsync(J.isTopReady(), 3000);
    if (top === true) {
      await dismissNotice(bridge);
      return;
    }
  } catch (e) {
    /* fallthrough */
  }

  // ログインフォームが見えていれば入力
  const hasForm = await bridge.evalAsync(J.isLoginFormVisible(), 4000).catch(() => false);
  if (hasForm !== true) {
    throw new EntryError("ログインフォームもTOP画面も検出できません（WebViewのURL/状態を確認）");
  }

  log("ログイン入力");
  const fl = await bridge.evalAsync(
    J.fillLogin({ memberNo: cfg.memberNo, pin: cfg.pin, authPassword: cfg.authPassword })
  );
  if (!fl || !fl.ok) throw new EntryError(`ログイン入力に失敗: ${(fl && fl.error) || "?"}`);

  // ログイン後はポップアップ画面へ遷移する。
  // ※ react-native-webview は setSupportMultipleWindows={false} で
  //   ポップアップを同一WebViewに読み込む前提（RunScreen 参照）。
  await bridge.waitFor(J.isTopReady(), { timeoutMs: 20000 });
  await dismissNotice(bridge);
  log("ログイン完了");
}
