/** Saved salary calculation JSON on candidate (salary_calculation_json). */

export function createEmptySalaryCalculatorForm() {
  return {
    company_id: "",
    rank: "",
    total_wage: "",
    period_of_employment: "",
    basic_monthly_wage: "",
    monthly_overtime: "",
    overtime_rate: "",
    sepf: "",
    imtf: "",
    leave: "",
    leave_sub: "",
    various_extra_overtime: "",
    fixed_components_total: "",
    owners_bonus: "",
  };
}

export function parseSalaryCalculationJson(raw) {
  const empty = createEmptySalaryCalculatorForm();
  if (!raw || typeof raw !== "string" || !raw.trim()) {
    return empty;
  }
  try {
    const data = JSON.parse(raw);
    if (!data || typeof data !== "object") {
      return empty;
    }
    return {
      company_id: data.company_id != null ? String(data.company_id) : "",
      rank: data.rank || "",
      total_wage: data.total_wage != null ? String(data.total_wage) : "",
      period_of_employment: data.period_of_employment || "",
      basic_monthly_wage: fmtComponent(data.basic_monthly_wage),
      monthly_overtime: fmtComponent(data.monthly_overtime),
      overtime_rate: fmtComponent(data.overtime_rate),
      sepf: fmtComponent(data.sepf),
      imtf: fmtComponent(data.imtf),
      leave: fmtComponent(data.leave),
      leave_sub: fmtComponent(data.leave_sub),
      various_extra_overtime: fmtComponent(data.various_extra_overtime),
      fixed_components_total: fmtComponent(data.fixed_components_total),
      owners_bonus: fmtComponent(data.owners_bonus),
    };
  } catch {
    return empty;
  }
}

function fmtComponent(value) {
  if (value == null || value === "") {
    return "";
  }
  const num = Number(value);
  if (Number.isNaN(num)) {
    return String(value);
  }
  return String(num);
}

export const SALARY_COMPONENT_LABELS = [
  ["basic_monthly_wage", "Basic Monthly Wage"],
  ["monthly_overtime", "Monthly Overtime"],
  ["overtime_rate", "Overtime Rate"],
  ["sepf", "SEPF"],
  ["imtf", "IMTF"],
  ["leave", "Leave"],
  ["leave_sub", "Leave Sub"],
  ["various_extra_overtime", "Various / Extra Overtime"],
];
