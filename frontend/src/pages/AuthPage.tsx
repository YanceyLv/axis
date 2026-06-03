import { BarChart3 } from "lucide-react";
import type { FormEvent } from "react";
import { useState } from "react";
import type { AuthResponse } from "../types";

interface AuthPageProps {
  onLogin: (email: string, password: string) => Promise<AuthResponse>;
  onRegister: (email: string, password: string) => Promise<AuthResponse>;
  onAuthenticated: (auth: AuthResponse) => void;
}

type AuthMode = "login" | "register";

export function AuthPage({ onLogin, onRegister, onAuthenticated }: AuthPageProps) {
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const isRegister = mode === "register";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const auth = isRegister ? await onRegister(email, password) : await onLogin(email, password);
      onAuthenticated(auth);
    } catch (err) {
      setError(err instanceof Error ? err.message : isRegister ? "注册失败" : "登录失败");
    } finally {
      setBusy(false);
    }
  }

  function switchMode(nextMode: AuthMode) {
    setMode(nextMode);
    setError(null);
  }

  return (
    <main className="auth-screen">
      <section className="auth-panel">
        <div className="auth-brand">
          <div className="brand-mark">
            <BarChart3 size={22} aria-hidden="true" />
          </div>
          <span>TrendAI</span>
        </div>

        <div className="auth-heading">
          <h1>{isRegister ? "创建账号" : "登录账号"}</h1>
          <p>{isRegister ? "使用邮箱注册后进入信号发现系统。" : "登录后继续管理策略和观察信号。"}</p>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label>
            <span>邮箱</span>
            <input
              autoComplete="email"
              required
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="trader@example.com"
            />
          </label>
          <label>
            <span>密码</span>
            <input
              autoComplete={isRegister ? "new-password" : "current-password"}
              minLength={8}
              required
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="至少 8 位"
            />
          </label>

          {error ? <p className="inline-error">{error}</p> : null}

          <button className="primary auth-submit" disabled={busy} type="submit">
            {busy ? "处理中..." : isRegister ? "注册并进入" : "登录"}
          </button>
        </form>

        <footer className="auth-switch">
          {isRegister ? "已有账号？" : "还没有账号？"}
          <button type="button" onClick={() => switchMode(isRegister ? "login" : "register")}>
            {isRegister ? "去登录" : "去注册"}
          </button>
        </footer>
      </section>
    </main>
  );
}
