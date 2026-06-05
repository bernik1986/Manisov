import React from "react";
import { useState } from "react";
import { createCandidateFromText, previewTextImport, uploadCandidateFile } from "../api";
import FileDropzone from "./FileDropzone";

const allowedExtensions = [".doc", ".docx", ".xls", ".xlsx", ".pdf"];

const MANUAL_JSON_PROMPT = `Ты — ассистент, который должен преобразовать входные данные анкеты моряка в строго валидный JSON для CRM.

ВАЖНО (формат ответа)
- Верни ТОЛЬКО JSON, без пояснений, без Markdown, без тройных кавычек.
- Все даты приводи к формату YYYY-MM-DD.
- Если значение неизвестно — ставь null (не пустую строку).
- Числа (рост/вес/годы) — числа, без “cm/kg/years”.
- Поля в JSON должны быть только из схемы ниже. Никаких дополнительных ключей.

СХЕМА JSON (обязательная структура)
{
  "personal_data": {
    "surname": null,
    "first_name": null,
    "middle_name": null,
    "full_name": null,
    "latin_full_name": null,
    "native_full_name": null,
    "date_of_birth": null,
    "place_of_birth": null,
    "country_of_birth": null,
    "nationality": null,
    "citizenship": null,
    "gender": null,
    "marital_status": null,
    "father_name": null,
    "mother_name": null,
    "primary_phone": null,
    "secondary_phone": null,
    "mobile_phone": null,
    "telephone_no": null,
    "email": null,
    "secondary_email": null,
    "permanent_address": null,
    "home_address": null,
    "current_address": null,
    "city": null,
    "region": null,
    "postal_code": null,
    "country": null,
    "spouse_name": null,
    "number_of_children": null,
    "children_under_18_count": null,
    "beneficiary_full_name": null,
    "beneficiary_relationship": null,
    "beneficiary_address": null,
    "beneficiary_phone": null,
    "next_of_kin_full_name": null,
    "next_of_kin_relationship": null,
    "next_of_kin_address": null,
    "next_of_kin_phone": null,
    "highest_educational_attainment": null,
    "school_name": null,
    "graduation_year": null,
    "english_level": null,
    "english_certificate": null,
    "other_languages": null,
    "height_cm": null,
    "weight_kg": null,
    "distinctive_marks": null,
    "current_rank": null,
    "certificate_of_competency_rank": null,
    "certificate_of_competency_number": null,
    "passport_number": null,
    "passport_issue_date": null,
    "passport_expiry_date": null,
    "passport_place_of_issue": null,
    "seaman_book_number": null,
    "usa_visa_number": null,
    "usa_visa_issue_date": null,
    "usa_visa_expiry_date": null,
    "usa_visa_place_of_issue": null,
    "visa_status_note": null,
    "yellow_fever_issue_date": null,
    "yellow_fever_expiry_date": null,
    "yellow_fever_unlimited": null
  },
  "applications": [
    {
      "position_applied_for": null,
      "rank_applied_for": null,
      "proposed_vessel": null,
      "date_applied": null,
      "date_available": null
    }
  ],
  "documents": [
    {
      "document_type": null,
      "document_number": null,
      "issuing_authority": null,
      "place_of_issue": null,
      "date_of_issue": null,
      "date_of_expiry": null,
      "remarks": null
    }
  ],
  "certificates": [
    {
      "certificate_type": null,
      "certificate_number": null,
      "issuing_authority": null,
      "date_issued": null,
      "expiry_date": null,
      "remarks": null
    }
  ],
  "sea_service": [
    {
      "vessel_name": null,
      "vessel_type": null,
      "dwt": null,
      "grt": null,
      "main_engine": null,
      "rank_on_vessel": null,
      "sign_on_date": null,
      "sign_off_date": null,
      "employer": null,
      "remarks": null
    }
  ],
  "flag_documents": [
    {
      "flag_country": null,
      "flag_document_type": null,
      "rank": null,
      "doc_number": null,
      "date_of_issuance": null,
      "date_of_expiry": null,
      "remarks": null
    }
  ],
  "family_contacts": [
    {
      "full_name": null,
      "relationship_to_candidate": null,
      "phone": null,
      "email": null,
      "address": null
    }
  ]
}

ПРАВИЛА МАППИНГА
- В documents[] клади: паспорт, seaman book, visas, licences и т.п.
- В certificates[] клади: STCW/курсы/сертификаты.
- В sea_service[] — каждую строку контракта отдельным объектом.
- Если есть несколько телефонов или email — заполни primary_phone, secondary_phone, email, secondary_email.
- graduation_year — год (например 2022), даже если во входе дата.
- Если во входе “Validity for life …” → yellow_fever_unlimited = true.

ВХОДНЫЕ ДАННЫЕ (заменяй этот блок)
<PASTE_HERE_THE_TEXT_FROM_THE_FORM_OR_OCR>`;

export default function UploadForm({ onUploaded }) {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [warning, setWarning] = useState("");
  const [manualText, setManualText] = useState("");
  const [manualPreview, setManualPreview] = useState(null);
  const [manualBusy, setManualBusy] = useState(false);
  const [promptCopied, setPromptCopied] = useState(false);

  async function onSubmit(event) {
    event.preventDefault();
    setError("");
    setSuccess("");
    setWarning("");

    if (!file) {
      setError("Выберите файл для загрузки");
      return;
    }

    const fileName = file.name.toLowerCase();
    const isSupported = allowedExtensions.some((ext) => fileName.endsWith(ext));
    if (!isSupported) {
      setError("Разрешены только DOC, DOCX, XLS, XLSX и PDF");
      return;
    }

    setLoading(true);
    try {
      const response = await uploadCandidateFile(file);
      if (response?.duplicate && response?.requires_confirmation) {
        const shouldUpdate = window.confirm(
          response.message || "Такой кандидат уже существует. Хотите обновить его данные при помощи этой анкеты?"
        );
        if (!shouldUpdate) {
          setWarning("Обновление существующего кандидата отменено.");
          return;
        }
        const mergedResponse = await uploadCandidateFile(file, { confirmDuplicateUpdate: true });
        const mergedMessage =
          mergedResponse?.message || `Кандидат (ID: ${mergedResponse?.candidate_id ?? response?.candidate_id}) обновлён.`;
        setWarning(mergedMessage);
        window.alert(mergedMessage);
        setFile(null);
        onUploaded?.(mergedResponse);
        return;
      }

      if (response?.duplicate) {
        const duplicateMessage = response.message || `Такой кандидат уже есть (ID: ${response.candidate_id})`;
        setWarning(duplicateMessage);
        window.alert(duplicateMessage);
      } else {
        setSuccess("Файл успешно загружен");
      }
      setFile(null);
      onUploaded?.(response);
    } catch (requestError) {
      const backendMessage = requestError?.response?.data?.detail;
      const isTimeout = requestError?.code === "ECONNABORTED";
      if (backendMessage) {
        setError(`Ошибка загрузки файла: ${backendMessage}`);
      } else if (isTimeout) {
        setError("Превышено время ожидания загрузки. Попробуйте файл меньшего размера.");
      } else {
        setError("Ошибка загрузки файла. Проверьте подключение к серверу.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="upload-form" data-testid="form-application-upload">
      <form onSubmit={onSubmit}>
        <label htmlFor="candidate-upload">Загрузка анкеты кандидата (DOCX, XLSX, PDF)</label>
        <FileDropzone
          inputId="candidate-upload"
          accept=".doc,.docx,.xls,.xlsx,.pdf"
          label={file ? `Выбрано: ${file.name}` : "Перетащите файл сюда или выберите"}
          disabled={loading}
          testId="dropzone-candidate-upload"
          onFile={async (nextFile) => {
            setFile(nextFile || null);
            setError("");
            setSuccess("");
            setWarning("");
          }}
        />
        <button type="submit" disabled={loading}>
          {loading ? "Отправка..." : "Загрузить"}
        </button>
      </form>

      <div style={{ marginTop: 16 }}>
        <label htmlFor="manual-import">Импорт из текста (вариант B)</label>
        <textarea
          id="manual-import"
          rows={10}
          value={manualText}
          onChange={(e) => {
            setManualText(e.target.value);
            setManualPreview(null);
          }}
          placeholder="Вставьте текст с плейсхолдерами ({{ surname }}: ...) и блоками documents/certificates/sea_service"
          style={{ width: "100%", resize: "vertical" }}
        />
        <details className="prompt-box">
          <summary>Промт для ИИ (JSON)</summary>
          <div className="prompt-box-body">
            <div className="prompt-actions">
              <button
                type="button"
                onClick={async () => {
                  setPromptCopied(false);
                  try {
                    await navigator.clipboard.writeText(MANUAL_JSON_PROMPT);
                    setPromptCopied(true);
                  } catch {
                    try {
                      const textarea = document.createElement("textarea");
                      textarea.value = MANUAL_JSON_PROMPT;
                      textarea.setAttribute("readonly", "true");
                      textarea.style.position = "absolute";
                      textarea.style.left = "-9999px";
                      document.body.appendChild(textarea);
                      textarea.select();
                      document.execCommand("copy");
                      document.body.removeChild(textarea);
                      setPromptCopied(true);
                    } catch {
                      setError("Не удалось скопировать промт. Скопируйте вручную из блока ниже.");
                    }
                  }
                }}
              >
                Копировать промт
              </button>
              {promptCopied ? <span className="success">Скопировано</span> : null}
            </div>
            <pre>{MANUAL_JSON_PROMPT}</pre>
          </div>
        </details>
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button
            type="button"
            disabled={manualBusy || !manualText.trim()}
            onClick={async () => {
              setError("");
              setSuccess("");
              setWarning("");
              setManualBusy(true);
              try {
                const resp = await previewTextImport(manualText);
                setManualPreview(resp?.parsed || null);
                setSuccess("Текст распознан. Проверьте предпросмотр ниже.");
              } catch (e) {
                const backendMessage = e?.response?.data?.detail;
                setError(backendMessage ? `Ошибка распознавания: ${backendMessage}` : "Ошибка распознавания текста");
              } finally {
                setManualBusy(false);
              }
            }}
          >
            {manualBusy ? "Распознаю..." : "Распознать"}
          </button>
          <button
            type="button"
            disabled={manualBusy || !manualText.trim()}
            onClick={async () => {
              setError("");
              setSuccess("");
              setWarning("");
              setManualBusy(true);
              try {
                const resp = await createCandidateFromText(manualText);
                const id = resp?.candidate_id;
                setManualPreview(resp?.parsed || null);
                const msg = id ? `Карточка создана (ID: ${id})` : "Карточка создана";
                setSuccess(msg);
                window.alert(msg);
                onUploaded?.(resp);
              } catch (e) {
                const backendMessage = e?.response?.data?.detail;
                setError(backendMessage ? `Ошибка создания: ${backendMessage}` : "Ошибка создания карточки из текста");
              } finally {
                setManualBusy(false);
              }
            }}
          >
            Создать карточку
          </button>
        </div>
        {manualPreview ? (
          <pre style={{ marginTop: 8, maxHeight: 260, overflow: "auto", background: "#111827", color: "#e5e7eb", padding: 12 }}>
            {JSON.stringify(manualPreview, null, 2)}
          </pre>
        ) : null}
      </div>

      {success ? <p className="success">{success}</p> : null}
      {warning ? <p className="warning">{warning}</p> : null}
      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}
