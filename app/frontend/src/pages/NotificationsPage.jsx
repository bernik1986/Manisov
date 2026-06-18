import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchCandidates, fetchNotifications } from "../api";
import CrmLayout from "../components/CrmLayout";

function getFocusTarget(item) {
  if (!item?.candidate_id) return null;
  const docId = item?.document_id;
  const certId = item?.certificate_id;
  if (docId) return `document:${docId}`;
  if (certId) return `certificate:${certId}`;
  return null;
}

function isExpiryNotification(item) {
  const message = String(item?.message || "").toLowerCase();
  return (
    message.includes("просрочен") ||
    message.includes("истечёт") ||
    message.includes("истекает") ||
    message.includes("скоро истеч")
  );
}

export default function NotificationsPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [candidatePreviewMap, setCandidatePreviewMap] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expandedCandidates, setExpandedCandidates] = useState({});

  async function loadNotifications() {
    setLoading(true);
    setError("");
    try {
      const payload = await fetchNotifications(false, 2500);
      setItems((payload.items || []).filter(isExpiryNotification));
      const candidatesPayload = await fetchCandidates();
      const candidates = Array.isArray(candidatesPayload) ? candidatesPayload : candidatesPayload.items || [];
      const previewMap = candidates.reduce((acc, candidate) => {
        acc[candidate.id] = {
          surname: candidate.surname || "",
          firstName: candidate.first_name || "",
          position: candidate.position || "",
        };
        return acc;
      }, {});
      setCandidatePreviewMap(previewMap);
    } catch (requestError) {
      setError("Не удалось загрузить уведомления");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadNotifications();
  }, []);

  function onOpenNotification(item) {
    if (!item?.candidate_id) return;
    const focusTarget = getFocusTarget(item);
    const nextPath = focusTarget
      ? `/candidates/${item.candidate_id}?focus=${encodeURIComponent(focusTarget)}`
      : `/candidates/${item.candidate_id}`;
    navigate(nextPath);
  }

  const groupedByCandidate = items.reduce((acc, item) => {
    const candidateId = item?.candidate_id;
    if (!candidateId) return acc;
    if (!acc[candidateId]) {
      acc[candidateId] = { all: [] };
    }
    acc[candidateId].all.push(item);
    return acc;
  }, {});

  const candidateIds = Object.keys(groupedByCandidate)
    .map((value) => Number(value))
    .sort((a, b) => b - a);

  function renderRows(list) {
    return list.map((item) => (
      <tr key={item.id}>
        <td className="notifications-col-message">
          <button type="button" className="notification-link-btn" onClick={() => onOpenNotification(item)}>
            {item.message}
          </button>
        </td>
      </tr>
    ));
  }

  function renderSection(title, list) {
    if (list.length === 0) return null;
    return (
      <div className="detail-block">
        <h2>{title}</h2>
        <div className="table-wrap">
          <table className="candidate-table notifications-table">
          <thead>
            <tr>
              <th>Уведомление</th>
            </tr>
          </thead>
          <tbody>{renderRows(list)}</tbody>
          </table>
        </div>
      </div>
    );
  }

  function toggleCandidate(candidateId) {
    setExpandedCandidates((prev) => ({ ...prev, [candidateId]: !prev[candidateId] }));
  }

  function getCandidateLabel(candidateId) {
    const preview = candidatePreviewMap[candidateId];
    if (!preview) return `Кандидат #${candidateId}`;
    const fullName = [preview.surname, preview.firstName].filter(Boolean).join(" ").trim();
    const position = preview.position || "-";
    if (!fullName) return `Кандидат #${candidateId} — ${position}`;
    return `${fullName} — ${position}`;
  }

  return (
    <CrmLayout
      title="Уведомления"
      subtitle="Просроченные и скоро истекающие документы и сертификаты по каждому кандидату."
    >
      <div className="card candidates-card" data-testid="notifications-content">

        {error ? <p className="error">{error}</p> : null}

        {loading ? (
          <p>Загрузка...</p>
        ) : (
          <>
            {candidateIds.map((candidateId) => {
              const group = groupedByCandidate[candidateId];
              const expanded = Boolean(expandedCandidates[candidateId]);
              return (
                <div key={candidateId} className="detail-block">
                  <div className="menu-header">
                    <h2 style={{ marginBottom: 0 }}>{getCandidateLabel(candidateId)}</h2>
                    <button type="button" className="secondary-btn" onClick={() => toggleCandidate(candidateId)}>
                      {expanded ? "Скрыть" : `Раскрыть (${group.all.length})`}
                    </button>
                  </div>
                  {expanded ? (
                    renderSection("Срок действия документов", group.all)
                  ) : null}
                </div>
              );
            })}
            {items.length === 0 ? <p className="empty-row">Уведомлений пока нет</p> : null}
          </>
        )}
      </div>
    </CrmLayout>
  );
}
