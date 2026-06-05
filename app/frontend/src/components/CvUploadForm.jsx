import React, { useState } from "react";
import { uploadCvFile } from "../api";

export default function CvUploadForm({ onUploaded }) {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function onSubmit(event) {
    event.preventDefault();
    setError("");
    setSuccess("");

    if (!file) {
      setError("Выберите PDF файл резюме");
      return;
    }
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Разрешен только PDF формат");
      return;
    }

    setLoading(true);
    try {
      const response = await uploadCvFile(file);
      setSuccess(`CV загружен, кандидат #${response.candidate_id}, cv_imported=true`);
      setFile(null);
      onUploaded?.(response);
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Ошибка загрузки CV");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="upload-form" data-testid="form-cv-upload" onSubmit={onSubmit}>
      <label htmlFor="cv-upload">Загрузка CV резюме (PDF, pyresparser)</label>
      <input
        id="cv-upload"
        type="file"
        accept=".pdf,application/pdf"
        onChange={(event) => {
          const selectedFile = event.target.files?.[0] || null;
          setFile(selectedFile);
          setError("");
          setSuccess("");
        }}
      />
      <button type="submit" disabled={loading}>
        {loading ? "Обработка CV..." : "Загрузить CV"}
      </button>
      {success ? <p className="success">{success}</p> : null}
      {error ? <p className="error">{error}</p> : null}
    </form>
  );
}
