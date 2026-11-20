import React, { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { loadPublicDocumentUpload, sendPublicDocumentUpload } from "../publicDocumentUploadApi.js";
import "./DocumentUploadPage.css";

const IMAGE_ACCEPT = ".jpg,.jpeg,.png,image/jpeg,image/png";
const FILE_ACCEPT = ".pdf,application/pdf," + IMAGE_ACCEPT;
const KIND_LABELS = {
  document: "Личные документы",
  diploma: "Дипломы",
  certificate: "Сертификаты",
  medical: "Медицинские документы",
  visa: "Визы",
  flag_document: "Флаговые документы",
};
const ERROR_TEXT = {
  upload_link_unavailable: "Ссылка больше не действует. Попросите менеджера прислать новую.",
  empty_file: "Один из файлов пуст. Выберите другую копию.",
  unsupported_file: "Можно приложить файлы PDF, JPG и PNG.",
  invalid_scan: "Один из файлов не читается. Замените его и попробуйте снова.",
  draft_storage_limit: "Сейчас загрузка недоступна. Попробуйте позже.",
  batch_busy: "Система обрабатывает другую загрузку. Попробуйте через минуту.",
  invalid_manifest: "Проверьте типы документов и добавленные страницы.",
  type_required: "Выберите тип для каждого документа с фотографиями.",
  submission_limit: "По этой ссылке уже отправлено несколько наборов. Свяжитесь с менеджером.",
};

function megabytes(bytes) {
  return new Intl.NumberFormat("ru", { maximumFractionDigits: 1 }).format(bytes / (1024 * 1024)) + " МБ";
}

function errorText(code, limits) {
  if (code === "batch_file_limit") return `Можно приложить до ${limits.max_files} файлов и фотографий за одну отправку.`;
  if (code === "file_size_limit") return `Размер одного файла не должен превышать ${megabytes(limits.max_file_bytes)}.`;
  if (code === "batch_size_limit") return `Общий размер файлов не должен превышать ${megabytes(limits.max_batch_bytes)}.`;
  return ERROR_TEXT[code] || "Не удалось отправить документы. Проверьте подключение и повторите отправку.";
}

function checkFileLimits(chosen, current, limits) {
  if (chosen.some(file => !file.size)) return "empty_file";
  if (chosen.some(file => file.size > limits.max_file_bytes)) return "file_size_limit";
  if (current.length + chosen.length > limits.max_files) return "batch_file_limit";
  const totalSize = chosen.reduce((bytes, file) => bytes + file.size,
    current.reduce((bytes, item) => bytes + item.file.size, 0));
  return totalSize > limits.max_batch_bytes ? "batch_size_limit" : "";
}

function requestId() {
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("");
}

function plural(value, forms) {
  const lastTwo = value % 100;
  const last = value % 10;
  const index = lastTwo >= 11 && lastTwo <= 14 ? 2 : last === 1 ? 0 : last >= 2 && last <= 4 ? 1 : 2;
  return value + " " + forms[index];
}

const fileCount = value => plural(value, ["файл", "файла", "файлов"]);
const pageCount = value => plural(value, ["страница", "страницы", "страниц"]);

function TypeSelect({ catalog, value, onChange }) {
  const groups = new Map();
  for (const item of catalog) {
    if (!groups.has(item.kind)) groups.set(item.kind, []);
    groups.get(item.kind).push(item);
  }
  return (
    <label className="upload-type-label">
      Тип документа
      <select value={value} onChange={event => onChange(event.target.value)}>
        <option value="">Выберите из списка</option>
        {[...groups].map(([kind, group]) => (
          <optgroup key={kind} label={KIND_LABELS[kind] || "Другие документы"}>
            {group.map(item => <option key={item.key} value={item.key}>{item.label}</option>)}
          </optgroup>
        ))}
      </select>
    </label>
  );
}

function PhotoPreview({ file, number }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    const current = URL.createObjectURL(file);
    setUrl(current);
    return () => URL.revokeObjectURL(current);
  }, [file]);
  return url ? <img src={url} alt={`Снимок страницы ${number}`} /> : null;
}

function DocumentEditor({ catalog, group, onType, onPhotos, onMove, onRemovePage, onDone }) {
  const gallery = useRef(null);
  const camera = useRef(null);
  const nextPage = group.pages.length + 1;

  function read(event) {
    const chosen = Array.from(event.target.files);
    event.target.value = "";
    if (chosen.length) onPhotos(chosen);
  }

  return (
    <div className="upload-document-editor">
      <TypeSelect catalog={catalog} value={group.typeKey} onChange={onType} />
      <p className="upload-note">Добавляйте страницы в том порядке, в котором они идут в документе.</p>
      <div className="upload-actions">
        <input ref={camera} hidden type="file" capture="environment" accept={IMAGE_ACCEPT} onChange={read} />
        <input ref={gallery} hidden type="file" multiple accept={IMAGE_ACCEPT} onChange={read} />
        <button type="button" disabled={!group.typeKey} onClick={() => camera.current.click()}>
          {group.pages.length ? "Снять следующую страницу" : "Открыть камеру"}
        </button>
        <button type="button" className="secondary-btn" disabled={!group.typeKey} onClick={() => gallery.current.click()}>Добавить фото</button>
      </div>
      {group.typeKey && <p className="upload-next-page" role="status">{`Следующая страница — ${nextPage}`}</p>}
      {group.pages.length > 0 && (
        <ol className="upload-pages">
          {group.pages.map(({ file, id }, index) => (
            <li key={id} className="upload-page">
              <div className="upload-thumbnail"><PhotoPreview file={file} number={index + 1} /></div>
              <div className="upload-page-info">
                <strong>{`Страница ${index + 1}`}</strong>
                <span title={file.name}>{file.name}</span>
              </div>
              <div className="upload-page-actions">
                <button className="secondary-btn" type="button" aria-label={`Переместить страницу ${index + 1} раньше`}
                  disabled={index === 0} onClick={() => onMove(index, -1)}>↑</button>
                <button className="secondary-btn" type="button" aria-label={`Переместить страницу ${index + 1} позже`}
                  disabled={index === group.pages.length - 1} onClick={() => onMove(index, 1)}>↓</button>
                <button className="secondary-btn" type="button" aria-label={`Удалить страницу ${index + 1}`}
                  onClick={() => onRemovePage(index)}>Удалить</button>
              </div>
            </li>
          ))}
        </ol>
      )}
      <button type="button" className="secondary-btn" disabled={!group.typeKey || !group.pages.length} onClick={onDone}>Готово</button>
    </div>
  );
}

function UploadForm({ token, config }) {
  const { catalog, limits } = config;
  const [files, setFiles] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [editor, setEditor] = useState(null);
  const [stage, setStage] = useState("edit");
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(null);
  const nextId = useRef(1);
  const idempotency = useRef(null);
  const submission = useRef(null);
  const filePicker = useRef(null);
  const folderPicker = useRef(null);
  const title = useRef(null);

  useEffect(() => () => submission.current?.abort(), []);
  useEffect(() => {
    if (stage !== "edit") title.current?.focus();
  }, [stage]);

  const photoItems = documents.flatMap(group => group.pages);
  const allFiles = [...files, ...photoItems];
  const typeNames = new Map(catalog.map(item => [item.key, item.label]));

  function changed(note = "") {
    idempotency.current = null;
    setMessage(note);
  }

  function addFiles(chosen, groupId = null) {
    if (!chosen.length) return;
    const matches = groupId === null ? /\.(pdf|jpe?g|png)$/i : /\.(jpe?g|png)$/i;
    const supported = chosen.filter(file => matches.test(file.name));
    if (!supported.length) {
      setMessage(groupId === null ? ERROR_TEXT.unsupported_file : "Для страниц документа выберите фотографии JPG или PNG.");
      return;
    }
    const group = documents.find(item => item.id === groupId);
    if (groupId !== null && !group) return;
    const failure = checkFileLimits(supported, allFiles, limits);
    if (failure) {
      setMessage(errorText(failure, limits));
      return;
    }
    if (group && group.pages.length + supported.length > limits.max_pages) {
      setMessage(`В один документ можно добавить до ${limits.max_pages} страниц.`);
      return;
    }
    const added = supported.map(file => ({ file, id: nextId.current++ }));
    if (group) updateDocument(groupId, { pages: [...group.pages, ...added] });
    else setFiles(previous => [...previous, ...added]);
    const skipped = chosen.length - supported.length;
    changed(skipped ? `Пропущено ${fileCount(skipped)}. Поддерживаются форматы ${group ? "JPG и PNG" : "PDF, JPG и PNG"}.` : "");
  }

  function pickFiles(event) {
    const chosen = Array.from(event.target.files);
    event.target.value = "";
    addFiles(chosen);
  }

  function updateDocument(id, changes) {
    setDocuments(previous => previous.map(group => group.id === id ? { ...group, ...changes } : group));
  }

  function addDocument() {
    const id = nextId.current++;
    setDocuments(previous => [...previous, { id, typeKey: "", pages: [] }]);
    setEditor(id);
    changed();
  }

  function review(event) {
    event.preventDefault();
    const incomplete = documents.find(group => !group.typeKey || !group.pages.length);
    if (incomplete) {
      setEditor(incomplete.id);
      setMessage("Выберите тип и добавьте хотя бы одну страницу или удалите пустой документ.");
    } else if (allFiles.length) {
      setMessage("");
      setStage("review");
    }
  }

  async function send(event) {
    event.preventDefault();
    if (submission.current) return;
    const controller = new AbortController();
    submission.current = controller;
    setSending(true);
    setMessage("");
    try {
      idempotency.current ??= requestId();
      const result = await sendPublicDocumentUpload(token, idempotency.current, files, documents, controller.signal);
      if (!controller.signal.aborted) {
        setSent(result);
        setFiles([]);
        setDocuments([]);
        setStage("sent");
      }
    } catch (error) {
      if (!controller.signal.aborted) setMessage(errorText(error.message, limits));
    } finally {
      submission.current = null;
      if (!controller.signal.aborted) setSending(false);
    }
  }

  if (stage === "sent") return (
    <section className="upload-panel upload-result">
      <span className="upload-success-icon" aria-hidden="true">✓</span>
      <h1 ref={title} tabIndex={-1}>Документы отправлены</h1>
      <p>Менеджер получил уведомление и проверит документы.</p>
      {Number.isInteger(sent?.file_count) && <p className="upload-note">Отправлено {fileCount(sent.file_count)}.</p>}
      <button type="button" className="secondary-btn" onClick={() => {
        setSent(null);
        setEditor(null);
        setStage("edit");
        changed();
      }}>Отправить ещё документы</button>
    </section>
  );

  if (stage === "review") return (
    <form className="upload-panel upload-form" onSubmit={send} aria-busy={sending}>
      <div>
        <h1 ref={title} tabIndex={-1}>Проверьте документы</h1>
        <p>Менеджер получит перечисленные ниже файлы.</p>
      </div>
      <ul className="upload-list">
        {files.map(({ file, id }) => <li key={id}><strong>{file.name}</strong><span>{megabytes(file.size)}</span></li>)}
        {documents.map(group => (
          <li key={group.id}><strong>{typeNames.get(group.typeKey)}.pdf</strong><span>{pageCount(group.pages.length)}</span></li>
        ))}
      </ul>
      {message && <p role="alert" className="upload-message">{message}</p>}
      <div className="upload-actions">
        <button type="submit" disabled={sending}>{sending ? "Отправляем документы…" : "Отправить документы"}</button>
        <button type="button" className="secondary-btn" disabled={sending} onClick={() => {
          setMessage("");
          setStage("edit");
        }}>Изменить</button>
      </div>
    </form>
  );

  return (
    <form className="upload-panel upload-form" onSubmit={review}>
      <div>
        <h1>Загрузите документы</h1>
        <p>Прикрепите файлы с телефона или компьютера либо снимите страницы камерой.</p>
      </div>
      <section className="upload-section">
        <h2>Файлы и папки</h2>
        <p className="upload-note">Выберите папку целиком или отдельные файлы PDF, JPG и PNG.</p>
        <div className="upload-actions">
          <input type="file" ref={folderPicker} hidden multiple webkitdirectory="" onChange={pickFiles} />
          <input type="file" ref={filePicker} hidden multiple accept={FILE_ACCEPT} onChange={pickFiles} />
          <button type="button" className="secondary-btn" onClick={() => folderPicker.current.click()}>Загрузить папку</button>
          <button type="button" className="secondary-btn" onClick={() => filePicker.current.click()}>Прикрепить файлы</button>
        </div>
        {files.length > 0 && <ul className="upload-list">
          {files.map(({ file, id }) => (
            <li key={id}>
              <strong>{file.name}</strong>
              <button type="button" className="secondary-btn" aria-label={`Удалить файл ${file.name}`} onClick={() => {
                setFiles(previous => previous.filter(item => item.id !== id));
                changed();
              }}>Удалить</button>
            </li>
          ))}
        </ul>}
      </section>
      <section className="upload-section">
        <h2>Фотографии страниц</h2>
        <p className="upload-note">Выберите тип документа. Его страницы соберутся в один PDF в указанном порядке.</p>
        {documents.map(group => (
          <article className="upload-document" key={group.id}>
            <div className="upload-document-heading">
              <div><strong>{typeNames.get(group.typeKey) || "Новый документ"}</strong><span>{pageCount(group.pages.length)}</span></div>
              <div className="upload-actions">
                {editor !== group.id && <button type="button" className="secondary-btn" onClick={() => setEditor(group.id)}>Изменить</button>}
                <button type="button" className="secondary-btn" aria-label={`Удалить документ ${typeNames.get(group.typeKey) || "без типа"}`} onClick={() => {
                  setDocuments(previous => previous.filter(item => item.id !== group.id));
                  if (editor === group.id) setEditor(null);
                  changed();
                }}>Удалить</button>
              </div>
            </div>
            {editor === group.id && <DocumentEditor catalog={catalog} group={group}
              onType={typeKey => { updateDocument(group.id, { typeKey }); changed(); }}
              onPhotos={chosen => addFiles(chosen, group.id)}
              onMove={(from, delta) => {
                const pages = [...group.pages];
                const to = from + delta;
                [pages[from], pages[to]] = [pages[to], pages[from]];
                updateDocument(group.id, { pages });
                changed();
              }}
              onRemovePage={index => { updateDocument(group.id, { pages: group.pages.filter((_, at) => at !== index) }); changed(); }}
              onDone={() => setEditor(null)} />}
          </article>
        ))}
        <button type="button" className="secondary-btn" onClick={addDocument}>Добавить документ с фото</button>
      </section>
      {message && <p role="alert" className="upload-message">{message}</p>}
      <div className="upload-submit">
        <span className="upload-note" aria-live="polite">{allFiles.length ? `Добавлено ${fileCount(allFiles.length)} с учётом страниц` : "Добавьте хотя бы один файл или фотографию"}</span>
        <button type="submit" disabled={!allFiles.length}>Проверить перед отправкой</button>
      </div>
    </form>
  );
}

function UploadPage({ token }) {
  const [config, setConfig] = useState(null);
  const [loadingError, setLoadingError] = useState(token ? "" : "upload_link_unavailable");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    loadPublicDocumentUpload(token, controller.signal).then(data => {
      if (!controller.signal.aborted) setConfig(data);
    }).catch(error => {
      if (!controller.signal.aborted) setLoadingError(error.message);
    });
    return () => controller.abort();
  }, [token, attempt]);

  return (
    <main className="public-upload" lang="ru">
      <div className="upload-shell">
        <header className="upload-brand"><strong>CrewDeck CRM</strong></header>
        {config ? <UploadForm token={token} config={config} /> : (
          <section className="upload-panel upload-result">
            <h1>Загрузка документов</h1>
            {loadingError ? (
              <>
                <p role="alert">{ERROR_TEXT[loadingError] || "Не удалось открыть страницу. Проверьте подключение."}</p>
                {loadingError !== "upload_link_unavailable" && <button type="button" className="secondary-btn" onClick={() => {
                  setLoadingError("");
                  setAttempt(previous => previous + 1);
                }}>Попробовать снова</button>}
              </>
            ) : <p role="status">Открываем страницу…</p>}
          </section>
        )}
      </div>
    </main>
  );
}

export default function DocumentUploadPage() {
  const token = useLocation().hash.slice(1);
  return <UploadPage key={token} token={token} />;
}
