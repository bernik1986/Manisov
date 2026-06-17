/** Sea contract tab — saved JSON on candidate (contract_json). */

/** Candidate profile fields available in docxtpl (from CRM card, not contract_json). */
export const CANDIDATE_PERSONAL_PLACEHOLDER_DEFS = [
  { key: "current_date", label: "Current date" },
  { key: "surname", label: "Фамилия" },
  { key: "first_name", label: "Имя" },
  { key: "middle_name", label: "Отчество" },
  { key: "full_name", label: "Полное имя" },
  { key: "latin_full_name", label: "Latin Full Name" },
  { key: "native_full_name", label: "Native Full Name" },
  { key: "date_of_birth", label: "Дата рождения" },
  { key: "place_of_birth", label: "Место рождения" },
  { key: "country_of_birth", label: "Страна рождения" },
  { key: "nationality", label: "Национальность" },
  { key: "citizenship", label: "Гражданство" },
  { key: "age", label: "Возраст" },
  { key: "gender", label: "Пол" },
  { key: "marital_status", label: "Семейное положение" },
  { key: "father_name", label: "Имя отца" },
  { key: "mother_name", label: "Имя матери" },
  { key: "primary_phone", label: "Основной телефон" },
  { key: "mobile_phone", label: "Мобильный" },
  { key: "email", label: "Email" },
  { key: "home_address", label: "Домашний адрес" },
  { key: "permanent_address", label: "Постоянный адрес" },
  { key: "city", label: "Город" },
  { key: "country", label: "Страна" },
  { key: "current_rank", label: "Текущая должность" },
  { key: "passport_number", label: "Номер паспорта" },
  { key: "passport_issue_date", label: "Дата выдачи паспорта" },
  { key: "passport_expiry_date", label: "Срок действия паспорта" },
  { key: "passport_place_of_issue", label: "Кем / где выдан паспорт" },
  { key: "seaman_book_number", label: "Seaman's Book — номер" },
  { key: "seaman_book_issue_date", label: "Seaman's Book — дата выдачи" },
  { key: "seaman_book_expiry_date", label: "Seaman's Book — срок действия" },
];

export const CANDIDATE_PERSONAL_PLACEHOLDER_LINES = CANDIDATE_PERSONAL_PLACEHOLDER_DEFS.map(
  ({ key }) => `{{ ${key} }}`
);

export const CONTRACT_EDITABLE_FIELD_DEFS = [
  { key: "contract_sign_date", label: "Дата подписания контракта", placeholder: "contract_sign_date", type: "date" },
  { key: "contract_period", label: "Срок контракта / Period of employment", placeholder: "contract_period", type: "text" },
  { key: "contract_embarkation_date", label: "Дата посадки", placeholder: "contract_embarkation_date", type: "date" },
  { key: "contract_embarkation_port", label: "Порт посадки", placeholder: "contract_embarkation_port", type: "text" },
  { key: "contract_number", label: "Номер контракта", placeholder: "contract_number", type: "text" },
  { key: "contract_remarks", label: "Примечания", placeholder: "contract_remarks", type: "text" },
];

export const CONTRACT_DEPARTURE_FIELD_DEFS = [
  {
    key: "contract_departure_date",
    label: "Дата вылета",
    placeholder: "contract_departure_date",
    type: "date",
  },
];

export const CONTRACT_AIRPORT_FIELD_DEFS = [
  { key: "contract_home_airport", label: "Home airport", placeholder: "contract_home_airport", type: "text" },
  {
    key: "contract_departure_airport",
    label: "Departure airport",
    placeholder: "contract_departure_airport",
    type: "text",
  },
];

export const CONTRACT_ALL_EDITABLE_FIELD_DEFS = [
  ...CONTRACT_EDITABLE_FIELD_DEFS,
  ...CONTRACT_DEPARTURE_FIELD_DEFS,
  ...CONTRACT_AIRPORT_FIELD_DEFS,
];

export const CONTRACT_VESSEL_PREVIEW_FIELDS = [
  ["name", "Название"],
  ["imo", "IMO"],
  ["flag", "Флаг"],
  ["port_of_registry", "Port of Registry"],
  ["grt", "GRT"],
  ["deadweight", "Dead Weight"],
  ["year_built", "Year of Built"],
  ["engine_type", "Engine Type"],
  ["engine_hp", "H.P."],
];

export const CONTRACT_PLACEHOLDER_LINES = [
  "{{ contract_company_name }}",
  "{{ contract_company_slug }}",
  "{{ contract_vessel_name }}",
  "{{ contract_rank }}",
  ...CONTRACT_ALL_EDITABLE_FIELD_DEFS.map((f) => `{{ ${f.placeholder} }}`),
  "{{ home_airport }}",
  "{{ departure_airport }}",
  "{{ departure_date }}",
  "{{ contract_vessel_imo }}",
  "{{ contract_vessel_flag }}",
  "{{ contract_vessel_grt }}",
  "{{ contract_vessel_type }}",
  "{{ salary_total_wage }}",
  "{{ salary_basic_monthly_wage }}",
];

export function createEmptyContractForm() {
  return {
    company_id: "",
    vessel_id: "",
    rank: "",
    ...Object.fromEntries(CONTRACT_ALL_EDITABLE_FIELD_DEFS.map(({ key }) => [key, ""])),
  };
}

export function hydrateContractForm(parsed, candidate) {
  const next = { ...parsed };
  for (const { key } of CONTRACT_AIRPORT_FIELD_DEFS) {
    if (String(next[key] ?? "").trim()) {
      continue;
    }
    if (key === "contract_home_airport" && candidate?.home_airport) {
      next[key] = String(candidate.home_airport);
    }
    if (key === "contract_departure_airport" && candidate?.departure_airport) {
      next[key] = String(candidate.departure_airport);
    }
  }
  return next;
}

export function parseContractJson(raw) {
  const empty = createEmptyContractForm();
  if (!raw || typeof raw !== "string" || !raw.trim()) {
    return empty;
  }
  try {
    const data = JSON.parse(raw);
    if (!data || typeof data !== "object") {
      return empty;
    }
    const next = { ...empty };
    next.company_id = data.company_id != null ? String(data.company_id) : "";
    next.vessel_id = data.vessel_id != null ? String(data.vessel_id) : "";
    next.rank = data.rank || "";
    for (const { key } of CONTRACT_ALL_EDITABLE_FIELD_DEFS) {
      next[key] = data[key] == null ? "" : String(data[key]);
    }
    return next;
  } catch {
    return empty;
  }
}

export function contractFormToApiPayload(form) {
  const companyId = Number(form.company_id);
  const vesselRaw = String(form.vessel_id ?? "").trim();
  const payload = {
    company_id: companyId,
    vessel_id: vesselRaw === "" ? null : Number(vesselRaw),
    rank: String(form.rank || "").trim(),
  };
  for (const { key } of CONTRACT_ALL_EDITABLE_FIELD_DEFS) {
    const value = String(form[key] ?? "").trim();
    payload[key] = value === "" ? null : value;
  }
  return payload;
}

export function salaryMatchesContract(form, salaryJson) {
  if (!salaryJson || !form.company_id || !form.rank) {
    return false;
  }
  return (
    String(salaryJson.company_id) === String(form.company_id) &&
    String(salaryJson.rank || "").trim() === String(form.rank || "").trim()
  );
}
