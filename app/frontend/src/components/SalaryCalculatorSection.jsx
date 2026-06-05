import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  createEmptySalaryCalculatorForm,
  parseSalaryCalculationJson,
  SALARY_COMPONENT_LABELS,
} from "../salaryCalculatorFields";
import {
  fetchCompanySalaryRanks,
  previewSalaryCalculation,
  resetSalaryCalculation,
  saveSalaryCalculation,
} from "../api";
export default function SalaryCalculatorSection({
  candidateId,
  canEdit,
  companies,
  savedJson,
  hintRank = "",
  hintTotalWage = "",
  hintPeriod = "",
  onSaved,
}) {
  const [form, setForm] = useState(() => createEmptySalaryCalculatorForm());
  const [ranks, setRanks] = useState([]);
  const [errors, setErrors] = useState([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [lastSavedAt, setLastSavedAt] = useState("");

  const companyOptions = useMemo(
    () => (companies || []).slice().sort((a, b) => a.name.localeCompare(b.name)),
    [companies]
  );

  const configuredRanks = useMemo(() => new Set(ranks), [ranks]);

  const applyCalculation = useCallback((calc) => {
    if (!calc) {
      return;
    }
    const components = calc.components || {};
    setForm((prev) => ({
      ...prev,
      company_id: calc.company_id != null ? String(calc.company_id) : prev.company_id,
      rank: calc.rank || prev.rank,
      total_wage: calc.total_wage != null ? String(calc.total_wage) : prev.total_wage,
      period_of_employment: calc.period_of_employment ?? prev.period_of_employment,
      basic_monthly_wage: components.basic_monthly_wage ?? "",
      monthly_overtime: components.monthly_overtime ?? "",
      overtime_rate: components.overtime_rate ?? "",
      sepf: components.sepf ?? "",
      imtf: components.imtf ?? "",
      leave: components.leave ?? "",
      leave_sub: components.leave_sub ?? "",
      various_extra_overtime: components.various_extra_overtime ?? "",
      fixed_components_total: calc.fixed_components_total ?? "",
      owners_bonus: calc.owners_bonus ?? "",
    }));
    setErrors(calc.errors || []);
  }, []);

  const runPreview = useCallback(
    async (draft) => {
      if (!candidateId || !draft.company_id || !draft.rank) {
        return;
      }
      setBusy(true);
      setMessage("");
      try {
        const payload = await previewSalaryCalculation(candidateId, {
          company_id: Number(draft.company_id),
          rank: draft.rank,
          total_wage: draft.total_wage === "" ? null : Number(draft.total_wage),
          period_of_employment: draft.period_of_employment || null,
        });
        applyCalculation(payload.calculation);
      } catch (requestError) {
        const detail = requestError?.response?.data?.detail;
        setErrors(Array.isArray(detail?.errors) ? detail.errors : [String(detail || requestError.message)]);
      } finally {
        setBusy(false);
      }
    },
    [applyCalculation, candidateId]
  );

  useEffect(() => {
    const parsed = parseSalaryCalculationJson(savedJson);
    setForm(parsed);
    if (parsed.company_id) {
      fetchCompanySalaryRanks(parsed.company_id)
        .then((data) => setRanks(data.ranks || []))
        .catch(() => setRanks([]));
    }
  }, [savedJson]);

  async function onCompanyChange(event) {
    const companyId = event.target.value;
    setForm((prev) => ({
      ...createEmptySalaryCalculatorForm(),
      company_id: companyId,
      total_wage: prev.total_wage,
      period_of_employment: prev.period_of_employment,
    }));
    setErrors([]);
    setRanks([]);
    if (!companyId) {
      return;
    }
    try {
      const data = await fetchCompanySalaryRanks(companyId);
      setRanks(data.ranks || []);
    } catch {
      setErrors(["Failed to load ranks for company"]);
    }
  }

  async function onRankChange(event) {
    const rank = event.target.value;
    const next = { ...form, rank };
    setForm(next);
    await runPreview(next);
  }

  async function onTotalWageBlur() {
    await runPreview(form);
  }

  function onApplyHints() {
    const next = {
      ...form,
      rank: form.rank || (hintRank ? String(hintRank).trim() : ""),
      total_wage: form.total_wage || (hintTotalWage != null && hintTotalWage !== "" ? String(hintTotalWage) : ""),
      period_of_employment: form.period_of_employment || hintPeriod || "",
    };
    setForm(next);
    if (next.company_id && next.rank) {
      runPreview(next);
    }
  }

  async function onCalculate() {
    await runPreview(form);
  }

  async function onSave() {
    if (!canEdit) {
      return;
    }
    setBusy(true);
    setMessage("");
    setErrors([]);
    try {
      const payload = await saveSalaryCalculation(candidateId, {
        company_id: Number(form.company_id),
        rank: form.rank,
        total_wage: Number(form.total_wage),
        period_of_employment: form.period_of_employment || null,
      });
      applyCalculation({
        ...payload.calculation,
        components: {
          basic_monthly_wage: payload.calculation.basic_monthly_wage,
          monthly_overtime: payload.calculation.monthly_overtime,
          overtime_rate: payload.calculation.overtime_rate,
          sepf: payload.calculation.sepf,
          imtf: payload.calculation.imtf,
          leave: payload.calculation.leave,
          leave_sub: payload.calculation.leave_sub,
          various_extra_overtime: payload.calculation.various_extra_overtime,
        },
        valid: true,
        errors: [],
      });
      setLastSavedAt(payload.calculation?.calculation_date || new Date().toISOString());
      setMessage("Расчёт сохранён. Значения доступны в плейсхолдерах {{salary_*}} при генерации контракта.");
      onSaved?.(payload.candidate);
    } catch (requestError) {
      const detail = requestError?.response?.data?.detail;
      if (detail?.errors) {
        setErrors(detail.errors);
      } else {
        setErrors([String(detail || "Не удалось сохранить расчёт")]);
      }
    } finally {
      setBusy(false);
    }
  }

  async function onReset() {
    if (!canEdit) {
      return;
    }
    if (!window.confirm("Очистить сохранённый расчёт зарплаты для этого кандидата?")) {
      return;
    }
    setBusy(true);
    try {
      const payload = await resetSalaryCalculation(candidateId);
      setForm(createEmptySalaryCalculatorForm());
      setRanks([]);
      setErrors([]);
      setMessage("");
      setLastSavedAt("");
      onSaved?.(payload.candidate);
    } catch {
      setErrors(["Не удалось сбросить расчёт"]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="salary-calculator-section" data-testid="salary-calculator-section">
      <p className="muted-text">
        Порядок: Company → Rank → Total Wage → Period. Фиксированные компоненты подставляются из матрицы Company
        (настраивается в разделе Company). Owner&apos;s Bonus считается автоматически.
      </p>

      {errors.length > 0 ? (
        <ul className="error" data-testid="salary-calculator-errors">
          {errors.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : null}
      {message ? <p className="muted-text">{message}</p> : null}
      {lastSavedAt ? <p className="muted-text">Последнее сохранение: {lastSavedAt}</p> : null}

      <div className="detail-grid">
        <label>
          Company *
          <select
            value={form.company_id}
            disabled={!canEdit || busy}
            onChange={onCompanyChange}
            data-testid="salary-company-select"
          >
            <option value="">— выберите компанию —</option>
            {companyOptions.map((company) => (
              <option key={company.company_id} value={company.company_id}>
                {company.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Rank / Position *
          <select
            value={form.rank}
            disabled={!canEdit || busy || !form.company_id}
            onChange={onRankChange}
            data-testid="salary-rank-select"
          >
            <option value="">— выберите должность —</option>
            {ranks.map((rank) => (
              <option key={rank} value={rank}>
                {rank}
              </option>
            ))}
          </select>
          {form.company_id && ranks.length === 0 ? (
            <span className="muted-text" style={{ display: "block", marginTop: 4 }}>
              Нет ставок для этой компании — добавьте их в разделе Company.
            </span>
          ) : null}
          {form.company_id && ranks.length > 0 && hintRank && !configuredRanks.has(hintRank) ? (
            <span className="muted-text" style={{ display: "block", marginTop: 4 }}>
              Подсказка из карточки ({hintRank}) не найдена в матрице этой компании.
            </span>
          ) : null}
        </label>
        <label>
          Total Wage *
          <input
            type="number"
            step="0.01"
            min="0"
            value={form.total_wage}
            readOnly={!canEdit}
            disabled={busy}
            onChange={(event) => setForm((prev) => ({ ...prev, total_wage: event.target.value }))}
            onBlur={onTotalWageBlur}
            data-testid="salary-total-wage"
          />
        </label>
        <label>
          Period of Employment
          <input
            type="text"
            value={form.period_of_employment}
            readOnly={!canEdit}
            disabled={busy}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, period_of_employment: event.target.value }))
            }
            data-testid="salary-period"
          />
        </label>
      </div>

      {canEdit && (hintRank || hintTotalWage || hintPeriod) ? (
        <button type="button" className="secondary-btn tiny-btn" onClick={onApplyHints}>
          Подставить из заявки / профиля
        </button>
      ) : null}

      <h4 className="detail-block__panel-title">Фиксированные компоненты</h4>
      <div className="detail-grid">
        {SALARY_COMPONENT_LABELS.map(([key, label]) => (
          <label key={key}>
            {label}
            <input type="text" value={form[key] ?? ""} readOnly tabIndex={-1} />
          </label>
        ))}
      </div>

      <div className="detail-grid">
        <label>
          Fixed Components Total
          <input type="text" value={form.fixed_components_total} readOnly tabIndex={-1} />
        </label>
        <label>
          Owner&apos;s Bonus
          <input
            type="text"
            value={form.owners_bonus}
            readOnly
            tabIndex={-1}
            data-testid="salary-owners-bonus"
          />
        </label>
      </div>

      {canEdit ? (
        <div className="candidate-admin-toolbar" style={{ marginTop: "1rem" }}>
          <button type="button" onClick={onCalculate} disabled={busy} data-testid="salary-btn-calculate">
            {busy ? "…" : "Calculate"}
          </button>
          <button type="button" onClick={onCalculate} disabled={busy} data-testid="salary-btn-recalculate">
            Recalculate
          </button>
          <button type="button" className="secondary-btn" onClick={onSave} disabled={busy} data-testid="salary-btn-save">
            Save
          </button>
          <button type="button" className="secondary-btn" onClick={onReset} disabled={busy} data-testid="salary-btn-reset">
            Reset
          </button>
        </div>
      ) : (
        <p className="muted-text">Просмотр только. Редактирование — для admin и recruiter.</p>
      )}
    </div>
  );
}
