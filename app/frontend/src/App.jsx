import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import MainMenuPage from "./pages/MainMenuPage";
import CandidatesPage from "./pages/CandidatesPage";
import CandidateCardPage from "./pages/CandidateCardPage";
import UserManagementPage from "./pages/UserManagementPage";
import NotificationsPage from "./pages/NotificationsPage";
import TemplatesPage from "./pages/TemplatesPage";
import CompaniesPage from "./pages/CompaniesPage";
import LogsPage from "./pages/LogsPage";
import PrivateRoute from "./components/PrivateRoute";
import { useAuth } from "./context/AuthContext";

export default function App() {
  const { isAuthenticated } = useAuth();

  return (
    <Routes>
      <Route path="/login" element={isAuthenticated ? <Navigate to="/menu" replace /> : <LoginPage />} />
      <Route
        path="/menu"
        element={
          <PrivateRoute>
            <MainMenuPage />
          </PrivateRoute>
        }
      />
      <Route
        path="/candidates"
        element={
          <PrivateRoute>
            <CandidatesPage />
          </PrivateRoute>
        }
      />
      <Route
        path="/candidates/:id"
        element={
          <PrivateRoute>
            <CandidateCardPage />
          </PrivateRoute>
        }
      />
      <Route
        path="/users"
        element={
          <PrivateRoute roles={["admin"]}>
            <UserManagementPage />
          </PrivateRoute>
        }
      />
      <Route
        path="/templates"
        element={
          <PrivateRoute>
            <TemplatesPage />
          </PrivateRoute>
        }
      />
      <Route
        path="/companies"
        element={
          <PrivateRoute>
            <CompaniesPage />
          </PrivateRoute>
        }
      />
      <Route
        path="/notifications"
        element={
          <PrivateRoute>
            <NotificationsPage />
          </PrivateRoute>
        }
      />
      <Route
        path="/logs"
        element={
          <PrivateRoute roles={["admin"]}>
            <LogsPage />
          </PrivateRoute>
        }
      />
      <Route path="*" element={<Navigate to={isAuthenticated ? "/menu" : "/login"} replace />} />
    </Routes>
  );
}
