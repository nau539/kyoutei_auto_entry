// テレボート操作を WebView へ注入する JS ステップ群。
// PC版 ipat_playwright.py の _kyoutei_* メソッド（page.evaluate 部分）を忠実に移植。
//
// 各ビルダーは「関数本体として実行され値を return する JS 文字列」を返す。
// RunScreen 側の bridge.evalAsync() が (function(){ <body> })() でラップして実行し、
// 戻り値（または Promise の解決値）を React Native 側へ postMessage で返す。

// ---- 画面内ヘルパー（毎ステップ先頭に付与） ----
const HELPER = `
  window.__TB = window.__TB || {};
  __TB.vis = function(sel){
    var el = document.querySelector(sel);
    if(!el) return false;
    var st = window.getComputedStyle(el);
    if(st && (st.display==='none' || st.visibility==='hidden')) return false;
    return el.offsetParent !== null || (el.getClientRects && el.getClientRects().length>0);
  };
  __TB.anyVis = function(sels){ for(var i=0;i<sels.length;i++){ if(__TB.vis(sels[i])) return true; } return false; };
  __TB.set = function(sel,val){
    var el = document.querySelector(sel);
    if(!el) return false;
    try{ el.focus(); }catch(e){}
    el.value = val;
    el.dispatchEvent(new Event('input',{bubbles:true}));
    el.dispatchEvent(new Event('change',{bubbles:true}));
    return true;
  };
  __TB.click = function(sel){ var el = document.querySelector(sel); if(!el) return false; el.click(); return true; };
`;

function step(body) {
  return HELPER + "\n" + body;
}

// WebView の injectedJavaScriptBeforeContentLoaded に渡す。
// テレボートのログインは window.open("","pctablet",...) で別窓を開き、その窓へ
// loginForm(target=pctablet) をPOSTする方式。WebViewでは別窓を扱えないため、
// pctablet窓の生成を握りつぶし、フォームを同一ビュー(_self)へ送らせて
// 正規フロー（reCAPTCHAトークン込み）のまま同一WebViewで認証完了させる。
// ※実WebViewで検証済み（同一ビューで /service/bet/top へ到達）。
export const LOGIN_POPUP_FIX = `
(function(){
  if (window.__tbPatched) return;
  window.__tbPatched = true;
  var realOpen = window.open;
  window.open = function(url, name, feat){
    if (name === 'pctablet') {
      var f = document.querySelector('#loginForm');
      if (f) { f.target = '_self'; }
      return { focus:function(){}, blur:function(){}, close:function(){}, closed:false,
               location:{ href:'', replace:function(){} }, document:{}, postMessage:function(){} };
    }
    return realOpen ? realOpen.apply(window, arguments) : null;
  };
})();
true;
`;

// ---- セレクタ定義（PC版と一致） ----
export const SEL = {
  loginForm: ["#memberNo", "#pin", "#authPassword", "#loginButton"],
  topReady: ["#todayForm", "#beforeForm", "#jyoInfos", "#jyoInfosTab", "#raceSelection", "#toplogoForm"],
  topPage: ["#jyoInfos li", "#jyoInfosTab li", "#todayForm", "#beforeForm"],
  raceTabs: ["#raceSelection .raceSelTab", "#raceSelection li"],
  betPageReady: ["#betlist", "#raceSelection"],
  confirmReady: ["#confirmationArea", "#betconfForm", "#amount", "#pass"],
  complete: ["#sameJyoBet", "#modifyJyoBetForm", "#voteListAreaInner"],
  specialNotice: ["#newsoverviewDisp", "div#newsoverviewDisp"],
};

// ---- 述語（RunScreen がポーリングで待機に使う） ----
export const isAnyVisible = (sels) => step(`return __TB.anyVis(${JSON.stringify(sels)});`);
export const isLoginFormVisible = () => isAnyVisible(SEL.loginForm);
export const isTopReady = () => isAnyVisible(SEL.topReady);
export const isTopPage = () => isAnyVisible(SEL.topPage);
export const isRaceTabsReady = () => isAnyVisible(SEL.raceTabs);
export const isBetPageReady = () => isAnyVisible(SEL.betPageReady);
export const isConfirmReady = () => isAnyVisible(SEL.confirmReady);
export const isComplete = () => isAnyVisible(SEL.complete);
export const isSpecialNoticeVisible = () => isAnyVisible(SEL.specialNotice);

// ---- ステップ ----

// ログインフォーム入力＋送信。creds: {memberNo, pin, authPassword}
export const fillLogin = (creds) =>
  step(`
    var c = ${JSON.stringify(creds)};
    var ok = __TB.set('#memberNo', c.memberNo)
          && __TB.set('#pin', c.pin)
          && __TB.set('#authPassword', c.authPassword);
    if(!ok) return { ok:false, error:'login form fields not found' };
    var b = document.querySelector('#loginButton');
    if(!b) return { ok:false, error:'loginButton not found' };
    b.disabled = false; // 初期 disabled を解除
    // jQuery委譲ハンドラ(_onclickLogin)を確実に発火させる
    ['mousedown','mouseup','click'].forEach(function(t){
      b.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true}));
    });
    return { ok:true };
  `);

// 特別なお知らせモーダルを閉じる（出ていなければ no-op）
export const dismissSpecialNotice = () =>
  step(`
    if(!__TB.anyVis(${JSON.stringify(SEL.specialNotice)})) return { closed:false, present:false };
    var btn = document.querySelector('#newsoverviewdispCloseButton');
    if(btn){ btn.click(); return { closed:true, present:true }; }
    return { closed:false, present:true, error:'close button not found' };
  `);

// TOP へ戻る（#toplogoForm を submit）
export const returnTop = () =>
  step(`
    var form = document.querySelector('#toplogoForm');
    if(!form) return { ok:false, error:'toplogoForm not found' };
    form.submit();
    return { ok:true };
  `);

// 場選択（#todayForm or #beforeForm の jyoCode/operationKbn をセットして submit）
export const selectVenue = (jyoCode) =>
  step(`
    var form = document.querySelector('#todayForm') || document.querySelector('#beforeForm');
    if(!form) return { ok:false, error:'venue form not found' };
    var jyo = form.querySelector("input[name='jyoCode']");
    var op  = form.querySelector("input[name='operationKbn']");
    if(!jyo || !op) return { ok:false, error:'jyoCode/operationKbn not found' };
    jyo.value = ${JSON.stringify(String(jyoCode))};
    op.value = '2';
    form.submit();
    return { ok:true };
  `);

// レース選択（selRaceNoNN を優先、無ければ "NR" を含むタブ）
export const selectRace = (raceNum) =>
  step(`
    var n = ${Number(raceNum)};
    var targetId = 'selRaceNo' + String(n).padStart(2,'0');
    var targetText = String(n) + 'R';
    var exact = document.getElementById(targetId);
    if(exact){ exact.click(); return { ok:true, via:'id' }; }
    var nodes = Array.prototype.slice.call(document.querySelectorAll('#raceSelection .raceSelTab, #raceSelection li'));
    for(var i=0;i<nodes.length;i++){
      var t = String(nodes[i].textContent||'').replace(/\\s+/g,'');
      if(t.indexOf(targetText) >= 0){ nodes[i].click(); return { ok:true, via:'text' }; }
    }
    return { ok:false, error:'race tab not found' };
  `);

// 既存の買い目をクリア
export const clearBets = () =>
  step(`
    try{
      if(window.BOAT && BOAT.betlist_service && typeof BOAT.betlist_service.deleteBetAll==='function'){ BOAT.betlist_service.deleteBetAll(); }
      if(window.BOAT && BOAT.betlist_controller && typeof BOAT.betlist_controller.draw==='function'){ BOAT.betlist_controller.draw(true); }
    }catch(e){}
    return { ok:true };
  `);

// 買い目追加。t: {numberOfSheets, kachishiki, selectList:[..]}
export const addBet = (t) =>
  step(`
    var p = ${JSON.stringify(t)};
    try{
      if(!(window.BOAT && BOAT.reg_service && typeof BOAT.reg_service.addBet==='function')){
        return { ok:false, error:'BOAT.reg_service.addBet unavailable' };
      }
      var res = BOAT.reg_service.addBet(p.numberOfSheets, p.kachishiki, '1', p.selectList, false) || {};
      try{
        if(BOAT.betlist_controller && typeof BOAT.betlist_controller.draw==='function'){ BOAT.betlist_controller.draw(true); }
      }catch(e){}
      return {
        ok: !res.isErrorDisp,
        isAlertDisp: !!res.isAlertDisp,
        alertCode: String(res.alertCode||''),
        isErrorDisp: !!res.isErrorDisp,
        errorCode: String(res.errorCode||''),
        errorReplaceString: String(res.errorReplaceString||'')
      };
    }catch(e){ return { ok:false, error:String(e) }; }
  `);

// 投票内容確認画面へ
export const moveToConfirm = () =>
  step(`
    if(__TB.click('#betlist .btnSubmit') || __TB.click('#betlist .betlistbtn.submit')) return { ok:true, via:'button' };
    try{
      if(window.BOAT && BOAT.betlist_controller && typeof BOAT.betlist_controller.betlistSubmit==='function'){
        BOAT.betlist_controller.betlistSubmit();
        return { ok:true, via:'js' };
      }
    }catch(e){}
    return { ok:false, error:'confirm trigger not found' };
  `);

// 確認画面で金額・投票用パスワードを入力（submit はしない＝submit OFF 相当）
export const fillConfirm = (amount, votePassword) =>
  step(`
    var amt = __TB.set('#amount', ${JSON.stringify(String(amount))})
           || __TB.set("#betconfForm input[name='betAmount']", ${JSON.stringify(String(amount))});
    var pw  = __TB.set('#pass', ${JSON.stringify(String(votePassword))})
           || __TB.set("#betconfForm input[name='betPassword']", ${JSON.stringify(String(votePassword))});
    return { ok: amt && pw, amountSet:amt, passSet:pw };
  `);

// 投票実行ボタン押下（submit ON のときだけ呼ぶ）
export const clickSubmit = () =>
  step(`
    if(__TB.click('#submitBet a') || __TB.click('#submitBet')) return { ok:true };
    return { ok:false, error:'submitBet not found' };
  `);

// 完了/確認後のポップアップを閉じる
export const dismissPopup = () =>
  step(`
    if(!__TB.vis('#popup')) return { closed:false };
    if(__TB.click('#ok') || __TB.click('#close')) return { closed:true };
    return { closed:false, error:'popup ok/close not found' };
  `);
