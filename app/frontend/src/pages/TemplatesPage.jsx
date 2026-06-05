import React, { useEffect, useMemo, useState } from "react";
import CrmLayout from "../components/CrmLayout";
import {
  createTemplateFolder,
  deleteTemplateFile,
  deleteTemplateFolder,
  downloadTemplateFile,
  fetchTemplatesManager,
  renameTemplateFile,
  renameTemplateFolder,
  uploadTemplateFile,
} from "../api";

const ALLOWED_TEMPLATE_EXT = /\.(doc|docx|pdf)$/i;

function isAllowedTemplateFilename(name) {
  return ALLOWED_TEMPLATE_EXT.test(String(name || ""));
}

/** Windows/macOS/Linux junk beside real templates — ignore without red error banners. */
function isSkippableFolderNoiseFilename(name) {
  const base = String(name || "")
    .split(/[/\\]/)
    .pop();
  const lower = (base || "").toLowerCase();
  if (lower === "desktop.ini" || lower === "thumbs.db" || lower === "ehthumbs.db" || lower === ".ds_store") return true;
  if (/^~\$/.test(base || "") || /^\.~/.test(base || "")) return true;
  return false;
}

function templateFileExtDisplay(fileName) {
  const base = String(fileName || "").split(/[/\\]/).pop() || "";
  const dot = base.lastIndexOf(".");
  return dot >= 0 ? base.slice(dot + 1).toUpperCase() : "";
}

function fileTypeTagKind(ext) {
  const e = String(ext || "").toLowerCase();
  if (e === "pdf") return "pdf";
  if (e === "docx") return "docx";
  if (e === "doc") return "doc";
  return "other";
}

function IconEditFolder() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.25"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 20h9M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z" />
    </svg>
  );
}

function IconTrashFolder() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.25"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M3 6h18" />
      <path d="M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2" />
      <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6" />
      <path d="M10 11v6M14 11v6" />
    </svg>
  );
}

function IconDownloadFile() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.25"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}

export default function TemplatesPage() {
  const [folders, setFolders] = useState([]);
  const [files, setFiles] = useState([]);
  const [rootFolderId, setRootFolderId] = useState(null);
  const [selectedFolderId, setSelectedFolderId] = useState(null);
  const [treeSearch, setTreeSearch] = useState("");
  const [isDragOver, setIsDragOver] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  /** If an id is present, that folder subtree is collapsed (hidden). Default empty = all expanded. */
  const [collapsedFolderIds, setCollapsedFolderIds] = useState([]);

  const childrenMap = useMemo(() => {
    return folders.reduce((acc, folder) => {
      const key = folder.parent_id || "__none__";
      if (!acc[key]) acc[key] = [];
      acc[key].push(folder);
      return acc;
    }, {});
  }, [folders]);

  function folderChildren(parentId) {
    const raw = childrenMap[parentId] || [];
    return raw.filter((node) => (rootFolderId == null ? true : node.folder_id !== rootFolderId));
  }

  function sortFoldersByName(list) {
    return list.slice().sort((a, b) => String(a.name || "").localeCompare(String(b.name || ""), "ru"));
  }

  const treeSearchNormalized = treeSearch.trim().toLowerCase();

  const isFolderVisibleInSearch = useMemo(() => {
    if (!treeSearchNormalized) {
      return () => true;
    }
    const cache = new Map();
    function visible(folderId) {
      if (cache.has(folderId)) return cache.get(folderId);
      const folder = folders.find((item) => item.folder_id === folderId);
      const nameMatch = folder && String(folder.name || "").toLowerCase().includes(treeSearchNormalized);
      const fileMatch = files.some(
        (f) =>
          f.folder_id === folderId && String(f.file_name || "").toLowerCase().includes(treeSearchNormalized)
      );
      const kids = folderChildren(folderId);
      const childMatch = kids.some((c) => visible(c.folder_id));
      const result = Boolean(nameMatch || fileMatch || childMatch);
      cache.set(folderId, result);
      return result;
    }
    return visible;
  }, [treeSearchNormalized, folders, files, childrenMap, rootFolderId]);

  function isFolderExpanded(folderId) {
    if (folderId == null) return true;
    if (treeSearchNormalized) return true;
    return !collapsedFolderIds.includes(folderId);
  }

  function toggleFolderExpanded(folderId) {
    if (folderId == null) return;
    setCollapsedFolderIds((prev) =>
      prev.includes(folderId) ? prev.filter((id) => id !== folderId) : [...prev, folderId]
    );
  }

  const selectedFolder = folders.find((folder) => folder.folder_id === selectedFolderId);
  const selectedFiles = files.filter((file) => file.folder_id === selectedFolderId);

  const selectedFilesFiltered = useMemo(() => {
    if (!treeSearchNormalized) return selectedFiles;
    return selectedFiles.filter((f) => String(f.file_name || "").toLowerCase().includes(treeSearchNormalized));
  }, [selectedFiles, treeSearchNormalized]);

  async function loadTemplates() {
    setLoading(true);
    setError("");
    try {
      const payload = await fetchTemplatesManager();
      const nextFolders = payload.folders || [];
      const nextFiles = payload.files || [];
      const nextRootId = payload.root_folder_id;
      setFolders(nextFolders);
      setFiles(nextFiles);
      setRootFolderId(nextRootId);
      setSelectedFolderId((prev) =>
        prev && nextFolders.some((item) => item.folder_id === prev) ? prev : nextRootId
      );
    } catch (requestError) {
      setError("Не удалось загрузить templates manager");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadTemplates();
  }, []);

  async function createFolder(parentId) {
    const name = window.prompt("Folder name");
    if (!name || !name.trim()) return;
    try {
      const response = await createTemplateFolder({ name: name.trim(), parent_id: parentId });
      const created = response.folder;
      setFolders((prev) => [...prev, created]);
      setSelectedFolderId(created.folder_id);
    } catch (requestError) {
      setError("Не удалось создать папку");
    }
  }

  async function addLocalFiles(fileList) {
    if (!selectedFolderId || !fileList?.length) return;
    const filesArr = Array.from(fileList);
    const rejectedNames = filesArr
      .filter((file) => !isSkippableFolderNoiseFilename(file.name) && !isAllowedTemplateFilename(file.name))
      .map((file) => file.name);
    if (rejectedNames.length) {
      setError(`Недопустимый формат файла: ${rejectedNames.join(", ")}`);
    } else {
      setError("");
    }
    const toUpload = filesArr.filter((file) => isAllowedTemplateFilename(file.name));
    if (!toUpload.length) return;
    try {
      const uploadedItems = [];
      for (const file of toUpload) {
        const response = await uploadTemplateFile(selectedFolderId, file);
        if (response.file) uploadedItems.push(response.file);
      }
      if (uploadedItems.length > 0) {
        setFiles((prev) => [...uploadedItems, ...prev]);
      }
    } catch (requestError) {
      const detail =
        requestError?.response?.data?.detail ||
        requestError?.response?.data?.message ||
        (typeof requestError?.response?.data === "string" ? requestError.response.data : null);
      setError(detail || "Не удалось загрузить файл(ы)");
    }
  }

  async function addFolderFiles(fileList) {
    if (!selectedFolderId || !fileList?.length) return;

    const filesArr = Array.from(fileList);
    const withPaths = filesArr.map((file) => ({
      file,
      relPath: String(file.webkitRelativePath || "").replace(/\\/g, "/"),
    }));
    const rejectedNames = withPaths
      .filter(({ file }) => !isSkippableFolderNoiseFilename(file.name) && !isAllowedTemplateFilename(file.name))
      .map(({ relPath, file }) => relPath || file.name);

    if (rejectedNames.length) {
      setError(`Недопустимый формат файла: ${rejectedNames.join(", ")}`);
    } else {
      setError("");
    }

    const toUpload = withPaths.filter(({ file }) => isAllowedTemplateFilename(file.name));
    if (!toUpload.length) return;

    try {
      const knownFolders = [...folders];
      const findChildFolder = (parentId, name) =>
        knownFolders.find((item) => item.parent_id === parentId && item.name === name) || null;

      // Collect unique folder paths from selected directory, preserving top folder.
      const dirPaths = Array.from(
        new Set(
          toUpload
            .map(({ relPath }) => relPath.split("/").slice(0, -1).filter(Boolean).join("/"))
            .filter(Boolean)
        )
      ).sort((a, b) => a.split("/").length - b.split("/").length);

      const pathToFolderId = new Map();

      for (const dirPath of dirPaths) {
        const segments = dirPath.split("/").filter(Boolean);
        let parentId = selectedFolderId;
        let acc = "";
        for (const seg of segments) {
          acc = acc ? `${acc}/${seg}` : seg;
          if (pathToFolderId.has(acc)) {
            parentId = pathToFolderId.get(acc);
            continue;
          }
          const existing = findChildFolder(parentId, seg);
          if (existing) {
            pathToFolderId.set(acc, existing.folder_id);
            parentId = existing.folder_id;
            continue;
          }
          const createdResp = await createTemplateFolder({ name: seg, parent_id: parentId });
          const created = createdResp.folder;
          knownFolders.push(created);
          pathToFolderId.set(acc, created.folder_id);
          parentId = created.folder_id;
        }
      }

      for (const { file, relPath } of toUpload) {
        const dirPath = relPath.split("/").slice(0, -1).filter(Boolean).join("/");
        const targetFolderId = dirPath ? pathToFolderId.get(dirPath) || selectedFolderId : selectedFolderId;
        await uploadTemplateFile(targetFolderId, file);
      }

      await loadTemplates();
    } catch (requestError) {
      const detail =
        requestError?.response?.data?.detail ||
        requestError?.response?.data?.message ||
        (typeof requestError?.response?.data === "string" ? requestError.response.data : null);
      setError(detail || "Не удалось загрузить папку");
    }
  }

  async function onBrowseFiles(event) {
    await addLocalFiles(event.target.files);
    event.target.value = "";
  }

  async function onBrowseFolder(event) {
    await addFolderFiles(event.target.files);
    event.target.value = "";
  }

  async function onDropFiles(event) {
    event.preventDefault();
    setIsDragOver(false);
    await addLocalFiles(event.dataTransfer.files);
  }

  async function renameFolder(folderId) {
    if (folderId === rootFolderId) return;
    const folder = folders.find((item) => item.folder_id === folderId);
    if (!folder) return;
    const nextName = window.prompt("New folder name", folder.name || "");
    if (!nextName || !nextName.trim()) return;
    try {
      const response = await renameTemplateFolder(folderId, { name: nextName.trim() });
      const updated = response.folder;
      setFolders((prev) => prev.map((item) => (item.folder_id === folderId ? updated : item)));
    } catch (requestError) {
      setError("Не удалось переименовать папку");
    }
  }

  function collectDescendantIds(folderId) {
    const bucket = [folderId];
    let index = 0;
    while (index < bucket.length) {
      const current = bucket[index];
      folders.forEach((folder) => {
        if (folder.parent_id === current) bucket.push(folder.folder_id);
      });
      index += 1;
    }
    return bucket;
  }

  async function deleteFolder(folderId) {
    if (folderId === rootFolderId) return;
    const folder = folders.find((item) => item.folder_id === folderId);
    if (!folder) return;
    const confirmed = window.confirm(`Delete folder "${folder.name}" and all nested files/folders?`);
    if (!confirmed) return;
    try {
      await deleteTemplateFolder(folderId);
      const targets = new Set(collectDescendantIds(folderId));
      setFolders((prev) => prev.filter((item) => !targets.has(item.folder_id)));
      setFiles((prev) => prev.filter((item) => !targets.has(item.folder_id)));
      setSelectedFolderId((prev) => (targets.has(prev) ? rootFolderId : prev));
    } catch (requestError) {
      setError("Не удалось удалить папку");
    }
  }

  async function renameFile(fileId) {
    const file = files.find((item) => item.template_file_id === fileId);
    if (!file) return;
    const nextName = window.prompt("New file name", file.file_name);
    if (!nextName || !nextName.trim()) return;
    try {
      const response = await renameTemplateFile(fileId, { file_name: nextName.trim() });
      const updated = response.file;
      setFiles((prev) => prev.map((item) => (item.template_file_id === fileId ? updated : item)));
    } catch (requestError) {
      setError("Не удалось переименовать файл");
    }
  }

  async function deleteFile(fileId) {
    const file = files.find((item) => item.template_file_id === fileId);
    const fileName = file?.file_name || "этот файл";
    const confirmed = window.confirm(`Удалить файл "${fileName}"? Действие нельзя отменить.`);
    if (!confirmed) return;
    try {
      await deleteTemplateFile(fileId);
      setFiles((prev) => prev.filter((item) => item.template_file_id !== fileId));
    } catch (requestError) {
      setError("Не удалось удалить файл");
    }
  }

  async function downloadTemplate(file) {
    setError("");
    try {
      const { blob, fileName } = await downloadTemplateFile(file.template_file_id);
      const blobUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = fileName || file?.file_name || "template.docx";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(blobUrl);
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Не удалось скачать файл шаблона");
    }
  }

  function renderTree(parentId, level = 0) {
    const children = sortFoldersByName(folderChildren(parentId)).filter((folder) =>
      isFolderVisibleInSearch(folder.folder_id)
    );
    return children.map((folder) => {
      const subChildren = folderChildren(folder.folder_id);
      const hasSubfolders = subChildren.length > 0;
      const expanded = isFolderExpanded(folder.folder_id);
      const pad = 6 + level * 22;
      const isRootFolder = folder.folder_id === rootFolderId;
      return (
        <div key={folder.folder_id} className="templates-tree-node">
          <div
            className={`templates-tree-row-wrap${selectedFolderId === folder.folder_id ? " templates-tree-row-wrap--selected" : ""}`}
          >
            <div className="templates-tree-row-main" style={{ paddingLeft: `${pad}px` }}>
              {hasSubfolders ? (
                <button
                  type="button"
                  className="templates-tree-chevron"
                  onClick={() => toggleFolderExpanded(folder.folder_id)}
                  aria-label={expanded ? "Свернуть папку" : "Раскрыть папку"}
                >
                  <span className={`templates-chevron${expanded ? " templates-chevron--expanded" : ""}`} aria-hidden />
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
                onClick={() => setSelectedFolderId(folder.folder_id)}
              >
                {folder.name}
              </button>
            </div>
            {!isRootFolder ? (
              <div className="templates-tree-row-actions">
                <button
                  type="button"
                  className="templates-icon-btn"
                  aria-label="Переименовать папку"
                  title="Переименовать"
                  onClick={(event) => {
                    event.stopPropagation();
                    renameFolder(folder.folder_id);
                  }}
                >
                  <IconEditFolder />
                </button>
                <button
                  type="button"
                  className="templates-icon-btn templates-icon-btn--danger"
                  aria-label="Удалить папку"
                  title="Удалить"
                  onClick={(event) => {
                    event.stopPropagation();
                    deleteFolder(folder.folder_id);
                  }}
                >
                  <IconTrashFolder />
                </button>
              </div>
            ) : null}
          </div>
          {hasSubfolders && expanded ? renderTree(folder.folder_id, level + 1) : null}
        </div>
      );
    });
  }

  const rootHasSubfolders =
    rootFolderId != null ? folderChildren(rootFolderId).length > 0 : false;
  const rootExpanded = rootFolderId != null && isFolderExpanded(rootFolderId);
  const treeSearchNoResults =
    Boolean(treeSearchNormalized) && rootFolderId != null && !isFolderVisibleInSearch(rootFolderId);

  return (
    <CrmLayout title="Manager Templates" subtitle="Folder tree on the left, files of selected folder on the right.">
      <div className="card candidates-card templates-manager-card" data-testid="templates-manager">
        <div className="templates-manager-layout">
          <aside className="templates-tree templates-tree-panel">
            <div className="templates-tree-toolbar">
              <button
                type="button"
                className="secondary-btn"
                onClick={() => createFolder(rootFolderId)}
                disabled={!rootFolderId}
              >
                + Root folder
              </button>
              <button
                type="button"
                className="secondary-btn"
                onClick={() => createFolder(selectedFolderId)}
                disabled={!selectedFolderId}
              >
                + Subfolder
              </button>
              <button type="button" onClick={loadTemplates}>Refresh</button>
              <input
                type="search"
                className="templates-tree-search"
                placeholder="Поиск папок и файлов…"
                value={treeSearch}
                onChange={(event) => setTreeSearch(event.target.value)}
                aria-label="Поиск по папкам и файлам"
              />
            </div>
            <div className="templates-tree-scroll">
              <div className="templates-tree-node">
                <div
                  className={`templates-tree-row-wrap templates-tree-row-wrap--root${
                    selectedFolderId === rootFolderId ? " templates-tree-row-wrap--selected" : ""
                  }`}
                >
                  <div className="templates-tree-row-main templates-tree-row-main--root">
                    {rootFolderId != null && rootHasSubfolders ? (
                      <button
                        type="button"
                        className="templates-tree-chevron"
                        onClick={() => toggleFolderExpanded(rootFolderId)}
                        aria-label={
                          rootExpanded ? "Свернуть корневую папку" : "Раскрыть корневую папку"
                        }
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
                      onClick={() => rootFolderId != null && setSelectedFolderId(rootFolderId)}
                      disabled={rootFolderId == null}
                    >
                      Templates
                    </button>
                  </div>
                </div>
                {treeSearchNoResults ? (
                  <p className="templates-tree-empty">Ничего не найдено по запросу</p>
                ) : rootFolderId != null && rootExpanded ? (
                  renderTree(rootFolderId, 1)
                ) : null}
              </div>
            </div>
          </aside>

          <section className="templates-files templates-files-panel">
            {error ? <p className="error">{error}</p> : null}
            <div className="menu-header">
              <h2 style={{ marginBottom: 0 }}>{selectedFolder?.name || "Folder"}</h2>
              <div className="templates-header-actions">
                <span className="muted-text">
                  {treeSearchNormalized
                    ? `${selectedFilesFiltered.length} из ${selectedFiles.length} файлов`
                    : `${selectedFiles.length} file(s)`}
                </span>
                {selectedFolderId && selectedFolderId !== rootFolderId ? (
                  <>
                    <button type="button" className="secondary-btn tiny-btn" onClick={() => renameFolder(selectedFolderId)}>
                      Rename folder
                    </button>
                    <button type="button" className="danger-btn tiny-btn" onClick={() => deleteFolder(selectedFolderId)}>
                      Delete folder
                    </button>
                  </>
                ) : null}
              </div>
            </div>

            <div
              className={`templates-dropzone${isDragOver ? " drag-over" : ""}`}
              onDragOver={(event) => {
                event.preventDefault();
                setIsDragOver(true);
              }}
              onDragLeave={() => setIsDragOver(false)}
              onDrop={onDropFiles}
            >
              <p>Перетащите файлы сюда (Drag & Drop) или загрузите через Browse. Разрешены только DOC, DOCX, PDF.</p>
              <label className="secondary-btn templates-browse-btn">
                Browse
                <input
                  type="file"
                  multiple
                  accept=".doc,.docx,.pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/pdf"
                  className="hidden-file-input"
                  onChange={onBrowseFiles}
                  disabled={!selectedFolderId}
                />
              </label>
              <label className="secondary-btn templates-browse-btn" style={{ marginLeft: 8 }}>
                Browse Folder
                <input
                  type="file"
                  multiple
                  webkitdirectory=""
                  directory=""
                  className="hidden-file-input"
                  onChange={onBrowseFolder}
                  disabled={!selectedFolderId}
                />
              </label>
            </div>
            {loading ? (
              <p>Загрузка...</p>
            ) : selectedFiles.length === 0 ? (
              <p className="empty-row">В этой папке пока нет файлов</p>
            ) : selectedFilesFiltered.length === 0 ? (
              <p className="empty-row">Файлы не найдены по запросу в этой папке</p>
            ) : (
              <table className="candidate-table templates-files-table">
                <thead>
                  <tr>
                    <th>File name</th>
                    <th>Type</th>
                    <th>Updated</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedFilesFiltered.map((file) => {
                    const ext = templateFileExtDisplay(file.file_name);
                    const kind = fileTypeTagKind(ext);
                    return (
                      <tr key={file.template_file_id}>
                        <td className="templates-file-name-cell">
                          <span className="templates-file-icon" aria-hidden>
                            📄
                          </span>
                          {file.file_name}
                        </td>
                        <td>
                          {ext ? (
                            <span className={`file-type-tag file-type-tag--${kind}`}>{ext}</span>
                          ) : (
                            <span className="muted-text">—</span>
                          )}
                        </td>
                        <td>{file.updated_at ? String(file.updated_at).slice(0, 10) : "-"}</td>
                        <td className="actions-row templates-file-actions">
                          <div className="templates-file-actions-inner">
                            <button
                              type="button"
                              className="templates-icon-btn"
                              aria-label="Переименовать файл"
                              title="Переименовать"
                              onClick={() => renameFile(file.template_file_id)}
                            >
                              <IconEditFolder />
                            </button>
                            <button
                              type="button"
                              className="templates-icon-btn"
                              aria-label="Скачать файл"
                              title="Скачать"
                              onClick={() => downloadTemplate(file)}
                            >
                              <IconDownloadFile />
                            </button>
                            <button
                              type="button"
                              className="templates-icon-btn templates-icon-btn--danger"
                              aria-label="Удалить файл"
                              title="Удалить"
                              onClick={() => deleteFile(file.template_file_id)}
                            >
                              <IconTrashFolder />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </section>
        </div>
      </div>
    </CrmLayout>
  );
}
