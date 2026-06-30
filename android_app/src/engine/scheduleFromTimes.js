// レースタブの締切時刻(HH:MM)から、発火スケジュール（締切1分前・衝突時2分前）を組む。
// scheduler.planSchedule を流用。深夜跨ぎ（締切が翌日）にも配慮。

import { planSchedule } from "./scheduler";

// "HH:MM" + 基準日(Date) -> epoch(ms)。基準時刻より大幅に過去なら翌日扱い。
export function hhmmToEpoch(hhmm, baseDate, nowMs) {
  const m = String(hhmm || "").match(/^(\d{1,2}):(\d{2})$/);
  if (!m) return null;
  const d = baseDate ? new Date(baseDate.getTime()) : new Date();
  d.setHours(parseInt(m[1], 10), parseInt(m[2], 10), 0, 0);
  let t = d.getTime();
  const now = typeof nowMs === "number" ? nowMs : Date.now();
  // 締切が現在より6時間以上過去なら、翌日のレース（深夜開催）とみなす
  if (t < now - 6 * 3600 * 1000) t += 24 * 3600 * 1000;
  return t;
}

// venueTimes: [{ venueName, raceNum, hhmm }]（対象レースのみ）
// -> planSchedule 形式 [{ key, venueName, raceNum, deadline(epoch秒), fireAt, leadUsed, collision }]
export function buildSchedule(venueTimes, { baseDate, nowMs, leadSeconds = 60, stepSeconds = 60 } = {}) {
  const races = [];
  for (const v of venueTimes || []) {
    const epochMs = hhmmToEpoch(v.hhmm, baseDate, nowMs);
    if (!epochMs) continue;
    races.push({
      key: `${v.venueName}-${v.raceNum}`,
      venueName: v.venueName,
      raceNum: v.raceNum,
      deadline: Math.floor(epochMs / 1000), // scheduler は秒
    });
  }
  return planSchedule(races, { leadSeconds, stepSeconds });
}

// (venueName, raceNum) -> 締切epoch(ms) を引く辞書を作る。
export function deadlineEpochMap(venueTimes, optsForBase = {}) {
  const map = {};
  for (const v of venueTimes || []) {
    const epochMs = hhmmToEpoch(v.hhmm, optsForBase.baseDate, optsForBase.nowMs);
    if (epochMs) map[`${v.venueName}-${v.raceNum}`] = epochMs;
  }
  return map;
}
