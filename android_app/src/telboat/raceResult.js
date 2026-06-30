// レース結果（着順1-2-3着）を公開サイト boatrace.jp から取得（ログイン不要）。
// 3連単の的中組番 = 1着-2着-3着。これで的中判定（isTrifectaBoxHit）の入力を得る。

import { venueCode } from "./constants";

// boatrace.jp の jcd は場コード（01-24）と同一。
export function raceResultUrl(venueName, raceNum, dateYmd) {
  const jcd = venueCode(venueName);
  if (!jcd) throw new Error(`競艇場コードを解決できません: ${venueName}`);
  return `https://www.boatrace.jp/owpc/pc/race/raceresult?rno=${parseInt(raceNum, 10)}&jcd=${jcd}&hd=${dateYmd}`;
}

// 3連単の確定組番から着順 top3 を抽出。未確定（レース未終了）なら null。
export function parseTop3(html) {
  if (!html) return null;
  const i = html.indexOf("3連単");
  if (i < 0) return null;
  const block = html.slice(i, i + 600);
  const nums = [];
  const re = />\s*([1-6])\s*</g;
  let m;
  while ((m = re.exec(block)) !== null) {
    nums.push(parseInt(m[1], 10));
    if (nums.length >= 3) break;
  }
  return nums.length >= 3 ? nums.slice(0, 3) : null;
}

// dateYmd: "YYYYMMDD"。未確定時は null を返す（呼び出し側でポーリング）。
export async function fetchRaceTop3(venueName, raceNum, dateYmd) {
  const url = raceResultUrl(venueName, raceNum, dateYmd);
  const res = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
  if (!res.ok) throw new Error(`結果取得失敗 HTTP ${res.status}`);
  return parseTop3(await res.text());
}

// 結果が確定するまでポーリング（orchestrator の waitForResult に使う）。
export async function waitForRaceTop3(venueName, raceNum, dateYmd, opts = {}) {
  const intervalMs = opts.intervalMs || 30000;
  const timeoutMs = opts.timeoutMs || 30 * 60 * 1000; // 最大30分
  const sleep = opts.sleep || ((ms) => new Promise((r) => setTimeout(r, ms)));
  const deadline = (opts.now ? opts.now() : Date.now()) + timeoutMs;
  while ((opts.now ? opts.now() : Date.now()) < deadline) {
    try {
      const top3 = await fetchRaceTop3(venueName, raceNum, dateYmd);
      if (top3) return top3;
    } catch (e) {
      /* 一時的失敗は再試行 */
    }
    await sleep(intervalMs);
  }
  return null; // タイムアウト（未確定）
}
