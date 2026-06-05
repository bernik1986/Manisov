import React from "react";
import { useLocation, useParams } from "react-router-dom";
import CandidateDetail from "../components/CandidateDetail";
import CrmLayout from "../components/CrmLayout";

export default function CandidateCardPage() {
  const { id } = useParams();
  const location = useLocation();
  const focusTarget = new URLSearchParams(location.search).get("focus") || "";

  return (
    <CrmLayout
      title="Seamen Profile"
      subtitle="Candidate card and document controls."
      collapsibleSidebar
      defaultSidebarHidden
    >
      <div className="card candidate-card">
        <CandidateDetail candidateId={id} focusTarget={focusTarget} />
      </div>
    </CrmLayout>
  );
}
