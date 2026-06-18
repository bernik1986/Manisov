import React from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import dayjs from "dayjs";
import {
  createApplication,
  createCandidateComment,
  createCertificate,
  createDocument,
  createFamilyContact,
  createFlagDocument,
  createSeaService,
  deleteAttachment,
  deleteCandidate,
  deleteCandidatePhoto,
  deleteCertificate,
  deleteDocument,
  deleteFamilyContact,
  deleteFlagDocument,
  deleteSeaService,
  fetchCandidateById,
  fetchCompaniesManager,
  fetchTemplatesManager,
  buildSubmissionPack,
  generateCandidateDocument,
  downloadCandidatePhoto,
  uploadAttachment,
  uploadCandidatePhoto,
  updateApplication,
  updateCandidate,
  updateCertificate,
  updateDocument,
  updateFamilyContact,
  updateFlagDocument,
  updateSeaService,
} from "../api";
import { useAuth } from "../context/AuthContext";
import {
  CANONICAL_DOCUMENT_SPECS,
  canonicalDocumentPlaceholderLines,
  findCanonicalSpecForRow,
  orderDocumentsForDisplay,
} from "../canonicalDocuments";
import { findCanonicalVisaSpecForRow, orderVisasForDisplay } from "../canonicalVisas";
import { CANONICAL_POSITION_OPTIONS } from "../canonicalPositions";
import VisasSection, { validateVisaSavePayload, VISA_EDIT_FIELDS } from "./VisasSection";
import {
  buildDiplomaDisplayList,
  CANONICAL_DIPLOMA_SPECS,
  CANONICAL_TANKER_DIPLOMA_SPECS,
  canonicalDiplomaPlaceholderLines,
  DIPLOMA_GROUP,
  TANKER_DIPLOMA_GROUP,
  findCanonicalDiplomaSpec,
  isCanonicalDiplomaItem,
  isCustomDiplomaRow,
} from "../canonicalDiplomas";
import {
  buildMedicalDisplayList,
  CANONICAL_MEDICAL_SPECS,
  canonicalMedicalPlaceholderLines,
  findCanonicalMedicalSpec,
  isCustomMedicalRow,
  MEDICAL_GROUP,
} from "../canonicalMedical";
import {
  buildCertificateDisplayList,
  CANONICAL_BWTS_SPECS,
  CANONICAL_COMPANY_SPECS,
  CANONICAL_CONVENTIONAL_SPECS,
  CANONICAL_ECDIS_SPECS,
  canonicalCertificatePlaceholderLines,
  findCanonicalCertificateSpec,
  isCanonicalCertificateItem,
} from "../canonicalCertificates";
import CertificateRowsTable from "./CertificateRowsTable";
import CertificateInlineAddForm, { createEmptyCertificateDraft } from "./CertificateInlineAddForm";
import { UKR_CONTRACT_FIELD_DEFS, createEmptyUkrContractForm, parseUkrContractJson } from "../ukrContractFields";
import CertificateValidityControls from "./CertificateValidityControls";
import SalaryCalculatorSection from "./SalaryCalculatorSection";
import ContractSection from "./ContractSection";
import DateDdMmYyyyInput from "./DateDdMmYyyyInput";
import FileDropzone from "./FileDropzone";
import {
  VALIDITY_MODE,
  certificatePayloadFromDraft,
  formatCertificateExpiryDisplay,
  inferValidityMode,
  needsValidityAssist,
  applyPlus5Years,
  mergeCertificateDateChange,
  patchCertificateWithValidity,
} from "../utils/certificateValidity";
import { SEA_SERVICE_DEFAULT_REMARKS, withComputedContractDuration } from "../utils/seaServiceDuration";
import ScanDownloadLink from "./ScanDownloadLink";
import SeaServiceSection from "./SeaServiceSection";
import { toIsoDateString, toUiDateString, validateUiDateStringForSubmit } from "../utils/dateInputSupport";

const readOnlyCandidateKeys = new Set(["candidate_id", "created_at", "updated_at"]);
const uppercaseCandidateNameFields = new Set([
  "surname",
  "first_name",
  "middle_name",
  "full_name",
  "latin_full_name",
  "native_full_name",
]);

function _uppercaseCandidateName(value) {
  return String(value ?? "").toUpperCase();
}

function _ageFromBirthDateUi(birthDateUi) {
  const iso = toIsoDateString(birthDateUi);
  if (!iso) return null;
  const b = dayjs(iso);
  if (!b.isValid()) return null;
  const today = dayjs().startOf("day");
  const years = today.diff(b, "year");
  if (!Number.isFinite(years) || years < 0 || years > 120) return null;
  return String(years);
}

function _composeUkrFullNameUa({ ukr_surname, ukr_first_name, ukr_patronymic }) {
  const parts = [ukr_surname, ukr_first_name, ukr_patronymic]
    .map((v) => String(v ?? "").trim())
    .filter(Boolean);
  return parts.join(" ");
}

function _composeFullNameFromParts(surname, firstName) {
  const parts = [surname, firstName].map((value) => _uppercaseCandidateName(value).trim()).filter(Boolean);
  return parts.join(" ");
}

function _withComposedFullNames(record) {
  const normalized = { ...record };
  uppercaseCandidateNameFields.forEach((field) => {
    if (field in normalized) normalized[field] = _uppercaseCandidateName(normalized[field]);
  });
  const composed = _composeFullNameFromParts(normalized?.surname, normalized?.first_name);
  if (!composed) {
    return normalized;
  }
  return {
    ...normalized,
    full_name: composed,
    latin_full_name: composed,
  };
}

function sortSeaServiceRows(rows) {
  const arr = Array.isArray(rows) ? rows.slice() : [];
  const toKey = (v) => {
    if (!v) return Number.NEGATIVE_INFINITY;
    const text = String(v).trim();
    let d = dayjs(text);
    if (!d.isValid()) {
      const m = text.match(/^(\d{2})-(\d{2})-(\d{4})$/);
      if (m) {
        const [, dd, mm, yyyy] = m;
        d = dayjs(`${yyyy}-${mm}-${dd}`);
      }
    }
    return d.isValid() ? d.valueOf() : Number.NEGATIVE_INFINITY;
  };
  return arr.sort((a, b) => {
    const aTop = Math.max(toKey(a?.sign_on_date), toKey(a?.sign_off_date));
    const bTop = Math.max(toKey(b?.sign_on_date), toKey(b?.sign_off_date));
    const byTopDate = bTop - aTop;
    if (byTopDate !== 0) return byTopDate;
    const bySignOn = toKey(b?.sign_on_date) - toKey(a?.sign_on_date);
    if (bySignOn !== 0) return bySignOn;
    return Number(b?.sea_service_id || b?.id || 0) - Number(a?.sea_service_id || a?.id || 0);
  });
}

const candidateFieldGroups = [
  {
    title: "Профиль кандидата / основная карточка",
    fields: [
      ["candidate_id", "Candidate ID"],
      ["company_id", "Company"],
      ["application_id", "Application ID"],
      ["erp_no", "ERP No"],
      ["e_registration_no", "E-registration No"],
      ["application_form_no", "Application Form No"],
      ["cv_prepared_by", "CV Prepared By"],
      ["record_status", "Record Status"],
      ["source_form_type", "Source Form Type"],
      ["source_file_name", "Source File Name"],
    ],
  },
  {
    title: "Персональные данные",
    fields: [
      ["surname", "Фамилия"],
      ["first_name", "Имя"],
      ["middle_name", "Отчество"],
      ["full_name", "Полное имя"],
      ["latin_full_name", "Latin Full Name"],
      ["native_full_name", "Native Full Name"],
      ["date_of_birth", "Дата рождения"],
      ["place_of_birth", "Место рождения"],
      ["country_of_birth", "Страна рождения"],
      ["nationality", "Национальность"],
      ["citizenship", "Гражданство"],
      ["age", "Возраст"],
      ["gender", "Пол"],
      ["marital_status", "Семейное положение"],
      ["primary_phone", "Основной телефон"],
      ["secondary_phone", "Доп. телефон"],
      ["mobile_phone", "Мобильный"],
      ["telephone_no", "Telephone No"],
      ["email", "Email"],
      ["secondary_email", "Secondary Email"],
      ["skype_id", "Skype"],
      ["permanent_address", "Permanent Address"],
      ["home_address", "Home Address"],
      ["current_address", "Current Address"],
      ["city", "City"],
      ["region", "Region"],
      ["postal_code", "Postal Code"],
      ["country", "Country"],
    ],
  },
  {
    title: "Семья / dependants / next of kin / beneficiary",
    fields: [
      ["father_name", "Имя отца"],
      ["mother_name", "Имя матери"],
      ["spouse_name", "Spouse"],
      ["number_of_children", "Number of Children"],
      ["children_under_18_count", "Children Under 18"],
      ["dependants_count", "Dependants Count"],
      ["sons_count", "Sons Count"],
      ["daughters_count", "Daughters Count"],
      ["beneficiary_full_name", "Beneficiary Name"],
      ["beneficiary_relationship", "Beneficiary Relationship"],
      ["beneficiary_address", "Beneficiary Address"],
      ["beneficiary_phone", "Beneficiary Phone"],
      ["next_of_kin_relationship", "Next of Kin Relationship"],
      ["next_of_kin_surname", "Next of Kin Surname"],
      ["next_of_kin_first_name", "Next of Kin First Name"],
      ["next_of_kin_full_name", "Next of Kin Full Name"],
      ["next_of_kin_address", "Next of Kin Address"],
      ["next_of_kin_phone", "Next of Kin Phone"],
    ],
  },
  {
    title: "Образование, языки и физические данные",
    fields: [
      ["highest_educational_attainment", "Education Level"],
      ["school_name", "School"],
      ["graduation_year", "Graduation Year"],
      ["education_notes", "Education Notes"],
      ["native_language", "Native Language"],
      ["english_level", "English Level"],
      ["english_certificate", "English Certificate"],
      ["other_languages", "Other Languages"],
      ["height_cm", "Height (cm)"],
      ["height_m", "Height (m)"],
      ["weight_kg", "Weight (kg)"],
      ["distinctive_marks", "Distinctive Marks"],
    ],
  },
  {
    title: "Профессиональные данные и vessel experience",
    fields: [
      ["current_rank", "Current Rank"],
      ["certificate_of_competency_rank", "COC Rank"],
      ["certificate_of_competency_number", "COC Number"],
      ["watchkeeping_capacity", "Watchkeeping Capacity"],
      ["total_sea_service", "Total Sea Service"],
      ["total_sea_service_in_rank", "Sea Service In Rank"],
      ["years_in_rank", "Years in Rank"],
      ["years_in_this_type_of_vessel", "Years in Vessel Type"],
      ["years_in_all_types_of_tankers", "Years in Tankers"],
      ["years_as_watch_officer", "Years as Watch Officer"],
      ["total_years_of_sea_service", "Total Years Of Sea Service"],
      ["rank_experience_summary", "Rank Experience Summary"],
      ["bulk_carrier_years_in_rank", "Bulk Carrier Years in Rank"],
      ["bulk_carrier_years_in_vessel_type", "Bulk Carrier Years in Vessel Type"],
      ["tanker_years_in_rank", "Tanker Years in Rank"],
      ["tanker_years_in_this_tanker_type", "Tanker Years in Tanker Type"],
      ["tanker_years_in_all_tanker_types", "Tanker Years in All Tankers"],
      ["watch_officer_since_year", "Watch Officer Since Year"],
      ["oil_tanker_experience", "Oil Tanker Experience"],
      ["chemical_tanker_experience", "Chemical Tanker Experience"],
      ["gas_tanker_experience", "Gas Tanker Experience"],
      ["lng_experience", "LNG Experience"],
      ["lpg_experience", "LPG Experience"],
      ["container_experience", "Container Experience"],
      ["bulk_carrier_experience", "Bulk Carrier Experience"],
      ["general_cargo_experience", "General Cargo Experience"],
      ["offshore_experience", "Offshore Experience"],
    ],
  },
  {
    title: "Медицинские и визовые summary поля",
    fields: [
      ["medical_fitness_certificate_number", "Medical Fitness Number"],
      ["medical_fitness_issue_date", "Medical Fitness Issue Date"],
      ["medical_fitness_expiry_date", "Medical Fitness Expiry Date"],
      ["yellow_fever_issue_date", "Yellow Fever Issue Date"],
      ["yellow_fever_expiry_date", "Yellow Fever Expiry Date"],
      ["yellow_fever_unlimited", "Yellow Fever Unlimited"],
      ["visa_status_note", "Visa Status Note"],
      ["passport_visa_status_note", "Passport / Visa Note (info list)"],
      ["desirable_salary_usd", "Desirable Salary USD"],
      ["rejoin_bonus_usd", "Rejoin Bonus USD"],
      ["submission_contract_duration_text", "Contract Duration (submission)"],
      ["ecdis_systems_text", "ECDIS Systems"],
      ["vaccination_summary", "Vaccination Summary"],
      ["leaving_reason", "Leaving Reason"],
      ["employer_reference_note", "Employer Reference Note"],
      ["coc_gmdss_expiry_note", "COC / GMDSS Expiry Note"],
      ["coc_has_qr_codes", "COC has QR codes"],
      ["passport_number", "Passport Number"],
      ["passport_issue_date", "Passport Issue Date"],
      ["passport_expiry_date", "Passport Expiry Date"],
      ["passport_place_of_issue", "Passport Place Of Issue"],
      ["seaman_book_number", "Seaman Book Number"],
    ],
  },
];

const applicationFields = [
  ["position_applied_for", "Position Applied For"],
  ["rank_applied_for", "Rank Applied For"],
  ["willing_to_accept_lower_rank", "Willing To Accept Lower Rank"],
  ["proposed_vessel", "Proposed Vessel"],
  ["date_applied", "Date Applied"],
  ["date_available", "Date Available"],
  ["last_salary_usd", "Last Salary USD"],
  ["applicant_type", "Applicant Type"],
  ["recommended_by_ex_crew", "Recommended by Ex Crew"],
  ["recommended_by_ex_crew_name", "Ex Crew Name"],
  ["recommended_by_others", "Recommended by Others"],
  ["recommended_by_others_name", "Others Name"],
];

const APPLICATION_BOOLEAN_FIELDS = new Set([
  "willing_to_accept_lower_rank",
  "recommended_by_ex_crew",
  "recommended_by_others",
]);

function boolToSelect(v) {
  if (v === true || v === "true" || v === 1) return "true";
  if (v === false || v === "false" || v === 0) return "false";
  return "";
}

const editableDocumentFields = new Set([
  "document_category",
  "document_type",
  "document_name_raw",
  "document_number",
  "issuing_authority",
  "place_of_issue",
  "date_of_issue",
  "date_of_expiry",
  "validity_status",
  "unlimited_validity",
  "country_of_issue",
  "remarks",
  "scan_file",
  "verified",
]);

const editableCertificateFields = new Set([
  "certificate_group",
  "certificate_type",
  "certificate_name_raw",
  "certificate_code",
  "certificate_number",
  "competency_rank",
  "issuing_authority",
  "date_issued",
  "expiry_date",
  "unlimited_validity",
  "country_of_issue",
  "is_present",
  "remarks",
  "scan_file",
]);

const editableSeaServiceFields = new Set([
  "vessel_name",
  "vessel_type",
  "vessel_subtype",
  "flag",
  "imo_number",
  "year_built",
  "dwt",
  "grt",
  "main_engine",
  "engine_power",
  "ecdis_dg_maker",
  "rank_on_vessel",
  "sign_on_date",
  "sign_off_date",
  "contract_duration",
  "employer",
  "manning_agency",
  "trade_area",
  "cargo_type",
  "remarks",
  "total_sea_service_duration",
  "total_sea_service_by_rank",
  "total_sea_service_by_vessel_type",
  "tanker_service_duration",
  "bulk_service_duration",
  "watch_officer_experience_duration",
]);

const editableFamilyContactFields = new Set([
  "full_name",
  "relationship_to_candidate",
  "phone",
  "email",
  "address",
]);

const editableFlagDocumentFields = new Set([
  "flag_country",
  "flag_document_type",
  "rank",
  "doc_number",
  "date_of_issuance",
  "date_of_expiry",
  "remarks",
]);

function pickEditableFields(source, allowed) {
  return Object.fromEntries(Object.entries(source || {}).filter(([key]) => allowed.has(key)));
}

function isDateLikeField(fieldName) {
  if (typeof fieldName !== "string") {
    return false;
  }
  const lower = fieldName.toLowerCase();
  if (lower === "created_at" || lower === "updated_at" || lower === "uploaded_at") {
    return false;
  }
  /* `_date_`: e.g. ukr_passport_issue_date_ua; avoid bare "date" in relationship_to_candidate */
  if (lower.endsWith("_date") || lower.startsWith("date_") || lower.includes("_date_")) {
    return true;
  }
  return false;
}

/** Returns first validation error message or null. */
function firstBadDateInRecord(record, allowedFieldSet = null) {
  for (const [key, val] of Object.entries(record || {})) {
    if (!isDateLikeField(key)) {
      continue;
    }
    if (allowedFieldSet && !allowedFieldSet.has(key)) {
      continue;
    }
    const r = validateUiDateStringForSubmit(val);
    if (!r.ok) {
      return r.message;
    }
  }
  return null;
}

/** Compare issue/expiry in ISO yyyy-mm-dd; returns error message if expiry is before issue. */
function issueExpiryRangeErrorFromIsoOrNull(issuedIso, expiryIso) {
  const issued = issuedIso ? toIsoDateString(issuedIso) : null;
  const expiry = expiryIso ? toIsoDateString(expiryIso) : null;
  if (!issued || !expiry || expiry >= issued) {
    return null;
  }
  return "Дата окончания не может быть раньше даты выдачи";
}

function shouldShowAsPopupError(message) {
  return message === "Дата окончания не может быть раньше даты выдачи";
}

function mapDateFields(values, target = "ui") {
  const source = values || {};
  return Object.fromEntries(
    Object.entries(source).map(([key, value]) => {
      if (!isDateLikeField(key) || value === null || value === undefined || value === "") {
        return [key, value];
      }
      if (target === "api") {
        const iso = toIsoDateString(value);
        return [key, iso];
      }
      return [key, toUiDateString(value)];
    })
  );
}

/** Drop empty strings so FastAPI does not get "" for optional date/fields (Pydantic rejects). */
function omitEmptyPayloadValues(obj) {
  if (!obj || typeof obj !== "object") {
    return obj;
  }
  return Object.fromEntries(
    Object.entries(obj).filter(([, v]) => v !== "" && v !== null && v !== undefined)
  );
}

/** Flag document PUT: empty UI fields must become explicit JSON null so backend updates columns (exclude_unset skips omitted keys). */
function buildFlagDocumentUpdatePayload(draft) {
  const mapped = mapDateFields(pickEditableFields(draft, editableFlagDocumentFields), "api");
  const out = {};
  for (const key of editableFlagDocumentFields) {
    if (!Object.prototype.hasOwnProperty.call(mapped, key)) {
      continue;
    }
    const raw = mapped[key];
    if (raw === undefined) {
      continue;
    }
    if (isDateLikeField(key)) {
      out[key] = raw === null || raw === "" ? null : raw;
      continue;
    }
    if (typeof raw === "string") {
      out[key] = raw.trim() === "" ? null : raw;
    } else {
      out[key] = raw;
    }
  }
  return out;
}

/** Family contact PUT: cleared optional fields become explicit JSON null (same as flag documents / exclude_unset). */
function buildFamilyContactUpdatePayload(draft) {
  const mapped = mapDateFields(pickEditableFields(draft, editableFamilyContactFields), "api");
  const out = {};
  for (const key of editableFamilyContactFields) {
    if (!Object.prototype.hasOwnProperty.call(mapped, key)) {
      continue;
    }
    const raw = mapped[key];
    if (raw === undefined) {
      continue;
    }
    if (isDateLikeField(key)) {
      out[key] = raw === null || raw === "" ? null : raw;
      continue;
    }
    if (typeof raw === "string") {
      out[key] = raw.trim() === "" ? null : raw;
    } else {
      out[key] = raw;
    }
  }
  return out;
}

/** Generic PUT payload: when user clears a field, send explicit null so backend updates DB column. */
function buildNullableUpdatePayload(draft, allowedFields) {
  const mapped = mapDateFields(pickEditableFields(draft, allowedFields), "api");
  const out = {};
  for (const key of allowedFields) {
    if (!Object.prototype.hasOwnProperty.call(mapped, key)) {
      continue;
    }
    const raw = mapped[key];
    if (raw === undefined) {
      continue;
    }
    if (isDateLikeField(key)) {
      out[key] = raw === null || raw === "" ? null : raw;
      continue;
    }
    if (typeof raw === "string") {
      out[key] = raw.trim() === "" ? null : raw;
    } else {
      out[key] = raw;
    }
  }
  return out;
}

function buildApplicationApiPayload(draft) {
  const raw = {};
  for (const [field] of applicationFields) {
    const v = draft[field];
    if (APPLICATION_BOOLEAN_FIELDS.has(field)) {
      raw[field] = v === "" || v === null || v === undefined ? null : v === "true" || v === true;
    } else if (field === "last_salary_usd") {
      const t = String(v ?? "").trim().replace(",", ".");
      if (t === "") {
        raw[field] = null;
      } else {
        const n = Number(t);
        raw[field] = Number.isNaN(n) ? null : n;
      }
    } else if (isDateLikeField(field)) {
      raw[field] = String(v ?? "").trim() === "" ? null : v;
    } else {
      raw[field] = String(v ?? "").trim() === "" ? null : v;
    }
  }
  return mapDateFields(raw, "api");
}

function getId(item, fallbackKeys = []) {
  for (const key of fallbackKeys) {
    if (item?.[key] !== undefined && item?.[key] !== null) {
      return item[key];
    }
  }
  return item?.id;
}

function getCertificateExpiryClass(cert) {
  if (cert?.unlimited_validity === true) {
    return "";
  }
  return getExpiryClass(cert?.expiry_date);
}

function getExpiryClass(expiryDate) {
  if (!expiryDate) {
    return "";
  }

  const parsed = dayjs(toIsoDateString(expiryDate) || expiryDate);
  if (!parsed.isValid()) {
    return "";
  }

  const daysToExpiry = parsed.startOf("day").diff(dayjs().startOf("day"), "day");
  if (daysToExpiry < 0) {
    return "expired";
  }
  if (daysToExpiry < 240) {
    return "warning";
  }
  return "";
}

function displayValue(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}

function formatCommentDate(value) {
  if (!value) return "";
  const parsed = dayjs(value);
  return parsed.isValid() ? parsed.format("DD.MM.YYYY HH:mm") : String(value);
}

const CERTIFICATE_EDIT_SECTIONS = new Set([
  "certificates",
  "diplomas",
  "tankerDiplomas",
  "medicalDocuments",
  "conventionalCerts",
  "ecdisCerts",
  "companyCerts",
  "bwtsCerts",
]);

const SECTION = {
  RECRUITMENT: "recruitment",
  SALARY_CALCULATOR: "salary_calculator",
  CONTRACT: "contract",
  COMMENTS: "comments",
  DOCUMENTS: "documents",
  VISAS: "visas",
  DIPLOMAS: "diplomas",
  MEDICINE: "medicine",
  CERTIFICATES: "certificates",
  SEA_SERVICE: "sea_service",
  FLAG_DOCUMENTS: "flag_documents",
  FAMILY_CONTACTS: "family_contacts",
};

function profileSectionId(title) {
  return `profile:${title}`;
}

/** Tabs for candidate card (trial UI): one section open at a time. */
const CANDIDATE_SECTION_NAV_ITEMS = [
  ...candidateFieldGroups.map((group) => ({
    id: profileSectionId(group.title),
    label: group.title.length > 44 ? `${group.title.slice(0, 42)}…` : group.title,
  })),
  { id: SECTION.RECRUITMENT, label: "Заявка / recruitment" },
  { id: SECTION.SALARY_CALCULATOR, label: "Калькулятор зарплаты" },
  { id: SECTION.CONTRACT, label: "Контракт" },
  { id: SECTION.COMMENTS, label: "Комментарии" },
  { id: SECTION.DOCUMENTS, label: "Documents" },
  { id: SECTION.VISAS, label: "Визы" },
  { id: SECTION.DIPLOMAS, label: "Diplomas" },
  { id: SECTION.MEDICINE, label: "Медицина" },
  { id: SECTION.CERTIFICATES, label: "Certificates" },
  { id: SECTION.SEA_SERVICE, label: "Sea service" },
  { id: SECTION.FLAG_DOCUMENTS, label: "Flag documents" },
  { id: SECTION.FAMILY_CONTACTS, label: "Family contacts" },
];

function CollapsibleDetailBlock({ sectionId, title, expanded, onToggle = () => {}, children, panelOnly = false }) {
  if (panelOnly) {
    if (!expanded) {
      return null;
    }
    return (
      <div className="detail-block detail-block--tab-panel" data-section-panel={sectionId}>
        <h3 className="detail-block__panel-title">{title}</h3>
        <div className="detail-block__body">{children}</div>
      </div>
    );
  }
  return (
    <div className="detail-block detail-block--collapsible">
      <button type="button" className="detail-block__header" aria-expanded={expanded} onClick={() => onToggle(sectionId)}>
        <span className="detail-block__chevron" aria-hidden>
          {expanded ? "▾" : "▸"}
        </span>
        <span className="detail-block__title-text">{title}</span>
      </button>
      {expanded ? <div className="detail-block__body">{children}</div> : null}
    </div>
  );
}

export default function CandidateDetail({ candidateId, focusTarget = "" }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const canEditUkrContract = user?.role === "admin" || user?.role === "recruiter";
  const canEditRelations = user?.role === "admin" || user?.role === "recruiter";
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [candidate, setCandidate] = useState({});
  const [candidatePhoto, setCandidatePhoto] = useState(null);
  const [candidatePhotoUrl, setCandidatePhotoUrl] = useState("");
  const [candidatePhotoBusy, setCandidatePhotoBusy] = useState(false);
  const [candidatePhotoError, setCandidatePhotoError] = useState("");
  const [applications, setApplications] = useState([]);
  const [recruitmentDraft, setRecruitmentDraft] = useState({});
  const [recruitmentSaving, setRecruitmentSaving] = useState(false);
  const [familyContacts, setFamilyContacts] = useState([]);
  const [flagDocuments, setFlagDocuments] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [visas, setVisas] = useState([]);
  const [newVisaDraft, setNewVisaDraft] = useState({
    mode: "",
    customName: "",
    document_number: "",
    date_of_issue: "",
    date_of_expiry: "",
  });
  const [certificates, setCertificates] = useState([]);
  const [conventionalCertificates, setConventionalCertificates] = useState([]);
  const [ecdisCertificates, setEcdisCertificates] = useState([]);
  const [companyCertificates, setCompanyCertificates] = useState([]);
  const [bwtsCertificates, setBwtsCertificates] = useState([]);
  const [diplomas, setDiplomas] = useState([]);
  const [tankerDiplomas, setTankerDiplomas] = useState([]);
  const [medicalDocuments, setMedicalDocuments] = useState([]);
  const [seaService, setSeaService] = useState([]);
  const [attachments, setAttachments] = useState([]);
  const [comments, setComments] = useState([]);
  const [commentDraft, setCommentDraft] = useState("");
  const [commentSaving, setCommentSaving] = useState(false);
  const [attachmentBusy, setAttachmentBusy] = useState({});
  const [attachmentErrors, setAttachmentErrors] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [popupError, setPopupError] = useState("");
  const [templatesModalOpen, setTemplatesModalOpen] = useState(false);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [templatesError, setTemplatesError] = useState("");
  const [templateFolders, setTemplateFolders] = useState([]);
  const [templateFiles, setTemplateFiles] = useState([]);
  const [templatesRootFolderId, setTemplatesRootFolderId] = useState(null);
  const [expandedTemplateFolderIds, setExpandedTemplateFolderIds] = useState([]);
  const [selectedTemplateFolderId, setSelectedTemplateFolderId] = useState(null);
  const [selectedTemplateIds, setSelectedTemplateIds] = useState([]);
  const [generatingTemplates, setGeneratingTemplates] = useState(false);
  const [podachaModalOpen, setPodachaModalOpen] = useState(false);
  const [podachaLoading, setPodachaLoading] = useState(false);
  const [podachaBuilding, setPodachaBuilding] = useState(false);
  const [podachaError, setPodachaError] = useState("");
  const [openingVessel, setOpeningVessel] = useState("");
  const [previousVessel, setPreviousVessel] = useState("");
  const [selectedPodachaTemplateIds, setSelectedPodachaTemplateIds] = useState([]);
  const [selectedPodachaAttachmentIds, setSelectedPodachaAttachmentIds] = useState([]);
  const [includeCandidatePhotoInPodacha, setIncludeCandidatePhotoInPodacha] = useState(false);
  const [ukrContractModalOpen, setUkrContractModalOpen] = useState(false);
  const [ukrContractForm, setUkrContractForm] = useState(() => createEmptyUkrContractForm());
  const [ukrContractSaving, setUkrContractSaving] = useState(false);
  const [companiesList, setCompaniesList] = useState([]);
  const [vesselsList, setVesselsList] = useState([]);
  const [seaServiceModalOpen, setSeaServiceModalOpen] = useState(false);
  /** Single open section for tab navigation (click same tab again to close). */
  const [expandedSections, setExpandedSections] = useState(() => new Set([CANDIDATE_SECTION_NAV_ITEMS[0].id]));
  const [savingProfile, setSavingProfile] = useState(false);

  const closeSeaServiceModal = useCallback(() => {
    setSeaServiceModalOpen(false);
    setExpandedSections(new Set([CANDIDATE_SECTION_NAV_ITEMS[0].id]));
  }, []);

  const selectSectionTab = useCallback((sectionId) => {
    if (sectionId === SECTION.SEA_SERVICE) {
      setSeaServiceModalOpen(true);
      setExpandedSections(new Set([SECTION.SEA_SERVICE]));
      return;
    }
    setSeaServiceModalOpen(false);
    // Keep exactly one section open — do not clear all tabs on a second click (avoids empty panel / missing add form).
    setExpandedSections(new Set([sectionId]));
  }, []);

  useEffect(() => {
    if (!seaServiceModalOpen) return undefined;
    function onKeyDown(event) {
      if (event.key === "Escape") {
        closeSeaServiceModal();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [seaServiceModalOpen, closeSeaServiceModal]);
  const [editingRows, setEditingRows] = useState({
    documents: null,
    visas: null,
    diplomas: null,
    tankerDiplomas: null,
    medicalDocuments: null,
    conventionalCerts: null,
    ecdisCerts: null,
    companyCerts: null,
    bwtsCerts: null,
    certificates: null,
    seaService: null,
    familyContacts: null,
    flagDocuments: null,
  });
  const [newRows, setNewRows] = useState({
    document: { document_type: "", document_number: "", date_of_issue: "", issuing_authority: "", date_of_expiry: "" },
    certificate: createEmptyCertificateDraft(),
    diploma: createEmptyCertificateDraft(),
    tankerDiploma: createEmptyCertificateDraft(),
    medicalDocument: createEmptyCertificateDraft(),
    seaService: {
      vessel_name: "",
      rank_on_vessel: "",
      ecdis_dg_maker: "",
      sign_on_date: "",
      sign_off_date: "",
      remarks: SEA_SERVICE_DEFAULT_REMARKS,
    },
    familyContact: { full_name: "", relationship_to_candidate: "", phone: "", email: "", address: "" },
    flagDocument: {
      flag_country: "",
      flag_document_type: "",
      rank: "",
      doc_number: "",
      date_of_issuance: "",
      date_of_expiry: "",
      remarks: "",
    },
  });
  const [editDrafts, setEditDrafts] = useState({
    documents: {},
    visas: {},
    diplomas: {},
    tankerDiplomas: {},
    medicalDocuments: {},
    conventionalCerts: {},
    ecdisCerts: {},
    companyCerts: {},
    bwtsCerts: {},
    certificates: {},
    seaService: {},
    familyContacts: {},
    flagDocuments: {},
  });

  const templatesById = useMemo(() => {
    const map = new Map();
    templateFolders.forEach((item) => map.set(item.folder_id, item));
    return map;
  }, [templateFolders]);

  const templatesRootFolderName = useMemo(() => {
    const root = templateFolders.find((folder) => folder.folder_id === templatesRootFolderId);
    return root?.name || "Templates";
  }, [templateFolders, templatesRootFolderId]);

  const displayDocuments = useMemo(() => orderDocumentsForDisplay(documents), [documents]);
  const displayVisas = useMemo(() => orderVisasForDisplay(visas), [visas]);
  const editableVisaFields = useMemo(() => new Set(VISA_EDIT_FIELDS), []);

  const allCertificateRows = useMemo(() => {
    const rows = [];
    const seen = new Set();
    for (const list of [
      certificates,
      conventionalCertificates,
      ecdisCertificates,
      companyCertificates,
      bwtsCertificates,
    ]) {
      for (const item of list || []) {
        if (!item || isCanonicalDiplomaItem(item)) continue;
        const id = item.certificate_id;
        if (id != null && seen.has(id)) continue;
        if (id != null) seen.add(id);
        rows.push(item);
      }
    }
    return rows;
  }, [certificates, conventionalCertificates, ecdisCertificates, companyCertificates, bwtsCertificates]);

  const displayDiplomas = useMemo(
    () => buildDiplomaDisplayList(diplomas, null, CANONICAL_DIPLOMA_SPECS),
    [diplomas]
  );

  const displayTankerDiplomas = useMemo(
    () => buildDiplomaDisplayList(tankerDiplomas, null, CANONICAL_TANKER_DIPLOMA_SPECS),
    [tankerDiplomas]
  );

  const displayMedicalDocuments = useMemo(
    () => buildMedicalDisplayList(medicalDocuments, null, CANONICAL_MEDICAL_SPECS),
    [medicalDocuments]
  );

  const displayConventionalCertificates = useMemo(
    () => buildCertificateDisplayList(conventionalCertificates, allCertificateRows, CANONICAL_CONVENTIONAL_SPECS),
    [conventionalCertificates, allCertificateRows]
  );

  const displayEcdisCertificates = useMemo(
    () => buildCertificateDisplayList(ecdisCertificates, allCertificateRows, CANONICAL_ECDIS_SPECS),
    [ecdisCertificates, allCertificateRows]
  );

  const displayCompanyCertificates = useMemo(
    () => buildCertificateDisplayList(companyCertificates, allCertificateRows, CANONICAL_COMPANY_SPECS),
    [companyCertificates, allCertificateRows]
  );

  const displayBwtsCertificates = useMemo(
    () => buildCertificateDisplayList(bwtsCertificates, allCertificateRows, CANONICAL_BWTS_SPECS),
    [bwtsCertificates, allCertificateRows]
  );

  const displayOtherCertificates = useMemo(
    () => allCertificateRows.filter((item) => !isCanonicalCertificateItem(item)),
    [allCertificateRows]
  );

  function getCertificateDisplayList(section) {
    switch (section) {
      case "diplomas":
        return displayDiplomas;
      case "tankerDiplomas":
        return displayTankerDiplomas;
      case "medicalDocuments":
        return displayMedicalDocuments;
      case "conventionalCerts":
        return displayConventionalCertificates;
      case "ecdisCerts":
        return displayEcdisCertificates;
      case "companyCerts":
        return displayCompanyCertificates;
      case "bwtsCerts":
        return displayBwtsCertificates;
      default:
        return displayOtherCertificates;
    }
  }

  function documentRowCode(item) {
    return item.document_code || item.document_category || "";
  }

  function isCanonicalDocumentRow(item) {
    if (documentRowCode(item)) return true;
    return CANONICAL_DOCUMENT_SPECS.some((spec) => spec.documentType === String(item.document_type || "").trim());
  }

  const templateOptions = useMemo(() => {
    const renderableTemplateExt = /\.(docx|xlsx|xlsm)$/i;
    function buildFolderPath(folderId) {
      const parts = [];
      let currentId = folderId;
      const seen = new Set();
      while (currentId && !seen.has(currentId)) {
        seen.add(currentId);
        const node = templatesById.get(currentId);
        if (!node) break;
        parts.unshift(node.name);
        currentId = node.parent_id;
      }
      return parts.join(" / ");
    }
    return templateFiles
      .slice()
      .filter((item) => renderableTemplateExt.test(String(item.file_name || "")))
      .sort((a, b) => String(a.file_name || "").localeCompare(String(b.file_name || ""), "en"))
      .map((item) => ({
        id: item.template_file_id,
        fileName: item.file_name,
        folderPath: buildFolderPath(item.folder_id),
      }));
  }, [templateFiles, templatesById]);

  const templatesChildrenMap = useMemo(() => {
    return templateFolders.reduce((acc, folder) => {
      const parentKey = folder.parent_id ?? "__root__";
      if (!acc[parentKey]) {
        acc[parentKey] = [];
      }
      acc[parentKey].push(folder);
      return acc;
    }, {});
  }, [templateFolders]);

  const templatesFilesByFolder = useMemo(() => {
    return templateOptions.reduce((acc, file) => {
      const original = templateFiles.find((item) => item.template_file_id === file.id);
      const folderKey = original?.folder_id ?? "__root__";
      if (!acc[folderKey]) {
        acc[folderKey] = [];
      }
      acc[folderKey].push(file);
      return acc;
    }, {});
  }, [templateOptions, templateFiles]);

  const selectedFolderFiles = useMemo(() => {
    const key = selectedTemplateFolderId ?? "__root__";
    return (templatesFilesByFolder[key] || [])
      .slice()
      .sort((a, b) => String(a.fileName || "").localeCompare(String(b.fileName || ""), "ru"));
  }, [selectedTemplateFolderId, templatesFilesByFolder]);

  useEffect(() => {
    if (!focusTarget) return;
    const timer = window.setTimeout(() => {
      const targetNode = document.querySelector(`[data-scan-target="${focusTarget}"]`);
      if (targetNode) {
        targetNode.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 150);
    return () => window.clearTimeout(timer);
  }, [focusTarget, documents, visas, certificates, diplomas, tankerDiplomas, medicalDocuments, conventionalCertificates, ecdisCertificates, companyCertificates, bwtsCertificates, flagDocuments, expandedSections]);

  function notifyUserError(message) {
    const text = String(message || "").trim();
    if (!text) return;
    if (shouldShowAsPopupError(text)) {
      setPopupError(text);
      return;
    }
    setError(text);
  }

  useEffect(() => {
    loadCandidate({ showLoader: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidateId]);

  useEffect(() => {
    let active = true;
    let objectUrl = "";
    if (!candidatePhoto?.attachment_id) {
      setCandidatePhotoUrl("");
      return () => {};
    }
    downloadCandidatePhoto(candidateId)
      .then((blob) => {
        if (!active) return;
        objectUrl = window.URL.createObjectURL(blob);
        setCandidatePhotoUrl(objectUrl);
      })
      .catch(() => {
        if (active) setCandidatePhotoUrl("");
      });
    return () => {
      active = false;
      if (objectUrl) window.URL.revokeObjectURL(objectUrl);
    };
  }, [candidateId, candidatePhoto?.attachment_id]);

  useEffect(() => {
    let active = true;
    fetchCompaniesManager()
      .then((data) => {
        if (active) {
          setCompaniesList(data.companies || []);
          setVesselsList(data.vessels || []);
        }
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  /** Same candidate, new ?focus= in URL (e.g. another notification) — expand section without full reload */
  useEffect(() => {
    if (!focusTarget) return;
    if (focusTarget.startsWith("document:")) {
      const docId = focusTarget.split(":")[1];
      const inVisaSection = visas.some((row) => String(row?.document_id) === String(docId));
      setExpandedSections(new Set([inVisaSection ? SECTION.VISAS : SECTION.DOCUMENTS]));
    } else if (focusTarget.startsWith("certificate:")) {
      const certId = focusTarget.split(":")[1];
      const inDiplomaSection = [...diplomas, ...tankerDiplomas].some(
        (row) => String(row?.certificate_id) === String(certId)
      );
      const inMedicalSection = medicalDocuments.some((row) => String(row?.certificate_id) === String(certId));
      setExpandedSections(
        new Set([inMedicalSection ? SECTION.MEDICINE : inDiplomaSection ? SECTION.DIPLOMAS : SECTION.CERTIFICATES])
      );
    } else if (focusTarget.startsWith("flag_document:")) {
      setExpandedSections(new Set([SECTION.FLAG_DOCUMENTS]));
    }
  }, [focusTarget, diplomas, tankerDiplomas]);

  useEffect(() => {
    const first = applications[0];
    if (!first) {
      setRecruitmentDraft(
        Object.fromEntries(applicationFields.map(([f]) => [f, APPLICATION_BOOLEAN_FIELDS.has(f) ? "" : ""]))
      );
      return;
    }
    const next = {};
    for (const [field] of applicationFields) {
      const v = first[field];
      if (APPLICATION_BOOLEAN_FIELDS.has(field)) {
        next[field] = boolToSelect(v);
      } else {
        next[field] = v === null || v === undefined ? "" : String(v);
      }
    }
    setRecruitmentDraft(next);
  }, [applications]);

  useEffect(() => {
    const nextAge = _ageFromBirthDateUi(ukrContractForm?.ukr_birth_date_ua);
    if (!nextAge) {
      if ((ukrContractForm?.ukr_age_ua ?? "") !== "") {
        setUkrContractForm((prev) => ({ ...prev, ukr_age_ua: "" }));
      }
      return;
    }
    if ((ukrContractForm?.ukr_age_ua ?? "") !== nextAge) {
      setUkrContractForm((prev) => ({ ...prev, ukr_age_ua: nextAge }));
    }
  }, [ukrContractForm?.ukr_birth_date_ua]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const hasAny =
      String(ukrContractForm?.ukr_surname ?? "").trim() ||
      String(ukrContractForm?.ukr_first_name ?? "").trim() ||
      String(ukrContractForm?.ukr_patronymic ?? "").trim();
    if (!hasAny) {
      return;
    }
    const nextFull = _composeUkrFullNameUa(ukrContractForm || {});
    if ((ukrContractForm?.ukr_full_name_ua ?? "") !== nextFull) {
      setUkrContractForm((prev) => ({ ...prev, ukr_full_name_ua: nextFull }));
    }
  }, [ukrContractForm?.ukr_surname, ukrContractForm?.ukr_first_name, ukrContractForm?.ukr_patronymic]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const nextFull = _composeFullNameFromParts(candidate?.surname, candidate?.first_name);
    if (!nextFull) {
      return;
    }
    if ((candidate?.full_name ?? "") !== nextFull || (candidate?.latin_full_name ?? "") !== nextFull) {
      setCandidate((prev) => _withComposedFullNames(prev));
    }
  }, [candidate?.surname, candidate?.first_name]); // eslint-disable-line react-hooks/exhaustive-deps

  async function loadCandidate(options = { showLoader: false }) {
    const showLoader = options?.showLoader ?? false;
    if (showLoader) {
      setLoading(true);
      setCandidatePhoto(null);
      setSeaServiceModalOpen(false);
      setExpandedSections(new Set([CANDIDATE_SECTION_NAV_ITEMS[0].id]));
    }
    setError("");
    try {
      const payload = await fetchCandidateById(candidateId);
      setCandidate(_withComposedFullNames(mapDateFields(payload.candidate || payload, "ui")));
      setCandidatePhoto(payload.photo || null);
      setUkrContractForm(parseUkrContractJson(payload.candidate?.ukr_contract_json));
      setApplications((payload.applications || []).map((item) => mapDateFields(item, "ui")));
      setFamilyContacts((payload.family_contacts || []).map((item) => mapDateFields(item, "ui")));
      setFlagDocuments((payload.flag_documents || []).map((item) => mapDateFields(item, "ui")));
      setDocuments((payload.documents || []).map((item) => mapDateFields(item, "ui")));
      setVisas((payload.visas || []).map((item) => mapDateFields(item, "ui")));
      setCertificates((payload.certificates || []).map((item) => mapDateFields(item, "ui")));
      setConventionalCertificates((payload.conventional_certificates || []).map((item) => mapDateFields(item, "ui")));
      setEcdisCertificates((payload.ecdis_certificates || []).map((item) => mapDateFields(item, "ui")));
      setCompanyCertificates((payload.company_certificates || []).map((item) => mapDateFields(item, "ui")));
      setBwtsCertificates((payload.bwts_certificates || []).map((item) => mapDateFields(item, "ui")));
      setDiplomas((payload.diplomas || []).map((item) => mapDateFields(item, "ui")));
      setTankerDiplomas((payload.tanker_diplomas || []).map((item) => mapDateFields(item, "ui")));
      setMedicalDocuments((payload.medical_documents || []).map((item) => mapDateFields(item, "ui")));
      setSeaService(sortSeaServiceRows((payload.sea_service || payload.seaService || []).map((item) => mapDateFields(item, "ui"))));
      setAttachments(payload.attachments || []);
      setComments(payload.comments || []);
      if (focusTarget?.startsWith("document:")) {
        const docId = focusTarget.split(":")[1];
        const inVisaSection = (payload.visas || []).some(
          (row) => String(row?.document_id) === String(docId)
        );
        setExpandedSections(new Set([inVisaSection ? SECTION.VISAS : SECTION.DOCUMENTS]));
      } else if (focusTarget?.startsWith("certificate:")) {
        const certId = focusTarget.split(":")[1];
        const inDiplomaSection = [...(payload.diplomas || []), ...(payload.tanker_diplomas || [])].some(
          (row) => String(row?.certificate_id) === String(certId)
        );
        const inMedicalSection = (payload.medical_documents || []).some(
          (row) => String(row?.certificate_id) === String(certId)
        );
        setExpandedSections(
          new Set([
            inMedicalSection ? SECTION.MEDICINE : inDiplomaSection ? SECTION.DIPLOMAS : SECTION.CERTIFICATES,
          ])
        );
      } else if (focusTarget?.startsWith("flag_document:")) {
        setExpandedSections(new Set([SECTION.FLAG_DOCUMENTS]));
      }
    } catch (requestError) {
      setError("Не удалось загрузить карточку кандидата");
    } finally {
      if (showLoader) {
        setLoading(false);
      }
    }
  }

  async function onSaveProfile() {
    setSavingProfile(true);
    setError("");
    const badProfileDate = firstBadDateInRecord(candidate);
    if (badProfileDate) {
      setError(badProfileDate);
      setSavingProfile(false);
      return;
    }
    try {
      const payload = Object.fromEntries(
        Object.entries(candidate).filter(
          ([key]) =>
            !readOnlyCandidateKeys.has(key) &&
            key !== "ukr_contract_json" &&
            key !== "salary_calculation_json" &&
            key !== "contract_json"
        )
      );
      await updateCandidate(candidateId, mapDateFields(payload, "api"));
      await loadCandidate();
    } catch (requestError) {
      setError("Не удалось сохранить персональные данные");
    } finally {
      setSavingProfile(false);
    }
  }

  async function onUploadCandidatePhoto(file) {
    setCandidatePhotoBusy(true);
    setCandidatePhotoError("");
    try {
      const payload = await uploadCandidatePhoto(candidateId, file);
      setCandidatePhoto(payload.photo || null);
    } catch (requestError) {
      setCandidatePhotoError(requestError?.response?.data?.detail || "Не удалось загрузить фото");
    } finally {
      setCandidatePhotoBusy(false);
    }
  }

  async function onDeleteCandidatePhoto() {
    setCandidatePhotoBusy(true);
    setCandidatePhotoError("");
    try {
      await deleteCandidatePhoto(candidateId);
      setCandidatePhoto(null);
      setIncludeCandidatePhotoInPodacha(false);
    } catch (requestError) {
      setCandidatePhotoError(requestError?.response?.data?.detail || "Не удалось удалить фото");
    } finally {
      setCandidatePhotoBusy(false);
    }
  }

  async function onAddComment() {
    const text = commentDraft.trim();
    if (!text) {
      return;
    }
    setCommentSaving(true);
    setError("");
    try {
      const response = await createCandidateComment(candidateId, text);
      if (response?.comment) {
        setComments((prev) => [response.comment, ...prev]);
      } else {
        await loadCandidate({ showLoader: false });
      }
      setCommentDraft("");
    } catch (requestError) {
      const detail = requestError?.response?.data?.detail;
      setError(detail || "Не удалось сохранить комментарий");
    } finally {
      setCommentSaving(false);
    }
  }

  async function onSaveUkrContract() {
    if (!canEditUkrContract) return;
    setUkrContractSaving(true);
    setError("");
    const badUkrDate = firstBadDateInRecord(ukrContractForm);
    if (badUkrDate) {
      setError(badUkrDate);
      setUkrContractSaving(false);
      return;
    }
    try {
      await updateCandidate(candidateId, { ukr_contract_json: JSON.stringify(ukrContractForm) });
      setUkrContractModalOpen(false);
      await loadCandidate({ showLoader: false });
    } catch (requestError) {
      const detail = requestError?.response?.data?.detail;
      setError(detail || "Не удалось зберегти дані українського контракту");
    } finally {
      setUkrContractSaving(false);
    }
  }

  async function onSaveRecruitment() {
    if (!canEditRelations) return;
    setRecruitmentSaving(true);
    setError("");
    const badRecruitmentDate = firstBadDateInRecord(recruitmentDraft);
    if (badRecruitmentDate) {
      setError(badRecruitmentDate);
      setRecruitmentSaving(false);
      return;
    }
    try {
      const payload = buildApplicationApiPayload(recruitmentDraft);
      const first = applications[0];
      let savedApplication;
      if (first?.application_id) {
        const response = await updateApplication(candidateId, first.application_id, payload);
        savedApplication = response?.application;
      } else {
        const response = await createApplication(candidateId, payload);
        savedApplication = response?.application;
      }
      if (savedApplication) {
        const mapped = mapDateFields(savedApplication, "ui");
        setApplications((prev) => {
          const id = mapped.application_id;
          if (id && prev.some((row) => String(row.application_id) === String(id))) {
            return prev.map((row) =>
              String(row.application_id) === String(id) ? { ...row, ...mapped } : row
            );
          }
          return [mapped, ...prev.filter((row) => row.application_id !== mapped.application_id)];
        });
      }
      await loadCandidate({ showLoader: false });
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Не удалось сохранить заявку");
    } finally {
      setRecruitmentSaving(false);
    }
  }

  async function beginEditCertificateSlot(item, section, specs, findSpecFn) {
    if (!canEditRelations) return;
    let relationId = getId(item, ["certificate_id"]);
    let row = item;
    if (!relationId) {
      const spec = findSpecFn(item, specs) || findSpecFn(item);
      if (!spec) return;
      try {
        const isDiplomaSpec = Boolean(spec.certificateType && !spec.displayType);
        const diplomaLabel = spec.certificateType || spec.displayType || "";
        const response = await createCertificate(candidateId, {
          certificate_type: diplomaLabel,
          certificate_code: isDiplomaSpec ? diplomaLabel : spec.displayCode || spec.code,
          certificate_name_raw: spec.code,
          certificate_group: spec.group,
        });
        row = mapDateFields(response.certificate, "ui");
        relationId = row.certificate_id;
        await loadCandidate({ showLoader: false });
      } catch (requestError) {
        setError(requestError?.response?.data?.detail || "Не удалось создать строку сертификата");
        return;
      }
    }
    if (!relationId) return;
    startEdit(section, relationId, row);
  }

  async function beginEditDiploma(item, section) {
    const specs = section === "tankerDiplomas" ? CANONICAL_TANKER_DIPLOMA_SPECS : CANONICAL_DIPLOMA_SPECS;
    return beginEditCertificateSlot(item, section, specs, findCanonicalDiplomaSpec);
  }

  async function beginEditMedical(item, section = "medicalDocuments") {
    return beginEditCertificateSlot(item, section, CANONICAL_MEDICAL_SPECS, findCanonicalMedicalSpec);
  }

  function beginEditCanonicalCertificate(item, section, specs) {
    return beginEditCertificateSlot(item, section, specs, findCanonicalCertificateSpec);
  }

  async function beginEditDocument(item) {
    if (!canEditRelations) return;
    let relationId = getId(item, ["document_id"]);
    let row = item;
    if (!relationId && isCanonicalDocumentRow(item)) {
      const spec = findCanonicalSpecForRow(item);
      try {
        const response = await createDocument(candidateId, {
          document_type: spec?.documentType || item.document_type,
          document_category: spec?.code || documentRowCode(item) || null,
        });
        row = mapDateFields(response.document, "ui");
        relationId = row.document_id;
        await loadCandidate({ showLoader: false });
      } catch (requestError) {
        setError(requestError?.response?.data?.detail || "Не удалось создать строку документа");
        return;
      }
    }
    if (!relationId) return;
    startEdit("documents", relationId, row);
  }

  function startEdit(section, rowId, row) {
    setEditingRows((prev) => ({ ...prev, [section]: rowId }));
    const draft = { ...row };
    if (section === "seaService" && !String(draft.remarks || "").trim()) {
      draft.remarks = SEA_SERVICE_DEFAULT_REMARKS;
    }
    if (CERTIFICATE_EDIT_SECTIONS.has(section)) {
      draft.validityMode = inferValidityMode(row);
      if (needsValidityAssist(row) && draft.validityMode === VALIDITY_MODE.PLUS5) {
        Object.assign(draft, applyPlus5Years(draft));
      }
    }
    setEditDrafts((prev) => ({ ...prev, [section]: draft }));
  }

  function cancelEdit(section) {
    setEditingRows((prev) => ({ ...prev, [section]: null }));
    setEditDrafts((prev) => ({ ...prev, [section]: {} }));
  }

  async function onAddDocument() {
    setError("");
    const badDocDate = firstBadDateInRecord(newRows.document);
    if (badDocDate) {
      setError(badDocDate);
      return;
    }
    const raw = mapDateFields(newRows.document, "api");
    const payload = omitEmptyPayloadValues(raw);
    if (!String(payload.document_type || "").trim()) {
      setError("Укажите тип документа");
      return;
    }
    const docRangeErr = issueExpiryRangeErrorFromIsoOrNull(
      payload.date_of_issue ? String(payload.date_of_issue) : null,
      payload.date_of_expiry ? String(payload.date_of_expiry) : null
    );
    if (docRangeErr) {
      notifyUserError(docRangeErr);
      return;
    }
    payload.document_type = String(payload.document_type).trim();
    try {
      await createDocument(candidateId, payload);
      setNewRows((prev) => ({
        ...prev,
        document: { document_type: "", document_number: "", date_of_issue: "", issuing_authority: "", date_of_expiry: "" },
      }));
      await loadCandidate();
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Не удалось добавить документ");
    }
  }

  async function onUpdateDocument(documentId) {
    try {
      setError("");
      const badDocEdit = firstBadDateInRecord(editDrafts.documents, editableDocumentFields);
      if (badDocEdit) {
        setError(badDocEdit);
        return;
      }
      const payload = buildNullableUpdatePayload(editDrafts.documents, editableDocumentFields);
      const row = documents.find((d) => String(getId(d, ["document_id"])) === String(documentId));
      const mergedIssue =
        payload.date_of_issue ??
        (row?.date_of_issue ? toIsoDateString(row.date_of_issue) : null);
      const mergedExpiry =
        payload.date_of_expiry ??
        (row?.date_of_expiry ? toIsoDateString(row.date_of_expiry) : null);
      const docUpdateRangeErr = issueExpiryRangeErrorFromIsoOrNull(mergedIssue, mergedExpiry);
      if (docUpdateRangeErr) {
        notifyUserError(docUpdateRangeErr);
        return;
      }
      await updateDocument(candidateId, documentId, payload);
      cancelEdit("documents");
      await loadCandidate({ showLoader: false });
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Не удалось сохранить документ");
    }
  }

  async function onDeleteDocument(documentId) {
    const confirmed = typeof window !== "undefined"
      ? window.confirm("Удалить документ? Действие нельзя отменить.")
      : true;
    if (!confirmed) {
      return;
    }
    await deleteDocument(candidateId, documentId);
    await loadCandidate();
  }

  async function beginEditVisa(item) {
    if (!canEditRelations) return;
    let relationId = getId(item, ["document_id"]);
    let row = item;
    if (!relationId) {
      const spec = findCanonicalVisaSpecForRow(item);
      try {
        const response = await createDocument(candidateId, {
          document_type: spec?.documentType || item.document_type,
          document_category: spec?.code || item.visa_code || item.document_category || null,
        });
        row = mapDateFields(response.document, "ui");
        relationId = row.document_id;
        await loadCandidate({ showLoader: false });
      } catch (requestError) {
        setError(requestError?.response?.data?.detail || "Не удалось создать строку визы");
        return;
      }
    }
    if (!relationId) return;
    startEdit("visas", relationId, row);
  }

  async function onAddVisa() {
    setError("");
    const mode = newVisaDraft.mode;
    if (!mode) {
      setError("Выберите тип визы");
      return;
    }
    const visaName =
      mode === "custom" ? newVisaDraft.customName.trim() : mode;
    if (!visaName) {
      setError("Укажите название визы");
      return;
    }
    const badDate = firstBadDateInRecord(newVisaDraft);
    if (badDate) {
      setError(badDate);
      return;
    }
    const raw = mapDateFields(
      {
        document_type: visaName,
        document_category: visaName,
        document_number: newVisaDraft.document_number,
        date_of_issue: newVisaDraft.date_of_issue,
        date_of_expiry: newVisaDraft.date_of_expiry,
      },
      "api"
    );
    const validationErr = validateVisaSavePayload(raw, null);
    if (validationErr) {
      setError(validationErr);
      return;
    }
    const docRangeErr = issueExpiryRangeErrorFromIsoOrNull(
      raw.date_of_issue ? String(raw.date_of_issue) : null,
      raw.date_of_expiry ? String(raw.date_of_expiry) : null
    );
    if (docRangeErr) {
      notifyUserError(docRangeErr);
      return;
    }
    try {
      const existing = visas.find(
        (row) =>
          String(row.visa_code || row.document_category || "").trim() === visaName ||
          String(row.document_type || "").trim() === visaName
      );
      if (existing?.document_id) {
        await updateDocument(candidateId, existing.document_id, omitEmptyPayloadValues(raw));
      } else {
        await createDocument(candidateId, omitEmptyPayloadValues(raw));
      }
      setNewVisaDraft({
        mode: "",
        customName: "",
        document_number: "",
        date_of_issue: "",
        date_of_expiry: "",
      });
      await loadCandidate();
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Не удалось добавить визу");
    }
  }

  async function onUpdateVisa(documentId) {
    try {
      setError("");
      const badDate = firstBadDateInRecord(editDrafts.visas, editableVisaFields);
      if (badDate) {
        setError(badDate);
        return;
      }
      const payload = buildNullableUpdatePayload(editDrafts.visas, editableVisaFields);
      const row = visas.find((d) => String(getId(d, ["document_id"])) === String(documentId));
      const validationErr = validateVisaSavePayload(payload, row);
      if (validationErr) {
        setError(validationErr);
        return;
      }
      const mergedIssue =
        payload.date_of_issue ??
        (row?.date_of_issue ? toIsoDateString(row.date_of_issue) : null);
      const mergedExpiry =
        payload.date_of_expiry ??
        (row?.date_of_expiry ? toIsoDateString(row.date_of_expiry) : null);
      const docUpdateRangeErr = issueExpiryRangeErrorFromIsoOrNull(mergedIssue, mergedExpiry);
      if (docUpdateRangeErr) {
        notifyUserError(docUpdateRangeErr);
        return;
      }
      await updateDocument(candidateId, documentId, payload);
      cancelEdit("visas");
      await loadCandidate({ showLoader: false });
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Не удалось сохранить визу");
    }
  }

  async function onDeleteVisa(documentId) {
    const confirmed =
      typeof window !== "undefined" ? window.confirm("Удалить визу?") : true;
    if (!confirmed) return;
    await deleteDocument(candidateId, documentId);
    await loadCandidate();
  }

  async function addCertificateFromDraft(draftKey, { certificateGroup = null } = {}) {
    setError("");
    const draft = newRows[draftKey];
    const badCertDate = firstBadDateInRecord(draft);
    if (badCertDate) {
      setError(badCertDate);
      return;
    }
    const prepared = certificatePayloadFromDraft(draft);
    const raw = mapDateFields(prepared, "api");
    const capPayload = omitEmptyPayloadValues(raw);
    if (!String(capPayload.certificate_type || "").trim()) {
      setError("Укажите тип сертификата");
      return;
    }
    capPayload.certificate_type = String(capPayload.certificate_type).trim();
    capPayload.certificate_code = capPayload.certificate_type;
    if (certificateGroup) {
      capPayload.certificate_group = certificateGroup;
    }
    if (prepared.unlimited_validity === true) {
      capPayload.unlimited_validity = true;
      capPayload.expiry_date = null;
    }
    const certRangeErr =
      prepared.unlimited_validity === true
        ? null
        : issueExpiryRangeErrorFromIsoOrNull(
            capPayload.date_issued ? String(capPayload.date_issued) : null,
            capPayload.expiry_date ? String(capPayload.expiry_date) : null
          );
    if (certRangeErr) {
      notifyUserError(certRangeErr);
      return;
    }
    try {
      await createCertificate(candidateId, capPayload);
      setNewRows((prev) => ({
        ...prev,
        [draftKey]: createEmptyCertificateDraft(),
      }));
      await loadCandidate();
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Не удалось добавить сертификат");
    }
  }

  function onAddCertificate() {
    return addCertificateFromDraft("certificate");
  }

  function onAddDiploma() {
    return addCertificateFromDraft("diploma", { certificateGroup: DIPLOMA_GROUP });
  }

  function onAddTankerDiploma() {
    return addCertificateFromDraft("tankerDiploma", { certificateGroup: TANKER_DIPLOMA_GROUP });
  }

  function onAddMedicalDocument() {
    return addCertificateFromDraft("medicalDocument", { certificateGroup: MEDICAL_GROUP });
  }

  async function onUpdateCertificate(certificateId, section = "certificates") {
    try {
      setError("");
      const draft = editDrafts[section];
      const badCertEdit = firstBadDateInRecord(draft, editableCertificateFields);
      if (badCertEdit) {
        setError(badCertEdit);
        return;
      }
      const prepared = certificatePayloadFromDraft(draft);
      const payload = buildNullableUpdatePayload(prepared, editableCertificateFields);
      if (prepared.unlimited_validity === true) {
        payload.unlimited_validity = true;
        payload.expiry_date = null;
      }
      const row = getCertificateDisplayList(section).find(
        (d) => String(getId(d, ["certificate_id"])) === String(certificateId)
      );
      const mergedIssued =
        payload.date_issued ?? (row?.date_issued ? toIsoDateString(row.date_issued) : null);
      const mergedCexp =
        prepared.unlimited_validity === true
          ? null
          : payload.expiry_date ?? (row?.expiry_date ? toIsoDateString(row.expiry_date) : null);
      const certUpdateErr =
        prepared.unlimited_validity === true
          ? null
          : issueExpiryRangeErrorFromIsoOrNull(mergedIssued, mergedCexp);
      if (certUpdateErr) {
        notifyUserError(certUpdateErr);
        return;
      }
      await updateCertificate(candidateId, certificateId, payload);
      cancelEdit(section);
      await loadCandidate({ showLoader: false });
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Не удалось сохранить сертификат");
    }
  }

  async function onDeleteCertificate(certificateId) {
    const confirmed = typeof window !== "undefined"
      ? window.confirm("Удалить сертификат? Действие нельзя отменить.")
      : true;
    if (!confirmed) {
      return;
    }
    await deleteCertificate(candidateId, certificateId);
    await loadCandidate();
  }

  async function onAddSeaService() {
    setError("");
    const badSeaDate = firstBadDateInRecord(newRows.seaService);
    if (badSeaDate) {
      setError(badSeaDate);
      return;
    }
    try {
      const payload = omitEmptyPayloadValues(
        mapDateFields(withComputedContractDuration(newRows.seaService), "api"),
      );
      await createSeaService(candidateId, payload);
      setNewRows((prev) => ({
        ...prev,
        seaService: {
          vessel_name: "",
          rank_on_vessel: "",
          ecdis_dg_maker: "",
          sign_on_date: "",
          sign_off_date: "",
          remarks: SEA_SERVICE_DEFAULT_REMARKS,
        },
      }));
      await loadCandidate();
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Не удалось добавить запись морского стажа");
    }
  }

  async function onUpdateSeaService(seaServiceId) {
    try {
      setError("");
      const badSeaEdit = firstBadDateInRecord(editDrafts.seaService, editableSeaServiceFields);
      if (badSeaEdit) {
        setError(badSeaEdit);
        return;
      }
      const payload = buildNullableUpdatePayload(
        withComputedContractDuration(editDrafts.seaService),
        editableSeaServiceFields,
      );
      await updateSeaService(candidateId, Number(seaServiceId), payload);
      cancelEdit("seaService");
      await loadCandidate({ showLoader: false });
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Не удалось сохранить опыт");
    }
  }

  async function onDeleteSeaService(seaServiceId) {
    const confirmed = typeof window !== "undefined"
      ? window.confirm("Удалить запись морского стажа? Действие нельзя отменить.")
      : true;
    if (!confirmed) {
      return;
    }
    try {
      await deleteSeaService(candidateId, seaServiceId);
      await loadCandidate();
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Не удалось удалить запись морского стажа");
    }
  }

  async function onAddFamilyContact() {
    setError("");
    const { full_name, relationship_to_candidate, phone, email, address } = newRows.familyContact;
    if (!String(full_name || "").trim()) {
      setError("Укажите ФИО контакта");
      return;
    }
    try {
      await createFamilyContact(candidateId, {
        full_name: String(full_name).trim(),
        relationship_to_candidate: relationship_to_candidate?.trim() || null,
        phone: phone?.trim() || null,
        email: email?.trim() || null,
        address: address?.trim() || null,
      });
      setNewRows((prev) => ({
        ...prev,
        familyContact: { full_name: "", relationship_to_candidate: "", phone: "", email: "", address: "" },
      }));
      await loadCandidate({ showLoader: false });
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Не удалось добавить контакт");
    }
  }

  async function onUpdateFamilyContact(contactId) {
    setError("");
    if (!String(editDrafts.familyContacts.full_name || "").trim()) {
      setError("Укажите ФИО контакта");
      return;
    }
    try {
      const picked = pickEditableFields(editDrafts.familyContacts, editableFamilyContactFields);
      const mapped = mapDateFields(picked, "api");
      const payload = buildFamilyContactUpdatePayload(editDrafts.familyContacts);
      await updateFamilyContact(candidateId, contactId, payload);
      cancelEdit("familyContacts");
      await loadCandidate({ showLoader: false });
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Не удалось сохранить контакт");
    }
  }

  async function onDeleteFamilyContact(contactId) {
    const confirmed = typeof window !== "undefined"
      ? window.confirm("Удалить контакт? Действие нельзя отменить.")
      : true;
    if (!confirmed) {
      return;
    }
    try {
      await deleteFamilyContact(candidateId, contactId);
      await loadCandidate({ showLoader: false });
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Не удалось удалить контакт");
    }
  }

  async function onAddFlagDocument() {
    setError("");
    const fd = newRows.flagDocument;
    if (!String(fd.flag_country || "").trim()) {
      setError("Укажите страну флага (Flag)");
      return;
    }
    const badFlagDate = firstBadDateInRecord(fd);
    if (badFlagDate) {
      setError(badFlagDate);
      return;
    }
    try {
      const flagCreateBody = mapDateFields(
        {
          flag_country: String(fd.flag_country).trim(),
          flag_document_type: fd.flag_document_type?.trim() || null,
          rank: fd.rank?.trim() || null,
          doc_number: fd.doc_number?.trim() || null,
          date_of_issuance: fd.date_of_issuance || null,
          date_of_expiry: fd.date_of_expiry || null,
          remarks: fd.remarks?.trim() || null,
        },
        "api"
      );
      const flagAddErr = issueExpiryRangeErrorFromIsoOrNull(
        flagCreateBody.date_of_issuance ? String(flagCreateBody.date_of_issuance) : null,
        flagCreateBody.date_of_expiry ? String(flagCreateBody.date_of_expiry) : null
      );
      if (flagAddErr) {
        notifyUserError(flagAddErr);
        return;
      }
      await createFlagDocument(candidateId, flagCreateBody);
      setNewRows((prev) => ({
        ...prev,
        flagDocument: {
          flag_country: "",
          flag_document_type: "",
          rank: "",
          doc_number: "",
          date_of_issuance: "",
          date_of_expiry: "",
          remarks: "",
        },
      }));
      await loadCandidate({ showLoader: false });
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Не удалось добавить запись");
    }
  }

  async function onUpdateFlagDocument(flagDocumentId) {
    setError("");
    if (!String(editDrafts.flagDocuments.flag_country || "").trim()) {
      setError("Укажите страну флага (Flag)");
      return;
    }
    const badFlagEdit = firstBadDateInRecord(editDrafts.flagDocuments, editableFlagDocumentFields);
    if (badFlagEdit) {
      setError(badFlagEdit);
      return;
    }
    try {
      const payload = buildFlagDocumentUpdatePayload(editDrafts.flagDocuments);
      const row = flagDocuments.find((d) => String(getId(d, ["flag_document_id"])) === String(flagDocumentId));
      const pickFlagDate = (key, rowKey) => {
        if (Object.prototype.hasOwnProperty.call(payload, key)) {
          const v = payload[key];
          if (v === null || v === "") return null;
          return String(v);
        }
        return row?.[rowKey] ? toIsoDateString(row[rowKey]) : null;
      };
      const mergedFlagIssuance = pickFlagDate("date_of_issuance", "date_of_issuance");
      const mergedFlagExpiry = pickFlagDate("date_of_expiry", "date_of_expiry");
      const flagUpdateErr = issueExpiryRangeErrorFromIsoOrNull(mergedFlagIssuance, mergedFlagExpiry);
      if (flagUpdateErr) {
        notifyUserError(flagUpdateErr);
        return;
      }
      await updateFlagDocument(candidateId, flagDocumentId, payload);
      cancelEdit("flagDocuments");
      await loadCandidate({ showLoader: false });
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Не удалось сохранить запись");
    }
  }

  async function onDeleteFlagDocument(flagDocumentId) {
    const confirmed = typeof window !== "undefined"
      ? window.confirm("Удалить запись документа флага? Действие нельзя отменить.")
      : true;
    if (!confirmed) {
      return;
    }
    try {
      await deleteFlagDocument(candidateId, flagDocumentId);
      await loadCandidate({ showLoader: false });
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Не удалось удалить запись");
    }
  }

  function getRelationAttachment(attachmentType, relationId) {
    return attachments.find(
      (item) =>
        item.source === attachmentType &&
        typeof item.description === "string" &&
        item.description.includes(`${attachmentType}:${relationId}`)
    );
  }

  async function onUploadRelationAttachment(attachmentType, relationId, file, currentAttachment) {
    if (!file || relationId === undefined || relationId === null) return;
    const key = `${attachmentType}:${relationId}`;
    setAttachmentBusy((prev) => ({ ...prev, [key]: true }));
    setAttachmentErrors((prev) => ({ ...prev, [key]: "" }));
    try {
      if (currentAttachment?.attachment_id) {
        await deleteAttachment(currentAttachment.attachment_id);
      }
      await uploadAttachment(candidateId, file, {
        attachmentType,
        relationId,
        description: key,
      });
      await loadCandidate({ showLoader: false });
    } catch (requestError) {
      setAttachmentErrors((prev) => ({
        ...prev,
        [key]: requestError?.response?.data?.detail || "Не удалось загрузить скан",
      }));
    } finally {
      setAttachmentBusy((prev) => ({ ...prev, [key]: false }));
    }
  }

  async function onDeleteRelationAttachment(attachmentType, relationId, attachmentId) {
    const confirmed = typeof window !== "undefined"
      ? window.confirm("Удалить скан? Действие нельзя отменить.")
      : true;
    if (!confirmed) {
      return;
    }
    const key = `${attachmentType}:${relationId}`;
    setAttachmentBusy((prev) => ({ ...prev, [key]: true }));
    setAttachmentErrors((prev) => ({ ...prev, [key]: "" }));
    try {
      await deleteAttachment(attachmentId);
      await loadCandidate({ showLoader: false });
    } catch (requestError) {
      setAttachmentErrors((prev) => ({
        ...prev,
        [key]: requestError?.response?.data?.detail || "Не удалось удалить скан",
      }));
    } finally {
      setAttachmentBusy((prev) => ({ ...prev, [key]: false }));
    }
  }

  async function openTemplatesModal() {
    setTemplatesModalOpen(true);
    setTemplatesLoading(true);
    setTemplatesError("");
    try {
      const payload = await fetchTemplatesManager();
      setTemplateFolders(payload.folders || []);
      setTemplateFiles(payload.files || []);
      setTemplatesRootFolderId(payload.root_folder_id ?? null);
      setExpandedTemplateFolderIds((payload.folders || []).map((folder) => folder.folder_id));
      setSelectedTemplateFolderId(payload.root_folder_id ?? null);
      setSelectedTemplateIds([]);
    } catch (requestError) {
      setTemplatesError("Не удалось загрузить шаблоны");
    } finally {
      setTemplatesLoading(false);
    }
  }

  function closeTemplatesModal() {
    if (generatingTemplates) return;
    setTemplatesModalOpen(false);
  }

  function toggleTemplateSelection(templateId) {
    setSelectedTemplateIds((prev) =>
      prev.includes(templateId) ? prev.filter((item) => item !== templateId) : [...prev, templateId]
    );
  }

  function toggleFolderExpanded(folderId) {
    setExpandedTemplateFolderIds((prev) => {
      const isExpanded = prev.includes(folderId);
      return isExpanded ? prev.filter((id) => id !== folderId) : [...prev, folderId];
    });
  }

  function renderTemplateTree(parentId, level = 0) {
    const folderKey = parentId ?? "__root__";
    const folders = (templatesChildrenMap[folderKey] || [])
      .slice()
      .sort((a, b) => String(a.name || "").localeCompare(String(b.name || ""), "ru"));
    return (
      <>
        {folders.map((folder) => (
          <div key={`folder-${folder.folder_id}`} className="templates-tree-node">
            <div className="templates-tree-folder-row" style={{ paddingLeft: `${level * 14}px` }}>
              <button
                type="button"
                className="templates-tree-toggle"
                onClick={() => toggleFolderExpanded(folder.folder_id)}
                aria-label={expandedTemplateFolderIds.includes(folder.folder_id) ? "Свернуть папку" : "Раскрыть папку"}
              >
                {expandedTemplateFolderIds.includes(folder.folder_id) ? "▾" : "▸"}
              </button>
              <button
                type="button"
                className={
                  selectedTemplateFolderId === folder.folder_id
                    ? "templates-tree-folder templates-tree-folder--active"
                    : "templates-tree-folder"
                }
                onClick={() => {
                  setSelectedTemplateFolderId(folder.folder_id);
                }}
              >
                <span className="templates-tree-folder-name">📁 {folder.name}</span>
              </button>
            </div>
            {expandedTemplateFolderIds.includes(folder.folder_id) ? renderTemplateTree(folder.folder_id, level + 1) : null}
          </div>
        ))}
      </>
    );
  }

  const podachaTemplateOptions = useMemo(() => {
    const preferred = templateOptions.filter(
      (item) =>
        String(item.folderPath || "").includes("Подача") ||
        String(item.fileName || "").toLowerCase().includes("инфо лист")
    );
    return preferred.length > 0 ? preferred : templateOptions;
  }, [templateOptions]);

  function togglePodachaTemplateSelection(templateId) {
    setSelectedPodachaTemplateIds((prev) =>
      prev.includes(templateId) ? prev.filter((item) => item !== templateId) : [...prev, templateId]
    );
  }

  function togglePodachaAttachmentSelection(attachmentId) {
    if (!attachmentId) return;
    setSelectedPodachaAttachmentIds((prev) =>
      prev.includes(attachmentId) ? prev.filter((item) => item !== attachmentId) : [...prev, attachmentId]
    );
  }

  async function openPodachaModal() {
    setPodachaModalOpen(true);
    setPodachaLoading(true);
    setPodachaError("");
    setOpeningVessel(applications[0]?.proposed_vessel || "");
    setPreviousVessel("");
    setSelectedPodachaTemplateIds([]);
    setSelectedPodachaAttachmentIds([]);
    setIncludeCandidatePhotoInPodacha(false);
    try {
      const payload = await fetchTemplatesManager();
      setTemplateFolders(payload.folders || []);
      setTemplateFiles(payload.files || []);
      setTemplatesRootFolderId(payload.root_folder_id ?? null);
      const files = payload.files || [];
      const infoListIds = files
        .filter((item) => String(item.file_name || "").toLowerCase().includes("инфо лист"))
        .map((item) => item.template_file_id);
      if (infoListIds.length > 0) {
        setSelectedPodachaTemplateIds(infoListIds);
      }
    } catch {
      setPodachaError("Не удалось загрузить шаблоны");
    } finally {
      setPodachaLoading(false);
    }
  }

  function closePodachaModal() {
    if (podachaBuilding) return;
    setPodachaModalOpen(false);
  }

  async function onBuildSubmissionPack() {
    if (
      selectedPodachaTemplateIds.length === 0 &&
      selectedPodachaAttachmentIds.length === 0 &&
      !includeCandidatePhotoInPodacha
    ) {
      setPodachaError("Выберите хотя бы один шаблон или скан");
      return;
    }
    setPodachaBuilding(true);
    setPodachaError("");
    try {
      const { blob, fileName } = await buildSubmissionPack(candidateId, {
        opening_vessel: openingVessel.trim() || null,
        previous_vessel: previousVessel.trim() || null,
        template_file_ids: selectedPodachaTemplateIds,
        attachment_ids: selectedPodachaAttachmentIds,
        include_candidate_photo: includeCandidatePhotoInPodacha,
      });
      const objectUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = fileName || `PODACHA_${candidateId}.zip`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(objectUrl);
      setPodachaModalOpen(false);
    } catch (requestError) {
      let detail = requestError?.response?.data?.detail;
      if (!detail && requestError?.response?.data instanceof Blob) {
        try {
          const text = await requestError.response.data.text();
          detail = JSON.parse(text)?.detail;
        } catch {
          detail = null;
        }
      }
      if (Array.isArray(detail)) {
        detail = detail.map((item) => item?.msg || String(item)).join("; ");
      }
      const status = requestError?.response?.status;
      let errorMessage = detail || "Не удалось собрать пакет";
      if (status === 404 && (detail === "Not Found" || !detail)) {
        errorMessage =
          "API ПОДАЧА не найден (404). Перезапустите backend с новым кодом: " +
          "docker compose build backend && docker compose up -d " +
          "(или локально: uvicorn app.main:app --reload).";
      } else if (status) {
        errorMessage = `[${status}] ${errorMessage}`;
      }
      setPodachaError(errorMessage);
    } finally {
      setPodachaBuilding(false);
    }
  }

  async function onGenerateSelectedTemplates() {
    if (selectedTemplateIds.length === 0) {
      setTemplatesError("Выберите хотя бы один шаблон");
      return;
    }
    setGeneratingTemplates(true);
    setTemplatesError("");
    try {
      const selectedTemplates = templateOptions.filter((item) => selectedTemplateIds.includes(item.id));
      for (const template of selectedTemplates) {
        const { blob, fileName } = await generateCandidateDocument(candidateId, template.fileName, template.id);
        const objectUrl = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = objectUrl;
        link.download = fileName || template.fileName;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(objectUrl);
      }
      setTemplatesModalOpen(false);
    } catch (requestError) {
      const detail = requestError?.response?.data?.detail;
      setTemplatesError(detail || "Не удалось сгенерировать документы");
    } finally {
      setGeneratingTemplates(false);
    }
  }

  if (loading) {
    return <p>Загрузка карточки кандидата...</p>;
  }

  async function onDeleteCandidate() {
    if (
      !window.confirm(
        "Удалить кандидата и все связанные данные (документы, сертификаты, вложения)? Действие нельзя отменить."
      )
    ) {
      return;
    }
    setDeleteBusy(true);
    setError("");
    try {
      await deleteCandidate(candidateId);
      const fromList =
        typeof location.state?.candidatesListPath === "string" ? location.state.candidatesListPath : "/candidates";
      navigate(fromList, { replace: true });
    } catch (requestError) {
      const detail = requestError?.response?.data?.detail;
      setError(detail || "Не удалось удалить кандидата");
    } finally {
      setDeleteBusy(false);
    }
  }

  return (
    <section className="candidate-detail" data-testid="candidate-detail">
      {error ? <p className="error">{error}</p> : null}
      {popupError ? (
        <div
          className="modal-overlay"
          role="presentation"
          onClick={() => setPopupError("")}
          data-testid="candidate-popup-error-overlay"
        >
          <div
            className="modal-card candidate-popup-error-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="candidate-popup-error-title"
            data-testid="candidate-popup-error-modal"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="menu-header">
              <h2 id="candidate-popup-error-title">Ошибка</h2>
            </div>
            <p className="error candidate-popup-error-text">{popupError}</p>
            <div className="candidate-popup-error-actions">
              <button type="button" onClick={() => setPopupError("")}>
                Понятно
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <div className="candidate-photo-panel" data-testid="candidate-photo-panel">
        <div className="candidate-photo-preview">
          {candidatePhotoUrl ? (
            <img src={candidatePhotoUrl} alt="Фото кандидата" />
          ) : (
            <span aria-hidden="true">
              {`${candidate.first_name?.[0] || ""}${candidate.surname?.[0] || ""}`.toUpperCase() || "?"}
            </span>
          )}
        </div>
        <div className="candidate-photo-info">
          <strong>{candidate.full_name || [candidate.first_name, candidate.surname].filter(Boolean).join(" ") || "Кандидат"}</strong>
          <span className="muted-text">Фото кандидата</span>
          {candidatePhotoError ? <span className="error">{candidatePhotoError}</span> : null}
        </div>
        {canEditRelations ? (
          <div className="candidate-photo-actions">
            <FileDropzone
              compact
              accept="image/jpeg,image/png,.jpg,.jpeg,.png"
              testId="candidate-photo-upload"
              disabled={candidatePhotoBusy}
              label={candidatePhoto ? "Заменить фото" : "Загрузить фото"}
              browseLabel={candidatePhotoBusy ? "Загрузка…" : candidatePhoto ? "Заменить" : "Загрузить"}
              onFile={onUploadCandidatePhoto}
            />
            {candidatePhoto ? (
              <button type="button" className="secondary-btn" disabled={candidatePhotoBusy} onClick={onDeleteCandidatePhoto}>
                Удалить
              </button>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className="candidate-admin-toolbar">
        <button type="button" className="secondary-btn" data-testid="btn-podacha" onClick={openPodachaModal}>
          ПОДАЧА
        </button>
        <button type="button" className="secondary-btn" data-testid="btn-generate-documents" onClick={openTemplatesModal}>
          Сгенерировать документы
        </button>
        {isAdmin ? (
          <button type="button" className="danger-btn" onClick={onDeleteCandidate} disabled={deleteBusy}>
            {deleteBusy ? "Удаление…" : "Удалить кандидата"}
          </button>
        ) : null}
      </div>

      <nav className="candidate-section-nav" aria-label="Разделы карточки кандидата" data-testid="candidate-section-nav">
        {CANDIDATE_SECTION_NAV_ITEMS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            className={`candidate-section-nav__btn${expandedSections.has(id) ? " is-active" : ""}`}
            data-section-tab={id}
            aria-pressed={expandedSections.has(id)}
            onClick={() => selectSectionTab(id)}
          >
            {label}
          </button>
        ))}
      </nav>
      {expandedSections.size === 0 ? (
        <p className="muted-text candidate-section-nav-hint">
          Выберите раздел кнопкой выше. Одновременно открыт один раздел.
        </p>
      ) : null}

      {seaServiceModalOpen ? (
        <div className="modal-overlay sea-service-modal-overlay" onClick={closeSeaServiceModal}>
          <div
            className="modal-card sea-service-modal-card"
            data-testid="sea-service-modal"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="sea-service-modal-title"
          >
            <div className="sea-service-modal-header menu-header">
              <h2 id="sea-service-modal-title">Sea service</h2>
              <button type="button" className="secondary-btn tiny-btn" onClick={closeSeaServiceModal}>
                Закрыть
              </button>
            </div>
            <div className="sea-service-modal-body">
              <SeaServiceSection
                newRows={newRows}
                setNewRows={setNewRows}
                seaService={seaService}
                editingRows={editingRows}
                editDrafts={editDrafts}
                setEditDrafts={setEditDrafts}
                onAddSeaService={onAddSeaService}
                onUpdateSeaService={onUpdateSeaService}
                onDeleteSeaService={onDeleteSeaService}
                startEdit={startEdit}
                cancelEdit={cancelEdit}
              />
            </div>
          </div>
        </div>
      ) : null}

      {ukrContractModalOpen ? (
        <div className="modal-overlay" onClick={() => !ukrContractSaving && setUkrContractModalOpen(false)}>
          <div className="modal-card ukr-contract-modal" data-testid="ukr-contract-modal" onClick={(event) => event.stopPropagation()}>
            <div className="menu-header">
              <h2>Украинский контракт (ручне заповнення)</h2>
              <button type="button" className="secondary-btn tiny-btn" onClick={() => !ukrContractSaving && setUkrContractModalOpen(false)}>
                Закрити
              </button>
            </div>
            <p className="muted" style={{ marginBottom: "1rem" }}>
              Поля зберігаються в картці кандидата. Для шаблонів Word/Excel використовуйте плейсхолдери зі списку нижче — наприклад{" "}
              <code>{"{{ ukr_surname }}"}</code>.
            </p>
            <div className="detail-grid ukr-contract-grid">
              {UKR_CONTRACT_FIELD_DEFS.map(({ key, label, type, options }) => (
                <label key={key}>
                  <span className="ukr-field-label">{label}</span>
                  {isDateLikeField(key) ? (
                    <DateDdMmYyyyInput
                      value={ukrContractForm[key] ?? ""}
                      readOnly={!canEditUkrContract}
                      onChange={(next) =>
                        setUkrContractForm((prev) => ({
                          ...prev,
                          [key]: next,
                        }))
                      }
                    />
                  ) : type === "select" ? (
                    <select
                      value={ukrContractForm[key] ?? ""}
                      disabled={!canEditUkrContract}
                      onChange={(event) =>
                        setUkrContractForm((prev) => ({
                          ...prev,
                          [key]: event.target.value,
                        }))
                      }
                    >
                      <option value="">—</option>
                      {(options || []).map((opt) => (
                        <option key={opt} value={opt}>
                          {opt}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type="text"
                      value={ukrContractForm[key] ?? ""}
                      readOnly={!canEditUkrContract || key === "ukr_full_name_ua"}
                      onChange={(event) =>
                        setUkrContractForm((prev) => ({
                          ...prev,
                          [key]: event.target.value,
                        }))
                      }
                    />
                  )}
                </label>
              ))}
            </div>
            <details className="ukr-placeholders-details" style={{ marginTop: "1rem" }}>
              <summary>Список плейсхолдерів для копіювання</summary>
              <pre className="ukr-placeholders-pre">{UKR_CONTRACT_FIELD_DEFS.map(({ placeholder }) => `{{ ${placeholder}}}`).join("\n")}</pre>
            </details>
            <div className="actions-row" style={{ marginTop: "1rem" }}>
              {canEditUkrContract ? (
                <button type="button" onClick={onSaveUkrContract} disabled={ukrContractSaving}>
                  {ukrContractSaving ? "Збереження…" : "Зберегти"}
                </button>
              ) : (
                <p className="muted">Перегляд: зміна полів доступна лише для admin / recruiter.</p>
              )}
              <button type="button" className="secondary-btn" onClick={() => !ukrContractSaving && setUkrContractModalOpen(false)}>
                Скасувати
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {podachaModalOpen ? (
        <div className="modal-overlay" onClick={closePodachaModal}>
          <div
            className="modal-card templates-select-modal"
            data-testid="podacha-modal"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="menu-header">
              <h2>ПОДАЧА — пакет для рассылки</h2>
              <button type="button" className="secondary-btn tiny-btn" onClick={closePodachaModal}>
                Закрыть
              </button>
            </div>
            {podachaError ? <p className="error">{podachaError}</p> : null}
            <section className="podacha-section">
              <h3>Поля этой подачи</h3>
              <label className="podacha-field">
                <span>Судно открытия (opening m/v)</span>
                <input
                  type="text"
                  value={openingVessel}
                  onChange={(event) => setOpeningVessel(event.target.value)}
                  disabled={podachaBuilding}
                />
              </label>
              <label className="podacha-field">
                <span>Предыдущее судно (ex-crew from m/v)</span>
                <input
                  type="text"
                  value={previousVessel}
                  onChange={(event) => setPreviousVessel(event.target.value)}
                  disabled={podachaBuilding}
                />
              </label>
            </section>
            <section className="podacha-section">
              <h3>Шаблоны</h3>
              {podachaLoading ? (
                <p className="muted-text">Загрузка шаблонов…</p>
              ) : podachaTemplateOptions.length === 0 ? (
                <p className="empty-row">Нет DOCX/XLSX шаблонов в менеджере</p>
              ) : (
                <div className="templates-select-list">
                  {podachaTemplateOptions.map((item) => (
                    <label key={item.id} className="templates-select-item">
                      <input
                        type="checkbox"
                        checked={selectedPodachaTemplateIds.includes(item.id)}
                        onChange={() => togglePodachaTemplateSelection(item.id)}
                        disabled={podachaBuilding}
                      />
                      <span className="templates-select-name">{item.fileName}</span>
                      <span className="templates-select-path">{item.folderPath || "Templates"}</span>
                    </label>
                  ))}
                </div>
              )}
            </section>
            <section className="podacha-section">
              <h3>Дополнительные файлы</h3>
              <div className="templates-select-list">
                <label className="templates-select-item">
                  <input
                    type="checkbox"
                    checked={includeCandidatePhotoInPodacha}
                    onChange={(event) => setIncludeCandidatePhotoInPodacha(event.target.checked)}
                    disabled={podachaBuilding || !candidatePhoto}
                  />
                  <span className="templates-select-name">Фото кандидата</span>
                  <span className="templates-select-path">
                    {candidatePhoto ? candidatePhoto.file_name : "фото не загружено"}
                  </span>
                </label>
              </div>
            </section>
            <section className="podacha-section">
              <h3>Сканы документов</h3>
              {displayDocuments.length === 0 ? (
                <p className="empty-row">Нет документов</p>
              ) : (
                <div className="templates-select-list">
                  {displayDocuments.map((doc) => {
                    const att = getRelationAttachment("document", doc.document_id);
                    return (
                      <label key={`doc-${doc.document_id}`} className="templates-select-item">
                        <input
                          type="checkbox"
                          checked={att ? selectedPodachaAttachmentIds.includes(att.attachment_id) : false}
                          onChange={() => togglePodachaAttachmentSelection(att?.attachment_id)}
                          disabled={podachaBuilding || !att}
                        />
                        <span className="templates-select-name">{doc.document_type || "Document"}</span>
                        <span className="templates-select-path">{att ? att.file_name : "нет скана"}</span>
                      </label>
                    );
                  })}
                </div>
              )}
            </section>
            <section className="podacha-section">
              <h3>Сканы сертификатов</h3>
              {allCertificateRows.length === 0 ? (
                <p className="empty-row">Нет сертификатов</p>
              ) : (
                <div className="templates-select-list">
                  {allCertificateRows.map((cert) => {
                    const att = getRelationAttachment("certificate", cert.certificate_id);
                    return (
                      <label key={`cert-${cert.certificate_id}`} className="templates-select-item">
                        <input
                          type="checkbox"
                          checked={att ? selectedPodachaAttachmentIds.includes(att.attachment_id) : false}
                          onChange={() => togglePodachaAttachmentSelection(att?.attachment_id)}
                          disabled={podachaBuilding || !att}
                        />
                        <span className="templates-select-name">{cert.certificate_type || "Certificate"}</span>
                        <span className="templates-select-path">{att ? att.file_name : "нет скана"}</span>
                      </label>
                    );
                  })}
                </div>
              )}
            </section>
            <div className="actions-row">
              <button
                type="button"
                data-testid="btn-podacha-build"
                onClick={onBuildSubmissionPack}
                disabled={podachaBuilding || podachaLoading}
              >
                {podachaBuilding ? "Сборка…" : "Собрать ZIP (до 5 МБ)"}
              </button>
              <button type="button" className="secondary-btn" onClick={closePodachaModal} disabled={podachaBuilding}>
                Отмена
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {templatesModalOpen ? (
        <div className="modal-overlay" onClick={closeTemplatesModal}>
          <div className="modal-card templates-select-modal" onClick={(event) => event.stopPropagation()}>
            <div className="menu-header">
              <h2>Выберите шаблоны для генерации</h2>
              <button type="button" className="secondary-btn tiny-btn" onClick={closeTemplatesModal}>
                Закрыть
              </button>
            </div>
            {templatesError ? <p className="error">{templatesError}</p> : null}
            {templatesLoading ? (
              <p>Загрузка шаблонов...</p>
            ) : templateOptions.length === 0 ? (
              <p className="empty-row">В разделе Templates пока нет файлов шаблонов</p>
            ) : (
              <div className="templates-explorer-layout">
                <div className="templates-explorer-tree">
                  <div className="templates-tree-node">
                    <div className="templates-tree-folder-row" style={{ paddingLeft: "0px" }}>
                      <button
                        type="button"
                        className="templates-tree-toggle"
                        onClick={() => {
                          if (templatesRootFolderId == null) return;
                          toggleFolderExpanded(templatesRootFolderId);
                        }}
                        aria-label={
                          templatesRootFolderId != null && expandedTemplateFolderIds.includes(templatesRootFolderId)
                            ? "Свернуть корневую папку"
                            : "Раскрыть корневую папку"
                        }
                      >
                        {templatesRootFolderId != null && expandedTemplateFolderIds.includes(templatesRootFolderId)
                          ? "▾"
                          : "▸"}
                      </button>
                      <button
                        type="button"
                        className={
                          selectedTemplateFolderId === templatesRootFolderId
                            ? "templates-tree-folder templates-tree-folder--active"
                            : "templates-tree-folder"
                        }
                        onClick={() => {
                          setSelectedTemplateFolderId(templatesRootFolderId);
                        }}
                      >
                        <span className="templates-tree-folder-name">📁 {templatesRootFolderName}</span>
                      </button>
                    </div>
                    {templatesRootFolderId != null && expandedTemplateFolderIds.includes(templatesRootFolderId)
                      ? renderTemplateTree(templatesRootFolderId, 1)
                      : null}
                  </div>
                </div>
                <div className="templates-explorer-files">
                  {selectedFolderFiles.length === 0 ? (
                    <p className="empty-row">В выбранной папке нет DOCX/XLSX шаблонов</p>
                  ) : (
                    <div className="templates-select-list">
                      {selectedFolderFiles.map((item) => (
                        <label key={item.id} className="templates-select-item">
                          <input
                            type="checkbox"
                            checked={selectedTemplateIds.includes(item.id)}
                            onChange={() => toggleTemplateSelection(item.id)}
                            disabled={generatingTemplates}
                          />
                          <span className="templates-select-name">{item.fileName}</span>
                          <span className="templates-select-path">{item.folderPath || "Templates"}</span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
            <div className="actions-row">
              <button
                type="button"
                onClick={onGenerateSelectedTemplates}
                disabled={generatingTemplates || templatesLoading || templateOptions.length === 0}
              >
                {generatingTemplates
                  ? "Генерация..."
                  : `Сгенерировать выбранные (${selectedTemplateIds.length})`}
              </button>
              <button type="button" className="secondary-btn" onClick={closeTemplatesModal} disabled={generatingTemplates}>
                Отмена
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {candidateFieldGroups.map((group) => {
        const sid = profileSectionId(group.title);
        return (
          <CollapsibleDetailBlock
            key={group.title}
            sectionId={sid}
            title={group.title}
            expanded={expandedSections.has(sid)}
            panelOnly
          >
            <div className="detail-grid">
              {group.fields.map(([field, label]) => (
                <label key={field}>
                  {label}
                  {field === "company_id" ? (
                    <select
                      value={candidate.company_id ?? ""}
                      onChange={(event) =>
                        setCandidate((prev) => ({
                          ...prev,
                          company_id: event.target.value ? Number(event.target.value) : null,
                        }))
                      }
                    >
                      <option value="">—</option>
                      {companiesList.map((company) => (
                        <option key={company.company_id} value={company.company_id}>
                          {company.name}
                        </option>
                      ))}
                    </select>
                  ) : field === "current_rank" ? (
                    <select
                      value={candidate.current_rank ?? ""}
                      onChange={(event) =>
                        setCandidate((prev) => ({
                          ...prev,
                          current_rank: event.target.value,
                        }))
                      }
                    >
                      <option value="">—</option>
                      {candidate.current_rank &&
                      !CANONICAL_POSITION_OPTIONS.includes(candidate.current_rank) ? (
                        <option value={candidate.current_rank}>
                          {candidate.current_rank} (текущее)
                        </option>
                      ) : null}
                      {CANONICAL_POSITION_OPTIONS.map((label) => (
                        <option key={label} value={label}>
                          {label}
                        </option>
                      ))}
                    </select>
                  ) : field === "surname" || field === "first_name" ? (
                    <input
                      type="text"
                      value={candidate[field] ?? ""}
                      onChange={(event) =>
                        setCandidate((prev) =>
                          _withComposedFullNames({
                            ...prev,
                            [field]: event.target.value,
                          })
                        )
                      }
                    />
                  ) : field === "full_name" || field === "latin_full_name" ? (
                    <input
                      type="text"
                      value={candidate[field] ?? ""}
                      readOnly
                    />
                  ) : isDateLikeField(field) ? (
                    <DateDdMmYyyyInput
                      value={candidate[field] ?? ""}
                      onChange={(next) =>
                        setCandidate((prev) => ({
                          ...prev,
                          [field]: next,
                        }))
                      }
                    />
                  ) : (
                    <input
                      type="text"
                      value={candidate[field] ?? ""}
                      onChange={(event) =>
                        setCandidate((prev) => ({
                          ...prev,
                          [field]: uppercaseCandidateNameFields.has(field)
                            ? _uppercaseCandidateName(event.target.value)
                            : event.target.value,
                        }))
                      }
                    />
                  )}
                </label>
              ))}
            </div>
            <button type="button" onClick={onSaveProfile} disabled={savingProfile}>
              {savingProfile ? "Сохранение..." : "Сохранить профиль"}
            </button>
          </CollapsibleDetailBlock>
        );
      })}

      <CollapsibleDetailBlock
        sectionId={SECTION.RECRUITMENT}
        title="Заявка / recruitment data"
        expanded={expandedSections.has(SECTION.RECRUITMENT)}
        panelOnly
      >
        <div className="detail-grid">
          {applicationFields.map(([field, label]) =>
            APPLICATION_BOOLEAN_FIELDS.has(field) ? (
              <label key={field}>
                {label}
                <select
                  value={recruitmentDraft[field] ?? ""}
                  disabled={!canEditRelations}
                  onChange={(event) =>
                    setRecruitmentDraft((prev) => ({
                      ...prev,
                      [field]: event.target.value,
                    }))
                  }
                >
                  <option value="">—</option>
                  <option value="true">Да</option>
                  <option value="false">Нет</option>
                </select>
              </label>
            ) : isDateLikeField(field) ? (
              <label key={field}>
                {label}
                <DateDdMmYyyyInput
                  value={recruitmentDraft[field] ?? ""}
                  readOnly={!canEditRelations}
                  onChange={(next) =>
                    setRecruitmentDraft((prev) => ({
                      ...prev,
                      [field]: next,
                    }))
                  }
                />
              </label>
            ) : (
              <label key={field}>
                {label}
                <input
                  type="text"
                  value={recruitmentDraft[field] ?? ""}
                  readOnly={!canEditRelations}
                  onChange={(event) =>
                    setRecruitmentDraft((prev) => ({
                      ...prev,
                      [field]: event.target.value,
                    }))
                  }
                />
              </label>
            )
          )}
        </div>
        {canEditRelations ? (
          <button type="button" onClick={onSaveRecruitment} disabled={recruitmentSaving}>
            {recruitmentSaving ? "Сохранение..." : "Сохранить заявку"}
          </button>
        ) : (
          <p className="muted-text">Редактирование заявки — для ролей admin и recruiter.</p>
        )}
      </CollapsibleDetailBlock>

      <CollapsibleDetailBlock
        sectionId={SECTION.SALARY_CALCULATOR}
        title="Калькулятор зарплаты"
        expanded={expandedSections.has(SECTION.SALARY_CALCULATOR)}
        panelOnly
      >
        <SalaryCalculatorSection
          candidateId={candidateId}
          canEdit={canEditRelations}
          companies={companiesList}
          savedJson={candidate?.salary_calculation_json}
          hintRank={recruitmentDraft.position_applied_for || recruitmentDraft.rank_applied_for || candidate?.current_rank}
          hintTotalWage={candidate?.desirable_salary_usd}
          hintPeriod={candidate?.submission_contract_duration_text}
          onSaved={() => loadCandidate({ showLoader: false })}
        />
      </CollapsibleDetailBlock>

      <CollapsibleDetailBlock
        sectionId={SECTION.CONTRACT}
        title="Контракт"
        expanded={expandedSections.has(SECTION.CONTRACT)}
        panelOnly
      >
        <ContractSection
          candidateId={candidateId}
          canEdit={canEditRelations}
          companies={companiesList}
          vessels={vesselsList}
          savedContractJson={candidate?.contract_json}
          savedSalaryJson={candidate?.salary_calculation_json}
          candidate={candidate}
          onSaved={() => loadCandidate({ showLoader: false })}
        />
      </CollapsibleDetailBlock>

      <CollapsibleDetailBlock
        sectionId={SECTION.COMMENTS}
        title="Комментарии"
        expanded={expandedSections.has(SECTION.COMMENTS)}
        panelOnly
      >
        {canEditRelations ? (
          <div className="candidate-comments-form">
            <textarea
              value={commentDraft}
              onChange={(event) => setCommentDraft(event.target.value)}
              placeholder="Новый комментарий"
              rows={4}
            />
            <button type="button" onClick={onAddComment} disabled={commentSaving || !commentDraft.trim()}>
              {commentSaving ? "Сохранение..." : "Добавить комментарий"}
            </button>
          </div>
        ) : null}
        <div className="candidate-comments-list">
          {comments.length === 0 ? (
            <p className="empty-row">Комментариев пока нет</p>
          ) : (
            comments.map((comment) => (
              <article key={comment.comment_id} className="candidate-comment-item">
                <time dateTime={comment.created_at || ""}>{formatCommentDate(comment.created_at)}</time>
                <p>{comment.comment_text}</p>
              </article>
            ))
          )}
        </div>
      </CollapsibleDetailBlock>

      <CollapsibleDetailBlock
        sectionId={SECTION.DOCUMENTS}
        title="Documents"
        expanded={expandedSections.has(SECTION.DOCUMENTS)}
        panelOnly
      >
        {canEditRelations ? (
          <div className="inline-form">
            <input
              type="text"
              placeholder="Тип документа"
              value={newRows.document.document_type}
              onChange={(event) =>
                setNewRows((prev) => ({
                  ...prev,
                  document: { ...prev.document, document_type: event.target.value },
                }))
              }
            />
            <input
              type="text"
              placeholder="Номер"
              value={newRows.document.document_number || ""}
              onChange={(event) =>
                setNewRows((prev) => ({
                  ...prev,
                  document: { ...prev.document, document_number: event.target.value },
                }))
              }
            />
            <input
              type="text"
              placeholder="Кем выдан"
              value={newRows.document.issuing_authority}
              onChange={(event) =>
                setNewRows((prev) => ({
                  ...prev,
                  document: { ...prev.document, issuing_authority: event.target.value },
                }))
              }
            />
            <DateDdMmYyyyInput
              value={newRows.document.date_of_issue}
              onChange={(next) =>
                setNewRows((prev) => ({
                  ...prev,
                  document: { ...prev.document, date_of_issue: next },
                }))
              }
            />
            <DateDdMmYyyyInput
              value={newRows.document.date_of_expiry}
              onChange={(next) =>
                setNewRows((prev) => ({
                  ...prev,
                  document: { ...prev.document, date_of_expiry: next },
                }))
              }
            />
            <button type="button" onClick={onAddDocument}>
              Добавить
            </button>
          </div>
        ) : (
          <p className="muted-text">Добавление и редактирование строк — для ролей admin и recruiter.</p>
        )}
        <details className="ukr-placeholders-details" style={{ marginBottom: "0.75rem" }}>
          <summary>Плейсхолдеры документов для Word/Excel</summary>
          <pre className="ukr-placeholders-pre">{canonicalDocumentPlaceholderLines().join("\n")}</pre>
        </details>
        <div className="table-wrap">
          <table className="candidate-table">
          <thead>
            <tr>
              <th>Код</th>
              <th>Тип</th>
              <th>Номер</th>
              <th>Кем выдан</th>
              <th>Дата выдачи</th>
              <th>Дата окончания</th>
              <th className="scan-col">Скан</th>
              <th>Действия</th>
            </tr>
          </thead>
          <tbody>
            {displayDocuments.map((item) => {
              const rowId = getId(item, ["document_id"]) ?? `canonical-${documentRowCode(item) || item.document_type}`;
              const relationId = getId(item, ["document_id"]);
              const canonicalRow = isCanonicalDocumentRow(item);
              const isEditing = relationId != null && editingRows.documents === relationId;
              const draft = isEditing ? editDrafts.documents : item;
              const attachmentKey = `document:${relationId}`;
              const currentAttachment = getRelationAttachment("document", relationId);
              const busy = Boolean(attachmentBusy[attachmentKey]);
              const rowClass = getExpiryClass(item.date_of_expiry || item.expiry_date);
              return (
                <tr
                  key={rowId}
                  data-scan-target={`document:${relationId}`}
                  className={`${rowClass} ${focusTarget === `document:${relationId}` ? "scan-target-highlight" : ""}`.trim()}
                >
                  <td className="muted-text">{documentRowCode(item) || "—"}</td>
                  <td>
                    <input
                      type="text"
                      value={draft.document_type || ""}
                      disabled={!isEditing || canonicalRow}
                      title={canonicalRow ? "Тип фиксирован для стандартного документа" : undefined}
                      onChange={(event) =>
                        setEditDrafts((prev) => ({
                          ...prev,
                          documents: { ...prev.documents, document_type: event.target.value },
                        }))
                      }
                    />
                  </td>
                  <td>
                    <input
                      type="text"
                      value={draft.document_number || ""}
                      disabled={!isEditing}
                      onChange={(event) =>
                        setEditDrafts((prev) => ({
                          ...prev,
                          documents: { ...prev.documents, document_number: event.target.value },
                        }))
                      }
                    />
                  </td>
                  <td>
                    <input
                      type="text"
                      value={draft.issuing_authority || ""}
                      disabled={!isEditing}
                      onChange={(event) =>
                        setEditDrafts((prev) => ({
                          ...prev,
                          documents: { ...prev.documents, issuing_authority: event.target.value },
                        }))
                      }
                    />
                  </td>
                  <td>
                    <DateDdMmYyyyInput
                      value={draft.date_of_issue || ""}
                      disabled={!isEditing}
                      onChange={(next) =>
                        setEditDrafts((prev) => ({
                          ...prev,
                          documents: { ...prev.documents, date_of_issue: next },
                        }))
                      }
                    />
                  </td>
                  <td>
                    <DateDdMmYyyyInput
                      value={draft.date_of_expiry || ""}
                      disabled={!isEditing}
                      onChange={(next) =>
                        setEditDrafts((prev) => ({
                          ...prev,
                          documents: { ...prev.documents, date_of_expiry: next },
                        }))
                      }
                    />
                  </td>
                  <td className={`scan-col ${!currentAttachment?.attachment_id ? "missing-scan-cell" : ""}`}>
                    <div className="scan-cell-inner">
                      <div className="scan-cell-toolbar">
                        {currentAttachment?.attachment_id ? (
                          <ScanDownloadLink
                            attachmentId={currentAttachment.attachment_id}
                            fileName={currentAttachment.file_name}
                          />
                        ) : (
                          <span className="muted-text">Нет скана</span>
                        )}
                        <FileDropzone
                          compact
                          disabled={busy || !relationId}
                          testId={`dropzone-document-${relationId || rowId}`}
                          label={busy ? "Загрузка..." : currentAttachment ? "Заменить скан" : "Загрузить скан"}
                          onFile={(file) =>
                            relationId
                              ? onUploadRelationAttachment("document", relationId, file, currentAttachment)
                              : undefined
                          }
                        />
                        {currentAttachment?.attachment_id ? (
                          <button
                            type="button"
                            className="danger-btn scan-delete-btn"
                            disabled={busy}
                            onClick={() =>
                              onDeleteRelationAttachment("document", relationId, currentAttachment.attachment_id)
                            }
                          >
                            Удалить скан
                          </button>
                        ) : null}
                      </div>
                    </div>
                    {attachmentErrors[attachmentKey] ? <div className="error">{attachmentErrors[attachmentKey]}</div> : null}
                  </td>
                  <td className="row-actions-cell">
                    <div className="actions-row">
                    {!canEditRelations ? (
                      <span className="muted-text">—</span>
                    ) : isEditing ? (
                      <>
                        <button type="button" onClick={() => onUpdateDocument(relationId)}>
                          Сохранить
                        </button>
                        <button type="button" className="secondary-btn" onClick={() => cancelEdit("documents")}>
                          Отмена
                        </button>
                      </>
                    ) : (
                      <>
                        <button type="button" onClick={() => beginEditDocument(item)}>
                          Редактировать
                        </button>
                        {relationId && !canonicalRow ? (
                          <button type="button" className="danger-btn" onClick={() => onDeleteDocument(relationId)}>
                            Удалить
                          </button>
                        ) : null}
                      </>
                    )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
          </table>
        </div>
      </CollapsibleDetailBlock>

      <CollapsibleDetailBlock
        sectionId={SECTION.VISAS}
        title="Визы"
        expanded={expandedSections.has(SECTION.VISAS)}
        panelOnly
      >
        <VisasSection
          displayVisas={displayVisas}
          canEditRelations={canEditRelations}
          focusTarget={focusTarget}
          editingVisaId={editingRows.visas}
          editDraft={editDrafts.visas}
          onEditDraftChange={(patch) =>
            setEditDrafts((prev) => ({ ...prev, visas: { ...prev.visas, ...patch } }))
          }
          newVisaDraft={newVisaDraft}
          onNewVisaDraftChange={setNewVisaDraft}
          onBeginEdit={beginEditVisa}
          onCancelEdit={() => cancelEdit("visas")}
          onSave={onUpdateVisa}
          onAdd={onAddVisa}
          onDelete={onDeleteVisa}
          getRelationAttachment={getRelationAttachment}
          onUploadRelationAttachment={onUploadRelationAttachment}
          onDeleteRelationAttachment={onDeleteRelationAttachment}
          attachmentBusy={attachmentBusy}
          attachmentErrors={attachmentErrors}
        />
      </CollapsibleDetailBlock>

      <CollapsibleDetailBlock
        sectionId={SECTION.DIPLOMAS}
        title="Diplomas"
        expanded={expandedSections.has(SECTION.DIPLOMAS)}
        panelOnly
      >
        <details className="ukr-placeholders-details" style={{ marginBottom: "0.75rem" }}>
          <summary>Плейсхолдеры дипломов для Word/Excel</summary>
          <pre className="ukr-placeholders-pre">{canonicalDiplomaPlaceholderLines().join("\n")}</pre>
        </details>
        {canEditRelations ? (
          <CertificateInlineAddForm
            draft={newRows.diploma}
            disabled={!canEditRelations}
            onDraftChange={(next) => setNewRows((prev) => ({ ...prev, diploma: next }))}
            onAdd={onAddDiploma}
          />
        ) : (
          <p className="muted-text">Добавление и редактирование — для ролей admin и recruiter.</p>
        )}
        <h4 className="detail-block__panel-title detail-block__panel-title--sub">Рабочие дипломы</h4>
        <CertificateRowsTable
          items={displayDiplomas}
          section="diplomas"
          lockCanonicalType
          showCodeColumn
          showCocRankColumn
          rowLabelMode="diploma"
          diplomaSpecs={CANONICAL_DIPLOMA_SPECS}
          canEditRelations={canEditRelations}
          focusTarget={focusTarget}
          editingRowId={editingRows.diplomas}
          editDraft={editDrafts.diplomas}
          setEditDrafts={setEditDrafts}
          attachmentBusy={attachmentBusy}
          attachmentErrors={attachmentErrors}
          getRelationAttachment={getRelationAttachment}
          onUploadRelationAttachment={onUploadRelationAttachment}
          onDeleteRelationAttachment={onDeleteRelationAttachment}
          onBeginEdit={(item) => beginEditDiploma(item, "diplomas")}
          onUpdate={(id) => onUpdateCertificate(id, "diplomas")}
          onCancelEdit={() => cancelEdit("diplomas")}
          onDelete={(id) => onDeleteCertificate(id)}
          canDeleteRow={(item) => isCustomDiplomaRow(item, CANONICAL_DIPLOMA_SPECS)}
          getRowExpiryClass={getCertificateExpiryClass}
        />
        <h4 className="detail-block__panel-title detail-block__panel-title--sub" style={{ marginTop: "1.25rem" }}>
          Tanker Diploma
        </h4>
        {canEditRelations ? (
          <CertificateInlineAddForm
            draft={newRows.tankerDiploma}
            disabled={!canEditRelations}
            onDraftChange={(next) => setNewRows((prev) => ({ ...prev, tankerDiploma: next }))}
            onAdd={onAddTankerDiploma}
          />
        ) : null}
        <CertificateRowsTable
          items={displayTankerDiplomas}
          section="tankerDiplomas"
          lockCanonicalType
          showCodeColumn
          rowLabelMode="diploma"
          diplomaSpecs={CANONICAL_TANKER_DIPLOMA_SPECS}
          canEditRelations={canEditRelations}
          focusTarget={focusTarget}
          editingRowId={editingRows.tankerDiplomas}
          editDraft={editDrafts.tankerDiplomas}
          setEditDrafts={setEditDrafts}
          attachmentBusy={attachmentBusy}
          attachmentErrors={attachmentErrors}
          getRelationAttachment={getRelationAttachment}
          onUploadRelationAttachment={onUploadRelationAttachment}
          onDeleteRelationAttachment={onDeleteRelationAttachment}
          onBeginEdit={(item) => beginEditDiploma(item, "tankerDiplomas")}
          onUpdate={(id) => onUpdateCertificate(id, "tankerDiplomas")}
          onCancelEdit={() => cancelEdit("tankerDiplomas")}
          onDelete={(id) => onDeleteCertificate(id)}
          canDeleteRow={(item) => isCustomDiplomaRow(item, CANONICAL_TANKER_DIPLOMA_SPECS)}
          getRowExpiryClass={getCertificateExpiryClass}
        />
        <p className="muted-text" style={{ marginTop: "0.75rem" }}>
          Список слотов и плейсхолдеров: docs/PLACEHOLDERS_DIPLOMAS.md
        </p>
      </CollapsibleDetailBlock>

      <CollapsibleDetailBlock
        sectionId={SECTION.MEDICINE}
        title="Медицина"
        expanded={expandedSections.has(SECTION.MEDICINE)}
        panelOnly
      >
        <details className="ukr-placeholders-details" style={{ marginBottom: "0.75rem" }}>
          <summary>Плейсхолдеры мед. документов для Word/Excel</summary>
          <pre className="ukr-placeholders-pre">{canonicalMedicalPlaceholderLines().join("\n")}</pre>
        </details>
        {canEditRelations ? (
          <CertificateInlineAddForm
            draft={newRows.medicalDocument}
            disabled={!canEditRelations}
            onDraftChange={(next) => setNewRows((prev) => ({ ...prev, medicalDocument: next }))}
            onAdd={onAddMedicalDocument}
          />
        ) : (
          <p className="muted-text">Добавление и редактирование — для ролей admin и recruiter.</p>
        )}
        <h4 className="detail-block__panel-title detail-block__panel-title--sub">Мед. документы</h4>
        <CertificateRowsTable
          items={displayMedicalDocuments}
          section="medicalDocuments"
          lockCanonicalType
          showCodeColumn
          rowLabelMode="medical"
          diplomaSpecs={CANONICAL_MEDICAL_SPECS}
          canEditRelations={canEditRelations}
          focusTarget={focusTarget}
          editingRowId={editingRows.medicalDocuments}
          editDraft={editDrafts.medicalDocuments}
          setEditDrafts={setEditDrafts}
          attachmentBusy={attachmentBusy}
          attachmentErrors={attachmentErrors}
          getRelationAttachment={getRelationAttachment}
          onUploadRelationAttachment={onUploadRelationAttachment}
          onDeleteRelationAttachment={onDeleteRelationAttachment}
          onBeginEdit={(item) => beginEditMedical(item)}
          onUpdate={(id) => onUpdateCertificate(id, "medicalDocuments")}
          onCancelEdit={() => cancelEdit("medicalDocuments")}
          onDelete={(id) => onDeleteCertificate(id)}
          canDeleteRow={(item) => isCustomMedicalRow(item, CANONICAL_MEDICAL_SPECS)}
          getRowExpiryClass={getCertificateExpiryClass}
        />
        <p className="muted-text" style={{ marginTop: "0.75rem" }}>
          Список слотов и плейсхолдеров: docs/PLACEHOLDERS_MEDICAL.md
        </p>
      </CollapsibleDetailBlock>

      <CollapsibleDetailBlock
        sectionId={SECTION.CERTIFICATES}
        title="Certificates"
        expanded={expandedSections.has(SECTION.CERTIFICATES)}
        panelOnly
      >
        <details className="ukr-placeholders-details" style={{ marginBottom: "0.75rem" }}>
          <summary>Плейсхолдеры сертификатов для Word/Excel</summary>
          <pre className="ukr-placeholders-pre">{canonicalCertificatePlaceholderLines().join("\n")}</pre>
        </details>
        {canEditRelations ? (
          <CertificateInlineAddForm
            draft={newRows.certificate}
            disabled={!canEditRelations}
            onDraftChange={(next) => setNewRows((prev) => ({ ...prev, certificate: next }))}
            onAdd={onAddCertificate}
          />
        ) : (
          <p className="muted-text">Добавление и редактирование — для ролей admin и recruiter.</p>
        )}

        <h4 className="detail-block__panel-title detail-block__panel-title--sub">Конвенционные сертификаты</h4>
        <CertificateRowsTable
          items={displayConventionalCertificates}
          section="conventionalCerts"
          lockCanonicalType
          showCodeColumn
          canEditRelations={canEditRelations}
          focusTarget={focusTarget}
          editingRowId={editingRows.conventionalCerts}
          editDraft={editDrafts.conventionalCerts}
          setEditDrafts={setEditDrafts}
          attachmentBusy={attachmentBusy}
          attachmentErrors={attachmentErrors}
          getRelationAttachment={getRelationAttachment}
          onUploadRelationAttachment={onUploadRelationAttachment}
          onDeleteRelationAttachment={onDeleteRelationAttachment}
          onBeginEdit={(item) => beginEditCanonicalCertificate(item, "conventionalCerts", CANONICAL_CONVENTIONAL_SPECS)}
          onUpdate={(id) => onUpdateCertificate(id, "conventionalCerts")}
          onCancelEdit={() => cancelEdit("conventionalCerts")}
          getRowExpiryClass={getCertificateExpiryClass}
        />

        <h4 className="detail-block__panel-title detail-block__panel-title--sub" style={{ marginTop: "1.25rem" }}>
          Specific type of ECDIS
        </h4>
        <CertificateRowsTable
          items={displayEcdisCertificates}
          section="ecdisCerts"
          lockCanonicalType
          showCodeColumn
          canEditRelations={canEditRelations}
          focusTarget={focusTarget}
          editingRowId={editingRows.ecdisCerts}
          editDraft={editDrafts.ecdisCerts}
          setEditDrafts={setEditDrafts}
          attachmentBusy={attachmentBusy}
          attachmentErrors={attachmentErrors}
          getRelationAttachment={getRelationAttachment}
          onUploadRelationAttachment={onUploadRelationAttachment}
          onDeleteRelationAttachment={onDeleteRelationAttachment}
          onBeginEdit={(item) => beginEditCanonicalCertificate(item, "ecdisCerts", CANONICAL_ECDIS_SPECS)}
          onUpdate={(id) => onUpdateCertificate(id, "ecdisCerts")}
          onCancelEdit={() => cancelEdit("ecdisCerts")}
          getRowExpiryClass={getCertificateExpiryClass}
        />

        <h4 className="detail-block__panel-title detail-block__panel-title--sub" style={{ marginTop: "1.25rem" }}>
          Компанейские сертификаты
        </h4>
        <CertificateRowsTable
          items={displayCompanyCertificates}
          section="companyCerts"
          lockCanonicalType
          showCodeColumn
          canEditRelations={canEditRelations}
          focusTarget={focusTarget}
          editingRowId={editingRows.companyCerts}
          editDraft={editDrafts.companyCerts}
          setEditDrafts={setEditDrafts}
          attachmentBusy={attachmentBusy}
          attachmentErrors={attachmentErrors}
          getRelationAttachment={getRelationAttachment}
          onUploadRelationAttachment={onUploadRelationAttachment}
          onDeleteRelationAttachment={onDeleteRelationAttachment}
          onBeginEdit={(item) => beginEditCanonicalCertificate(item, "companyCerts", CANONICAL_COMPANY_SPECS)}
          onUpdate={(id) => onUpdateCertificate(id, "companyCerts")}
          onCancelEdit={() => cancelEdit("companyCerts")}
          getRowExpiryClass={getCertificateExpiryClass}
        />

        <h4 className="detail-block__panel-title detail-block__panel-title--sub" style={{ marginTop: "1.25rem" }}>
          Specific type of BWTS
        </h4>
        <CertificateRowsTable
          items={displayBwtsCertificates}
          section="bwtsCerts"
          lockCanonicalType
          showCodeColumn
          canEditRelations={canEditRelations}
          focusTarget={focusTarget}
          editingRowId={editingRows.bwtsCerts}
          editDraft={editDrafts.bwtsCerts}
          setEditDrafts={setEditDrafts}
          attachmentBusy={attachmentBusy}
          attachmentErrors={attachmentErrors}
          getRelationAttachment={getRelationAttachment}
          onUploadRelationAttachment={onUploadRelationAttachment}
          onDeleteRelationAttachment={onDeleteRelationAttachment}
          onBeginEdit={(item) => beginEditCanonicalCertificate(item, "bwtsCerts", CANONICAL_BWTS_SPECS)}
          onUpdate={(id) => onUpdateCertificate(id, "bwtsCerts")}
          onCancelEdit={() => cancelEdit("bwtsCerts")}
          getRowExpiryClass={getCertificateExpiryClass}
        />

        <h4 className="detail-block__panel-title detail-block__panel-title--sub" style={{ marginTop: "1.25rem" }}>
          Прочие сертификаты
        </h4>
        <CertificateRowsTable
          items={displayOtherCertificates}
          section="certificates"
          showCodeColumn
          rowLabelMode="sameAsType"
          canEditRelations={canEditRelations}
          focusTarget={focusTarget}
          editingRowId={editingRows.certificates}
          editDraft={editDrafts.certificates}
          setEditDrafts={setEditDrafts}
          attachmentBusy={attachmentBusy}
          attachmentErrors={attachmentErrors}
          getRelationAttachment={getRelationAttachment}
          onUploadRelationAttachment={onUploadRelationAttachment}
          onDeleteRelationAttachment={onDeleteRelationAttachment}
          onBeginEdit={(item) => startEdit("certificates", getId(item, ["certificate_id"]), item)}
          onUpdate={(id) => onUpdateCertificate(id, "certificates")}
          onCancelEdit={() => cancelEdit("certificates")}
          onDelete={(id) => onDeleteCertificate(id)}
          getRowExpiryClass={getCertificateExpiryClass}
        />

        <p className="muted-text" style={{ marginTop: "0.75rem" }}>
          Список слотов и плейсхолдеров: docs/PLACEHOLDERS_CERTIFICATES.md
        </p>
      </CollapsibleDetailBlock>

      <CollapsibleDetailBlock
        sectionId={SECTION.FLAG_DOCUMENTS}
        title="Flag Documents"
        expanded={expandedSections.has(SECTION.FLAG_DOCUMENTS)}
        panelOnly
      >
        {canEditRelations ? (
          <div className="inline-form flag-document-inline-form">
            <input
              type="text"
              placeholder="Страна флага *"
              value={newRows.flagDocument.flag_country}
              onChange={(event) =>
                setNewRows((prev) => ({
                  ...prev,
                  flagDocument: { ...prev.flagDocument, flag_country: event.target.value },
                }))
              }
            />
            <input
              type="text"
              placeholder="Тип документа"
              value={newRows.flagDocument.flag_document_type}
              onChange={(event) =>
                setNewRows((prev) => ({
                  ...prev,
                  flagDocument: { ...prev.flagDocument, flag_document_type: event.target.value },
                }))
              }
            />
            <input
              type="text"
              placeholder="Rank"
              value={newRows.flagDocument.rank}
              onChange={(event) =>
                setNewRows((prev) => ({
                  ...prev,
                  flagDocument: { ...prev.flagDocument, rank: event.target.value },
                }))
              }
            />
            <input
              type="text"
              placeholder="Номер"
              value={newRows.flagDocument.doc_number}
              onChange={(event) =>
                setNewRows((prev) => ({
                  ...prev,
                  flagDocument: { ...prev.flagDocument, doc_number: event.target.value },
                }))
              }
            />
            <DateDdMmYyyyInput
              placeholder="Выдача дд-мм-гггг"
              value={newRows.flagDocument.date_of_issuance}
              onChange={(next) =>
                setNewRows((prev) => ({
                  ...prev,
                  flagDocument: { ...prev.flagDocument, date_of_issuance: next },
                }))
              }
            />
            <DateDdMmYyyyInput
              placeholder="Expiry дд-мм-гггг"
              value={newRows.flagDocument.date_of_expiry}
              onChange={(next) =>
                setNewRows((prev) => ({
                  ...prev,
                  flagDocument: { ...prev.flagDocument, date_of_expiry: next },
                }))
              }
            />
            <input
              type="text"
              placeholder="Remarks"
              value={newRows.flagDocument.remarks}
              onChange={(event) =>
                setNewRows((prev) => ({
                  ...prev,
                  flagDocument: { ...prev.flagDocument, remarks: event.target.value },
                }))
              }
            />
            <button type="button" onClick={onAddFlagDocument}>
              Добавить
            </button>
          </div>
        ) : null}
        <div className="table-wrap">
          <table className="candidate-table candidate-table--cells">
            <thead>
              <tr>
                <th>Flag</th>
                <th>Type</th>
                <th>Rank</th>
                <th>Doc №</th>
                <th>Выдача</th>
                <th>Expiry</th>
                <th>Remarks</th>
                <th className="scan-col">Скан</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {flagDocuments.length === 0 ? (
                <tr>
                  {[0, 1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
                    <td key={i} className="empty-cell muted-text">
                      {i === 0 ? "Нет записей" : "—"}
                    </td>
                  ))}
                </tr>
              ) : (
                flagDocuments.map((item) => {
                  const rowId = getId(item, ["flag_document_id"]);
                  const relationId = rowId;
                  const attachmentKey = `flag_document:${relationId}`;
                  const currentAttachment = getRelationAttachment("flag_document", relationId);
                  const busy = Boolean(attachmentBusy[attachmentKey]);
                  const isEditing = editingRows.flagDocuments === rowId;
                  const draft = isEditing ? editDrafts.flagDocuments : item;
                  const rowClass = getExpiryClass(item.date_of_expiry);
                  return (
                    <tr
                      key={rowId}
                      data-scan-target={`flag_document:${relationId}`}
                      className={`${rowClass} ${focusTarget === `flag_document:${relationId}` ? "scan-target-highlight" : ""}`.trim()}
                    >
                      <td>
                        {isEditing ? (
                          <input
                            type="text"
                            value={draft.flag_country || ""}
                            onChange={(event) =>
                              setEditDrafts((prev) => ({
                                ...prev,
                                flagDocuments: { ...prev.flagDocuments, flag_country: event.target.value },
                              }))
                            }
                          />
                        ) : (
                          displayValue(item.flag_country)
                        )}
                      </td>
                      <td>
                        {isEditing ? (
                          <input
                            type="text"
                            value={draft.flag_document_type || ""}
                            onChange={(event) =>
                              setEditDrafts((prev) => ({
                                ...prev,
                                flagDocuments: { ...prev.flagDocuments, flag_document_type: event.target.value },
                              }))
                            }
                          />
                        ) : (
                          displayValue(item.flag_document_type)
                        )}
                      </td>
                      <td>
                        {isEditing ? (
                          <input
                            type="text"
                            value={draft.rank || ""}
                            onChange={(event) =>
                              setEditDrafts((prev) => ({
                                ...prev,
                                flagDocuments: { ...prev.flagDocuments, rank: event.target.value },
                              }))
                            }
                          />
                        ) : (
                          displayValue(item.rank)
                        )}
                      </td>
                      <td>
                        {isEditing ? (
                          <input
                            type="text"
                            value={draft.doc_number || ""}
                            onChange={(event) =>
                              setEditDrafts((prev) => ({
                                ...prev,
                                flagDocuments: { ...prev.flagDocuments, doc_number: event.target.value },
                              }))
                            }
                          />
                        ) : (
                          displayValue(item.doc_number)
                        )}
                      </td>
                      <td>
                        {isEditing ? (
                          <DateDdMmYyyyInput
                            value={draft.date_of_issuance || ""}
                            onChange={(next) =>
                              setEditDrafts((prev) => ({
                                ...prev,
                                flagDocuments: { ...prev.flagDocuments, date_of_issuance: next },
                              }))
                            }
                          />
                        ) : (
                          displayValue(item.date_of_issuance)
                        )}
                      </td>
                      <td>
                        {isEditing ? (
                          <DateDdMmYyyyInput
                            value={draft.date_of_expiry || ""}
                            onChange={(next) =>
                              setEditDrafts((prev) => ({
                                ...prev,
                                flagDocuments: { ...prev.flagDocuments, date_of_expiry: next },
                              }))
                            }
                          />
                        ) : (
                          displayValue(item.date_of_expiry)
                        )}
                      </td>
                      <td>
                        {isEditing ? (
                          <input
                            type="text"
                            value={draft.remarks || ""}
                            onChange={(event) =>
                              setEditDrafts((prev) => ({
                                ...prev,
                                flagDocuments: { ...prev.flagDocuments, remarks: event.target.value },
                              }))
                            }
                          />
                        ) : (
                          displayValue(item.remarks)
                        )}
                      </td>
                      <td className={`scan-col ${!currentAttachment?.attachment_id ? "missing-scan-cell" : ""}`}>
                        <div className="scan-cell-inner">
                          <div className="scan-cell-toolbar">
                            {currentAttachment?.attachment_id ? (
                              <ScanDownloadLink
                                attachmentId={currentAttachment.attachment_id}
                                fileName={currentAttachment.file_name}
                              />
                            ) : (
                              <span className="muted-text">Нет скана</span>
                            )}
                            {canEditRelations ? (
                              <FileDropzone
                                compact
                                disabled={busy}
                                testId={`dropzone-flag_document-${relationId}`}
                                label={busy ? "Загрузка..." : currentAttachment ? "Заменить скан" : "Загрузить скан"}
                                onFile={(file) => onUploadRelationAttachment("flag_document", relationId, file, currentAttachment)}
                              />
                            ) : null}
                            {currentAttachment?.attachment_id ? (
                              <button
                                type="button"
                                className="danger-btn scan-delete-btn"
                                disabled={busy}
                                onClick={() =>
                                  onDeleteRelationAttachment("flag_document", relationId, currentAttachment.attachment_id)
                                }
                              >
                                Удалить скан
                              </button>
                            ) : null}
                          </div>
                        </div>
                        {attachmentErrors[attachmentKey] ? <div className="error">{attachmentErrors[attachmentKey]}</div> : null}
                      </td>
                      <td className="row-actions-cell">
                        <div className="actions-row">
                        {canEditRelations ? (
                          isEditing ? (
                            <>
                              <button type="button" onClick={() => onUpdateFlagDocument(rowId)}>
                                Сохранить
                              </button>
                              <button type="button" className="secondary-btn" onClick={() => cancelEdit("flagDocuments")}>
                                Отмена
                              </button>
                            </>
                          ) : (
                            <>
                              <button type="button" onClick={() => startEdit("flagDocuments", rowId, item)}>
                                Редактировать
                              </button>
                              <button type="button" className="danger-btn" onClick={() => onDeleteFlagDocument(rowId)}>
                                Удалить
                              </button>
                            </>
                          )
                        ) : (
                          <span className="muted-text">—</span>
                        )}
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </CollapsibleDetailBlock>

      <CollapsibleDetailBlock
        sectionId={SECTION.FAMILY_CONTACTS}
        title="Family Contacts"
        expanded={expandedSections.has(SECTION.FAMILY_CONTACTS)}
        panelOnly
      >
        {canEditRelations ? (
          <div className="inline-form family-contact-inline-form">
            <input
              type="text"
              placeholder="ФИО *"
              value={newRows.familyContact.full_name}
              onChange={(event) =>
                setNewRows((prev) => ({
                  ...prev,
                  familyContact: { ...prev.familyContact, full_name: event.target.value },
                }))
              }
            />
            <input
              type="text"
              placeholder="Relationship"
              value={newRows.familyContact.relationship_to_candidate}
              onChange={(event) =>
                setNewRows((prev) => ({
                  ...prev,
                  familyContact: { ...prev.familyContact, relationship_to_candidate: event.target.value },
                }))
              }
            />
            <input
              type="text"
              placeholder="Phone"
              value={newRows.familyContact.phone}
              onChange={(event) =>
                setNewRows((prev) => ({
                  ...prev,
                  familyContact: { ...prev.familyContact, phone: event.target.value },
                }))
              }
            />
            <input
              type="text"
              placeholder="Email"
              value={newRows.familyContact.email}
              onChange={(event) =>
                setNewRows((prev) => ({
                  ...prev,
                  familyContact: { ...prev.familyContact, email: event.target.value },
                }))
              }
            />
            <input
              type="text"
              placeholder="Address"
              value={newRows.familyContact.address}
              onChange={(event) =>
                setNewRows((prev) => ({
                  ...prev,
                  familyContact: { ...prev.familyContact, address: event.target.value },
                }))
              }
            />
            <button type="button" onClick={onAddFamilyContact}>
              Добавить
            </button>
          </div>
        ) : null}
        <div className="table-wrap">
          <table className="candidate-table candidate-table--cells">
            <thead>
              <tr>
                <th>ФИО</th>
                <th>Relationship</th>
                <th>Phone</th>
                <th>Email</th>
                <th>Address</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {familyContacts.length === 0 ? (
                <tr>
                  {[0, 1, 2, 3, 4, 5].map((i) => (
                    <td key={i} className="empty-cell muted-text">
                      {i === 0 ? "Нет записей" : "—"}
                    </td>
                  ))}
                </tr>
              ) : (
                familyContacts.map((item) => {
                  const rowId = getId(item, ["family_contact_id"]);
                  const isEditing = editingRows.familyContacts === rowId;
                  const draft = isEditing ? editDrafts.familyContacts : item;
                  return (
                    <tr key={rowId}>
                      <td>
                        {isEditing ? (
                          <input
                            type="text"
                            value={draft.full_name || ""}
                            onChange={(event) =>
                              setEditDrafts((prev) => ({
                                ...prev,
                                familyContacts: { ...prev.familyContacts, full_name: event.target.value },
                              }))
                            }
                          />
                        ) : (
                          displayValue(item.full_name)
                        )}
                      </td>
                      <td>
                        {isEditing ? (
                          <input
                            type="text"
                            value={draft.relationship_to_candidate || ""}
                            onChange={(event) =>
                              setEditDrafts((prev) => ({
                                ...prev,
                                familyContacts: { ...prev.familyContacts, relationship_to_candidate: event.target.value },
                              }))
                            }
                          />
                        ) : (
                          displayValue(item.relationship_to_candidate)
                        )}
                      </td>
                      <td>
                        {isEditing ? (
                          <input
                            type="text"
                            value={draft.phone || ""}
                            onChange={(event) =>
                              setEditDrafts((prev) => ({
                                ...prev,
                                familyContacts: { ...prev.familyContacts, phone: event.target.value },
                              }))
                            }
                          />
                        ) : (
                          displayValue(item.phone)
                        )}
                      </td>
                      <td>
                        {isEditing ? (
                          <input
                            type="text"
                            value={draft.email || ""}
                            onChange={(event) =>
                              setEditDrafts((prev) => ({
                                ...prev,
                                familyContacts: { ...prev.familyContacts, email: event.target.value },
                              }))
                            }
                          />
                        ) : (
                          displayValue(item.email)
                        )}
                      </td>
                      <td>
                        {isEditing ? (
                          <input
                            type="text"
                            value={draft.address || ""}
                            onChange={(event) =>
                              setEditDrafts((prev) => ({
                                ...prev,
                                familyContacts: { ...prev.familyContacts, address: event.target.value },
                              }))
                            }
                          />
                        ) : (
                          displayValue(item.address)
                        )}
                      </td>
                      <td className="actions-row">
                        {canEditRelations ? (
                          isEditing ? (
                            <>
                              <button type="button" onClick={() => onUpdateFamilyContact(rowId)}>
                                Сохранить
                              </button>
                              <button type="button" className="secondary-btn" onClick={() => cancelEdit("familyContacts")}>
                                Отмена
                              </button>
                            </>
                          ) : (
                            <>
                              <button type="button" onClick={() => startEdit("familyContacts", rowId, item)}>
                                Редактировать
                              </button>
                              <button type="button" className="danger-btn" onClick={() => onDeleteFamilyContact(rowId)}>
                                Удалить
                              </button>
                            </>
                          )
                        ) : (
                          <span className="muted-text">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </CollapsibleDetailBlock>
    </section>
  );
}
