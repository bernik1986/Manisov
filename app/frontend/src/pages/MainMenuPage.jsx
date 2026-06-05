import React from "react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchDashboardSummary, fetchNotifications } from "../api";
import CrmLayout from "../components/CrmLayout";

export default function MainMenuPage() {
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState([]);
  const [summary, setSummary] = useState({
    candidates_count: 0,
    most_active_user: null,
  });

  useEffect(() => {
    let active = true;
    async function loadNotificationPreview() {
      try {
        const [notificationPayload, summaryPayload] = await Promise.all([
          fetchNotifications(false, 5),
          fetchDashboardSummary(),
        ]);
        if (!active) return;
        const items = Array.isArray(notificationPayload?.items) ? notificationPayload.items : [];
        setNotifications(items.slice(0, 5));
        setSummary({
          candidates_count: Number(summaryPayload?.candidates_count || 0),
          most_active_user: summaryPayload?.most_active_user || null,
        });
      } catch (error) {
        if (!active) return;
        setNotifications([]);
        setSummary({
          candidates_count: 0,
          most_active_user: null,
        });
      }
    }
    loadNotificationPreview();
    return () => {
      active = false;
    };
  }, []);

  return (
    <CrmLayout title="Dashboard" subtitle="Welcome back! Here's your seamen data overview.">
      <div className="crm-kpi-grid">
        <article className="crm-kpi-card">
          <h3>Total Alerts</h3>
          <strong>{notifications.length}</strong>
          <span>Pending notifications</span>
        </article>
        <article className="crm-kpi-card">
          <h3>Candidates</h3>
          <strong>{summary.candidates_count}</strong>
          <span>Seamen in database</span>
        </article>
        <article className="crm-kpi-card">
          <h3>Most Active User</h3>
          <strong>{summary.most_active_user?.username || "—"}</strong>
          <span>
            {summary.most_active_user
              ? `${summary.most_active_user.actions_count} actions in audit log`
              : "No activity yet"}
          </span>
        </article>
      </div>

      <ul className="menu-list">
        <li className="menu-item">
          <h3>Seamens Data</h3>
          <p>Просмотр таблицы кандидатов и переход к карточке</p>
          <button type="button" onClick={() => navigate("/candidates")}>
            Open Data
          </button>
        </li>
        <li className="menu-item">
          <h3>Notifications</h3>
          <p>Истекающие документы/сертификаты, отсутствующие сканы и другие события</p>
          {notifications.length > 0 ? (
            <ul className="notification-preview-list">
              {notifications.map((item) => (
                <li key={item.id}>{item.message}</li>
              ))}
            </ul>
          ) : (
            <p className="muted">Новых уведомлений нет</p>
          )}
          <button type="button" onClick={() => navigate("/notifications")}>
            Open Notifications
          </button>
        </li>
      </ul>
    </CrmLayout>
  );
}
