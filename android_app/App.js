import React, { useEffect, useState } from "react";
import { SafeAreaView, View, Text, Pressable, StyleSheet, StatusBar, ActivityIndicator } from "react-native";
import { loadConfig, saveConfig } from "./src/storage";
import ConfigScreen from "./src/screens/ConfigScreen";
import RunScreen from "./src/screens/RunScreen";

export default function App() {
  const [tab, setTab] = useState("config");
  const [config, setConfig] = useState(null);

  useEffect(() => {
    loadConfig().then(setConfig);
  }, []);

  if (!config) {
    return (
      <SafeAreaView style={styles.loading}>
        <ActivityIndicator color="#4FD8FF" />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.root}>
      <StatusBar barStyle="light-content" />
      <View style={styles.header}>
        <Text style={styles.title}>AQUA EDGE AI</Text>
        <View style={styles.tabs}>
          <Tab label="設定" active={tab === "config"} onPress={() => setTab("config")} />
          <Tab label="実行" active={tab === "run"} onPress={() => setTab("run")} />
        </View>
      </View>

      <View style={{ flex: 1 }}>
        {tab === "config" ? (
          <ConfigScreen config={config} setConfig={setConfig} onSave={() => saveConfig(config).then(setConfig)} />
        ) : (
          <RunScreen config={config} />
        )}
      </View>
    </SafeAreaView>
  );
}

const Tab = ({ label, active, onPress }) => (
  <Pressable style={[styles.tab, active && styles.tabActive]} onPress={onPress}>
    <Text style={[styles.tabText, active && styles.tabTextActive]}>{label}</Text>
  </Pressable>
);

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#0e2433" },
  loading: { flex: 1, backgroundColor: "#0e2433", justifyContent: "center", alignItems: "center" },
  header: { paddingHorizontal: 16, paddingTop: 8, paddingBottom: 4, backgroundColor: "#0a1c28" },
  title: { color: "#4FD8FF", fontSize: 18, fontWeight: "800", letterSpacing: 1 },
  tabs: { flexDirection: "row", marginTop: 8, gap: 8 },
  tab: { paddingVertical: 8, paddingHorizontal: 18, borderRadius: 8, backgroundColor: "#13354a" },
  tabActive: { backgroundColor: "#008BC7" },
  tabText: { color: "#9fc4d6", fontWeight: "600" },
  tabTextActive: { color: "#fff" },
});
