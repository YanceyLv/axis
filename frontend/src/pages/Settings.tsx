import { Bell, KeyRound, Save } from "lucide-react";
import type { FormEvent } from "react";
import { useEffect, useState } from "react";
import type { AppSettings, UpdateSettingsPayload } from "../types";

interface SettingsProps {
  settings: AppSettings | null;
  onLoadSettings: () => Promise<void>;
  onSaveSettings: (payload: UpdateSettingsPayload) => Promise<void>;
}

export function Settings({ settings, onLoadSettings, onSaveSettings }: SettingsProps) {
  const [provider, setProvider] = useState("openai");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [pushoverEnabled, setPushoverEnabled] = useState(false);
  const [pushoverUserKey, setPushoverUserKey] = useState("");
  const [pushoverAppToken, setPushoverAppToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const llmSettings = settings?.llm ?? settings?.api;
  const pushoverSettings = settings?.pushover;

  useEffect(() => {
    void onLoadSettings();
  }, [onLoadSettings]);

  useEffect(() => {
    if (!settings) return;
    const nextLlmSettings = settings.llm ?? settings.api;
    if (nextLlmSettings) {
      setProvider(nextLlmSettings.provider || "openai");
      setBaseUrl(nextLlmSettings.baseUrl || "");
      setModel(nextLlmSettings.model || "");
    }
    setPushoverEnabled(settings.pushover.enabled);
  }, [settings]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      await onSaveSettings({
        llm: { provider, baseUrl, model, apiKey },
        pushover: { enabled: pushoverEnabled, userKey: pushoverUserKey, appToken: pushoverAppToken }
      });
      setApiKey("");
      setPushoverUserKey("");
      setPushoverAppToken("");
      setMessage("设置已保存");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page settings-page">
      <header className="page-header">
        <div>
          <h1>设置</h1>
          <p>配置大模型 API 和 Pushover 通知通道。</p>
        </div>
      </header>

      <form className="settings-grid" onSubmit={handleSubmit}>
        <section className="panel settings-panel">
          <div className="panel-title">
            <h2><KeyRound size={17} aria-hidden="true" /> API 设置</h2>
            <span className="status">{llmSettings?.apiKeySet ? "已配置" : "未配置"}</span>
          </div>
          <div className="form-grid">
            <label>
              <span>服务商</span>
              <select value={provider} onChange={(event) => setProvider(event.target.value)}>
                <option value="openai">OpenAI</option>
                <option value="deepseek">DeepSeek</option>
                <option value="qwen">通义千问</option>
                <option value="moonshot">Moonshot</option>
                <option value="custom">自定义</option>
              </select>
            </label>
            <label>
              <span>API Base URL</span>
              <input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://api.openai.com/v1" />
            </label>
            <label>
              <span>模型名称</span>
              <input value={model} onChange={(event) => setModel(event.target.value)} placeholder="gpt-4.1 / deepseek-chat" />
            </label>
            <label>
              <span>API Key {llmSettings?.apiKeySet ? "（已保存，留空不修改）" : ""}</span>
              <input value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="输入 API Key" />
            </label>
          </div>
        </section>

        <section className="panel settings-panel">
          <div className="panel-title">
            <h2><Bell size={17} aria-hidden="true" /> Pushover 设置</h2>
            <span className="status">{pushoverSettings?.enabled ? "已启用" : "未启用"}</span>
          </div>
          <label className="toggle-row">
            <input checked={pushoverEnabled} onChange={(event) => setPushoverEnabled(event.target.checked)} type="checkbox" />
            <span>启用 Pushover 推送</span>
          </label>
          <div className="form-grid">
            <label>
              <span>User Key {pushoverSettings?.userKeySet ? "（已保存，留空不修改）" : ""}</span>
              <input value={pushoverUserKey} onChange={(event) => setPushoverUserKey(event.target.value)} placeholder="输入 Pushover User Key" />
            </label>
            <label>
              <span>Application Token {pushoverSettings?.appTokenSet ? "（已保存，留空不修改）" : ""}</span>
              <input value={pushoverAppToken} onChange={(event) => setPushoverAppToken(event.target.value)} placeholder="输入 App Token" type="password" />
            </label>
          </div>
        </section>

        <footer className="settings-actions">
          {message ? <span className="status-on">{message}</span> : null}
          <button className="primary" disabled={busy} type="submit">
            <Save size={16} aria-hidden="true" />
            {busy ? "保存中..." : "保存设置"}
          </button>
        </footer>
      </form>
    </section>
  );
}
