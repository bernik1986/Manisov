import React from "react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [form, setForm] = useState({ username: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(event) {
    event.preventDefault();

    if (!form.username || !form.password) {
      setError("Введите логин и пароль");
      return;
    }

    setError("");
    setLoading(true);
    try {
      await login(form.username, form.password);
      navigate("/menu", { replace: true });
    } catch (requestError) {
      setError("Неверный логин или пароль");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <form className="card auth-form" onSubmit={onSubmit} data-testid="login-form">
        <h1>Авторизация</h1>
        <p className="muted">Войдите, чтобы открыть главное меню</p>

        <label htmlFor="username">Логин</label>
        <input
          id="username"
          type="text"
          placeholder="admin"
          value={form.username}
          onChange={(event) => setForm((prev) => ({ ...prev, username: event.target.value }))}
        />

        <label htmlFor="password">Пароль</label>
        <input
          id="password"
          type="password"
          placeholder="********"
          value={form.password}
          onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
        />

        {error ? <p className="error">{error}</p> : null}

        <button type="submit" disabled={loading}>
          {loading ? "Вход..." : "Войти"}
        </button>
      </form>
    </main>
  );
}
