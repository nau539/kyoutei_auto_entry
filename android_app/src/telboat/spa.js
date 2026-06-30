// 現行テレボートSPA向けの購入ステップ（実機WebViewで確認画面まで実地検証済み）。
// docs/telboat_recon.md「確定: 購入フロー全手順」に対応。
// 各ビルダーは bridge.evalAsync が (function(){...})() で実行する JS 文字列を返す。

const HELPER = `
  window.__SPA = window.__SPA || {};
  __SPA.q = function(sel){ return document.querySelector(sel); };
  __SPA.txt = function(el){ return String((el&&el.textContent)||'').replace(/\\s+/g,'').trim(); };
  __SPA.fire = function(el){ if(!el) return false;
    ['mousedown','mouseup','click'].forEach(function(t){ el.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true})); });
    return true; };
  __SPA.clickSel = function(sel){ return __SPA.fire(__SPA.q(sel)); };
  __SPA.set = function(sel,val){ var e=__SPA.q(sel); if(!e) return false;
    try{e.focus();}catch(x){} e.value=val;
    e.dispatchEvent(new Event('input',{bubbles:true})); e.dispatchEvent(new Event('change',{bubbles:true})); return true; };
  __SPA.bc = function(){ return (window.BOAT && BOAT.betcom_controller) || null; };
`;
const step = (body) => HELPER + "\n" + body;
const pad2 = (n) => String(parseInt(n, 10)).padStart(2, "0");

// 2. 場選択
export const selectVenue = (jyoCode) =>
  step(`return { ok: __SPA.fire(__SPA.q('#jyo${pad2(jyoCode)} a') || __SPA.q('#jyo${pad2(jyoCode)}')) };`);

// 投票ページ到達判定
export const isBetPageReady = () =>
  step(`return /\\/service\\/bet\\//.test(location.href) && !!__SPA.bc();`);

// 3. レース選択
export const selectRace = (raceNum) =>
  step(`
    var ok = __SPA.clickSel('#selRaceNo${pad2(raceNum)}');
    return { ok: ok, race: (function(){ try { return __SPA.bc().getSelectionRace(); } catch(e){ return '?'; } })() };
  `);
export const isRaceSelected = (raceNum) =>
  step(`try { return String(__SPA.bc().getSelectionRace()) === '${pad2(raceNum)}'; } catch(e){ return false; }`);

// 4. 券種=3連単（既定で "6"。違えば 3連単タブをクリック）
export const ensureSanrentan = () =>
  step(`
    var cur=''; try{ cur=String(__SPA.bc().getSelKachisiki()); }catch(e){}
    if(cur==='6') return { ok:true, kachi:cur, already:true };
    var nodes=Array.prototype.slice.call(document.querySelectorAll('a,li'));
    for(var i=0;i<nodes.length;i++){ if(__SPA.txt(nodes[i])==='3連単'){ __SPA.fire(nodes[i]); break; } }
    var now=''; try{ now=String(__SPA.bc().getSelKachisiki()); }catch(e){}
    return { ok: now==='6', kachi:now };
  `);

// 5. ボックスへ切替
export const selectBox = () => step(`return { ok: __SPA.clickSel('#betway3') };`);
export const isBoxMode = () =>
  step(`try { return String(__SPA.bc().getSelBetWay())==='3' || document.querySelectorAll('.combiSel').length>0; } catch(e){ return document.querySelectorAll('.combiSel').length>0; }`);

// 6. 艇選択（boats=[b1,b2,b3]）→ combiCount
export const selectBoats = (boats) =>
  step(`
    var want = ${JSON.stringify(boats.map((b) => String(parseInt(b, 10))))};
    var clicked = 0;
    document.querySelectorAll('.combiSel').forEach(function(e){
      if(want.indexOf(__SPA.txt(e)) >= 0){ __SPA.fire(e); clicked++; }
    });
    var cc = (__SPA.q('#combiCount') || {}).textContent;
    return { ok: clicked === want.length, clicked: clicked, combiCount: cc };
  `);

// 7. ボックス追加（金額は仮。資金配分で上書きされる）
export const addBox = (nominalYen) =>
  step(`
    __SPA.set('#amount', String(${parseInt(nominalYen, 10) || 100}));
    var ok = __SPA.clickSel('#boxAmountBtn');
    return { ok: ok };
  `);

// 8. 資金配分: 開く → 総額 → 配分実行 → 反映
export const openDistamo = () =>
  step(`
    // 検証済み: distamo_controller.open() の直接呼出が最も確実（.betlistbtn.combi は off の個体があるため）
    try{
      if(window.BOAT && BOAT.distamo_controller && typeof BOAT.distamo_controller.open === 'function'){
        BOAT.distamo_controller.open();
        return { ok:true, via:'js' };
      }
    }catch(e){ return { ok:false, error:String(e) }; }
    var btns = Array.prototype.slice.call(document.querySelectorAll('.betlistbtn.combi'));
    for(var i=0;i<btns.length;i++){
      if(!/(^|\\s)off(\\s|$)/.test(btns[i].className)){ __SPA.fire(btns[i]); return { ok:true, via:'button' }; }
    }
    return { ok:false, error:'distamo open unavailable' };
  `);
export const isDistamoOpen = () => step(`return !!__SPA.q('#distamoTotal');`);
export const execDistamo = (totalYen) =>
  step(`
    __SPA.set('#distamoTotal', String(${parseInt(totalYen, 10)}));
    var ok = __SPA.clickSel('#execDistamo');
    return { ok: ok };
  `);
export const isDistamoCalculated = () =>
  step(`var u=__SPA.q('#updateDistamo'); return !!u && !/(^|\\s)off(\\s|$)/.test(u.className);`);
export const applyDistamo = () => step(`return { ok: __SPA.clickSel('#updateDistamo') };`);

// 9. 投票内容確認へ
export const toConfirm = () =>
  step(`
    if(__SPA.clickSel('.btnSubmit') || __SPA.clickSel('#betlist .btnSubmit')) return { ok:true, via:'button' };
    try{ BOAT.betlist_controller.betlistSubmit(); return { ok:true, via:'js' }; }catch(e){ return { ok:false, error:String(e) }; }
  `);
export const isConfirmReady = () =>
  step(`return /\\/betconf/.test(location.href) || !!__SPA.q('#betconfForm') || !!__SPA.q('#pass');`);

// 10. 確認画面入力（投票用パスワード。金額は自動）／投票実行
export const fillConfirm = (votePassword) =>
  step(`
    var pw = __SPA.set('#pass', ${JSON.stringify(String(votePassword))})
          || __SPA.set("#betconfForm input[name='betPassword']", ${JSON.stringify(String(votePassword))});
    return { ok: pw };
  `);
export const submitVote = () =>
  step(`return { ok: __SPA.clickSel('#submitBet a') || __SPA.clickSel('#submitBet') };`);
export const isVoteComplete = () =>
  step(`return !!(__SPA.q('#sameJyoBet') || __SPA.q('#modifyJyoBetForm') || __SPA.q('#voteListAreaInner') || /承りました|完了/.test(document.body.innerText.slice(0,400)));`);

// 各レースの投票締切予定時刻をレースタブ（#selRaceNoNN「NR HH:MM」）から読む。
// 返り値: [{ raceNum, hhmm }]（締切済みなどでHH:MMが無い行は除外）
export const readRaceTimes = () =>
  step(`
    var out = [];
    var nodes = document.querySelectorAll('[id^=selRaceNo]');
    nodes.forEach(function(n){
      var idm = String(n.id||'').match(/selRaceNo(\\d{2})/);
      var tm = String(n.textContent||'').match(/(\\d{1,2}):(\\d{2})/);
      if(idm && tm){ out.push({ raceNum: parseInt(idm[1],10), hhmm: tm[1].padStart(2,'0')+':'+tm[2] }); }
    });
    return out;
  `);

// 締切までの残り分（#nextRaceDeadline「…締切予定時刻まで ◯分」）。選択中レース対象。
export const readDeadlineMinutes = () =>
  step(`
    var e = __SPA.q('#nextRaceDeadline');
    if(!e) return null;
    var m = String(e.textContent||'').match(/(\\d+)\\s*分/);
    return m ? parseInt(m[1],10) : null;
  `);

// 現在地ユーティリティ
export const currentSelection = () =>
  step(`
    try { var bc=__SPA.bc(); return { race: bc.getSelectionRace(), kachi: bc.getSelKachisiki(), betway: bc.getSelBetWay(), url: location.href }; }
    catch(e){ return { url: location.href, error: String(e) }; }
  `);
