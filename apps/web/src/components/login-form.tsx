"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import type { Locale } from "@/lib/types";
export function LoginForm({ lang, demo }: { lang: Locale; demo: boolean }) {
  const vi = lang === "vi";
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function login(email: string, password: string) {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await response.json();
      if (!response.ok)
        throw new Error(data.error?.message || "Sign-in failed.");
      router.push("/");
      router.refresh();
    } catch (error) {
      setError(error instanceof Error ? error.message : "Unable to sign in.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-form">
      <h2>{vi ? "Chào bạn trở lại." : "Welcome back."}</h2>
      <p className="muted">
        {vi
          ? "Đăng nhập vào bản nghiên cứu riêng tư."
          : "Sign in to the private research pilot."}
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          void login(String(form.get("email")), String(form.get("password")));
        }}
      >
        <label className="form-field">
          <span>Email</span>
          <input
            name="email"
            type="email"
            autoComplete="username"
            required
            maxLength={254}
          />
        </label>
        <label className="form-field">
          <span>{vi ? "Mật khẩu" : "Password"}</span>
          <input
            name="password"
            type="password"
            autoComplete="current-password"
            required
            maxLength={200}
          />
        </label>
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
        <button disabled={busy} type="submit" className="button primary">
          {busy
            ? vi
              ? "Đang đăng nhập…"
              : "Signing in…"
            : vi
              ? "Đăng nhập"
              : "Sign in"}
        </button>
      </form>
      {demo && (
        <div className="demo-login">
          <p>
            {vi
              ? "Thử ngay trên localhost với dữ liệu hư cấu. Không cần tài khoản thật."
              : "Explore on localhost with fictional data. No real account needed."}
          </p>
          <div>
            <button
              className="button outline"
              disabled={busy}
              type="button"
              onClick={() =>
                void login("tester@bouquetbrowse.local", "demo-tester")
              }
            >
              {vi ? "Khám phá bản thử" : "Explore demo"}
            </button>
            <button
              className="button secondary"
              disabled={busy}
              type="button"
              onClick={() =>
                void login("admin@bouquetbrowse.local", "demo-admin")
              }
            >
              {vi ? "Quản lý bản thử" : "Catalog studio demo"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
