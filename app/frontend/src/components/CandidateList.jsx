import React from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { fetchCandidatesPaged } from "../api";

const PAGE_SIZE = 20;
const Q_DEBOUNCE_MS = 400;

import { CANONICAL_POSITION_OPTIONS as POSITION_OPTIONS } from "../canonicalPositions";
import { FLEET_OPTIONS } from "../fleetOptions";

function useDebouncedValue(value, delay) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

/** @returns {(number | "ellipsis")[]} */
function getVisiblePageNumbers(current, totalPages) {
  if (totalPages < 1) {
    return [];
  }
  if (totalPages <= 9) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }
  const show = new Set([1, totalPages, current, current - 1, current + 1]);
  for (const n of [...show]) {
    if (n < 1 || n > totalPages) {
      show.delete(n);
    }
  }
  const sorted = [...show].sort((a, b) => a - b);
  const out = [];
  for (let i = 0; i < sorted.length; i += 1) {
    if (i > 0 && sorted[i] - sorted[i - 1] > 1) {
      out.push("ellipsis");
    }
    out.push(sorted[i]);
  }
  return out;
}

function parsePage(raw) {
  const n = parseInt(String(raw || "1"), 10);
  if (!Number.isFinite(n) || n < 1) {
    return 1;
  }
  return n;
}

function formatCandidatesLoadError(err) {
  const code = err?.code;
  const msg = String(err?.message || "");
  if (code === "ERR_NETWORK" || /network error/i.test(msg)) {
    return "Сервер API недоступен. Запустите бэкенд: uvicorn app.main:app --host 127.0.0.1 --port 8000 (по умолчанию фронт обращается к тому же хосту и порту 8000).";
  }
  const status = err?.response?.status;
  const detail = err?.response?.data?.detail;
  if (status === 404) {
    return "Запрос /candidates/paged не найден. Перезапустите бэкенд с актуальным кодом.";
  }
  if (typeof detail === "string" && detail.trim()) {
    return `Не удалось загрузить список: ${detail}`;
  }
  if (status) {
    return `Не удалось загрузить список (ошибка ${status}).`;
  }
  return "Не удалось загрузить список кандидатов.";
}

export default function CandidateList({ refreshKey = 0 }) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const urlQ = searchParams.get("q") || "";
  const urlPosition = searchParams.get("position") || "";
  const urlFleet = searchParams.get("fleet") || "";
  const page = parsePage(searchParams.get("page"));

  const [qInput, setQInput] = useState(urlQ);
  const debouncedQ = useDebouncedValue(qInput, Q_DEBOUNCE_MS);

  useEffect(() => {
    setQInput(urlQ);
  }, [urlQ]);

  useEffect(() => {
    if (debouncedQ.trim() === (urlQ || "").trim()) {
      return;
    }
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (debouncedQ.trim()) {
          next.set("q", debouncedQ.trim());
        } else {
          next.delete("q");
        }
        next.set("page", "1");
        return next;
      },
      { replace: true }
    );
  }, [debouncedQ, urlQ, setSearchParams]);

  const [payload, setPayload] = useState({
    data: [],
    total: 0,
    page: 1,
    page_size: PAGE_SIZE,
    total_pages: 0,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const requestSeqRef = useRef(0);

  const runFetch = useCallback(async () => {
    requestSeqRef.current += 1;
    const requestId = requestSeqRef.current;
    setLoading(true);
    setError("");
    try {
      const res = await fetchCandidatesPaged({
        page,
        pageSize: PAGE_SIZE,
        q: urlQ,
        position: urlPosition,
        fleet: urlFleet,
      });
      if (requestId !== requestSeqRef.current) {
        return;
      }
      setPayload({
        data: Array.isArray(res.data) ? res.data : [],
        total: res.total ?? 0,
        page: res.page ?? 1,
        page_size: res.page_size ?? PAGE_SIZE,
        total_pages: res.total_pages ?? 0,
      });
      if ((res.page ?? 1) !== page) {
        setSearchParams(
          (prev) => {
            const next = new URLSearchParams(prev);
            if ((res.page ?? 1) === 1) {
              next.delete("page");
            } else {
              next.set("page", String(res.page ?? 1));
            }
            return next;
          },
          { replace: true }
        );
      }
    } catch (requestError) {
      setError(formatCandidatesLoadError(requestError));
    } finally {
      if (requestId === requestSeqRef.current) {
        setLoading(false);
      }
    }
  }, [page, urlQ, urlPosition, urlFleet, refreshKey]);

  useEffect(() => {
    void runFetch();
  }, [runFetch, refreshKey]);

  const { data, total, total_pages, page: responsePage, page_size } = payload;

  const setFilter = (key, value) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value && String(value).trim()) {
          next.set(key, String(value).trim());
        } else {
          next.delete(key);
        }
        next.set("page", "1");
        return next;
      },
      { replace: true }
    );
  };

  const goToPage = (p) => {
    const n = Math.max(1, Math.min(p, total_pages || 1));
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (n === 1) {
          next.delete("page");
        } else {
          next.set("page", String(n));
        }
        return next;
      },
      { replace: true }
    );
  };

  const visiblePages = useMemo(
    () => getVisiblePageNumbers(responsePage || page, total_pages),
    [responsePage, page, total_pages]
  );

  const firstShown = total === 0 ? 0 : (responsePage - 1) * page_size + 1;
  const lastShown = total === 0 ? 0 : Math.min((responsePage - 1) * page_size + data.length, total);

  const listPathForCard = useMemo(() => {
    const s = searchParams.toString();
    return s ? `/candidates?${s}` : "/candidates";
  }, [searchParams]);

  const hasLegacyPosition =
    Boolean(urlPosition) && !POSITION_OPTIONS.includes(urlPosition);
  const hasLegacyFleet = Boolean(urlFleet) && !FLEET_OPTIONS.includes(urlFleet);

  if (error) {
    return <p className="error">{error}</p>;
  }

  return (
    <section className="candidate-section" data-testid="candidate-list-section">
      <div className="candidate-toolbar candidate-toolbar--filters">
        <div className="candidate-filters">
          <input
            type="text"
            placeholder="Поиск по фамилии, имени"
            value={qInput}
            onChange={(e) => setQInput(e.target.value)}
            aria-label="Поиск по фамилии"
          />
          <select
            className="candidate-filters__position"
            value={urlPosition}
            onChange={(e) => setFilter("position", e.target.value)}
            aria-label="Фильтр по должности"
          >
            <option value="">Все должности</option>
            {hasLegacyPosition ? (
              <option value={urlPosition}>
                {urlPosition} (текущий фильтр)
              </option>
            ) : null}
            {POSITION_OPTIONS.map((label) => (
              <option key={label} value={label}>
                {label}
              </option>
            ))}
          </select>
          <select
            className="candidate-filters__fleet"
            value={urlFleet}
            onChange={(e) => setFilter("fleet", e.target.value)}
            aria-label="Фильтр по флоту"
          >
            <option value="">Все типы судов</option>
            {hasLegacyFleet ? (
              <option value={urlFleet}>
                {urlFleet} (текущий фильтр)
              </option>
            ) : null}
            {FLEET_OPTIONS.map((label) => (
              <option key={label} value={label}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading ? <p>Загрузка кандидатов...</p> : null}

      <div className="table-wrap">
        <table className="candidate-table">
          <thead>
            <tr>
              <th>Фамилия</th>
              <th>Имя</th>
              <th>Должность</th>
              <th>Флот</th>
              <th>Действие</th>
            </tr>
          </thead>
          <tbody>
            {data.map((candidate) => (
              <tr key={candidate.id}>
                <td>{candidate.surname || "-"}</td>
                <td>{candidate.first_name || "-"}</td>
                <td>{candidate.position || "-"}</td>
                <td>{candidate.fleet || "-"}</td>
                <td>
                  <button
                    type="button"
                    onClick={() =>
                      navigate(`/candidates/${candidate.id}`, {
                        state: { candidatesListPath: listPathForCard },
                      })
                    }
                  >
                    Открыть карточку
                  </button>
                </td>
              </tr>
            ))}
            {data.length === 0 ? (
              <tr>
                <td colSpan={5} className="empty-row">
                  Кандидаты не найдены
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <div className="candidate-list-footer">
        <p className="candidate-list-range">
          Показано {firstShown}–{lastShown} из {total}
        </p>
        {total_pages > 1 ? (
          <nav className="candidate-pagination" aria-label="Страницы">
            <button
              type="button"
              className="candidate-pagination__btn"
              onClick={() => goToPage(1)}
              disabled={responsePage <= 1}
              aria-label="Первая страница"
            >
              {"<<"}
            </button>
            <button
              type="button"
              className="candidate-pagination__btn"
              onClick={() => goToPage(responsePage - 1)}
              disabled={responsePage <= 1}
              aria-label="Предыдущая страница"
            >
              &lt;
            </button>
            {visiblePages.map((item, idx) =>
              item === "ellipsis" ? (
                <span key={`e-${idx}`} className="candidate-pagination__ellipsis" aria-hidden>
                  …
                </span>
              ) : (
                <button
                  key={item}
                  type="button"
                  className={
                    item === responsePage
                      ? "candidate-pagination__page candidate-pagination__page--current"
                      : "candidate-pagination__page"
                  }
                  onClick={() => goToPage(item)}
                >
                  {item}
                </button>
              )
            )}
            <button
              type="button"
              className="candidate-pagination__btn"
              onClick={() => goToPage(responsePage + 1)}
              disabled={responsePage >= total_pages}
              aria-label="Следующая страница"
            >
              &gt;
            </button>
            <button
              type="button"
              className="candidate-pagination__btn"
              onClick={() => goToPage(total_pages)}
              disabled={responsePage >= total_pages}
              aria-label="Последняя страница"
            >
              {">>"}
            </button>
          </nav>
        ) : null}
      </div>
    </section>
  );
}
