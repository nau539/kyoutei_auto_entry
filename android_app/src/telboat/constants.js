// テレボート（BOAT RACE 中央投票）定数。
// PC版 ipat_playwright.py の KYOUTEI_VENUE_CODE_MAP / KYOUTEI_KACHISHIKI_MAP を移植。

export const TELBOAT_LOGIN_URL = "https://ib.mbrace.or.jp/";

export const VENUE_CODE_MAP = {
  桐生: "01",
  戸田: "02",
  江戸川: "03",
  平和島: "04",
  多摩川: "05",
  浜名湖: "06",
  蒲郡: "07",
  常滑: "08",
  津: "09",
  三国: "10",
  びわこ: "11",
  住之江: "12",
  尼崎: "13",
  鳴門: "14",
  丸亀: "15",
  児島: "16",
  宮島: "17",
  徳山: "18",
  下関: "19",
  若松: "20",
  芦屋: "21",
  福岡: "22",
  唐津: "23",
  大村: "24",
};

// 表記ゆれの吸収（PC版 _kyoutei_venue_code のエイリアス）
const VENUE_ALIASES = {
  琵琶湖: "びわこ",
};

export function venueCode(name) {
  const text = String(name || "").trim();
  const normalized = VENUE_ALIASES[text] || text;
  return VENUE_CODE_MAP[normalized] || "";
}

// 券種 -> kachishiki コード（公式 JS 定義に一致）
export const KACHISHIKI_MAP = {
  単勝: "1",
  複勝: "2",
  "2連単": "3",
  "2連複": "4",
  拡連複: "5",
  "3連単": "6",
  "3連複": "7",
};

const MARKET_ALIASES = {
  "２連単": "2連単",
  二連単: "2連単",
  "２連複": "2連複",
  二連複: "2連複",
  "３連単": "3連単",
  三連単: "3連単",
  "３連複": "3連複",
  三連複: "3連複",
};

export function kachishikiCode(market) {
  const text = String(market || "").trim();
  const normalized = MARKET_ALIASES[text] || text;
  return KACHISHIKI_MAP[normalized] || "";
}

export const VENUE_NAMES = Object.keys(VENUE_CODE_MAP);
