// 締切時刻からの発火スケジュール計算。
// 通常は「締切 - leadSeconds(=60)」に発火。締切が同時刻に重なる場合は
// 2番目以降を stepSeconds(=60) ずつ前倒し（締切-120, -180...）して同時実行を避ける。

export function planSchedule(races, opts = {}) {
  const leadSeconds = opts.leadSeconds ?? 60;
  const stepSeconds = opts.stepSeconds ?? 60;

  const valid = (races || []).filter((r) => Number.isFinite(r.deadline));

  // 締切（分単位）でグループ化＝同時刻の衝突判定
  const groups = new Map();
  for (const r of valid) {
    const minuteKey = Math.floor(r.deadline / 60);
    if (!groups.has(minuteKey)) groups.set(minuteKey, []);
    groups.get(minuteKey).push(r);
  }

  const plan = [];
  for (const group of groups.values()) {
    // 衝突時の優先順: venue名→raceNum で決定的に。先頭が -60、以降 -120, -180...
    group.sort(
      (a, b) =>
        String(a.venueName).localeCompare(String(b.venueName)) || a.raceNum - b.raceNum
    );
    group.forEach((r, idx) => {
      const lead = leadSeconds + idx * stepSeconds;
      plan.push({
        key: r.key,
        venueName: r.venueName,
        raceNum: r.raceNum,
        deadline: r.deadline,
        leadUsed: lead,
        fireAt: r.deadline - lead,
        collision: group.length > 1,
      });
    });
  }

  plan.sort((a, b) => a.fireAt - b.fireAt);
  return plan;
}
