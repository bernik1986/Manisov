import React, { createContext, useContext, useMemo, useSyncExternalStore } from "react";
import { getAuthSnapshot, login as loginRequest, logout, subscribeAuth } from "../api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const { token, user, revision } = useSyncExternalStore(subscribeAuth, getAuthSnapshot);
  const isAuthenticated = Boolean(token);

  async function login(username, password) {
    const payload = await loginRequest({ username, password });
    return payload.user;
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

  return <AuthContext.Provider value={value}>
    <React.Fragment key={token ? revision : "signed-out"}>{children}</React.Fragment>
  </AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
