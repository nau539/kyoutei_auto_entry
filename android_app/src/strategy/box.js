// 3連単ボックスの買い目生成。
// 3艇を指定 -> 順列6通り（計6点）。

export function normalizeBoxBoats(boats) {
  const arr = Array.from(
    new Set((boats || []).map((n) => parseInt(n, 10)).filter((n) => n >= 1 && n <= 6))
  );
  if (arr.length !== 3) {
    throw new Error(`3連単ボックスは異なる3艇の指定が必要です: ${JSON.stringify(boats)}`);
  }
  return arr.sort((a, b) => a - b);
}

// 返り値: [[1,2,3],[1,3,2],...] の6要素（着順あり=3連単）
export function trifectaBox(boats) {
  const xs = normalizeBoxBoats(boats);
  const out = [];
  for (let i = 0; i < 3; i++) {
    for (let j = 0; j < 3; j++) {
      for (let k = 0; k < 3; k++) {
        if (i !== j && j !== k && i !== k) out.push([xs[i], xs[j], xs[k]]);
      }
    }
  }
  return out; // 必ず6点
}

// driver.js が使う tickets 形へ変換。totalYen を6点へ均等割り（100円単位）。
// 端数は先頭の買い目に寄せる。資金配分を使わない素の均等割りフォールバック。
export function trifectaBoxTickets(boats, perTicketYen) {
  const combos = trifectaBox(boats);
  const yen = parseInt(perTicketYen, 10);
  if (!(yen > 0) || yen % 100 !== 0) {
    throw new Error(`1点あたり金額は100円単位が必要です: ${perTicketYen}`);
  }
  return combos.map((numbers) => ({ market: "3連単", numbers, betYen: yen }));
}
