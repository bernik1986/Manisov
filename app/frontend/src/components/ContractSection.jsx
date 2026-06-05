import React, { useCallback, useEffect, useMemo, useState } from "react";
import DateDdMmYyyyInput from "./DateDdMmYyyyInput";
import { CANONICAL_POSITION_OPTIONS } from "../canonicalPositions";
import {
  CANDIDATE_PERSONAL_PLACEHOLDER_LINES,
  CONTRACT_AIRPORT_FIELD_DEFS,
  CONTRACT_DEPARTURE_FIELD_DEFS,
  CONTRACT_EDITABLE_FIELD_DEFS,
  CONTRACT_PLACEHOLDER_LINES,
  CONTRACT_VESSEL_PREVIEW_FIELDS,
  contractFormToApiPayload,
  createEmptyContractForm,
  hydrateContractForm,
  parseContractJson,
  salaryMatchesContract,
} from "../contractFields";
import { parseSalaryCalculationJson, SALARY_COMPONENT_LABELS } from "../salaryCalculatorFields";
import {
  fetchCompanySalaryRanks,
  fetchContractTemplates,
  generateCandidateDocument,
  saveCandidateContract,
} from "../api";

function PreviewRow({ label, value }) {
  return (
    <div className="contract-preview-row">
      <dt>{label}</dt>
      <dd>{value || "—"}</dd>
    </div>
  );
}

export default function ContractSection({
  candidateId,
  canEdit,
  companies,
  vessels,
  savedContractJson,
  savedSalaryJson,
  candidate,
  onSaved,
}) {
  const [form, setForm] = useState(() => createEmptyContractForm());
  const [ranks, setRanks] = useState([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [contractTemplates, setContractTemplates] = useState([]);
  const [templatesMessage, setTemplatesMessage] = useState("");
  const [selectedTemplateIds, setSelectedTemplateIds] = useState([]);
  const [generating, setGenerating] = useState(false);

  const companyOptions = useMemo(
    () => (companies || []).slice().sort((a, b) => a.name.localeCompare(b.name)),
    [companies]
  );

  const vesselOptions = useMemo(() => {
    if (!form.company_id) return [];
    return (vessels || [])
      .filter((v) => String(v.company_id) === String(form.company_id))
      .slice()
      .sort((a, b) => (a.name || "").localeCompare(b.name || ""));
  }, [vessels, form.company_id]);

  const selectedCompany = useMemo(
    () => companyOptions.find((c) => String(c.company_id) === String(form.company_id)),
    [companyOptions, form.company_id]
  );

  const selectedVessel = useMemo(
    () => vesselOptions.find((v) => String(v.vessel_id) === String(form.vessel_id)),
    [vesselOptions, form.vessel_id]
  );

  const salarySaved = useMemo(() => parseSalaryCalculationJson(savedSalaryJson), [savedSalaryJson]);
  const salaryMatches = useMemo(() => salaryMatchesContract(form, salarySaved), [form, salarySaved]);

  const configuredRanks = useMemo(() => new Set(ranks), [ranks]);

  const rankOptions = useMemo(() => {
    const current = form.rank;
    return CANONICAL_POSITION_OPTIONS.filter(
      (rank) => !configuredRanks.size || configuredRanks.has(rank) || rank === current
    );
  }, [configuredRanks, form.rank]);

  useEffect(() => {
    setForm(hydrateContractForm(parseContractJson(savedContractJson), candidate));
  }, [savedContractJson, candidate?.home_airport, candidate?.departure_airport]);

  useEffect(() => {
    if (!form.company_id) {
      setRanks([]);
      return;
    }
    fetchCompanySalaryRanks(form.company_id)
      .then((data) => setRanks(data.ranks || []))
      .catch(() => setRanks([]));
  }, [form.company_id]);

  const onCompanyChange = useCallback((companyId) => {
    setForm((prev) => ({
      ...createEmptyContractForm(),
      company_id: companyId,
      rank: prev.rank,
    }));
  }, []);

  async function onSave() {
    if (!canEdit) return;
    setError("");
    setMessage("");
    if (!form.company_id) {
      setError("Выберите компанию");
      return;
    }
    if (!String(form.rank || "").trim()) {
      setError("Выберите должность");
      return;
    }
    setBusy(true);
    try {
      const payload = contractFormToApiPayload(form);
      await saveCandidateContract(candidateId, payload);
      setMessage("Контракт сохранён");
      onSaved?.();
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Не удалось сохранить");
    } finally {
      setBusy(false);
    }
  }

  async function openGenerateModal() {
    setModalOpen(true);
    setTemplatesLoading(true);
    setTemplatesMessage("");
    setSelectedTemplateIds([]);
    try {
      const data = await fetchContractTemplates();
      setContractTemplates(data.files || []);
      setTemplatesMessage(data.message || "");
    } catch {
      setError("Не удалось загрузить шаблоны контрактов");
      setModalOpen(false);
    } finally {
      setTemplatesLoading(false);
    }
  }

  async function onGenerateSelected() {
    if (selectedTemplateIds.length === 0) {
      setError("Выберите хотя бы один шаблон");
      return;
    }
    setGenerating(true);
    setError("");
    try {
      for (const templateFileId of selectedTemplateIds) {
        const tpl = contractTemplates.find((t) => t.template_file_id === templateFileId);
        if (!tpl) continue;
        const { blob, fileName } = await generateCandidateDocument(
          candidateId,
          tpl.file_name,
          tpl.template_file_id,
          { contractsOnly: true }
        );
        const objectUrl = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = objectUrl;
        link.download = fileName || tpl.file_name;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(objectUrl);
      }
      setModalOpen(false);
      setMessage("Документ(ы) сгенерированы");
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Не удалось сгенерировать контракт");
    } finally {
      setGenerating(false);
    }
  }

  function toggleTemplate(id) {
    setSelectedTemplateIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  }

  return (
    <div className="contract-section" data-testid="contract-section">
      {error ? <div className="error">{error}</div> : null}
      {message ? <p className="success-text">{message}</p> : null}

      <div className="contract-select-grid detail-grid">
        <label>
          <span>Компания *</span>
          <select
            value={form.company_id}
            disabled={!canEdit || busy}
            onChange={(e) => onCompanyChange(e.target.value)}
            aria-label="Компания"
          >
            <option value="">— выберите —</option>
            {companyOptions.map((c) => (
              <option key={c.company_id} value={c.company_id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Судно</span>
          <select
            value={form.vessel_id}
            disabled={!canEdit || busy || !form.company_id}
            onChange={(e) => setForm((prev) => ({ ...prev, vessel_id: e.target.value }))}
            aria-label="Судно"
          >
            <option value="">— не выбрано —</option>
            {vesselOptions.map((v) => (
              <option key={v.vessel_id} value={v.vessel_id}>
                {v.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Должность *</span>
          <select
            value={form.rank}
            disabled={!canEdit || busy || !form.company_id}
            onChange={(e) => setForm((prev) => ({ ...prev, rank: e.target.value }))}
            aria-label="Должность"
          >
            <option value="">— выберите —</option>
            {rankOptions.map((rank) => (
              <option key={rank} value={rank}>
                {rank}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="contract-preview-grid">
        <section className="contract-preview-card card">
          <h4>Компания</h4>
          <dl>
            <PreviewRow label="Название" value={selectedCompany?.name} />
            <PreviewRow label="Slug" value={selectedCompany?.slug} />
          </dl>
        </section>
        <section className="contract-preview-card card">
          <h4>Судно</h4>
          <dl>
            {CONTRACT_VESSEL_PREVIEW_FIELDS.map(([key, label]) => (
              <PreviewRow key={key} label={label} value={selectedVessel?.[key]} />
            ))}
          </dl>
        </section>
        <section className="contract-preview-card card">
          <h4>Кандидат</h4>
          <dl>
            <PreviewRow
              label="ФИО"
              value={[candidate?.surname, candidate?.first_name, candidate?.middle_name].filter(Boolean).join(" ")}
            />
            <PreviewRow label="Дата рождения" value={candidate?.date_of_birth} />
            <PreviewRow label="Возраст" value={candidate?.age != null ? String(candidate.age) : ""} />
            <PreviewRow label="Национальность" value={candidate?.nationality} />
            <PreviewRow label="Паспорт" value={candidate?.passport_number} />
            <PreviewRow label="Seaman's Book" value={candidate?.seaman_book_number} />
            <PreviewRow label="Home airport" value={form.contract_home_airport || candidate?.home_airport} />
            <PreviewRow
              label="Departure airport"
              value={form.contract_departure_airport || candidate?.departure_airport}
            />
            <PreviewRow label="Дата вылета" value={form.contract_departure_date} />
          </dl>
        </section>
        <section className="contract-preview-card card">
          <h4>Зарплата (калькулятор)</h4>
          {!salaryMatches ? (
            <p className="contract-warning">
              Сохраните расчёт в калькуляторе для выбранной компании и должности.
            </p>
          ) : (
            <dl>
              <PreviewRow label="Total Wage" value={salarySaved.total_wage} />
              {SALARY_COMPONENT_LABELS.map(([key, label]) => (
                <PreviewRow key={key} label={label} value={salarySaved[key]} />
              ))}
            </dl>
          )}
        </section>
      </div>

      <h4 className="detail-block__panel-title detail-block__panel-title--sub">Вылет</h4>
      <div className="contract-select-grid detail-grid">
        {CONTRACT_DEPARTURE_FIELD_DEFS.map(({ key, label, type }) => (
          <label key={key}>
            <span>{label}</span>
            {type === "date" ? (
              <DateDdMmYyyyInput
                value={form[key]}
                disabled={!canEdit || busy}
                onChange={(next) => setForm((prev) => ({ ...prev, [key]: next }))}
              />
            ) : (
              <input
                type="text"
                value={form[key]}
                disabled={!canEdit || busy}
                onChange={(e) => setForm((prev) => ({ ...prev, [key]: e.target.value }))}
              />
            )}
          </label>
        ))}
        {CONTRACT_AIRPORT_FIELD_DEFS.map(({ key, label }) => (
          <label key={key}>
            <span>{label}</span>
            <input
              type="text"
              value={form[key]}
              disabled={!canEdit || busy}
              onChange={(e) => setForm((prev) => ({ ...prev, [key]: e.target.value }))}
            />
          </label>
        ))}
      </div>

      <h4 className="detail-block__panel-title detail-block__panel-title--sub">Поля контракта</h4>
      <div className="contract-select-grid detail-grid">
        {CONTRACT_EDITABLE_FIELD_DEFS.map(({ key, label, type }) => (
          <label key={key}>
            <span>{label}</span>
            {type === "date" ? (
              <DateDdMmYyyyInput
                value={form[key]}
                disabled={!canEdit || busy}
                onChange={(next) => setForm((prev) => ({ ...prev, [key]: next }))}
              />
            ) : (
              <input
                type="text"
                value={form[key]}
                disabled={!canEdit || busy}
                onChange={(e) => setForm((prev) => ({ ...prev, [key]: e.target.value }))}
              />
            )}
          </label>
        ))}
      </div>

      <details className="ukr-placeholders-details" style={{ marginBottom: "0.75rem" }}>
        <summary>Плейсхолдеры — персональные данные кандидата (docxtpl)</summary>
        <pre className="ukr-placeholders-pre">{CANDIDATE_PERSONAL_PLACEHOLDER_LINES.join("\n")}</pre>
      </details>

      <details className="ukr-placeholders-details" style={{ marginBottom: "0.75rem" }}>
        <summary>Плейсхолдеры контракта для Word (docxtpl)</summary>
        <pre className="ukr-placeholders-pre">{CONTRACT_PLACEHOLDER_LINES.join("\n")}</pre>
      </details>

      {canEdit ? (
        <div className="form-actions">
          <button type="button" className="primary-btn" disabled={busy} onClick={onSave}>
            {busy ? "Сохранение…" : "Сохранить контракт"}
          </button>
          <button
            type="button"
            className="secondary-btn"
            data-testid="btn-create-contract"
            disabled={busy || !form.company_id || !form.rank}
            onClick={openGenerateModal}
          >
            Создать контракт
          </button>
        </div>
      ) : (
        <p className="muted-text">Редактирование — для ролей admin и recruiter.</p>
      )}

      {modalOpen ? (
        <div className="modal-overlay" onClick={() => !generating && setModalOpen(false)}>
          <div
            className="modal-card contract-templates-modal"
            data-testid="contract-templates-modal"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
          >
            <div className="menu-header">
              <h2>Создать контракт</h2>
              <button
                type="button"
                className="secondary-btn tiny-btn"
                onClick={() => setModalOpen(false)}
                disabled={generating}
              >
                Закрыть
              </button>
            </div>
            <p className="muted-text">Шаблоны только из папки «Контракты»</p>
            {templatesLoading ? <p>Загрузка…</p> : null}
            {templatesMessage ? <p className="contract-warning">{templatesMessage}</p> : null}
            {!templatesLoading && contractTemplates.length === 0 ? (
              <p className="empty-row">Нет DOCX-шаблонов в папке «Контракты»</p>
            ) : (
              <ul className="contract-template-list">
                {contractTemplates.map((tpl) => (
                  <li key={tpl.template_file_id}>
                    <label>
                      <input
                        type="checkbox"
                        checked={selectedTemplateIds.includes(tpl.template_file_id)}
                        onChange={() => toggleTemplate(tpl.template_file_id)}
                      />
                      {tpl.file_name}
                    </label>
                  </li>
                ))}
              </ul>
            )}
            <div className="form-actions">
              <button
                type="button"
                className="primary-btn"
                disabled={generating || selectedTemplateIds.length === 0}
                onClick={onGenerateSelected}
              >
                {generating ? "Генерация…" : "Сгенерировать"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
