import React from "react";
import DateDdMmYyyyInput from "./DateDdMmYyyyInput";
import { SEA_SERVICE_DEFAULT_REMARKS, contractDurationYmd } from "../utils/seaServiceDuration";

function displayValue(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}

function getId(item, fallbackKeys = []) {
  for (const key of fallbackKeys) {
    if (item?.[key] !== undefined && item?.[key] !== null) {
      return item[key];
    }
  }
  return item?.id;
}

function displayDuration(signOn, signOff, stored) {
  return contractDurationYmd(signOn, signOff) || stored || "-";
}

function patchSeaServiceDates(prev, patch) {
  const seaService = { ...prev.seaService, ...patch };
  const computed = contractDurationYmd(seaService.sign_on_date, seaService.sign_off_date);
  if (computed) {
    seaService.contract_duration = computed;
  }
  return { ...prev, seaService };
}

function SeaCell({ isEditing, value, onChange }) {
  if (!isEditing) {
    return <>{displayValue(value)}</>;
  }
  return <input type="text" value={value || ""} onChange={onChange} />;
}

export default function SeaServiceSection({
  newRows,
  setNewRows,
  seaService,
  editingRows,
  editDrafts,
  setEditDrafts,
  onAddSeaService,
  onUpdateSeaService,
  onDeleteSeaService,
  startEdit,
  cancelEdit,
}) {
  return (
    <>
      <div className="inline-form sea-service-modal-inline-form">
        <input
          type="text"
          placeholder="Судно"
          value={newRows.seaService.vessel_name}
          onChange={(event) =>
            setNewRows((prev) => ({
              ...prev,
              seaService: { ...prev.seaService, vessel_name: event.target.value },
            }))
          }
        />
        <input
          type="text"
          placeholder="Должность"
          value={newRows.seaService.rank_on_vessel}
          onChange={(event) =>
            setNewRows((prev) => ({
              ...prev,
              seaService: { ...prev.seaService, rank_on_vessel: event.target.value },
            }))
          }
        />
        <DateDdMmYyyyInput
          value={newRows.seaService.sign_on_date}
          onChange={(next) => setNewRows((prev) => patchSeaServiceDates(prev, { sign_on_date: next }))}
        />
        <DateDdMmYyyyInput
          value={newRows.seaService.sign_off_date}
          onChange={(next) => setNewRows((prev) => patchSeaServiceDates(prev, { sign_off_date: next }))}
        />
        <button type="button" onClick={onAddSeaService}>
          Добавить
        </button>
      </div>
      <div className="table-wrap sea-service-wrap sea-service-modal-table-wrap">
        <table className="candidate-table sea-service-table">
          <thead>
            <tr>
              <th>Rank</th>
              <th>Vessel</th>
              <th>Year Built</th>
              <th>Flag</th>
              <th>Type of Vessel</th>
              <th>DWT</th>
              <th>Engine type/model</th>
              <th>B.H.P / kW</th>
              <th>Name of Principal</th>
              <th>Manning Agent</th>
              <th>From</th>
              <th>To</th>
              <th>Duration</th>
              <th>Reason of Discharge</th>
              <th>Должность</th>
              <th>Действия</th>
            </tr>
          </thead>
          <tbody>
            {seaService.map((item) => {
              const rowId = getId(item, ["sea_service_id"]);
              const isEditing =
                rowId != null && String(editingRows.seaService) === String(rowId);
              const draft = isEditing ? editDrafts.seaService : item;
              return (
                <tr key={rowId}>
                  <td>{displayValue(item.rank_on_vessel)}</td>
                  <td>
                    <SeaCell
                      isEditing={isEditing}
                      value={draft.vessel_name}
                      onChange={(event) =>
                        setEditDrafts((prev) => ({ ...prev, seaService: { ...prev.seaService, vessel_name: event.target.value } }))
                      }
                    />
                  </td>
                  <td>
                    <SeaCell
                      isEditing={isEditing}
                      value={draft.year_built}
                      onChange={(event) =>
                        setEditDrafts((prev) => ({ ...prev, seaService: { ...prev.seaService, year_built: event.target.value } }))
                      }
                    />
                  </td>
                  <td>
                    <SeaCell
                      isEditing={isEditing}
                      value={draft.flag}
                      onChange={(event) =>
                        setEditDrafts((prev) => ({ ...prev, seaService: { ...prev.seaService, flag: event.target.value } }))
                      }
                    />
                  </td>
                  <td>
                    <SeaCell
                      isEditing={isEditing}
                      value={draft.vessel_type}
                      onChange={(event) =>
                        setEditDrafts((prev) => ({ ...prev, seaService: { ...prev.seaService, vessel_type: event.target.value } }))
                      }
                    />
                  </td>
                  <td>
                    <SeaCell
                      isEditing={isEditing}
                      value={draft.dwt}
                      onChange={(event) =>
                        setEditDrafts((prev) => ({ ...prev, seaService: { ...prev.seaService, dwt: event.target.value } }))
                      }
                    />
                  </td>
                  <td>
                    <SeaCell
                      isEditing={isEditing}
                      value={draft.main_engine}
                      onChange={(event) =>
                        setEditDrafts((prev) => ({ ...prev, seaService: { ...prev.seaService, main_engine: event.target.value } }))
                      }
                    />
                  </td>
                  <td>
                    <SeaCell
                      isEditing={isEditing}
                      value={draft.engine_power}
                      onChange={(event) =>
                        setEditDrafts((prev) => ({ ...prev, seaService: { ...prev.seaService, engine_power: event.target.value } }))
                      }
                    />
                  </td>
                  <td>
                    <SeaCell
                      isEditing={isEditing}
                      value={draft.employer}
                      onChange={(event) =>
                        setEditDrafts((prev) => ({ ...prev, seaService: { ...prev.seaService, employer: event.target.value } }))
                      }
                    />
                  </td>
                  <td>
                    <SeaCell
                      isEditing={isEditing}
                      value={draft.manning_agency}
                      onChange={(event) =>
                        setEditDrafts((prev) => ({ ...prev, seaService: { ...prev.seaService, manning_agency: event.target.value } }))
                      }
                    />
                  </td>
                  <td>
                    {isEditing ? (
                      <DateDdMmYyyyInput
                        value={draft.sign_on_date || ""}
                        onChange={(next) =>
                          setEditDrafts((prev) => patchSeaServiceDates(prev, { sign_on_date: next }))
                        }
                      />
                    ) : (
                      <>{displayValue(item.sign_on_date)}</>
                    )}
                  </td>
                  <td>
                    {isEditing ? (
                      <DateDdMmYyyyInput
                        value={draft.sign_off_date || ""}
                        onChange={(next) =>
                          setEditDrafts((prev) => patchSeaServiceDates(prev, { sign_off_date: next }))
                        }
                      />
                    ) : (
                      <>{displayValue(item.sign_off_date)}</>
                    )}
                  </td>
                  <td className="sea-service-duration-cell">
                    {displayDuration(
                      isEditing ? draft.sign_on_date : item.sign_on_date,
                      isEditing ? draft.sign_off_date : item.sign_off_date,
                      isEditing ? draft.contract_duration : item.contract_duration,
                    )}
                  </td>
                  <td>
                    <SeaCell
                      isEditing={isEditing}
                      value={
                        isEditing
                          ? draft.remarks ?? SEA_SERVICE_DEFAULT_REMARKS
                          : item.remarks || SEA_SERVICE_DEFAULT_REMARKS
                      }
                      onChange={(event) =>
                        setEditDrafts((prev) => ({ ...prev, seaService: { ...prev.seaService, remarks: event.target.value } }))
                      }
                    />
                  </td>
                  <td>
                    <SeaCell
                      isEditing={isEditing}
                      value={draft.rank_on_vessel}
                      onChange={(event) =>
                        setEditDrafts((prev) => ({ ...prev, seaService: { ...prev.seaService, rank_on_vessel: event.target.value } }))
                      }
                    />
                  </td>
                  <td className="actions-row">
                    {isEditing ? (
                      <>
                        <button type="button" onClick={() => onUpdateSeaService(rowId)}>
                          Сохранить
                        </button>
                        <button type="button" className="secondary-btn" onClick={() => cancelEdit("seaService")}>
                          Отмена
                        </button>
                      </>
                    ) : (
                      <>
                        <button type="button" onClick={() => startEdit("seaService", rowId, item)}>
                          Редактировать
                        </button>
                        <button type="button" className="danger-btn" onClick={() => onDeleteSeaService(rowId)}>
                          Удалить
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
