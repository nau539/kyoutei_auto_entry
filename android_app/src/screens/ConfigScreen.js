import React, { useState } from "react";
import { ScrollView, View, Text, TextInput, Switch, Pressable, StyleSheet } from "react-native";
import { VENUE_NAMES } from "../telboat/constants";

function Field({ label, value, onChangeText, secure, keyboardType, placeholder }) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        style={styles.input}
        value={String(value ?? "")}
        onChangeText={onChangeText}
        secureTextEntry={secure}
        keyboardType={keyboardType}
        placeholder={placeholder}
        autoCapitalize="none"
        autoCorrect={false}
      />
    </View>
  );
}

export default function ConfigScreen({ config, setConfig, onSave }) {
  const [saved, setSaved] = useState(false);
  const c = config;
  const up = (patch) => {
    setConfig({ ...c, ...patch });
    setSaved(false);
  };
  const upVenue = (i, v) => {
    const venues = [...(c.venues || ["", "", ""])];
    venues[i] = v;
    up({ venues });
  };

  return (
    <ScrollView style={styles.root} contentContainerStyle={{ paddingBottom: 48 }}>
      <Text style={styles.h}>テレボート認証情報</Text>
      <Field label="加入者番号" value={c.memberNo} onChangeText={(t) => up({ memberNo: t })} keyboardType="number-pad" />
      <Field label="暗証番号 (PIN)" value={c.pin} onChangeText={(t) => up({ pin: t })} secure keyboardType="number-pad" />
      <Field label="認証用パスワード" value={c.authPassword} onChangeText={(t) => up({ authPassword: t })} secure />
      <Field label="投票用パスワード" value={c.votePassword} onChangeText={(t) => up({ votePassword: t })} secure />

      <Text style={styles.h}>対象会場（最大3）</Text>
      <Text style={styles.hint}>有効な会場名: {VENUE_NAMES.join(" / ")}</Text>
      {[0, 1, 2].map((i) => (
        <Field key={i} label={`会場${i + 1}`} value={(c.venues || [])[i]} onChangeText={(t) => upVenue(i, t)} placeholder="例: 大村" />
      ))}

      <Text style={styles.h}>購入対象レース</Text>
      <View style={styles.row}>
        <Field label="最小R" value={c.raceMin} onChangeText={(t) => up({ raceMin: parseInt(t || "1", 10) || 1 })} keyboardType="number-pad" />
        <View style={{ width: 16 }} />
        <Field label="最大R" value={c.raceMax} onChangeText={(t) => up({ raceMax: parseInt(t || "6", 10) || 6 })} keyboardType="number-pad" />
      </View>

      <Text style={styles.h}>発注設定</Text>
      <Field label="締切何秒前に発注するか" value={c.leadSeconds} onChangeText={(t) => up({ leadSeconds: parseInt(t || "60", 10) || 60 })} keyboardType="number-pad" />
      <View style={styles.switchRow}>
        <View style={{ flex: 1 }}>
          <Text style={styles.label}>実投票を有効化 (submit)</Text>
          <Text style={styles.hint}>OFF=確認画面で停止（検証用）。本番のみ ON</Text>
        </View>
        <Switch value={!!c.submitEnabled} onValueChange={(v) => up({ submitEnabled: v })} />
      </View>

      <Pressable
        style={[styles.btn, c.submitEnabled ? styles.btnDanger : styles.btnPrimary]}
        onPress={async () => {
          await onSave();
          setSaved(true);
        }}
      >
        <Text style={styles.btnText}>{saved ? "保存しました ✓" : "設定を保存"}</Text>
      </Pressable>
      {c.submitEnabled && (
        <Text style={styles.warn}>⚠ 実投票が有効です。実口座から購入されます。</Text>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, padding: 16, backgroundColor: "#0e2433" },
  h: { color: "#4FD8FF", fontSize: 16, fontWeight: "700", marginTop: 20, marginBottom: 8 },
  hint: { color: "#9fc4d6", fontSize: 12, marginBottom: 8 },
  field: { marginBottom: 12, flex: 1 },
  label: { color: "#cfeefb", fontSize: 13, marginBottom: 4 },
  input: { backgroundColor: "#13354a", color: "#fff", borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10, borderWidth: 1, borderColor: "#1d4d68" },
  row: { flexDirection: "row" },
  switchRow: { flexDirection: "row", alignItems: "center", marginVertical: 10 },
  btn: { borderRadius: 10, paddingVertical: 14, alignItems: "center", marginTop: 24 },
  btnPrimary: { backgroundColor: "#008BC7" },
  btnDanger: { backgroundColor: "#c7452f" },
  btnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  warn: { color: "#ffb4a3", marginTop: 12, fontSize: 13, textAlign: "center" },
});
