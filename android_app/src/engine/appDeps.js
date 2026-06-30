// orchestrator.runAllVenues に渡す「実依存」を構築する。
//   purchase       = 検証済みSPA購入（spaDriver.runRaceEntry）
//   waitForResult  = boatrace.jp から着順 top3（公開・ログイン不要）
//   waitUntilFireTime = 締切-leadSeconds まで待機（締切時刻の取得は下記2方式）
//
// 注: 単一WebViewで最大3会場を捌くため、購入は逐次実行。精密な締切1分前スケジューリングと
//     Doze対策の常駐は第2弾（フォアグラウンドサービス＋exact alarm）で仕上げる。

import { runRaceEntry } from "../telboat/spaDriver";
import { waitForRaceTop3 } from "../telboat/raceResult";

export function todayYmd(d) {
  const x = d || new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${x.getFullYear()}${p(x.getMonth() + 1)}${p(x.getDate())}`;
}

// getDeadlineEpoch(venueName, raceNum) -> epochMs | null（任意。無ければ即購入）
export function makeAppDeps(bridge, cfg, opts = {}) {
  const log = opts.log || (() => {});
  const leadSeconds = opts.leadSeconds || cfg.leadSeconds || 60;
  const sleep = opts.sleep || ((ms) => new Promise((r) => setTimeout(r, ms)));
  const nowMs = opts.nowMs || (() => Date.now());

  // 単一WebViewのため購入は逐次化（複数会場の購入が同時にWebViewを奪い合わないように）
  let lock = Promise.resolve();
  const withWebView = (fn) => {
    const run = lock.then(fn, fn);
    lock = run.then(() => {}, () => {});
    return run;
  };

  return {
    log,
    onRecord: opts.onRecord,
    now: () => new Date().toISOString(),

    purchase: (entry) => withWebView(() => runRaceEntry(bridge, cfg, entry, log)),

    waitForResult: (venueName, raceNum) =>
      waitForRaceTop3(venueName, raceNum, todayYmd(), { sleep, now: nowMs }),

    // 締切-leadSeconds まで待機。getDeadlineEpoch があればそれを使う。
    waitUntilFireTime: async (venueName, raceNum) => {
      if (!opts.getDeadlineEpoch) return; // 締切情報なし→即購入（第2弾で精密化）
      let dl = null;
      try {
        dl = await opts.getDeadlineEpoch(venueName, raceNum);
      } catch (e) {
        return;
      }
      if (!dl) return;
      const fireAt = dl - leadSeconds * 1000;
      let waitMs = fireAt - nowMs();
      if (waitMs <= 0) return; // 既に発火時刻を過ぎている→即購入
      log(`[${venueName}] R${raceNum} 締切1分前まで待機 (${Math.round(waitMs / 1000)}秒)`);
      // 長い待機は分割（バックグラウンド維持は第2弾の常駐で担保）
      while (waitMs > 0) {
        const chunk = Math.min(waitMs, 30000);
        await sleep(chunk);
        waitMs = fireAt - nowMs();
      }
    },
  };
}
