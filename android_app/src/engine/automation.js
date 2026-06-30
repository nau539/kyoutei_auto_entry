// 自動運転ランナー：設定→ログイン→各会場の締切時刻先読み→締切1分前スケジュールで
// オーケストレータ実行（会場ごと独立・マーチン・的中で終了・ログ保存）。
//
// ⚠ 締切1分前の発火は in-app タイマー（setTimeout）で行う。画面OFF/省電力下でも動かし続けるには
//   フォアグラウンドサービス＋正確アラーム（第2弾ネイティブ・実機検証）が必要。

import { runAllVenues } from "./orchestrator";
import { makeAppDeps } from "./appDeps";
import { hhmmToEpoch } from "./scheduleFromTimes";
import { venueCode } from "../telboat/constants";
import * as S from "../telboat/spa";
import { fillLogin, isLoginFormVisible } from "../telboat/inject";

const noop = () => {};

export class AutomationRunner {
  constructor(bridge, cfg, hooks = {}) {
    this.bridge = bridge;
    this.cfg = cfg;
    this.log = hooks.log || noop;
    this.onRecord = hooks.onRecord;
    this.running = false;
    this._abort = false;
  }

  buildVenuesConfig() {
    const cfg = this.cfg;
    const venues = (cfg.venues || []).map((v) => String(v || "").trim()).filter(Boolean).slice(0, 3);
    const martingale = cfg.martingale || {
      rule: cfg.martingaleRule || "fixed_add",
      initialYen: cfg.initialStakeYen || 600,
      stepYen: cfg.stepStakeYen || 600,
      factor: cfg.martingaleFactor || 2,
      maxYen: cfg.maxStakeYen || null,
    };
    return venues.map((name) => ({
      venueName: name,
      // 買い目(3艇)は会場ごと設定。未設定時は共通 boxBoats（暫定既定 [1,2,3]）
      boxBoats: (cfg.venueBoats && cfg.venueBoats[name]) || cfg.boxBoats || [1, 2, 3],
      raceMin: cfg.raceMin || 1,
      raceMax: cfg.raceMax || 6,
      martingale,
    }));
  }

  async start() {
    if (this.running) throw new Error("既に自動運転中です");
    this.running = true;
    this._abort = false;
    try {
      const venuesConfig = this.buildVenuesConfig();
      if (!venuesConfig.length) throw new Error("対象会場が設定されていません（設定タブで指定）");
      for (const v of venuesConfig) {
        if (new Set(v.boxBoats.map((n) => parseInt(n, 10))).size !== 3) {
          throw new Error(`${v.venueName}: 3連単ボックスの3艇が未設定/不正です`);
        }
        if (!venueCode(v.venueName)) throw new Error(`会場名が不正: ${v.venueName}`);
      }

      await this.ensureLoggedIn();

      // 各会場の締切時刻を先読み → 締切epochマップ
      const deadlineMap = {};
      for (const v of venuesConfig) {
        if (this._abort) { this.log("停止しました"); return; }
        this.log(`[${v.venueName}] 締切時刻を取得中…`);
        await this.bridge.evalAsync(S.selectVenue(venueCode(v.venueName)));
        await this.bridge.waitFor(S.isBetPageReady(), { timeoutMs: 15000 });
        const times = await this.bridge.evalAsync(S.readRaceTimes());
        let n = 0;
        for (const t of times || []) {
          if (t.raceNum >= v.raceMin && t.raceNum <= v.raceMax) {
            const ep = hhmmToEpoch(t.hhmm);
            if (ep) { deadlineMap[`${v.venueName}-${t.raceNum}`] = ep; n++; }
          }
        }
        this.log(`[${v.venueName}] 締切時刻 ${n}レース分を取得`);
      }

      const deps = makeAppDeps(this.bridge, this.cfg, {
        log: this.log,
        onRecord: this.onRecord,
        leadSeconds: this.cfg.leadSeconds || 60,
        getDeadlineEpoch: (venueName, raceNum) => deadlineMap[`${venueName}-${raceNum}`] || null,
      });

      this.log("=== 自動運転 開始（締切1分前に各会場を購入） ===");
      const summary = await runAllVenues(venuesConfig, deps);
      this.log("=== 自動運転 終了 ===");
      summary.forEach((s) =>
        this.log(`[${s.venueName}] ${s.status}${s.hitRace ? ` (${s.hitRace}Rで的中)` : ""} / ${s.racesPlayed}レース`)
      );
      return summary;
    } finally {
      this.running = false;
    }
  }

  stop() {
    this._abort = true;
    this.log("停止要求を受け付けました（実行中の購入は完了まで継続）");
  }

  async ensureLoggedIn() {
    const loggedTop = await this.bridge
      .evalAsync(`return /\\/service\\/bet\\//.test(location.href) || !!document.querySelector('#jyoInfos');`, 3000)
      .catch(() => false);
    if (loggedTop === true) return;

    const hasForm = await this.bridge.evalAsync(isLoginFormVisible(), 4000).catch(() => false);
    if (hasForm !== true) throw new Error("ログイン画面もTOPも検出できません（WebViewを再読込してください）");

    this.log("ログイン中…");
    const fl = await this.bridge.evalAsync(
      fillLogin({ memberNo: this.cfg.memberNo, pin: this.cfg.pin, authPassword: this.cfg.authPassword })
    );
    if (!fl || !fl.ok) throw new Error(`ログイン入力に失敗: ${(fl && fl.error) || "?"}`);
    await this.bridge.waitFor(
      `return /\\/service\\/bet\\/top/.test(location.href) || !!document.querySelector('#jyoInfos');`,
      { timeoutMs: 20000 }
    );
    this.log("ログイン完了");
  }
}
