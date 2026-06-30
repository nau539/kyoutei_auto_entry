// WebView との非同期 JS 実行ブリッジ。
// evalAsync(jsBody) で「値を return する JS」を注入し、postMessage 経由で結果を待つ。

export function makeBridge(webviewRef) {
  const pending = new Map();
  let counter = 0;

  function wrap(id, body) {
    return (
      "(function(){var __id=" +
      JSON.stringify(id) +
      ";function __post(ok,data,err){try{window.ReactNativeWebView.postMessage(JSON.stringify({__bridge:true,id:__id,ok:ok,data:data,error:err==null?null:String(err)}));}catch(e){}}" +
      "try{var __r=(function(){" +
      body +
      "})();Promise.resolve(__r).then(function(d){__post(true,d,null);}).catch(function(e){__post(false,null,e);});}catch(e){__post(false,null,e);}true;})();"
    );
  }

  function evalAsync(body, timeoutMs = 8000) {
    const id = "b" + ++counter;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        if (pending.has(id)) {
          pending.delete(id);
          reject(new Error("evalAsync timeout"));
        }
      }, timeoutMs);
      pending.set(id, { resolve, reject, timer });
      const wv = webviewRef.current;
      if (!wv) {
        clearTimeout(timer);
        pending.delete(id);
        reject(new Error("WebView not ready"));
        return;
      }
      wv.injectJavaScript(wrap(id, body));
    });
  }

  // RunScreen の onMessage から呼ぶ。ブリッジ宛なら true を返す。
  function handleMessage(raw) {
    let msg;
    try {
      msg = JSON.parse(raw);
    } catch (e) {
      return false;
    }
    if (!msg || !msg.__bridge || !pending.has(msg.id)) return false;
    const { resolve, reject, timer } = pending.get(msg.id);
    clearTimeout(timer);
    pending.delete(msg.id);
    if (msg.ok) resolve(msg.data);
    else reject(new Error(msg.error || "eval failed"));
    return true;
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // builder() が返す述語 JS を data===true になるまでポーリング。
  async function waitFor(builder, { timeoutMs = 15000, pollMs = 150 } = {}) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      try {
        const ok = await evalAsync(builder, 4000);
        if (ok === true) return true;
      } catch (e) {
        // 注入失敗（遷移中など）は再試行
      }
      await sleep(pollMs);
    }
    throw new Error("waitFor timeout");
  }

  return { evalAsync, handleMessage, waitFor, sleep, pendingCount: () => pending.size };
}
