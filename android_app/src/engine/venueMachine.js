// 会場ごとの進行状態機械。
// active: 購入対象 / won: 的中で終了 / exhausted: 最大Rまで未的中で終了。

export function createVenueState(venueName, { raceMin = 1, raceMax = 6, boxBoats, martingale } = {}) {
  return {
    venueName,
    raceMin,
    raceMax,
    boxBoats: boxBoats || [],
    martingale: martingale || null, // マーチン設定（src/strategy/martingale.js のcfg）
    currentRace: raceMin,
    status: "active",
    history: [], // [{ raceNum, resultTop3, hit, stakeYen, purchasedAt }]
  };
}

// 当該レース時点の連続外し回数（R1=0, R2=1, ...）。会場は的中で終了するため現走前は全て外れ。
export function currentMissCount(state) {
  return state.currentRace - state.raceMin;
}

export function isVenueActive(state) {
  return state.status === "active";
}

// 購入を記録（結果はまだ）。
export function recordPurchase(state, raceNum, info = {}) {
  state.history.push({ raceNum, purchasedAt: info.at || null, result: "purchased", ...info });
  return state;
}

// レース結果を反映し、次の状態を決める。
// resultTop3: [1着,2着,3着]、hit: 的中判定結果(boolean)
export function recordRaceOutcome(state, raceNum, resultTop3, hit) {
  const entry = state.history.find((h) => h.raceNum === raceNum);
  if (entry) {
    entry.resultTop3 = resultTop3;
    entry.hit = hit;
  } else {
    state.history.push({ raceNum, resultTop3, hit });
  }

  if (hit) {
    state.status = "won";
  } else if (raceNum >= state.raceMax) {
    state.status = "exhausted";
  } else {
    state.currentRace = raceNum + 1;
  }
  return state;
}
