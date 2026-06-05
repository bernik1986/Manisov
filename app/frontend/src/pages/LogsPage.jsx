import React, { useEffect, useState } from "react";
import { fetchAuditLogs, fetchUsers } from "../api";
import CrmLayout from "../components/CrmLayout";

const QUICK_DAYS = [1, 3, 7, 14, 30];

export default function LogsPage() {
  const [items, setItems] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filters, setFilters] = useState({
    user_id: "",
    start_date: "",
    end_date: "",
    last_days: "7",
  });

  async function loadLogs(nextFilters = filters) {
    setLoading(true);
    setError("");
    try {
      const params = {};
      if (nextFilters.user_id) params.user_id = Number(nextFilters.user_id);
      if (nextFilters.start_date) params.start_date = nextFilters.start_date;
      if (nextFilters.end_date) params.end_date = nextFilters.end_date;
      if (nextFilters.last_days) params.last_days = Number(nextFilters.last_days);
      const [logsPayload, usersPayload] = await Promise.all([fetchAuditLogs(params), fetchUsers()]);
      setItems(logsPayload.items || []);
      setUsers(usersPayload.items || []);
    } catch (requestError) {
      setError("Не удалось загрузить логи");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadLogs();
  }, []);

  function onSubmit(event) {
    event.preventDefault();
    loadLogs(filters);
  }

  return (
    <CrmLayout title="Audit Logs" subtitle="Admin log of user actions with filters.">
      <div className="card candidates-card">
        <form className="inline-form" onSubmit={onSubmit}>
          <label>
            Пользователь
            <select
              value={filters.user_id}
              onChange={(event) => setFilters((prev) => ({ ...prev, user_id: event.target.value }))}
            >
              <option value="">Все</option>
              {users.map((user) => (
                <option key={user.user_id} value={String(user.user_id)}>
                  {user.username} ({user.role || "-"})
                </option>
              ))}
            </select>
          </label>
          <label>
            С даты
            <input
              type="date"
              value={filters.start_date}
              onChange={(event) => setFilters((prev) => ({ ...prev, start_date: event.target.value }))}
            />
          </label>
          <label>
            По дату
            <input
              type="date"
              value={filters.end_date}
              onChange={(event) => setFilters((prev) => ({ ...prev, end_date: event.target.value }))}
            />
          </label>
          <label>
            Период (дней)
            <select
              value={filters.last_days}
              onChange={(event) => setFilters((prev) => ({ ...prev, last_days: event.target.value }))}
            >
              <option value="">Выключено</option>
              {QUICK_DAYS.map((days) => (
                <option key={days} value={String(days)}>
                  {days}
                </option>
              ))}
            </select>
          </label>
          <div className="actions-row">
            <button type="submit">Применить</button>
            <button type="button" className="secondary-btn" onClick={() => loadLogs(filters)}>
              Обновить
            </button>
          </div>
        </form>

        {error ? <p className="error">{error}</p> : null}

        {loading ? (
          <p>Загрузка...</p>
        ) : (
          <div className="table-wrap">
            <table className="candidate-table">
              <thead>
                <tr>
                  <th>Дата</th>
                  <th>Пользователь</th>
                  <th>Роль</th>
                  <th>Действие</th>
                  <th>Сущность</th>
                  <th>ID</th>
                  <th>Детали</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.log_id}>
                    <td>{item.created_at ? String(item.created_at).slice(0, 19).replace("T", " ") : "-"}</td>
                    <td>{item.username || "-"}</td>
                    <td>{item.role_name || "-"}</td>
                    <td>{item.action || "-"}</td>
                    <td>{item.entity_type || "-"}</td>
                    <td>{item.entity_id || "-"}</td>
                    <td>{item.details || "-"}</td>
                  </tr>
                ))}
                {items.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="empty-row">
                      Логов нет
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </CrmLayout>
  );
}
