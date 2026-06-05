/**
 * Ukrainian labour contract — manual fields stored in `candidates.ukr_contract_json`.
 * In Word (docxtpl) use: {{ ukr_surname }}, {{ ukr_first_name }}, …
 */
export const UKR_CONTRACT_FIELD_DEFS = [
  { key: "ukr_surname", label: "Прізвище", placeholder: "ukr_surname" },
  { key: "ukr_first_name", label: "Ім'я", placeholder: "ukr_first_name" },
  { key: "ukr_patronymic", label: "По батькові", placeholder: "ukr_patronymic" },
  { key: "ukr_full_name_ua", label: "Повне ПІБ", placeholder: "ukr_full_name_ua" },
  { key: "ukr_birth_date_ua", label: "Дата народження", placeholder: "ukr_birth_date_ua" },
  { key: "ukr_age_ua", label: "Вік", placeholder: "ukr_age_ua" },
  {
    key: "ukr_education_ua",
    label: "Освіта",
    placeholder: "ukr_education_ua",
    type: "select",
    options: [
      "Вища освіта (університет, академія, інститут, коледж)",
      "Професійно-технічна освіта (училище, технікум)",
      "Повна загальна освіта (середня загальноосвітня школа 3 ступеню / старша школа)",
    ],
  },
  {
    key: "ukr_work_in_ukraine",
    label: "Робота в Україні",
    placeholder: "ukr_work_in_ukraine",
    type: "select",
    options: ["Працював в Україні до виїзду за кордон", "Не працював в Україні до виїзду за кордон"],
  },
  { key: "ukr_residence_city_before_departure", label: "Місто проживання до виїзду за кордон", placeholder: "ukr_residence_city_before_departure" },
  { key: "ukr_residence_village_before_departure", label: "Село проживання до виїзду за кордон", placeholder: "ukr_residence_village_before_departure" },
  { key: "ukr_contract_term_duration", label: "Строк дії трудового договору", placeholder: "ukr_contract_term_duration" },
  { key: "ukr_passport_series", label: "Серія паспорта", placeholder: "ukr_passport_series" },
  { key: "ukr_passport_number_ua", label: "Номер паспорта", placeholder: "ukr_passport_number_ua" },
  { key: "ukr_passport_issued_by", label: "Ким виданий паспорт", placeholder: "ukr_passport_issued_by" },
  { key: "ukr_passport_issue_date_ua", label: "Дата видачі паспорта", placeholder: "ukr_passport_issue_date_ua" },
  { key: "ukr_contract_sign_date", label: "Дата підписання контракту", placeholder: "ukr_contract_sign_date" },
  { key: "ukr_confirmation_date", label: "Дата підтвердження", placeholder: "ukr_confirmation_date" },
  { key: "ukr_tax_id", label: "Ідентифікаційний код", placeholder: "ukr_tax_id" },
  { key: "ukr_registered_address", label: "Зареєстрований та проживає за адресою", placeholder: "ukr_registered_address" },
  { key: "ukr_vessel_name", label: "Судно", placeholder: "ukr_vessel_name" },
  { key: "ukr_contract_duration", label: "Тривалість контракту", placeholder: "ukr_contract_duration" },
  { key: "ukr_embarkation_date", label: "Дата посадки на судно", placeholder: "ukr_embarkation_date" },
  { key: "ukr_embarkation_port", label: "Порт посадки", placeholder: "ukr_embarkation_port" },
  { key: "ukr_bonus_discretion", label: "Преміальні за розсудом судновласника", placeholder: "ukr_bonus_discretion" },
  { key: "ukr_monthly_salary_total", label: "Загальна сума місячної заробітної плати", placeholder: "ukr_monthly_salary_total" },
  { key: "ukr_home_address_ua", label: "Домашня адреса", placeholder: "ukr_home_address_ua" },
  { key: "ukr_phone_ua", label: "Телефон", placeholder: "ukr_phone_ua" },
];

export function createEmptyUkrContractForm() {
  return Object.fromEntries(UKR_CONTRACT_FIELD_DEFS.map(({ key }) => [key, ""]));
}

export function parseUkrContractJson(raw) {
  const empty = createEmptyUkrContractForm();
  if (!raw || typeof raw !== "string" || !raw.trim()) {
    return empty;
  }
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) {
      return empty;
    }
    const next = { ...empty };
    for (const k of Object.keys(empty)) {
      const v = parsed[k];
      next[k] = v === null || v === undefined ? "" : String(v);
    }
    // Backward compatibility: old key stored only a year (ukr_birth_year).
    if (
      !String(next.ukr_birth_date_ua || "").trim() &&
      typeof parsed.ukr_birth_year === "string" &&
      parsed.ukr_birth_year.trim().match(/^\d{4}$/)
    ) {
      next.ukr_birth_date_ua = `01-01-${parsed.ukr_birth_year.trim()}`;
    }
    // Backward compatibility: old key stored a single combined residence string.
    if (
      !String(next.ukr_residence_city_before_departure || "").trim() &&
      !String(next.ukr_residence_village_before_departure || "").trim() &&
      typeof parsed.ukr_residence_before_departure === "string" &&
      parsed.ukr_residence_before_departure.trim()
    ) {
      next.ukr_residence_city_before_departure = parsed.ukr_residence_before_departure.trim();
    }
    return next;
  } catch {
    return empty;
  }
}
