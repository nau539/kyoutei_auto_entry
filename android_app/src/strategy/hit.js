// 的中判定。3連単ボックス（3艇）は、結果の1-2-3着がその3艇と一致（順不同）なら的中。

export function isTrifectaBoxHit(boxBoats, resultTop3) {
  const box = Array.from(
    new Set((boxBoats || []).map((n) => parseInt(n, 10)).filter((n) => n >= 1 && n <= 6))
  );
  if (box.length !== 3) return false;

  const top3 = (resultTop3 || []).map((n) => parseInt(n, 10)).slice(0, 3);
  if (top3.length < 3 || top3.some((n) => !(n >= 1 && n <= 6))) return false;

  const s = new Set(top3);
  if (s.size !== 3) return false; // 同番含む不正データ除外
  return box.every((b) => s.has(b));
}
