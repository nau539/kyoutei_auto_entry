// 会場ごと独立のマーチンゲール掛金計算。
// 「外れたら次レースで増額、的中で当該会場終了（初期額にリセット）」を 1R〜6R で実行。
// 掛金 = そのレースの「資金配分合計（#distamoTotal に入れる総額）」として扱う。
//
// 増額ルールは可変（お客様の数値は契約後に確定）。既定は「一定額上乗せ(fixed_add)」。

export const DEFAULT_MARTINGALE = {
  rule: "fixed_add", // "fixed_add" | "multiplier" | "sequence"
  initialYen: 600, // 初期掛金（6点×100円相当を仮の既定に）
  stepYen: 600, // fixed_add: 1段ごとの上乗せ額
  factor: 2, // multiplier: 倍率（倍々なら2）
  sequence: [], // sequence: [R1, R2, ...] の明示額（未指定段は最後の値を流用）
  maxYen: null, // 上限（任意）。超える場合はここで頭打ち
};

// missCount = 当該レース時点での「連続外し回数」（R1=0, R2=1, ...）。
// 会場は的中で終了するため、現走前の同会場レースは全て外れ＝missCount。
export function stakeForMissCount(missCount, cfg = {}) {
  const c = { ...DEFAULT_MARTINGALE, ...cfg };
  const m = Math.max(0, Math.floor(missCount || 0));

  let yen;
  if (c.rule === "multiplier") {
    yen = c.initialYen * Math.pow(c.factor, m);
  } else if (c.rule === "sequence") {
    const seq = Array.isArray(c.sequence) ? c.sequence : [];
    yen = seq.length ? seq[Math.min(m, seq.length - 1)] : c.initialYen;
  } else {
    // fixed_add
    yen = c.initialYen + m * c.stepYen;
  }

  yen = Math.round(yen);
  if (c.maxYen) yen = Math.min(yen, c.maxYen);
  // 100円単位へ切り捨て
  yen = Math.floor(yen / 100) * 100;
  if (!(yen >= 100)) throw new Error(`不正な掛金額になりました: ${yen}（cfg=${JSON.stringify(cfg)}）`);
  return yen;
}

// 会場状態（venueMachine.js）から現走の掛金を求める。
export function stakeForVenueState(state) {
  const missCount = (state.currentRace ?? state.raceMin) - state.raceMin;
  return stakeForMissCount(missCount, state.martingale || {});
}

// 1走分の進行を金額付きで先読み（ログ・確認用）。
export function previewProgression(cfg = {}, { raceMin = 1, raceMax = 6 } = {}) {
  const out = [];
  for (let r = raceMin; r <= raceMax; r++) {
    out.push({ raceNum: r, missCount: r - raceMin, stakeYen: stakeForMissCount(r - raceMin, cfg) });
  }
  return out;
}
