// 1レース分の購入オーケストレーション（現行SPA・ボックス＋資金配分）。
// docs/telboat_recon.md の確定フローに対応。submit OFF で確認画面停止。

import { venueCode } from "./constants";
import { fillLogin, isLoginFormVisible } from "./inject";
import * as S from "./spa";

export class SpaEntryError extends Error {}

// entry: { venueName, raceNum, boats:[b1,b2,b3], stakeYen }
// cfg:   storage設定（memberNo/pin/authPassword/votePassword/submitEnabled）
export async function runRaceEntry(bridge, cfg, entry, log = () => {}) {
  const jyo = venueCode(entry.venueName);
  if (!jyo) throw new SpaEntryError(`競艇場コードを解決できません: ${entry.venueName}`);
  if (!(entry.raceNum >= 1 && entry.raceNum <= 12)) throw new SpaEntryError(`レース番号が不正: ${entry.raceNum}`);
  const boats = (entry.boats || []).map((n) => parseInt(n, 10)).filter((n) => n >= 1 && n <= 6);
  if (new Set(boats).size !== 3) throw new SpaEntryError(`ボックスは異なる3艇が必要: ${JSON.stringify(entry.boats)}`);
  const stakeYen = parseInt(entry.stakeYen, 10);
  if (!(stakeYen > 0) || stakeYen % 100 !== 0) throw new SpaEntryError(`資金配分合計は100円単位が必要: ${entry.stakeYen}`);

  await ensureLoggedIn(bridge, cfg, log);

  log(`場選択: ${entry.venueName}(${jyo})`);
  await bridge.evalAsync(S.selectVenue(jyo));
  await bridge.waitFor(S.isBetPageReady(), { timeoutMs: 15000 });

  log(`レース選択: ${entry.raceNum}R`);
  await bridge.evalAsync(S.selectRace(entry.raceNum));
  await bridge.waitFor(S.isRaceSelected(entry.raceNum), { timeoutMs: 10000 });

  const k = await bridge.evalAsync(S.ensureSanrentan());
  if (!k || !k.ok) throw new SpaEntryError(`3連単を選択できません (kachi=${k && k.kachi})`);

  log("ボックスモードへ");
  await bridge.evalAsync(S.selectBox());
  await bridge.waitFor(S.isBoxMode(), { timeoutMs: 8000 });

  log(`艇選択: ${boats.join("-")} ボックス`);
  const sb = await bridge.evalAsync(S.selectBoats(boats));
  const cc = parseInt(sb && sb.combiCount, 10);
  if (cc !== 6) throw new SpaEntryError(`ボックス6点になりません (clicked=${sb && sb.clicked}, combiCount=${sb && sb.combiCount})`);

  await bridge.evalAsync(S.addBox(100));

  log(`資金配分: 合計 ${stakeYen.toLocaleString()}円`);
  await bridge.evalAsync(S.openDistamo());
  await bridge.waitFor(S.isDistamoOpen(), { timeoutMs: 8000 });
  await bridge.evalAsync(S.execDistamo(stakeYen));
  await bridge.waitFor(S.isDistamoCalculated(), { timeoutMs: 8000 });
  await bridge.evalAsync(S.applyDistamo());

  log("投票内容確認へ");
  const mv = await bridge.evalAsync(S.toConfirm());
  if (!mv || !mv.ok) throw new SpaEntryError("投票内容確認へ進めません");
  await bridge.waitFor(S.isConfirmReady(), { timeoutMs: 12000 });

  log("投票用パスワード入力");
  const fc = await bridge.evalAsync(S.fillConfirm(cfg.votePassword));
  if (!fc || !fc.ok) throw new SpaEntryError("投票用パスワード入力に失敗");

  if (!cfg.submitEnabled) {
    log("submit OFF: 確認画面で停止（実購入なし）");
    return { status: "prepared", venue: entry.venueName, raceNum: entry.raceNum, boats, stakeYen };
  }

  log("投票実行");
  const sv = await bridge.evalAsync(S.submitVote());
  if (!sv || !sv.ok) throw new SpaEntryError("投票実行ボタンを押せません");
  await bridge.waitFor(S.isVoteComplete(), { timeoutMs: 15000 });
  log("投票完了");
  return { status: "submitted", venue: entry.venueName, raceNum: entry.raceNum, boats, stakeYen };
}

async function ensureLoggedIn(bridge, cfg, log) {
  const onBet = await bridge.evalAsync(S.isBetPageReady(), 3000).catch(() => false);
  const loggedTop = await bridge
    .evalAsync(`return /\\/service\\/bet\\//.test(location.href) || !!document.querySelector('#jyoInfos');`, 3000)
    .catch(() => false);
  if (onBet === true || loggedTop === true) return;

  const hasForm = await bridge.evalAsync(isLoginFormVisible(), 4000).catch(() => false);
  if (hasForm !== true) throw new SpaEntryError("ログインフォームもTOPも検出できません");

  log("ログイン");
  const fl = await bridge.evalAsync(
    fillLogin({ memberNo: cfg.memberNo, pin: cfg.pin, authPassword: cfg.authPassword })
  );
  if (!fl || !fl.ok) throw new SpaEntryError(`ログイン入力に失敗: ${(fl && fl.error) || "?"}`);
  // LOGIN_POPUP_FIX により同一WebViewで /service/bet/top へ遷移
  await bridge.waitFor(
    `return /\\/service\\/bet\\/top/.test(location.href) || !!document.querySelector('#jyoInfos');`,
    { timeoutMs: 20000 }
  );
  log("ログイン完了");
}
