import React, { useEffect, useMemo, useRef, useState } from "react";
import CrmLayout from "../components/CrmLayout";
import { useAuth } from "../context/AuthContext";
import {
  createCompany,
  createCompanyFolder,
  createVessel,
  deleteCompany,
  deleteCompanyFolder,
  deleteVessel,
  createSalaryTemplate,
  deleteSalaryTemplate,
  fetchCompaniesManager,
  fetchCompanySalaryTemplates,
  importCompaniesFromXlsx,
  importSalaryScaleFromXlsx,
  renameCompanyFolder,
  updateCompany,
  updateSalaryTemplate,
  updateVessel,
} from "../api";
import { CANONICAL_POSITION_OPTIONS } from "../canonicalPositions";
import { FLEET_OPTIONS } from "../fleetOptions";

const VESSEL_FORM_FIELDS = [
  { key: "name", label: "Название", type: "text", required: true },
  { key: "imo", label: "ИМО", type: "text" },
  { key: "flag", label: "Флаг", type: "text" },
  { key: "port_of_registry", label: "Port of Registry", type: "text" },
  { key: "vessel_type", label: "Тип судна", type: "select" },
  { key: "registry_address", label: "Адрес судна (регистрация)", type: "text" },
  { key: "official_number", label: "Official No", type: "text" },
  { key: "call_sign", label: "CALL SIGN", type: "text" },
  { key: "grt", label: "GRT", type: "text" },
  { key: "deadweight", label: "Dead Weight", type: "text" },
  { key: "year_built", label: "Year of Built", type: "number" },
  { key: "engine_type", label: "Engine Type", type: "text" },
  { key: "engine_hp", label: "H.P.", type: "text" },
  { key: "classification_society", label: "Classification society", type: "text" },
];

const VESSEL_PLACEHOLDER_LABELS = Object.fromEntries(
  VESSEL_FORM_FIELDS.map(({ key, label }) => [key === "vessel_type" ? "type" : key, label])
);

function emptyVesselForm() {
  return Object.fromEntries(VESSEL_FORM_FIELDS.map(({ key }) => [key, ""]));
}

const EMPTY_VESSEL_FORM = emptyVesselForm();

function vesselToForm(vessel) {
  const form = emptyVesselForm();
  for (const { key } of VESSEL_FORM_FIELDS) {
    const value = vessel[key];
    form[key] = value == null || value === "" ? "" : String(value);
  }
  return form;
}

function buildVesselPayload(form) {
  const name = form.name.trim();
  const payload = { name };
  for (const { key, type } of VESSEL_FORM_FIELDS) {
    if (key === "name") continue;
    const raw = String(form[key] ?? "").trim();
    if (type === "number") {
      if (!raw) {
        payload[key] = null;
      } else {
        const parsed = Number.parseInt(raw, 10);
        if (Number.isNaN(parsed)) {
          throw new Error("invalid_year");
        }
        payload[key] = parsed;
      }
    } else {
      payload[key] = raw || null;
    }
  }
  return payload;
}

const SALARY_MATRIX_COLUMNS = [
  { key: "rank", label: "Должность (Rank)", type: "rank" },
  { key: "basic_monthly_wage", label: "Basic Monthly Wage", type: "number" },
  { key: "monthly_overtime", label: "Monthly Overtime", type: "number" },
  { key: "overtime_rate", label: "Overtime Rate", type: "number" },
  { key: "sepf", label: "SEPF", type: "number" },
  { key: "imtf", label: "IMTF", type: "number" },
  { key: "leave", label: "Leave", type: "number" },
  { key: "leave_sub", label: "Leave Sub", type: "number" },
  { key: "various_extra_overtime", label: "Various / Extra OT", type: "number" },
];

const EMPTY_SALARY_ROW = Object.fromEntries(
  SALARY_MATRIX_COLUMNS.map((col) => [col.key, col.type === "rank" ? "" : "0"])
);

function salaryTemplateToDraft(row) {
  return {
    rank: row.rank || "",
    basic_monthly_wage: String(row.basic_monthly_wage ?? 0),
    monthly_overtime: String(row.monthly_overtime ?? 0),
    overtime_rate: String(row.overtime_rate ?? 0),
    sepf: String(row.sepf ?? 0),
    imtf: String(row.imtf ?? 0),
    leave: String(row.leave ?? 0),
    leave_sub: String(row.leave_sub ?? 0),
    various_extra_overtime: String(row.various_extra_overtime ?? 0),
  };
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

export default function CompaniesPage() {
  const { user } = useAuth();
  const canEdit = user?.role === "admin" || user?.role === "recruiter";

  const [folders, setFolders] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [vessels, setVessels] = useState([]);
  const [rootFolderId, setRootFolderId] = useState(null);
  const [selectedFolderId, setSelectedFolderId] = useState(null);
  const [selectedCompanyId, setSelectedCompanyId] = useState(null);
  const [selectedVesselId, setSelectedVesselId] = useState(null);
  const [treeSearch, setTreeSearch] = useState("");
  const [vesselSearch, setVesselSearch] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [collapsedFolderIds, setCollapsedFolderIds] = useState([]);
  const [copyHint, setCopyHint] = useState("");
  const [vesselModalOpen, setVesselModalOpen] = useState(false);
  const [vesselModalMode, setVesselModalMode] = useState("create");
  const [editingVesselId, setEditingVesselId] = useState(null);
  const [vesselForm, setVesselForm] = useState(EMPTY_VESSEL_FORM);
  const [vesselSaving, setVesselSaving] = useState(false);
  const [importingXlsx, setImportingXlsx] = useState(false);
  const [importingSalaryScale, setImportingSalaryScale] = useState(false);
  const [salaryImportMessage, setSalaryImportMessage] = useState("");
  const salaryScaleInputRef = useRef(null);
  const [importMessage, setImportMessage] = useState("");
  const [salaryTemplates, setSalaryTemplates] = useState([]);
  const [salaryFormDraft, setSalaryFormDraft] = useState(EMPTY_SALARY_ROW);
  const [salaryEditingId, setSalaryEditingId] = useState(null);
  const [salarySaving, setSalarySaving] = useState(false);
  const [salaryTemplatesLoading, setSalaryTemplatesLoading] = useState(false);

  const usedSalaryRanks = useMemo(
    () => new Set(salaryTemplates.map((row) => row.rank)),
    [salaryTemplates]
  );

  const availableRankOptions = useMemo(() => {
    const currentRank = salaryFormDraft.rank;
    return CANONICAL_POSITION_OPTIONS.filter(
      (rank) => !usedSalaryRanks.has(rank) || rank === currentRank
    );
  }, [usedSalaryRanks, salaryFormDraft.rank]);

  const childrenMap = useMemo(() => {
    return folders.reduce((acc, folder) => {
      const key = folder.parent_id || "__none__";
      if (!acc[key]) acc[key] = [];
      acc[key].push(folder);
      return acc;
    }, {});
  }, [folders]);

  const companiesByFolder = useMemo(() => {
    return companies.reduce((acc, company) => {
      if (!acc[company.folder_id]) acc[company.folder_id] = [];
      acc[company.folder_id].push(company);
      return acc;
    }, {});
  }, [companies]);

  function folderChildren(parentId) {
    const raw = childrenMap[parentId] || [];
    return raw.filter((node) => (rootFolderId == null ? true : node.folder_id !== rootFolderId));
  }

  function sortByName(list, key = "name") {
    return list.slice().sort((a, b) => String(a[key] || "").localeCompare(String(b[key] || ""), "ru"));
  }

  const treeSearchNormalized = treeSearch.trim().toLowerCase();
  const selectedCompany = companies.find((item) => item.company_id === selectedCompanyId) || null;

  const companyVessels = useMemo(() => {
    if (!selectedCompanyId) return [];
    return sortByName(vessels.filter((item) => item.company_id === selectedCompanyId));
  }, [vessels, selectedCompanyId]);

  const companyVesselsFiltered = useMemo(() => {
    const q = vesselSearch.trim().toLowerCase();
    if (!q) return companyVessels;
    return companyVessels.filter((item) => {
      const hay = [item.name, item.imo, item.flag, item.vessel_type, item.slug]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [companyVessels, vesselSearch]);

  const selectedVessel =
    vessels.find((item) => item.vessel_id === selectedVesselId) ||
    companyVesselsFiltered.find((item) => item.vessel_id === selectedVesselId) ||
    null;

  const vesselTypeSelectOptions = useMemo(() => {
    const current = vesselForm.vessel_type?.trim();
    if (current && !FLEET_OPTIONS.includes(current)) {
      return [current, ...FLEET_OPTIONS];
    }
    return FLEET_OPTIONS;
  }, [vesselForm.vessel_type]);

  const isFolderExpanded = (folderId) => !collapsedFolderIds.includes(folderId);

  function toggleFolderExpanded(folderId) {
    setCollapsedFolderIds((prev) =>
      prev.includes(folderId) ? prev.filter((id) => id !== folderId) : [...prev, folderId]
    );
  }

  const isFolderVisibleInSearch = useMemo(() => {
    if (!treeSearchNormalized) return () => true;
    const cache = new Map();
    function companyMatches(folderId) {
      return (companiesByFolder[folderId] || []).some((company) =>
        String(company.name || "").toLowerCase().includes(treeSearchNormalized)
      );
    }
    function visible(folderId) {
      if (cache.has(folderId)) return cache.get(folderId);
      const folder = folders.find((item) => item.folder_id === folderId);
      const nameMatch = folder && String(folder.name || "").toLowerCase().includes(treeSearchNormalized);
      const kids = folderChildren(folderId);
      const childMatch = kids.some((c) => visible(c.folder_id)) || companyMatches(folderId);
      const result = Boolean(nameMatch || childMatch);
      cache.set(folderId, result);
      return result;
    }
    return visible;
  }, [treeSearchNormalized, folders, companiesByFolder, childrenMap, rootFolderId]);

  async function loadCompanies() {
    setLoading(true);
    setError("");
    try {
      const payload = await fetchCompaniesManager();
      const nextFolders = payload.folders || [];
      const nextCompanies = payload.companies || [];
      const nextVessels = payload.vessels || [];
      const nextRootId = payload.root_folder_id;
      setFolders(nextFolders);
      setCompanies(nextCompanies);
      setVessels(nextVessels);
      setRootFolderId(nextRootId);
      setSelectedFolderId((prev) =>
        prev && nextFolders.some((item) => item.folder_id === prev) ? prev : nextRootId
      );
      setSelectedCompanyId((prev) =>
        prev && nextCompanies.some((item) => item.company_id === prev) ? prev : null
      );
      setSelectedVesselId((prev) =>
        prev && nextVessels.some((item) => item.vessel_id === prev) ? prev : null
      );
    } catch (requestError) {
      const detail =
        requestError?.response?.data?.detail ||
        (requestError?.response?.status ? `HTTP ${requestError.response.status}` : null);
      setError(detail ? `Не удалось загрузить раздел Company: ${detail}` : "Не удалось загрузить раздел Company");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadCompanies();
  }, []);

  useEffect(() => {
    if (!selectedCompanyId) {
      setSalaryTemplates([]);
      resetSalaryForm();
      return;
    }
    let active = true;
    setSalaryTemplatesLoading(true);
    fetchCompanySalaryTemplates(selectedCompanyId)
      .then((data) => {
        if (active) {
          setSalaryTemplates(data.items || []);
        }
      })
      .catch(() => {
        if (active) {
          setSalaryTemplates([]);
        }
      })
      .finally(() => {
        if (active) {
          setSalaryTemplatesLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [selectedCompanyId]);

  function buildSalaryPayload(draft) {
    return {
      rank: draft.rank.trim(),
      basic_monthly_wage: Number(draft.basic_monthly_wage) || 0,
      monthly_overtime: Number(draft.monthly_overtime) || 0,
      overtime_rate: Number(draft.overtime_rate) || 0,
      sepf: Number(draft.sepf) || 0,
      imtf: Number(draft.imtf) || 0,
      leave: Number(draft.leave) || 0,
      leave_sub: Number(draft.leave_sub) || 0,
      various_extra_overtime: Number(draft.various_extra_overtime) || 0,
    };
  }

  function resetSalaryForm() {
    setSalaryFormDraft(EMPTY_SALARY_ROW);
    setSalaryEditingId(null);
  }

  function startEditSalaryTemplate(row) {
    setSalaryEditingId(row.template_id);
    setSalaryFormDraft(salaryTemplateToDraft(row));
    setError("");
  }

  async function onSaveSalaryTemplate() {
    if (!selectedCompanyId || !canEdit) {
      return;
    }
    const components = buildSalaryPayload(salaryFormDraft);
    if (!components.rank) {
      setError("Выберите должность (Rank)");
      return;
    }
    setSalarySaving(true);
    setError("");
    try {
      if (salaryEditingId) {
        const response = await updateSalaryTemplate(salaryEditingId, components);
        setSalaryTemplates((prev) =>
          prev
            .map((row) => (row.template_id === salaryEditingId ? response.template : row))
            .sort((a, b) => a.rank.localeCompare(b.rank))
        );
      } else {
        const response = await createSalaryTemplate({
          company_id: selectedCompanyId,
          ...components,
        });
        setSalaryTemplates((prev) =>
          [...prev, response.template].sort((a, b) => a.rank.localeCompare(b.rank))
        );
      }
      resetSalaryForm();
    } catch (requestError) {
      const detail = requestError?.response?.data?.detail;
      setError(detail ? `Матрица зарплат: ${detail}` : "Не удалось сохранить строку матрицы");
    } finally {
      setSalarySaving(false);
    }
  }

  function renderSalaryCell(col, draft, onChange) {
    if (col.type === "rank") {
      return (
        <select
          value={draft.rank}
          disabled={salarySaving}
          onChange={(event) => onChange(col.key, event.target.value)}
          aria-label={col.label}
        >
          <option value="">— выберите —</option>
          {availableRankOptions.map((rank) => (
            <option key={rank} value={rank}>
              {rank}
            </option>
          ))}
        </select>
      );
    }
    return (
      <input
        type="number"
        step="0.01"
        min="0"
        value={draft[col.key]}
        disabled={salarySaving}
        onChange={(event) => onChange(col.key, event.target.value)}
        aria-label={col.label}
      />
    );
  }

  async function onDeleteSalaryTemplate(templateId) {
    if (!window.confirm("Удалить строку матрицы зарплаты?")) {
      return;
    }
    try {
      await deleteSalaryTemplate(templateId);
      setSalaryTemplates((prev) => prev.filter((row) => row.template_id !== templateId));
    } catch {
      setError("Не удалось удалить строку матрицы");
    }
  }

  async function onImportSalaryScale(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !selectedCompany?.slug) {
      return;
    }
    const lower = file.name.toLowerCase();
    if (!lower.endsWith(".xlsx") && !lower.endsWith(".xls")) {
      setError("Выберите файл Excel (.xlsx или .xls)");
      return;
    }
    setImportingSalaryScale(true);
    setError("");
    setSalaryImportMessage("");
    try {
      const result = await importSalaryScaleFromXlsx(file, selectedCompany.slug);
      const stats = result.stats || {};
      setSalaryImportMessage(
        `Зарплатная матрица: создано ${stats.created || 0}, обновлено ${stats.updated || 0}` +
          (stats.skipped?.length ? ` (пропуски: ${stats.skipped.join("; ")})` : "")
      );
      const data = await fetchCompanySalaryTemplates(selectedCompany.company_id);
      setSalaryTemplates(data.items || []);
      resetSalaryForm();
    } catch (requestError) {
      const detail =
        requestError?.response?.data?.detail ||
        (requestError?.response?.status ? `HTTP ${requestError.response.status}` : null);
      setError(detail ? `Импорт зарплат: ${detail}` : "Не удалось импортировать зарплатную матрицу");
    } finally {
      setImportingSalaryScale(false);
    }
  }

  async function onImportXlsx(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const lower = file.name.toLowerCase();
    if (!lower.endsWith(".xlsx") && !lower.endsWith(".xls")) {
      setError("Выберите файл Excel (.xlsx или .xls)");
      return;
    }
    setImportingXlsx(true);
    setError("");
    setImportMessage("");
    try {
      const targetFolderId = selectedFolderId || rootFolderId;
      const result = await importCompaniesFromXlsx(file, targetFolderId);
      const stats = result.stats || {};
      setImportMessage(
        `Импорт завершён: компаний +${stats.companies_created || 0} (уже было ${stats.companies_existing || 0}), ` +
          `судов +${stats.vessels_created || 0} (пропущено ${stats.vessels_skipped || 0})`
      );
      await loadCompanies();
    } catch (requestError) {
      const detail =
        requestError?.response?.data?.detail ||
        (requestError?.response?.status ? `HTTP ${requestError.response.status}` : null);
      setError(detail ? `Импорт Excel: ${detail}` : "Не удалось импортировать Excel");
    } finally {
      setImportingXlsx(false);
    }
  }

  async function onCreateFolder(parentId) {
    const name = window.prompt("Название папки");
    if (!name || !name.trim()) return;
    try {
      const response = await createCompanyFolder({ name: name.trim(), parent_id: parentId });
      const created = response.folder;
      setFolders((prev) => [...prev, created]);
      setSelectedFolderId(created.folder_id);
    } catch {
      setError("Не удалось создать папку");
    }
  }

  async function onCreateCompany(folderId) {
    const name = window.prompt("Название компании");
    if (!name || !name.trim()) return;
    try {
      const response = await createCompany({ name: name.trim(), folder_id: folderId });
      const created = response.company;
      setCompanies((prev) => [...prev, created]);
      setSelectedCompanyId(created.company_id);
      setSelectedFolderId(folderId);
    } catch {
      setError("Не удалось создать компанию");
    }
  }

  async function onRenameFolder(folderId) {
    if (folderId === rootFolderId) return;
    const folder = folders.find((item) => item.folder_id === folderId);
    if (!folder) return;
    const nextName = window.prompt("Новое название папки", folder.name || "");
    if (!nextName || !nextName.trim()) return;
    try {
      const response = await renameCompanyFolder(folderId, { name: nextName.trim() });
      const updated = response.folder;
      setFolders((prev) => prev.map((item) => (item.folder_id === folderId ? updated : item)));
    } catch {
      setError("Не удалось переименовать папку");
    }
  }

  async function onDeleteFolder(folderId) {
    if (folderId === rootFolderId) return;
    if (!window.confirm("Удалить папку? Компании внутри должны быть удалены заранее.")) return;
    try {
      await deleteCompanyFolder(folderId);
      setFolders((prev) => prev.filter((item) => item.folder_id !== folderId));
      if (selectedFolderId === folderId) setSelectedFolderId(rootFolderId);
    } catch (requestError) {
      const detail = requestError?.response?.data?.detail;
      setError(detail || "Не удалось удалить папку");
    }
  }

  async function onRenameCompany(companyId) {
    const company = companies.find((item) => item.company_id === companyId);
    if (!company) return;
    const nextName = window.prompt("Новое название компании", company.name || "");
    if (!nextName || !nextName.trim()) return;
    try {
      const response = await updateCompany(companyId, { name: nextName.trim() });
      const updated = response.company;
      setCompanies((prev) => prev.map((item) => (item.company_id === companyId ? updated : item)));
      await loadCompanies();
    } catch {
      setError("Не удалось переименовать компанию");
    }
  }

  async function onDeleteCompany(companyId) {
    if (!window.confirm("Удалить компанию и все её суда?")) return;
    try {
      await deleteCompany(companyId);
      setCompanies((prev) => prev.filter((item) => item.company_id !== companyId));
      setVessels((prev) => prev.filter((item) => item.company_id !== companyId));
      if (selectedCompanyId === companyId) {
        setSelectedCompanyId(null);
        setSelectedVesselId(null);
      }
    } catch {
      setError("Не удалось удалить компанию");
    }
  }

  function openCreateVesselModal() {
    if (!selectedCompanyId) return;
    setVesselModalMode("create");
    setEditingVesselId(null);
    setVesselForm(EMPTY_VESSEL_FORM);
    setVesselModalOpen(true);
  }

  function openEditVesselModal(vessel) {
    setVesselModalMode("edit");
    setEditingVesselId(vessel.vessel_id);
    setVesselForm(vesselToForm(vessel));
    setVesselModalOpen(true);
  }

  function closeVesselModal() {
    if (vesselSaving) return;
    setVesselModalOpen(false);
  }

  async function submitVesselForm(event) {
    event.preventDefault();
    let payload;
    try {
      payload = buildVesselPayload(vesselForm);
    } catch {
      setError("Year of Built должен быть целым числом");
      return;
    }
    if (!payload.name) {
      setError("Укажите название судна");
      return;
    }
    setVesselSaving(true);
    setError("");
    try {
      if (vesselModalMode === "create") {
        const response = await createVessel({ company_id: selectedCompanyId, ...payload });
        const created = response.vessel;
        setVessels((prev) => [...prev, created]);
        setSelectedVesselId(created.vessel_id);
      } else if (editingVesselId != null) {
        const response = await updateVessel(editingVesselId, payload);
        const updated = response.vessel;
        setVessels((prev) => prev.map((item) => (item.vessel_id === editingVesselId ? updated : item)));
        setSelectedVesselId(updated.vessel_id);
      }
      setVesselModalOpen(false);
    } catch {
      setError(vesselModalMode === "create" ? "Не удалось создать судно" : "Не удалось обновить судно");
    } finally {
      setVesselSaving(false);
    }
  }

  async function onDeleteVessel(vesselId) {
    if (!window.confirm("Удалить судно?")) return;
    try {
      await deleteVessel(vesselId);
      setVessels((prev) => prev.filter((item) => item.vessel_id !== vesselId));
      if (selectedVesselId === vesselId) setSelectedVesselId(null);
    } catch {
      setError("Не удалось удалить судно");
    }
  }

  async function onCopyPlaceholder(token) {
    const ok = await copyText(token);
    setCopyHint(ok ? "Скопировано" : "Не удалось скопировать");
    window.setTimeout(() => setCopyHint(""), 2000);
  }

  function renderCompaniesInFolder(folderId, level) {
    const list = sortByName(companiesByFolder[folderId] || []);
    return list.map((company) => {
      if (treeSearchNormalized && !String(company.name || "").toLowerCase().includes(treeSearchNormalized)) {
        const folderVisible = isFolderVisibleInSearch(folderId);
        if (!folderVisible) return null;
      }
      const pad = 8 + level * 14;
      return (
        <div key={`company-${company.company_id}`} className="templates-tree-node">
          <div
            className={`templates-tree-row-wrap${
              selectedCompanyId === company.company_id ? " templates-tree-row-wrap--selected" : ""
            }`}
          >
            <div className="templates-tree-row-main" style={{ paddingLeft: `${pad}px` }}>
              <span className="templates-tree-chevron-spacer" aria-hidden />
              <span className="templates-folder-glyph" aria-hidden>
                🏢
              </span>
              <button
                type="button"
                className={`tree-node-btn${selectedCompanyId === company.company_id ? " active" : ""}`}
                onClick={() => {
                  setSelectedCompanyId(company.company_id);
                  setSelectedFolderId(folderId);
                  setSelectedVesselId(null);
                }}
              >
                {company.name}
              </button>
            </div>
            {canEdit ? (
              <div className="templates-tree-row-actions">
                <button
                  type="button"
                  className="templates-icon-btn"
                  title="Переименовать"
                  onClick={() => onRenameCompany(company.company_id)}
                >
                  ✎
                </button>
                <button
                  type="button"
                  className="templates-icon-btn templates-icon-btn--danger"
                  title="Удалить"
                  onClick={() => onDeleteCompany(company.company_id)}
                >
                  🗑
                </button>
              </div>
            ) : null}
          </div>
        </div>
      );
    });
  }

  function renderTree(parentId, level) {
    const kids = sortByName(folderChildren(parentId));
    return kids.flatMap((folder) => {
      if (!isFolderVisibleInSearch(folder.folder_id)) return [];
      const hasSubfolders = folderChildren(folder.folder_id).length > 0;
      const expanded = isFolderExpanded(folder.folder_id);
      const pad = 8 + level * 14;
      const row = (
        <div key={folder.folder_id} className="templates-tree-node">
          <div
            className={`templates-tree-row-wrap${
              selectedFolderId === folder.folder_id && !selectedCompanyId
                ? " templates-tree-row-wrap--selected"
                : ""
            }`}
          >
            <div className="templates-tree-row-main" style={{ paddingLeft: `${pad}px` }}>
              {hasSubfolders ? (
                <button
                  type="button"
                  className="templates-tree-chevron"
                  onClick={() => toggleFolderExpanded(folder.folder_id)}
                  aria-label={expanded ? "Свернуть" : "Раскрыть"}
                >
                  <span
                    className={`templates-chevron${expanded ? " templates-chevron--expanded" : ""}`}
                    aria-hidden
                  />
                </button>
              ) : (
                <span className="templates-tree-chevron-spacer" aria-hidden />
              )}
              <span className="templates-folder-glyph" aria-hidden>
                {hasSubfolders && expanded ? "📂" : "📁"}
              </span>
              <button
                type="button"
                className={`tree-node-btn${selectedFolderId === folder.folder_id ? " active" : ""}`}
                onClick={() => {
                  setSelectedFolderId(folder.folder_id);
                  setSelectedCompanyId(null);
                  setSelectedVesselId(null);
                }}
              >
                {folder.name}
              </button>
            </div>
            {canEdit ? (
              <div className="templates-tree-row-actions">
                <button
                  type="button"
                  className="templates-icon-btn"
                  title="Переименовать"
                  onClick={() => onRenameFolder(folder.folder_id)}
                >
                  ✎
                </button>
                <button
                  type="button"
                  className="templates-icon-btn templates-icon-btn--danger"
                  title="Удалить"
                  onClick={() => onDeleteFolder(folder.folder_id)}
                >
                  🗑
                </button>
              </div>
            ) : null}
          </div>
          {expanded ? (
            <>
              {renderCompaniesInFolder(folder.folder_id, level + 1)}
              {renderTree(folder.folder_id, level + 1)}
            </>
          ) : null}
        </div>
      );
      return [row];
    });
  }

  const rootHasSubfolders = rootFolderId != null ? folderChildren(rootFolderId).length > 0 : false;
  const rootExpanded = rootFolderId != null && isFolderExpanded(rootFolderId);

  return (
    <CrmLayout
      title="Company & Vessels"
      subtitle="Папки компаний, суда и плейсхолдеры для DOCX шаблонов."
    >
      <div className="card candidates-card templates-manager-card" data-testid="companies-manager">
        {error ? <p className="error">{error}</p> : null}
        {importMessage ? <p className="muted-text">{importMessage}</p> : null}
        {loading ? <p className="muted-text">Загрузка...</p> : null}
        <div className="templates-manager-layout companies-manager-layout">
          <aside className="templates-tree templates-tree-panel">
            <div className="templates-tree-toolbar">
              {canEdit ? (
                <>
                  <button
                    type="button"
                    className="secondary-btn"
                    onClick={() => onCreateFolder(rootFolderId)}
                    disabled={!rootFolderId}
                  >
                    + Папка
                  </button>
                  <button
                    type="button"
                    className="secondary-btn"
                    onClick={() => onCreateFolder(selectedFolderId)}
                    disabled={!selectedFolderId}
                  >
                    + Подпапка
                  </button>
                  <button
                    type="button"
                    className="secondary-btn"
                    onClick={() => onCreateCompany(selectedFolderId || rootFolderId)}
                    disabled={!selectedFolderId && !rootFolderId}
                  >
                    + Компания
                  </button>
                  <label
                    className={`secondary-btn templates-browse-btn${importingXlsx ? " disabled" : ""}`}
                    title="Колонки: Company, IMO, Vessel name"
                  >
                    {importingXlsx ? "Импорт…" : "Импорт Excel"}
                    <input
                      type="file"
                      accept=".xlsx,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
                      className="hidden-file-input"
                      disabled={importingXlsx || (!selectedFolderId && !rootFolderId)}
                      onChange={onImportXlsx}
                    />
                  </label>
                </>
              ) : null}
              <button type="button" onClick={loadCompanies}>
                Refresh
              </button>
              <input
                type="search"
                className="templates-tree-search"
                placeholder="Поиск папок и компаний…"
                value={treeSearch}
                onChange={(event) => setTreeSearch(event.target.value)}
                aria-label="Поиск"
              />
            </div>
            <div className="templates-tree-scroll">
              <div className="templates-tree-node">
                <div
                  className={`templates-tree-row-wrap templates-tree-row-wrap--root${
                    selectedFolderId === rootFolderId && !selectedCompanyId
                      ? " templates-tree-row-wrap--selected"
                      : ""
                  }`}
                >
                  <div className="templates-tree-row-main templates-tree-row-main--root">
                    {rootFolderId != null && rootHasSubfolders ? (
                      <button
                        type="button"
                        className="templates-tree-chevron"
                        onClick={() => toggleFolderExpanded(rootFolderId)}
                        aria-label={rootExpanded ? "Свернуть" : "Раскрыть"}
                      >
                        <span
                          className={`templates-chevron${rootExpanded ? " templates-chevron--expanded" : ""}`}
                          aria-hidden
                        />
                      </button>
                    ) : (
                      <span className="templates-tree-chevron-spacer" aria-hidden />
                    )}
                    <span className="templates-folder-glyph" aria-hidden>
                      {rootHasSubfolders && rootExpanded ? "📂" : "📁"}
                    </span>
                    <button
                      type="button"
                      className={`tree-node-btn${selectedFolderId === rootFolderId ? " active" : ""}`}
                      onClick={() => {
                        if (rootFolderId != null) {
                          setSelectedFolderId(rootFolderId);
                          setSelectedCompanyId(null);
                          setSelectedVesselId(null);
                        }
                      }}
                      disabled={rootFolderId == null}
                    >
                      Companies
                    </button>
                  </div>
                </div>
                {rootFolderId != null && rootExpanded ? (
                  <>
                    {renderCompaniesInFolder(rootFolderId, 1)}
                    {renderTree(rootFolderId, 1)}
                  </>
                ) : null}
              </div>
            </div>
          </aside>

          <section className="templates-files templates-files-panel companies-vessels-panel">
            {copyHint ? <p className="muted-text">{copyHint}</p> : null}
            <div className="menu-header">
              <h2 style={{ marginBottom: 0 }}>
                {selectedCompany ? selectedCompany.name : "Выберите компанию"}
              </h2>
              {canEdit && selectedCompany ? (
                <button type="button" className="secondary-btn" onClick={openCreateVesselModal}>
                  + Судно
                </button>
              ) : null}
            </div>

            {!selectedCompany ? (
              <p className="empty-row">Выберите компанию в дереве слева, чтобы увидеть суда.</p>
            ) : (
              <>
                <div className="detail-block" data-testid="company-salary-matrix" style={{ marginBottom: "1.25rem" }}>
                  <div className="menu-header" style={{ marginBottom: "0.5rem", alignItems: "flex-start" }}>
                    <h3 style={{ margin: 0 }}>Зарплатные ставки (Company + Rank)</h3>
                    {canEdit ? (
                      <>
                        <button
                          type="button"
                          className={`secondary-btn templates-browse-btn${importingSalaryScale ? " disabled" : ""}`}
                          disabled={importingSalaryScale}
                          data-testid="salary-scale-import-btn"
                          onClick={() => salaryScaleInputRef.current?.click()}
                        >
                          {importingSalaryScale ? "Импорт…" : "Загрузить из Excel"}
                        </button>
                        <input
                          ref={salaryScaleInputRef}
                          type="file"
                          accept=".xlsx,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
                          hidden
                          disabled={importingSalaryScale}
                          onChange={onImportSalaryScale}
                        />
                      </>
                    ) : null}
                  </div>
                  <p className="muted-text">
                    Используются в калькуляторе зарплаты на карточке кандидата. Файл{" "}
                    <strong>Salary Scale.xlsx</strong> — лист DryLog или Chandris для выбранной компании.
                    Должность выбирается из списка; каждая колонка таблицы соответствует полю в форме добавления ниже.
                  </p>
                  {salaryImportMessage ? <p className="success-text">{salaryImportMessage}</p> : null}
                  {salaryTemplatesLoading ? <p className="muted-text">Загрузка матрицы…</p> : null}
                  <div className="table-wrap salary-matrix-table-wrap">
                    <table className="data-table salary-matrix-table">
                      <thead>
                        <tr>
                          {SALARY_MATRIX_COLUMNS.map((col) => (
                            <th key={col.key} title={col.label}>
                              {col.label}
                            </th>
                          ))}
                          {canEdit ? <th className="salary-matrix-actions-col">Действия</th> : null}
                        </tr>
                      </thead>
                      <tbody>
                        {salaryTemplates.length === 0 && !salaryEditingId ? (
                          <tr>
                            <td colSpan={canEdit ? SALARY_MATRIX_COLUMNS.length + 1 : SALARY_MATRIX_COLUMNS.length} className="empty-row">
                              Нет строк — добавьте должность в форме ниже
                            </td>
                          </tr>
                        ) : (
                          salaryTemplates.map((row) => {
                            const isEditing = salaryEditingId === row.template_id;
                            const draft = isEditing ? salaryFormDraft : salaryTemplateToDraft(row);
                            const onDraftChange = (key, value) => {
                              if (isEditing) {
                                setSalaryFormDraft((prev) => ({ ...prev, [key]: value }));
                              }
                            };
                            return (
                              <tr
                                key={row.template_id}
                                className={isEditing ? "salary-matrix-row--editing" : undefined}
                              >
                                {SALARY_MATRIX_COLUMNS.map((col) => (
                                  <td key={col.key}>
                                    {isEditing && canEdit ? (
                                      renderSalaryCell(col, draft, onDraftChange)
                                    ) : (
                                      <span>{row[col.key]}</span>
                                    )}
                                  </td>
                                ))}
                                {canEdit ? (
                                  <td className="salary-matrix-actions-col">
                                    {isEditing ? (
                                      <div className="salary-matrix-row-actions">
                                        <button
                                          type="button"
                                          disabled={salarySaving}
                                          onClick={onSaveSalaryTemplate}
                                        >
                                          {salarySaving ? "…" : "Сохранить"}
                                        </button>
                                        <button
                                          type="button"
                                          className="secondary-btn tiny-btn"
                                          disabled={salarySaving}
                                          onClick={resetSalaryForm}
                                        >
                                          Отмена
                                        </button>
                                      </div>
                                    ) : (
                                      <div className="salary-matrix-row-actions">
                                        <button
                                          type="button"
                                          className="secondary-btn tiny-btn"
                                          disabled={salaryEditingId != null}
                                          onClick={() => startEditSalaryTemplate(row)}
                                        >
                                          Изменить
                                        </button>
                                        <button
                                          type="button"
                                          className="danger-btn tiny-btn"
                                          disabled={salaryEditingId != null}
                                          onClick={() => onDeleteSalaryTemplate(row.template_id)}
                                        >
                                          Удалить
                                        </button>
                                      </div>
                                    )}
                                  </td>
                                ) : null}
                              </tr>
                            );
                          })
                        )}
                      </tbody>
                      {canEdit && !salaryEditingId ? (
                        <tfoot>
                          <tr className="salary-matrix-add-row">
                            {SALARY_MATRIX_COLUMNS.map((col) => (
                              <td key={col.key}>
                                <div className="salary-matrix-field">
                                  <span className="salary-matrix-field-label">{col.label}</span>
                                  {renderSalaryCell(col, salaryFormDraft, (key, value) =>
                                    setSalaryFormDraft((prev) => ({ ...prev, [key]: value }))
                                  )}
                                </div>
                              </td>
                            ))}
                            <td className="salary-matrix-actions-col">
                              <button
                                type="button"
                                className="secondary-btn"
                                disabled={salarySaving}
                                onClick={onSaveSalaryTemplate}
                                data-testid="salary-matrix-add-row"
                              >
                                {salarySaving ? "Сохранение…" : "+ Добавить строку"}
                              </button>
                            </td>
                          </tr>
                        </tfoot>
                      ) : null}
                    </table>
                  </div>
                  {salaryEditingId ? (
                    <p className="muted-text">Завершите редактирование строки или нажмите «Отмена».</p>
                  ) : null}
                </div>

                <input
                  type="search"
                  className="templates-tree-search"
                  placeholder="Поиск по судам…"
                  value={vesselSearch}
                  onChange={(event) => setVesselSearch(event.target.value)}
                  aria-label="Поиск судов"
                />
                <div className="companies-vessels-grid">
                  <div className="companies-vessels-list">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Название</th>
                          <th>IMO</th>
                          <th>Флаг</th>
                          <th>Тип</th>
                          {canEdit ? <th /> : null}
                        </tr>
                      </thead>
                      <tbody>
                        {companyVesselsFiltered.length === 0 ? (
                          <tr>
                            <td colSpan={canEdit ? 5 : 4} className="empty-row">
                              Нет судов
                            </td>
                          </tr>
                        ) : (
                          companyVesselsFiltered.map((vessel) => (
                            <tr
                              key={vessel.vessel_id}
                              className={
                                selectedVesselId === vessel.vessel_id ? "row-selected" : undefined
                              }
                              onClick={() => setSelectedVesselId(vessel.vessel_id)}
                              style={{ cursor: "pointer" }}
                            >
                              <td>{vessel.name}</td>
                              <td>{vessel.imo || "—"}</td>
                              <td>{vessel.flag || "—"}</td>
                              <td>{vessel.vessel_type || "—"}</td>
                              {canEdit ? (
                                <td>
                                  <button
                                    type="button"
                                    className="secondary-btn tiny-btn"
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      openEditVesselModal(vessel);
                                    }}
                                  >
                                    Изменить
                                  </button>
                                  <button
                                    type="button"
                                    className="danger-btn tiny-btn"
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      onDeleteVessel(vessel.vessel_id);
                                    }}
                                  >
                                    Удалить
                                  </button>
                                </td>
                              ) : null}
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>

                  {selectedVessel ? (
                    <aside className="companies-vessel-detail card" data-testid="vessel-detail">
                      <h3>{selectedVessel.name}</h3>
                      <dl className="companies-vessel-fields">
                        {VESSEL_FORM_FIELDS.map(({ key, label }) => (
                          <div key={key}>
                            <dt>{label}</dt>
                            <dd>
                              {selectedVessel[key] == null || selectedVessel[key] === ""
                                ? "—"
                                : selectedVessel[key]}
                            </dd>
                          </div>
                        ))}
                      </dl>
                      <h4>Плейсхолдеры</h4>
                      <ul className="companies-placeholder-list">
                        {Object.entries(selectedVessel.placeholders || {}).map(([field, token]) => (
                          <li key={field}>
                            <span className="muted-text">
                              {VESSEL_PLACEHOLDER_LABELS[field] || field}
                            </span>
                            <code>{token}</code>
                            <button
                              type="button"
                              className="secondary-btn tiny-btn"
                              data-testid={`copy-placeholder-${field}`}
                              onClick={() => onCopyPlaceholder(token)}
                            >
                              Копировать
                            </button>
                          </li>
                        ))}
                      </ul>
                    </aside>
                  ) : (
                    <p className="empty-row">Выберите судно в таблице для просмотра плейсхолдеров.</p>
                  )}
                </div>
              </>
            )}
          </section>
        </div>
      </div>

      {vesselModalOpen ? (
        <div className="modal-overlay" onClick={closeVesselModal}>
          <div
            className="modal-card companies-vessel-form-modal"
            data-testid="vessel-form-modal"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="vessel-form-modal-title"
          >
            <div className="menu-header">
              <h2 id="vessel-form-modal-title">
                {vesselModalMode === "create" ? "Добавить судно" : "Изменить судно"}
              </h2>
              <button type="button" className="secondary-btn tiny-btn" onClick={closeVesselModal} disabled={vesselSaving}>
                Закрыть
              </button>
            </div>
            <form className="detail-grid companies-vessel-form-grid" onSubmit={submitVesselForm}>
              {VESSEL_FORM_FIELDS.map(({ key, label, type, required }) => (
                <label key={key}>
                  <span>{label}</span>
                  {type === "select" ? (
                    <select
                      value={vesselForm[key]}
                      onChange={(event) =>
                        setVesselForm((prev) => ({ ...prev, [key]: event.target.value }))
                      }
                      aria-label={label}
                    >
                      <option value="">— не выбран —</option>
                      {vesselTypeSelectOptions.map((optionLabel) => (
                        <option key={optionLabel} value={optionLabel}>
                          {optionLabel}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type={type === "number" ? "number" : "text"}
                      required={required}
                      min={type === "number" ? 1800 : undefined}
                      max={type === "number" ? 2100 : undefined}
                      value={vesselForm[key]}
                      onChange={(event) =>
                        setVesselForm((prev) => ({ ...prev, [key]: event.target.value }))
                      }
                      aria-label={label}
                      autoFocus={key === "name" && vesselModalMode === "create"}
                    />
                  )}
                </label>
              ))}
              <div className="form-actions" style={{ gridColumn: "1 / -1" }}>
                <button type="submit" className="primary-btn" disabled={vesselSaving}>
                  {vesselSaving ? "Сохранение…" : vesselModalMode === "create" ? "Добавить" : "Сохранить"}
                </button>
                <button type="button" className="secondary-btn" onClick={closeVesselModal} disabled={vesselSaving}>
                  Отмена
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </CrmLayout>
  );
}
