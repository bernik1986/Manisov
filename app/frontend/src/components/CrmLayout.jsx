import React from "react";
import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const navItems = [
  { to: "/menu", label: "Dashboard" },
  { to: "/candidates", label: "Seamens Data" },
  { to: "/templates", label: "Templates" },
  { to: "/companies", label: "Company" },
  { to: "/notifications", label: "Notifications" },
  { to: "/logs", label: "Logs", adminOnly: true },
  { to: "/users", label: "Users", adminOnly: true },
];

export default function CrmLayout({
  title,
  subtitle,
  actions,
  children,
  collapsibleSidebar = false,
  defaultSidebarHidden = false,
}) {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const isAdmin = user?.role === "admin";
  const [sidebarHidden, setSidebarHidden] = useState(defaultSidebarHidden);

  const visibleNav = navItems.filter((item) => !item.adminOnly || isAdmin);

  return (
    <main className="crm-layout-page" data-testid="crm-layout">
      <div className={`crm-shell ${collapsibleSidebar && sidebarHidden ? "crm-shell--sidebar-hidden" : ""}`}>
        <aside className="crm-sidebar" data-testid="crm-sidebar">
          <div className="crm-brand">
            <h2>CrewDeck CRM</h2>
            <p>Maritime Management</p>
          </div>

          <nav className="crm-nav" data-testid="crm-nav">
            {visibleNav.map((item) => {
              const testId =
                item.to === "/users"
                  ? "nav-users"
                  : item.to === "/logs"
                    ? "nav-logs"
                    : item.to === "/menu"
                      ? "nav-menu"
                      : item.to === "/candidates"
                        ? "nav-seamens"
                        : item.to === "/templates"
                          ? "nav-templates"
                          : item.to === "/companies"
                            ? "nav-companies"
                            : item.to === "/notifications"
                            ? "nav-notifications"
                            : undefined;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  data-testid={testId}
                  className={({ isActive }) => `crm-nav-link${isActive ? " active" : ""}`}
                >
                  {item.label}
                </NavLink>
              );
            })}
          </nav>

          <div className="crm-sidebar-footer">
            <div className="crm-user-meta">
              <strong>{user?.full_name || user?.username || "User"}</strong>
              <span>{user?.role || "-"}</span>
            </div>
            <button type="button" className="secondary-btn" onClick={logout}>
              Выйти
            </button>
          </div>
        </aside>

        <section className="crm-content">
          <header className="crm-topbar">
            <div>
              <h1>{title}</h1>
              {subtitle ? <p>{subtitle}</p> : null}
            </div>
            <div className="crm-topbar-actions">
              {collapsibleSidebar ? (
                <button type="button" className="secondary-btn" onClick={() => setSidebarHidden((prev) => !prev)}>
                  {sidebarHidden ? "→ Меню" : "← Скрыть"}
                </button>
              ) : null}
              {actions}
              <button type="button" className="secondary-btn" onClick={() => navigate("/menu")}>
                В меню
              </button>
            </div>
          </header>

          <div className="crm-content-body">{children}</div>
        </section>
      </div>
    </main>
  );
}
