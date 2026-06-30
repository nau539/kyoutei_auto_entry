import AsyncStorage from "@react-native-async-storage/async-storage";

// 実行ログと購入結果の永続化（仕様8）。
const LOG_KEY = "aqua_edge_logs_v1";
const RESULT_KEY = "aqua_edge_results_v1";
const LOG_CAP = 1000;

async function readArr(key) {
  try {
    const raw = await AsyncStorage.getItem(key);
    return raw ? JSON.parse(raw) : [];
  } catch (e) {
    return [];
  }
}

export async function appendLog(message, isoTime) {
  const arr = await readArr(LOG_KEY);
  arr.push({ t: isoTime || null, m: String(message) });
  const trimmed = arr.slice(-LOG_CAP);
  await AsyncStorage.setItem(LOG_KEY, JSON.stringify(trimmed));
  return trimmed.length;
}

export async function loadLogs() {
  return readArr(LOG_KEY);
}

// record: { venueName, raceNum, boats, stakeYen, status, top3, hit, isoTime }
export async function recordResult(record) {
  const arr = await readArr(RESULT_KEY);
  arr.push(record);
  await AsyncStorage.setItem(RESULT_KEY, JSON.stringify(arr));
  return arr.length;
}

export async function loadResults() {
  return readArr(RESULT_KEY);
}

export async function clearAll() {
  await AsyncStorage.multiRemove([LOG_KEY, RESULT_KEY]);
}
