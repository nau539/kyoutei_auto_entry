import AsyncStorage from "@react-native-async-storage/async-storage";

const KEY = "aqua_edge_ai_config_v1";

// PC版の認証マッピング（README）と対応:
//   memberNo     = 加入者番号 (ipat.inet_id)
//   pin          = 暗証番号   (ipat.pars_no)
//   authPassword = 認証用パスワード (ipat.password)
//   votePassword = 投票用パスワード (ipat.login_id)
export const DEFAULT_CONFIG = {
  memberNo: "",
  pin: "",
  authPassword: "",
  votePassword: "",
  venues: ["", "", ""], // 最大3会場
  raceMin: 1,
  raceMax: 6,
  submitEnabled: false, // 既定は OFF（確認画面で停止）
  leadSeconds: 60, // 締切何秒前に発注するか
};

export async function loadConfig() {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    if (!raw) return { ...DEFAULT_CONFIG };
    const parsed = JSON.parse(raw);
    return { ...DEFAULT_CONFIG, ...parsed };
  } catch (e) {
    return { ...DEFAULT_CONFIG };
  }
}

export async function saveConfig(cfg) {
  const merged = { ...DEFAULT_CONFIG, ...cfg };
  await AsyncStorage.setItem(KEY, JSON.stringify(merged));
  return merged;
}
