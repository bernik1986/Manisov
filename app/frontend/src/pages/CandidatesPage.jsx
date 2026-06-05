import React from "react";
import { useState, useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import CandidateList from "../components/CandidateList";
import UploadForm from "../components/UploadForm";
import CrmLayout from "../components/CrmLayout";
import { createEmptyCandidate } from "../api";

export default function CandidatesPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const listPathForReturn = useMemo(() => {
    const s = searchParams.toString();
    return s ? `/candidates?${s}` : "/candidates";
  }, [searchParams]);
  const [refreshKey, setRefreshKey] = useState(0);
  const [creatingCard, setCreatingCard] = useState(false);
  const [createError, setCreateError] = useState("");

  function handleUploaded(response) {
    setRefreshKey((prev) => prev + 1);
    if (response?.candidate_id) {
      const isDuplicate = response?.duplicate === true;
      const notifyText = isDuplicate
        ? response?.message || `Кандидат #${response.candidate_id} уже был в базе и обновлен.`
        : `Кандидат #${response.candidate_id} добавлен в базу данных.`;
      const openCard = window.confirm(`${notifyText}\n\nОткрыть карточку кандидата сейчас?`);
      if (openCard) {
        navigate(`/candidates/${response.candidate_id}`, { state: { candidatesListPath: listPathForReturn } });
      }
    }
  }

  async function handleNewEmptyCard() {
    setCreateError("");
    setCreatingCard(true);
    try {
      const data = await createEmptyCandidate();
      setRefreshKey((prev) => prev + 1);
      if (data?.candidate_id) {
        navigate(`/candidates/${data.candidate_id}`, { state: { candidatesListPath: listPathForReturn } });
      }
    } catch (e) {
      setCreateError("Не удалось создать карточку. Проверьте права доступа и сеть.");
    } finally {
      setCreatingCard(false);
    }
  }

  return (
    <CrmLayout title="Seamen Data Management" subtitle="Manage crew members, certifications and assignments.">
      <div className="card candidates-card">
        <div className="candidate-new-card-bar">
          <button type="button" data-testid="btn-new-empty-candidate" onClick={handleNewEmptyCard} disabled={creatingCard}>
            {creatingCard ? "Создаём…" : "Новая пустая карточка"}
          </button>
          {createError ? <p className="error inline-error">{createError}</p> : null}
        </div>
        <UploadForm onUploaded={handleUploaded} />
        <CandidateList refreshKey={refreshKey} />
      </div>
    </CrmLayout>
  );
}
