// 全体制御：各会場を独立に「購入完了まで」進める（仕様の中核）。
// 会場ごと: 締切1分前に購入(ボックス+資金配分) → 結果待ち → 的中で終了 / 外れで次R(マーチン増額)。
//
// 実時刻・サイト依存部分は deps 経由で注入（テスト可能・第2弾の常駐実装と分離）:
//   deps.waitUntilFireTime(venueName, raceNum) -> Promise   締切-1分(衝突時2分)まで待つ
//   deps.purchase({venueName, raceNum, boats, stakeYen})   -> Promise<{status}>  spaDriver.runRaceEntry
//   deps.waitForResult(venueName, raceNum)                 -> Promise<[a,b,c]|null> 確定着順
//   deps.now()  -> ISO文字列（任意）
//   deps.log(msg), deps.onRecord(record)（任意）

import { createVenueState, recordPurchase, recordRaceOutcome, isVenueActive } from "./venueMachine";
import { stakeForVenueState } from "../strategy/martingale";
import { isTrifectaBoxHit } from "../strategy/hit";

const noop = () => {};

// venuesConfig: [{ venueName, boxBoats:[3], raceMin, raceMax, martingale }]
export async function runAllVenues(venuesConfig, deps = {}) {
  const log = deps.log || noop;
  const states = (venuesConfig || []).slice(0, 3).map((v) => createVenueState(v.venueName, v));
  await Promise.all(states.map((s) => runVenue(s, deps, log)));
  return states.map(summarize);
}

async function runVenue(state, deps, log) {
  while (isVenueActive(state)) {
    const raceNum = state.currentRace;
    const stakeYen = stakeForVenueState(state);
    const boats = state.boxBoats;
    const at = deps.now ? deps.now() : null;

    // 締切1分前(衝突時2分前)まで待機
    if (deps.waitUntilFireTime) {
      try {
        await deps.waitUntilFireTime(state.venueName, raceNum);
      } catch (e) {
        log(`[${state.venueName}] R${raceNum} 発火待ち中断: ${e.message}`);
      }
    }

    log(`[${state.venueName}] R${raceNum} 購入開始 (掛金 ${stakeYen.toLocaleString()}円 / ${boats.join("-")}ボックス)`);
    let purchaseStatus = "error";
    try {
      const res = await deps.purchase({ venueName: state.venueName, raceNum, boats, stakeYen });
      purchaseStatus = (res && res.status) || "submitted";
      recordPurchase(state, raceNum, { at, stakeYen, status: purchaseStatus });
      await emit(deps, { venueName: state.venueName, raceNum, boats, stakeYen, status: purchaseStatus, isoTime: at });
      log(`[${state.venueName}] R${raceNum} 購入: ${purchaseStatus}`);
    } catch (e) {
      log(`[${state.venueName}] R${raceNum} 購入失敗: ${e.message}`);
      await emit(deps, { venueName: state.venueName, raceNum, boats, stakeYen, status: "purchase_error", error: e.message, isoTime: at });
      // 購入できなかったレースは見送り、掛金据え置きで次レースへ（外れ扱いにはしない）
      if (raceNum >= state.raceMax) { state.status = "exhausted"; break; }
      state.currentRace = raceNum + 1;
      continue;
    }

    // 結果待ち→的中判定
    let top3 = null;
    try {
      top3 = await deps.waitForResult(state.venueName, raceNum);
    } catch (e) {
      log(`[${state.venueName}] R${raceNum} 結果取得失敗: ${e.message}`);
    }
    const hit = isTrifectaBoxHit(boats, top3 || []);
    recordRaceOutcome(state, raceNum, top3, hit);
    await emit(deps, { venueName: state.venueName, raceNum, boats, stakeYen, status: "result", top3, hit, isoTime: deps.now ? deps.now() : at });
    log(`[${state.venueName}] R${raceNum} 結果 ${JSON.stringify(top3)} → ${hit ? "的中・会場終了" : "外れ"}`);
  }
  log(`[${state.venueName}] 会場終了: ${state.status}`);
}

async function emit(deps, record) {
  if (deps.onRecord) {
    try { await deps.onRecord(record); } catch (e) { /* ログ保存失敗は無視 */ }
  }
}

function summarize(state) {
  return {
    venueName: state.venueName,
    status: state.status, // won / exhausted
    racesPlayed: state.history.filter((h) => h.resultTop3 !== undefined).length,
    hitRace: (state.history.find((h) => h.hit) || {}).raceNum || null,
    history: state.history,
  };
}
