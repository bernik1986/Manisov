import React, { useEffect, useState } from "react";
import { deleteUser, fetchUsers, registerUser, updateUserActive, updateUserPassword, updateUserRole } from "../api";
import CrmLayout from "../components/CrmLayout";
import { useAuth } from "../context/AuthContext";

const roleOptions = ["admin", "recruiter", "viewer"];

export default function UserManagementPage() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [passwordInputs, setPasswordInputs] = useState({});
  const [form, setForm] = useState({
    username: "",
    password: "",
    full_name: "",
    role: "viewer",
  });

  async function loadUsers() {
    setLoading(true);
    setError("");
    try {
      const response = await fetchUsers();
      setUsers(response.items || []);
    } catch (requestError) {
      setError("Не удалось загрузить пользователей");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadUsers();
  }, []);

  async function onRegister(event) {
    event.preventDefault();
    setError("");
    try {
      await registerUser(form);
      setForm({ username: "", password: "", full_name: "", role: "viewer" });
      await loadUsers();
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Не удалось зарегистрировать пользователя");
    }
  }

  async function onRoleChange(userId, role) {
    setError("");
    try {
      await updateUserRole(userId, role);
      await loadUsers();
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Не удалось обновить роль");
    }
  }

  async function onSetPassword(userId) {
    const password = (passwordInputs[userId] || "").trim();
    if (password.length < 6) {
      setError("Пароль: не менее 6 символов");
      return;
    }
    setError("");
    try {
      await updateUserPassword(userId, password);
      setPasswordInputs((prev) => ({ ...prev, [userId]: "" }));
      await loadUsers();
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Не удалось сменить пароль");
    }
  }

  async function onActiveChange(userId, isActive) {
    setError("");
    try {
      await updateUserActive(userId, isActive);
      await loadUsers();
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Не удалось обновить статус");
    }
  }

  async function onDeleteUser(userId) {
    if (!window.confirm("Удалить этого пользователя? Действие нельзя отменить.")) {
      return;
    }
    setError("");
    try {
      await deleteUser(userId);
      await loadUsers();
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Не удалось удалить пользователя");
    }
  }

  return (
    <CrmLayout title="User Management" subtitle="Manage user accounts, roles and permissions.">
      <div className="card candidates-card">
        <form className="upload-form" data-testid="user-register-form" onSubmit={onRegister}>
          <h3>Регистрация пользователя</h3>
          <input
            type="text"
            placeholder="Логин"
            value={form.username}
            onChange={(event) => setForm((prev) => ({ ...prev, username: event.target.value }))}
            required
          />
          <input
            type="password"
            placeholder="Пароль"
            value={form.password}
            onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
            required
          />
          <input
            type="text"
            placeholder="Полное имя"
            value={form.full_name}
            onChange={(event) => setForm((prev) => ({ ...prev, full_name: event.target.value }))}
          />
          <select
            value={form.role}
            onChange={(event) => setForm((prev) => ({ ...prev, role: event.target.value }))}
          >
            {roleOptions.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </select>
          <button type="submit">Создать пользователя</button>
        </form>

        {error ? <p className="error">{error}</p> : null}
        {loading ? (
          <p>Загрузка...</p>
        ) : (
          <table className="candidate-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Логин</th>
                <th>Имя</th>
                <th>Роль</th>
                <th>Статус</th>
                <th>Новый пароль</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {users.map((item) => (
                <tr key={item.user_id}>
                  <td>{item.user_id}</td>
                  <td>{item.username}</td>
                  <td>{item.full_name || "-"}</td>
                  <td>
                    {(() => {
                      const isSelfRow = String(item.user_id) === String(currentUser?.user_id);
                      const selfActiveAdmin = isSelfRow && item.role === "admin" && item.is_active;
                      return (
                    <select
                      value={item.role || "viewer"}
                      disabled={selfActiveAdmin}
                      title={
                        selfActiveAdmin
                          ? "Нельзя изменить роль собственного активного admin-аккаунта"
                          : "Изменить роль пользователя"
                      }
                      onChange={(event) => onRoleChange(item.user_id, event.target.value)}
                    >
                      {roleOptions.map((role) => (
                        <option key={role} value={role}>
                          {role}
                        </option>
                      ))}
                    </select>
                      );
                    })()}
                  </td>
                  <td>
                    <select
                      value={item.is_active ? "active" : "inactive"}
                      onChange={(event) => onActiveChange(item.user_id, event.target.value === "active")}
                    >
                      <option value="active">active</option>
                      <option value="inactive">inactive</option>
                    </select>
                  </td>
                  <td>
                    <input
                      type="password"
                      autoComplete="new-password"
                      placeholder="••••••"
                      value={passwordInputs[item.user_id] || ""}
                      onChange={(event) =>
                        setPasswordInputs((prev) => ({ ...prev, [item.user_id]: event.target.value }))
                      }
                    />
                    <button type="button" onClick={() => onSetPassword(item.user_id)} style={{ marginLeft: 6 }}>
                      Сменить
                    </button>
                  </td>
                  <td>
                    <button
                      type="button"
                      className="danger-btn"
                      disabled={item.user_id === currentUser?.user_id}
                      title={item.user_id === currentUser?.user_id ? "Нельзя удалить свою учётную запись" : "Удалить пользователя"}
                      onClick={() => onDeleteUser(item.user_id)}
                    >
                      Удалить
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </CrmLayout>
  );
}
