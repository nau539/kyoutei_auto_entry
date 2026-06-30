import React, { useRef, useState, useMemo } from "react";
import { View, Text, TextInput, Pressable, ScrollView, StyleSheet } from "react-native";
import { WebView } from "react-native-webview";
import { TELBOAT_LOGIN_URL } from "../telboat/constants";
import { activateKeepAwakeAsync, deactivateKeepAwake } from "expo-keep-awake";
import { makeBridge } from "../telboat/bridge";
import { runRaceEntry } from "../telboat/spaDriver";
import { LOGIN_POPUP_FIX } from "../telboat/inject";
import { AutomationRunner } from "../engine/automation";
import { appendLog as persistLog, recordResult } from "../store/results";

export default function RunScreen({ config }) {
  const webviewRef = useRef(null);
  const bridge = useMemo(() => makeBridge(webviewRef), []);
  const [log, setLog] = useState([]);
  const [busy, setBusy] = useState(false);
  const [auto, setAuto] = useState(false);
  const runnerRef = useRef(null);

  const [venue, setVenue] = useState((config.venues || [])[0] || "");
  const [race, setRace] = useState("1");
  const [boats, setBoats] = useState("1-2-3");
  const [stake, setStake] = useState("600");

  const appendLog = (s) => setLog((prev) => [...prev.slice(-200), `${ts()} ${s}`]);

  async function runTest() {
    if (busy) return;
    setBusy(true);
    appendLog(`=== 開始: ${venue} ${race}R 3連単ボックス ${boats} 資金配分${stake}円 ===`);
    try {
      const entry = {
        venueName: venue.trim(),
        raceNum: parseInt(race, 10),
        boats: boats.split(/[-,> /]/).map((x) => parseInt(x.trim(), 10)).filter((n) => n > 0),
        stakeYen: parseInt(stake, 10),
      };
      const res = await runRaceEntry(bridge, config, entry, appendLog);
      appendLog(`=== 完了: ${JSON.stringify(res)} ===`);
    } catch (e) {
      appendLog(`✗ エラー: ${e.message || String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  function reload() {
    setLog([]);
    webviewRef.current && webviewRef.current.reload();
    appendLog("WebView を再読み込みしました");
  }

  async function startAuto() {
    if (auto) return;
    setAuto(true);
    const iso = () => new Date().toISOString();
    const logBoth = (s) => {
      appendLog(s);
      persistLog(s, iso()).catch(() => {});
    };
    try {
      await activateKeepAwakeAsync().catch(() => {});
      const runner = new AutomationRunner(bridge, config, {
        log: logBoth,
        onRecord: (rec) => recordResult({ ...rec, isoTime: rec.isoTime || iso() }).catch(() => {}),
      });
      runnerRef.current = runner;
      logBoth("▶ 自動運転を開始します");
      await runner.start();
    } catch (e) {
      appendLog(`✗ 自動運転エラー: ${e.message || String(e)}`);
    } finally {
      deactivateKeepAwake();
      setAuto(false);
      runnerRef.current = null;
    }
  }

  function stopAuto() {
    runnerRef.current && runnerRef.current.stop();
  }

  return (
    <View style={styles.root}>
      <View style={styles.webWrap}>
        <WebView
          ref={webviewRef}
          source={{ uri: TELBOAT_LOGIN_URL }}
          javaScriptEnabled
          domStorageEnabled
          // テレボートのログイン別窓(pctablet)を同一ビューへ誘導する修正を
          // ページ読込前に注入（検証済み）
          injectedJavaScriptBeforeContentLoaded={LOGIN_POPUP_FIX}
          // 別窓は LOGIN_POPUP_FIX 側で握りつぶすため false 固定
          setSupportMultipleWindows={false}
          onMessage={(e) => {
            bridge.handleMessage(e.nativeEvent.data);
          }}
          onError={(e) => appendLog(`WebViewエラー: ${e.nativeEvent.description}`)}
        />
      </View>

      <ScrollView style={styles.panel} contentContainerStyle={{ padding: 12 }}>
        <Text style={styles.h}>テスト発注（{config.submitEnabled ? "⚠実投票ON" : "確認画面まで"}）</Text>
        <Row>
          <Mini label="会場" value={venue} onChangeText={setVenue} />
          <Mini label="R" value={race} onChangeText={setRace} kb="number-pad" w={56} />
        </Row>
        <Row>
          <Mini label="3艇(ボックス)" value={boats} onChangeText={setBoats} />
          <Mini label="資金配分(円)" value={stake} onChangeText={setStake} kb="number-pad" w={110} />
        </Row>
        <View style={styles.btnRow}>
          <Pressable style={[styles.btn, styles.run, busy && styles.dim]} disabled={busy} onPress={runTest}>
            <Text style={styles.btnText}>{busy ? "実行中…" : "実行"}</Text>
          </Pressable>
          <Pressable style={[styles.btn, styles.sub]} onPress={reload}>
            <Text style={styles.btnText}>WebView再読込</Text>
          </Pressable>
        </View>

        <Text style={styles.h}>自動運転（設定タブの会場・R範囲・マーチンで全自動）</Text>
        <View style={styles.btnRow}>
          {!auto ? (
            <Pressable style={[styles.btn, config.submitEnabled ? styles.danger : styles.run]} onPress={startAuto}>
              <Text style={styles.btnText}>{config.submitEnabled ? "⚠自動運転 開始(実投票)" : "自動運転 開始(確認まで)"}</Text>
            </Pressable>
          ) : (
            <Pressable style={[styles.btn, styles.stop]} onPress={stopAuto}>
              <Text style={styles.btnText}>停止</Text>
            </Pressable>
          )}
        </View>

        <Text style={styles.h}>ログ</Text>
        <View style={styles.logBox}>
          {log.length === 0 ? (
            <Text style={styles.logEmpty}>まだログはありません</Text>
          ) : (
            log.map((line, i) => (
              <Text key={i} style={styles.logLine}>
                {line}
              </Text>
            ))
          )}
        </View>
      </ScrollView>
    </View>
  );
}

const Row = ({ children }) => <View style={styles.row}>{children}</View>;
const Mini = ({ label, value, onChangeText, kb, w }) => (
  <View style={[styles.mini, w ? { width: w } : { flex: 1 }]}>
    <Text style={styles.miniLabel}>{label}</Text>
    <TextInput style={styles.miniInput} value={String(value)} onChangeText={onChangeText} keyboardType={kb} autoCapitalize="none" autoCorrect={false} />
  </View>
);

function ts() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#0e2433" },
  webWrap: { height: "42%", borderBottomWidth: 2, borderBottomColor: "#1d4d68" },
  panel: { flex: 1 },
  h: { color: "#4FD8FF", fontSize: 14, fontWeight: "700", marginTop: 10, marginBottom: 6 },
  row: { flexDirection: "row", gap: 8, marginBottom: 8 },
  mini: {},
  miniLabel: { color: "#cfeefb", fontSize: 11, marginBottom: 2 },
  miniInput: { backgroundColor: "#13354a", color: "#fff", borderRadius: 6, paddingHorizontal: 8, paddingVertical: 6, borderWidth: 1, borderColor: "#1d4d68" },
  btnRow: { flexDirection: "row", gap: 10, marginTop: 4 },
  btn: { flex: 1, borderRadius: 8, paddingVertical: 12, alignItems: "center" },
  run: { backgroundColor: "#008BC7" },
  sub: { backgroundColor: "#274b61" },
  danger: { backgroundColor: "#c7452f" },
  stop: { backgroundColor: "#b5392a" },
  dim: { opacity: 0.5 },
  btnText: { color: "#fff", fontWeight: "700" },
  logBox: { backgroundColor: "#08161f", borderRadius: 8, padding: 10, minHeight: 120 },
  logEmpty: { color: "#5b7c8d" },
  logLine: { color: "#bfe6f5", fontSize: 12, fontFamily: "monospace", marginBottom: 2 },
});
