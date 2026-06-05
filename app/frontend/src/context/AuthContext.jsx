import React, { createContext, useContext, useMemo, useState } from "react";
import { login as loginRequest } from "../api";

const AuthContext = createContext(null);

function parseJwtPayload(token) {
  try {
    const parts = String(token || "").split(".");
    if (parts.length < 2) return null;
    const normalized = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    return JSON.parse(atob(padded));
  } catch {
    return null;
  }
}

function isTokenExpired(token) {
  const payload = parseJwtPayload(token);
  const exp = Number(payload?.exp);
  if (!Number.isFinite(exp)) return true;
  return exp * 1000 <= Date.now();
}

function loadValidToken() {
  const token = localStorage.getItem("authToken");
  if (!token || isTokenExpired(token)) {
    localStorage.removeItem("authToken");
    localStorage.removeItem("authUser");
    return null;
  }
  return token;
}

export function AuthProvider({ children }) {
  const [token, setToken] = useState(loadValidToken);
  const [user, setUser] = useState(() => {
    if (!localStorage.getItem("authToken")) return null;
    const raw = localStorage.getItem("authUser");
    return raw ? JSON.parse(raw) : null;
  });

  const isAuthenticated = Boolean(token);

  async function login(username, password) {
    const payload = await loginRequest({ username, password });
    const nextToken = payload.access_token;
    const nextUser = payload.user;
    localStorage.setItem("authToken", nextToken);
    localStorage.setItem("authUser", JSON.stringify(nextUser));
    setToken(nextToken);
    setUser(nextUser);
    return nextUser;
  }

  function logout() {
    localStorage.removeItem("authToken");
    localStorage.removeItem("authUser");
    setToken(null);
    setUser(null);
  }

  const value = useMemo(
    () => ({
      token,
      user,
      isAuthenticated,
      login,
      logout,
    }),
    [token, user, isAuthenticated]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
