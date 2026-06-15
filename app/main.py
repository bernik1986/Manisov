from __future__ import annotations

from datetime import date, datetime, timedelta
import json
import logging
import os
import re
import threading
import time
from urllib.parse import quote
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from docxtpl import DocxTemplate
from parser.base import BaseParser
from passlib.context import CryptContext
import pdfplumber
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, exists, func, not_, or_, select
from sqlalchemy.orm import Session, selectinload

from models.db import Base, SessionLocal, engine, init_db
from models.schema import (
    Application,
    Attachment,
    Candidate,
    CandidateComment,
    Certificate,
    Company,
    CompanyFolder,
    Document,
    FamilyContact,
    FlagDocument,
    Notification,
    Role,
    SeaService,
    AuditLog,
    TemplateFile,
    TemplateFolder,
    User,
    SalaryComponentTemplate,
    Vessel,
)
from parser.base import BaseParser
from parser.crewwell_pdf_parser import CrewwellPDFParser
from parser.docx_parser import DocxParser
from parser.excel_parser import ExcelParser
from parser.pdf_parser import PDFParser

from app.canonical_documents import (
    apply_canonical_document_placeholders,
    ensure_canonical_documents,
    order_documents_for_response,
)
from app.canonical_visas import (
    apply_canonical_visa_placeholders,
    ensure_canonical_visas,
    order_visas_for_response,
    partition_documents_and_visas,
)
from app.canonical_diplomas import (
    CANONICAL_DIPLOMA_SPECS,
    CANONICAL_TANKER_DIPLOMA_SPECS,
    apply_canonical_diploma_placeholders,
    ensure_canonical_diplomas,
    is_canonical_diploma_record,
    is_working_coc_diploma,
    order_specs_for_response,
)
from app.canonical_certificates import (
    CANONICAL_BWTS_SPECS,
    CANONICAL_COMPANY_SPECS,
    CANONICAL_CONVENTIONAL_SPECS,
    CANONICAL_ECDIS_SPECS,
    apply_canonical_certificate_placeholders,
    ensure_canonical_certificates,
    is_canonical_certificate_record,
    order_certificates_for_response,
)
from app.canonical_medical import (
    apply_canonical_medical_placeholders,
    ensure_canonical_medical,
    is_canonical_medical_record,
    order_medical_for_response,
)
from app.fleet_normalization import display_fleet_label, fleet_search_terms, resolve_canonical_fleet
from app.certificate_validity import apply_certificate_validity_defaults
from app.sea_service_duration import (
    apply_contract_duration_to_payload,
    apply_sea_service_defaults,
    normalize_sea_service_dict,
)
from app.rank_normalization import canonical_rank_for_storage, display_position_label, position_search_terms
from app.attachment_convert import prepare_attachment_bytes
from app.attachment_naming import attachment_download_filename
from app.vessel_specs import (
    VESSEL_FIELD_SPECS,
    VESSEL_OPTIONAL_STRING_FIELDS,
    vessel_placeholder_token,
    vessel_placeholder_value,
)
from app.contract_fields import (
    CONTRACTS_FOLDER_NAMES,
    CONTRACT_EDITABLE_FIELDS,
    build_saved_contract_payload,
    contract_placeholders_from_saved,
    parse_contract_json,
)
from app.salary_calculator import (
    build_saved_calculation_payload,
    calculate_salary,
    list_ranks_for_company,
    parse_saved_calculation,
    salary_placeholders_from_saved,
)
from app.submission_pack import build_submission_zip, ensure_podacha_builtin_templates

app = FastAPI()
# Сохранённые файлы только как пользовательские данные; приложение их не выполняет (см. отдачу через FileResponse API).
UPLOADS_DIR = Path(__file__).resolve().parents[1] / "uploads"
TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
GENERATED_DIR = Path(__file__).resolve().parents[1] / "generated"
TEMPLATES_MANAGER_DIR = TEMPLATES_DIR / "manager_files"
logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 2
LAST_ACTIVE_ADMIN_ERROR = (
    "Нельзя снять права администратора с последнего активного администратора. "
    "Сначала назначьте другого администратора."
)
SELF_ACTIVE_ADMIN_ROLE_CHANGE_ERROR = (
    "Нельзя изменить роль для собственного активного аккаунта администратора."
)
ALLOWED_ATTACHMENT_SUFFIXES = {".jpeg", ".jpg", ".png", ".pdf"}
ALLOWED_TEMPLATE_MANAGER_SUFFIXES = frozenset({".doc", ".docx", ".pdf"})
INVALID_TEMPLATE_FILE_TYPE_MESSAGE = "Недопустимый формат файла"


def _is_allowed_template_manager_filename(name: str) -> bool:
    return Path(name or "").suffix.lower() in ALLOWED_TEMPLATE_MANAGER_SUFFIXES


def _upload_max_bytes_from_mb_env(env_name: str, default_mb: int) -> int:
    raw = os.getenv(env_name)
    if raw is None or not str(raw).strip():
        mb = default_mb
    else:
        try:
            mb = int(str(raw).strip())
        except ValueError:
            mb = default_mb
    return max(1, mb) * 1024 * 1024


# Размеры загрузок (байты). Переопределяются env: *_MAX_UPLOAD_MB.
MAX_TEMPLATE_MANAGER_UPLOAD_BYTES = _upload_max_bytes_from_mb_env("TEMPLATE_MANAGER_MAX_UPLOAD_MB", 40)
MAX_APPLICATION_UPLOAD_BYTES = _upload_max_bytes_from_mb_env("APPLICATION_UPLOAD_MAX_MB", 40)
MAX_CV_UPLOAD_BYTES = _upload_max_bytes_from_mb_env("CV_UPLOAD_MAX_MB", 25)
MAX_ATTACHMENT_UPLOAD_BYTES = _upload_max_bytes_from_mb_env("ATTACHMENT_MAX_UPLOAD_MB", 15)
MAX_COMPANIES_XLSX_UPLOAD_BYTES = _upload_max_bytes_from_mb_env("COMPANIES_XLSX_MAX_UPLOAD_MB", 10)


async def _read_upload_limited(file: UploadFile, max_bytes: int) -> bytes:
    """Читает тело файла с верхней границей размера (без загрузки всего гигабайтного тела в память)."""
    chunk = await file.read(max_bytes + 1)
    if len(chunk) > max_bytes:
        limit_mb = max(1, max_bytes // (1024 * 1024))
        raise HTTPException(
            status_code=413,
            detail=f"Размер файла превышает допустимый лимит ({limit_mb} МБ)",
        )
    return chunk


def _nosniff_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    h: dict[str, str] = {"X-Content-Type-Options": "nosniff"}
    if extra:
        h.update(extra)
    return h


def _ascii_filename_fallback(name: str, *, default: str) -> str:
    """
    HTTP headers are commonly encoded as latin-1; avoid raw non-ASCII in filename="...".
    Keep a conservative ASCII fallback and rely on filename*=UTF-8''... for the real name.
    """
    cleaned = re.sub(r"\.(docx|doc|pdf|zip|xlsx|xls|txt|csv)$", "", str(name or "").strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r'[\x00-\x1f<>:"/\\|?*]+', "", cleaned).strip()
    cleaned = re.sub(r"\s+", "_", cleaned).strip("._")
    ascii_only = cleaned.encode("ascii", "ignore").decode("ascii")
    base = ascii_only or default
    return base[:80] or default


def _attachment_content_disposition(download_name: str) -> str:
    safe_utf8 = str(download_name or "download").replace('"', "")
    suffix = Path(safe_utf8).suffix.lower()
    if suffix not in {".docx", ".doc", ".pdf", ".zip", ".xlsx", ".xls", ".txt", ".csv"}:
        suffix = ""
    fallback = _ascii_filename_fallback(safe_utf8, default="download") + suffix
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(safe_utf8)}"


def _env_truthy(name: str) -> bool:
    raw = os.getenv(name, "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _ensure_nltk_resource(resource_path: str, download_name: str) -> bool:
    try:
        import nltk

        nltk.data.find(resource_path)
        return True
    except LookupError:
        try:
            import nltk

            nltk.download(download_name, quiet=True)
            nltk.data.find(resource_path)
            return True
        except Exception:
            return False
    except Exception:
        return False


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.on_event("startup")
def on_startup() -> None:
    if _env_truthy("RESET_DB_ON_START"):
        logger.warning("RESET_DB_ON_START is enabled: dropping all DB tables before init")
        Base.metadata.drop_all(bind=engine)
    init_db()
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATES_MANAGER_DIR.mkdir(parents=True, exist_ok=True)
    session = SessionLocal()
    try:
        _ensure_default_auth_data(session)
        _ensure_initial_candidate_companies(session)
        try:
            ensure_podacha_builtin_templates(
                session,
                templates_dir=TEMPLATES_DIR,
                templates_manager_dir=TEMPLATES_MANAGER_DIR,
                get_or_create_root=_get_or_create_templates_root,
            )
        except Exception:
            logger.exception("Failed to register Podacha builtin templates at startup")
    finally:
        session.close()


def get_db_session() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


class CandidateListItem(BaseModel):
    id: int
    surname: str | None = None
    first_name: str | None = None
    position: str | None = None
    fleet: str | None = None
    company_id: int | None = None
    company_name: str | None = None
    application_date: date | None = None
    created_at: datetime | None = None


def _latest_sea_service(row: Candidate) -> SeaService | None:
    """Most recent sea service contract (latest sign-on, then highest id)."""
    if not row.sea_service:
        return None
    return max(
        row.sea_service,
        key=lambda s: (
            s.sign_on_date.toordinal() if s.sign_on_date else -1,
            s.sea_service_id,
        ),
    )


def _raw_list_fleet_from_row(row: Candidate) -> str | None:
    """Seamens Data fleet: vessel_type from latest sea service contract only."""
    sea = _latest_sea_service(row)
    if not sea:
        return None
    raw = sea.vessel_type
    return raw.strip() if raw and str(raw).strip() else None


def _display_list_fleet_from_row(row: Candidate) -> str | None:
    raw = _raw_list_fleet_from_row(row)
    if not raw:
        return None
    canon = resolve_canonical_fleet(raw)
    return canon if canon else None


def _first_application(row: Candidate) -> Application | None:
    if not row.applications:
        return None
    return min(row.applications, key=lambda app: app.application_id)


def _raw_list_position_from_row(row: Candidate) -> str | None:
    """Seamens Data position: recruitment application only (not sea service / current_rank)."""
    app = _first_application(row)
    if not app:
        return None
    position = app.position_applied_for or app.rank_applied_for
    return position.strip() if position and position.strip() else None


def _latest_sea_service_vessel_type_subquery() -> Any:
    return (
        select(SeaService.vessel_type)
        .where(SeaService.candidate_id == Candidate.candidate_id)
        .order_by(SeaService.sign_on_date.desc().nullslast(), SeaService.sea_service_id.desc())
        .limit(1)
        .correlate(Candidate)
        .scalar_subquery()
    )


def _fleet_filter_clauses(terms: list[str]) -> Any:
    """Match _raw_list_fleet_from_row: latest sea_service.vessel_type only."""
    latest_type = _latest_sea_service_vessel_type_subquery()
    has_type = and_(latest_type.isnot(None), func.trim(latest_type) != "")

    parts: list[Any] = []
    for t in terms:
        st = t.strip()[:500].replace("%", "").replace("_", "")
        if not st:
            continue
        like_pattern = f"%{st}%"
        parts.append(and_(has_type, latest_type.ilike(like_pattern)))
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return or_(*parts)


def _candidate_row_to_list_item_dict(row: Candidate) -> dict[str, Any]:
    position = display_position_label(_raw_list_position_from_row(row))
    fleet = _display_list_fleet_from_row(row)
    application_date = None
    if row.applications:
        application_date = row.applications[0].date_applied
    return CandidateListItem(
        id=row.candidate_id,
        surname=row.surname,
        first_name=row.first_name,
        position=position,
        fleet=fleet,
        company_id=row.company_id,
        company_name=row.company.name if row.company else None,
        application_date=application_date,
        created_at=row.created_at,
    ).model_dump()


def _first_application_rank_subquery() -> Any:
    return (
        select(
            func.coalesce(
                func.nullif(func.trim(Application.position_applied_for), ""),
                Application.rank_applied_for,
            )
        )
        .where(Application.candidate_id == Candidate.candidate_id)
        .order_by(Application.application_id.asc())
        .limit(1)
        .correlate(Candidate)
        .scalar_subquery()
    )


def _position_filter_clauses(terms: list[str], *, include_sea_service: bool) -> Any:
    """
    OR of (current_rank, applications, optional sea_service) for each search phrase.
    terms come from position_search_terms() (synonym expansion) or a single user fragment.
    """
    if not include_sea_service:
        return _position_filter_clauses_for_list_display(terms)
    parts: list[Any] = []
    for t in terms:
        st = t.strip()[:500].replace("%", "").replace("_", "")
        if not st:
            continue
        like_pattern = f"%{st}%"
        parts.append(
            or_(
                Candidate.current_rank.ilike(like_pattern),
                Candidate.applications.any(
                    or_(
                        Application.position_applied_for.ilike(like_pattern),
                        Application.rank_applied_for.ilike(like_pattern),
                    )
                ),
                Candidate.sea_service.any(SeaService.rank_on_vessel.ilike(like_pattern)),
            )
        )
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return or_(*parts)


def _position_filter_clauses_for_list_display(terms: list[str]) -> Any:
    """
    Match _raw_list_position_from_row: first application position_applied_for / rank_applied_for only.
    """
    first_app_rank = _first_application_rank_subquery()
    has_app_rank = and_(first_app_rank.isnot(None), func.trim(first_app_rank) != "")

    parts: list[Any] = []
    for t in terms:
        st = t.strip()[:500].replace("%", "").replace("_", "")
        if not st:
            continue
        like_pattern = f"%{st}%"
        parts.append(and_(has_app_rank, first_app_rank.ilike(like_pattern)))
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return or_(*parts)


class CandidateUpdate(BaseModel):
    # Accept any candidate profile fields from frontend and validate keys in handler.
    model_config = ConfigDict(extra="allow")


class CandidateCommentCreate(BaseModel):
    comment_text: str


class SubmissionPackRequest(BaseModel):
    opening_vessel: str | None = None
    previous_vessel: str | None = None
    template_file_ids: list[int] = []
    attachment_ids: list[int] = []


ISSUE_EXPIRY_ORDER_ERROR_MSG = "Дата окончания не может быть раньше даты выдачи"


def _expiry_before_issue(issued: date | None, expiry: date | None) -> bool:
    """True when both dates are present and expiry is strictly before issue/issuance."""
    return bool(issued and expiry and expiry < issued)


class DocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_category: str | None = None
    document_type: str
    document_name_raw: str | None = None
    document_number: str | None = None
    issuing_authority: str | None = None
    place_of_issue: str | None = None
    date_of_issue: date | None = None
    date_of_expiry: date | None = None
    validity_status: str | None = None
    unlimited_validity: bool | None = None
    country_of_issue: str | None = None
    remarks: str | None = None
    scan_file: str | None = None
    verified: bool | None = None


def _normalize_application_rank_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Store canonical rank labels on application fields when mappable."""
    out = dict(data)
    for key in ("position_applied_for", "rank_applied_for"):
        raw = out.get(key)
        if not isinstance(raw, str) or not raw.strip():
            continue
        canon = canonical_rank_for_storage(raw)
        if canon:
            out[key] = canon
    return out


class ApplicationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position_applied_for: str | None = None
    rank_applied_for: str | None = None
    willing_to_accept_lower_rank: bool | None = None
    proposed_vessel: str | None = None
    date_applied: date | None = None
    date_available: date | None = None
    last_salary_usd: float | None = None
    applicant_type: str | None = None
    recommended_by_ex_crew: bool | None = None
    recommended_by_ex_crew_name: str | None = None
    recommended_by_others: bool | None = None
    recommended_by_others_name: str | None = None


class DocumentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_category: str | None = None
    document_type: str | None = None
    document_name_raw: str | None = None
    document_number: str | None = None
    issuing_authority: str | None = None
    place_of_issue: str | None = None
    date_of_issue: date | None = None
    date_of_expiry: date | None = None
    validity_status: str | None = None
    unlimited_validity: bool | None = None
    country_of_issue: str | None = None
    remarks: str | None = None
    scan_file: str | None = None
    verified: bool | None = None


class CertificateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    certificate_group: str | None = None
    certificate_type: str
    certificate_name_raw: str | None = None
    certificate_code: str | None = None
    certificate_number: str | None = None
    competency_rank: str | None = None
    issuing_authority: str | None = None
    date_issued: date | None = None
    expiry_date: date | None = None
    unlimited_validity: bool | None = None
    country_of_issue: str | None = None
    is_present: bool | None = None
    remarks: str | None = None
    scan_file: str | None = None


class CertificateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    certificate_group: str | None = None
    certificate_type: str | None = None
    certificate_name_raw: str | None = None
    certificate_code: str | None = None
    certificate_number: str | None = None
    competency_rank: str | None = None
    issuing_authority: str | None = None
    date_issued: date | None = None
    expiry_date: date | None = None
    unlimited_validity: bool | None = None
    country_of_issue: str | None = None
    is_present: bool | None = None
    remarks: str | None = None
    scan_file: str | None = None


class SeaServiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vessel_name: str | None = None
    vessel_type: str | None = None
    vessel_subtype: str | None = None
    flag: str | None = None
    imo_number: str | None = None
    year_built: int | None = None
    dwt: float | None = None
    grt: float | None = None
    main_engine: str | None = None
    engine_power: str | None = None
    rank_on_vessel: str | None = None
    sign_on_date: date | None = None
    sign_off_date: date | None = None
    contract_duration: str | None = None
    employer: str | None = None
    manning_agency: str | None = None
    trade_area: str | None = None
    cargo_type: str | None = None
    remarks: str | None = None
    total_sea_service_duration: str | None = None
    total_sea_service_by_rank: str | None = None
    total_sea_service_by_vessel_type: str | None = None
    tanker_service_duration: str | None = None
    bulk_service_duration: str | None = None
    watch_officer_experience_duration: str | None = None


class SeaServiceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vessel_name: str | None = None
    vessel_type: str | None = None
    vessel_subtype: str | None = None
    flag: str | None = None
    imo_number: str | None = None
    year_built: int | None = None
    dwt: float | None = None
    grt: float | None = None
    main_engine: str | None = None
    engine_power: str | None = None
    rank_on_vessel: str | None = None
    sign_on_date: date | None = None
    sign_off_date: date | None = None
    contract_duration: str | None = None
    employer: str | None = None
    manning_agency: str | None = None
    trade_area: str | None = None
    cargo_type: str | None = None
    remarks: str | None = None
    total_sea_service_duration: str | None = None
    total_sea_service_by_rank: str | None = None
    total_sea_service_by_vessel_type: str | None = None
    tanker_service_duration: str | None = None
    bulk_service_duration: str | None = None
    watch_officer_experience_duration: str | None = None


class FamilyContactCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str
    relationship_to_candidate: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None


class FamilyContactUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = None
    relationship_to_candidate: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None


class FlagDocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flag_country: str
    flag_document_type: str | None = None
    rank: str | None = None
    doc_number: str | None = None
    date_of_issuance: date | None = None
    date_of_expiry: date | None = None
    remarks: str | None = None
    scan_file: str | None = None


class FlagDocumentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flag_country: str | None = None
    flag_document_type: str | None = None
    rank: str | None = None
    doc_number: str | None = None
    date_of_issuance: date | None = None
    date_of_expiry: date | None = None
    remarks: str | None = None
    scan_file: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict[str, Any]


LoginResponse.model_rebuild()


class RegisterRequest(BaseModel):
    username: str
    password: str
    full_name: str | None = None
    role: str = "viewer"
    is_active: bool = True


class UpdateUserRoleRequest(BaseModel):
    role: str


class UpdateUserPasswordRequest(BaseModel):
    password: str


class UpdateUserActiveRequest(BaseModel):
    is_active: bool


class NotificationSentUpdate(BaseModel):
    sent: bool


class TemplateFolderCreate(BaseModel):
    name: str
    parent_id: int | None = None


class TemplateFolderUpdate(BaseModel):
    name: str


class TemplateFileUpdate(BaseModel):
    file_name: str


class CompanyFolderCreate(BaseModel):
    name: str
    parent_id: int | None = None


class CompanyFolderUpdate(BaseModel):
    name: str


class CompanyCreate(BaseModel):
    name: str
    folder_id: int


class CompanyUpdate(BaseModel):
    name: str


class VesselFieldsBase(BaseModel):
    imo: str | None = None
    flag: str | None = None
    port_of_registry: str | None = None
    vessel_type: str | None = None
    registry_address: str | None = None
    official_number: str | None = None
    call_sign: str | None = None
    grt: str | None = None
    deadweight: str | None = None
    year_built: int | None = None
    engine_type: str | None = None
    engine_hp: str | None = None
    classification_society: str | None = None


class VesselCreate(VesselFieldsBase):
    name: str
    company_id: int


class VesselUpdate(VesselFieldsBase):
    name: str


class SalaryComponentTemplateCreate(BaseModel):
    company_id: int
    rank: str
    basic_monthly_wage: float = 0
    monthly_overtime: float = 0
    overtime_rate: float = 0
    sepf: float = 0
    imtf: float = 0
    leave: float = 0
    leave_sub: float = 0
    various_extra_overtime: float = 0


class SalaryComponentTemplateUpdate(BaseModel):
    rank: str | None = None
    basic_monthly_wage: float | None = None
    monthly_overtime: float | None = None
    overtime_rate: float | None = None
    sepf: float | None = None
    imtf: float | None = None
    leave: float | None = None
    leave_sub: float | None = None
    various_extra_overtime: float | None = None


class SalaryCalculatorPreviewRequest(BaseModel):
    company_id: int
    rank: str
    total_wage: float | None = None
    period_of_employment: str | None = None


class SalaryCalculatorSaveRequest(BaseModel):
    company_id: int
    rank: str
    total_wage: float
    period_of_employment: str | None = None


class ContractSaveRequest(BaseModel):
    company_id: int
    vessel_id: int | None = None
    rank: str
    contract_sign_date: str | None = None
    contract_period: str | None = None
    contract_embarkation_date: str | None = None
    contract_embarkation_port: str | None = None
    contract_number: str | None = None
    contract_remarks: str | None = None
    contract_home_airport: str | None = None
    contract_departure_airport: str | None = None
    contract_departure_date: str | None = None


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_, exc: RequestValidationError) -> JSONResponse:
    logger.warning("Validation error: %s", exc)
    return JSONResponse(status_code=400, content={"detail": "Bad Request: invalid request data"})


@app.exception_handler(Exception)
async def generic_exception_handler(_, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled API error: %s", exc)
    content: dict[str, Any] = {"detail": "Internal server error while processing request"}
    # Set CREWDECK_EXPOSE_ERROR_DETAIL=1 on the server temporarily to see the real error in JSON (disable after debugging).
    if os.getenv("CREWDECK_EXPOSE_ERROR_DETAIL", "").strip().lower() in {"1", "true", "yes"}:
        content["error"] = f"{type(exc).__name__}: {exc}"
    return JSONResponse(status_code=500, content=content)


def _get_parser(file_path: Path) -> BaseParser:
    extension = file_path.suffix.lower()
    if extension in {".docx", ".doc"}:
        return DocxParser()
    if extension in {".xlsx", ".xls"}:
        return ExcelParser()
    if extension == ".pdf":
        looks_crewwell = _looks_like_crewwell_pdf(file_path)
        if looks_crewwell:
            return CrewwellPDFParser()
        return PDFParser()
    raise HTTPException(status_code=400, detail=f"Unsupported file type: {extension or 'unknown'}")


def _looks_like_crewwell_pdf(file_path: Path) -> bool:
    try:
        with pdfplumber.open(str(file_path)) as pdf_doc:
            chunks: list[str] = []
            for page in pdf_doc.pages[:2]:
                chunks.append(page.extract_text() or "")
        text = "\n".join(chunks).lower()
        return (
            "main info" in text
            and "passports / smbk" in text
            and ("crewell id" in text or "position applied for" in text)
        )
    except Exception:
        return False


def _model_to_dict(obj: Any) -> dict[str, Any]:
    return {column.name: getattr(obj, column.name) for column in obj.__table__.columns}


def _serialize_candidate_comment(comment: CandidateComment) -> dict[str, Any]:
    return _model_to_dict(comment)


def _with_expiry_flags(items: list[dict[str, Any]], expiry_key: str) -> list[dict[str, Any]]:
    today = date.today()
    flagged: list[dict[str, Any]] = []
    for item in items:
        enriched = dict(item)
        expiry_value = enriched.get(expiry_key)
        expiry_date: date | None = None
        if isinstance(expiry_value, datetime):
            expiry_date = expiry_value.date()
        elif isinstance(expiry_value, date):
            expiry_date = expiry_value
        elif isinstance(expiry_value, str):
            try:
                expiry_date = date.fromisoformat(expiry_value.strip())
            except ValueError:
                expiry_date = None

        if expiry_date is not None:
            days_left = (expiry_date - today).days
            enriched["days_to_expiry"] = days_left
            enriched["warning"] = 0 <= days_left < 240
            enriched["expired"] = days_left < 0
        else:
            enriched["warning"] = False
            enriched["expired"] = False
        flagged.append(enriched)
    return flagged


def _normalize_name_part(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _middle_names_duplicate_compatible(db_value: Any, file_value: Any) -> bool:
    """Allow duplicate match when one side omits middle name; both present must match."""
    m_db = _normalize_name_part(db_value)
    m_file = _normalize_name_part(file_value)
    if not m_db or not m_file:
        return True
    return m_db == m_file


def _coerce_to_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        parsed = DocxParser._to_date(value)
        if parsed is not None:
            return parsed
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def _coerce_to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if not cleaned:
            return None
        try:
            return int(float(cleaned))
        except ValueError:
            return None
    return None


def _coerce_to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _coerce_to_bool(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    return None


def _coerce_model_payload(
    model_cls: type[Any],
    raw: dict[str, Any],
    *,
    exclude: set[str] | None = None,
) -> dict[str, Any]:
    exclude = exclude or set()
    columns = {column.name: column for column in model_cls.__table__.columns}
    payload: dict[str, Any] = {}
    for key, value in raw.items():
        if key in exclude or key not in columns:
            continue
        column = columns[key]
        column_type = column.type.__class__.__name__
        if column_type == "Date":
            payload[key] = _coerce_to_date(value)
        elif column_type == "Integer":
            payload[key] = _coerce_to_int(value)
        elif column_type == "Float":
            payload[key] = _coerce_to_float(value)
        elif column_type == "Boolean":
            payload[key] = _coerce_to_bool(value)
        else:
            payload[key] = value
    return payload


def _has_meaningful_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _delete_notifications_linked_to_subresources(
    session: Session,
    candidate_id: int,
    *,
    document_ids: list[int] | None = None,
    certificate_ids: list[int] | None = None,
) -> None:
    """Remove notification rows before documents/certificates are replaced (PostgreSQL FK)."""
    if document_ids:
        session.query(Notification).filter(Notification.document_id.in_(document_ids)).delete(
            synchronize_session=False
        )
    if certificate_ids:
        session.query(Notification).filter(Notification.certificate_id.in_(certificate_ids)).delete(
            synchronize_session=False
        )


def _save_related_records_for_candidate(
    session: Session,
    candidate: Candidate,
    parsed_data: dict[str, Any],
    *,
    clear_missing: bool = True,
) -> None:
    applications = parsed_data.get("applications", []) or []
    documents = parsed_data.get("documents", []) or []
    certificates = parsed_data.get("certificates", []) or []
    flag_documents = parsed_data.get("flag_documents", []) or []
    sea_service = parsed_data.get("sea_service", []) or []
    family_contacts = parsed_data.get("family_contacts", []) or []

    if applications or clear_missing:
        session.query(Application).filter(Application.candidate_id == candidate.candidate_id).delete(synchronize_session=False)
        for raw in applications:
            payload = _coerce_model_payload(Application, raw, exclude={"application_id", "candidate_id", "created_at", "updated_at"})
            payload["candidate_id"] = candidate.candidate_id
            if not payload.get("position_applied_for") and not payload.get("rank_applied_for"):
                continue
            session.add(Application(**payload))

    if documents or clear_missing:
        existing_doc_ids = [
            row.document_id
            for row in session.query(Document.document_id)
            .filter(Document.candidate_id == candidate.candidate_id)
            .all()
        ]
        if existing_doc_ids:
            _delete_notifications_linked_to_subresources(
                session, candidate.candidate_id, document_ids=existing_doc_ids
            )
        session.query(Document).filter(Document.candidate_id == candidate.candidate_id).delete(synchronize_session=False)
        for raw in documents:
            payload = _coerce_model_payload(Document, raw, exclude={"document_id", "candidate_id", "created_at"})
            payload["candidate_id"] = candidate.candidate_id
            if not payload.get("document_type"):
                payload["document_type"] = raw.get("document_type") or "Unknown document"
            session.add(Document(**payload))
        ensure_canonical_documents(session, candidate.candidate_id)
        ensure_canonical_visas(session, candidate.candidate_id)

    if certificates or clear_missing:
        existing_cert_ids = [
            row.certificate_id
            for row in session.query(Certificate.certificate_id)
            .filter(Certificate.candidate_id == candidate.candidate_id)
            .all()
        ]
        if existing_cert_ids:
            _delete_notifications_linked_to_subresources(
                session, candidate.candidate_id, certificate_ids=existing_cert_ids
            )
        session.query(Certificate).filter(Certificate.candidate_id == candidate.candidate_id).delete(synchronize_session=False)
        for raw in certificates:
            payload = _coerce_model_payload(Certificate, raw, exclude={"certificate_id", "candidate_id", "created_at"})
            payload["candidate_id"] = candidate.candidate_id
            if not payload.get("certificate_type"):
                payload["certificate_type"] = raw.get("certificate_type") or "Unknown certificate"
            session.add(Certificate(**apply_certificate_validity_defaults(payload)))
        ensure_canonical_diplomas(session, candidate.candidate_id)
        ensure_canonical_medical(session, candidate.candidate_id)
        ensure_canonical_certificates(session, candidate.candidate_id)

    if flag_documents or clear_missing:
        session.query(FlagDocument).filter(FlagDocument.candidate_id == candidate.candidate_id).delete(synchronize_session=False)
        for raw in flag_documents:
            payload = _coerce_model_payload(FlagDocument, raw, exclude={"flag_document_id", "candidate_id", "created_at"})
            payload["candidate_id"] = candidate.candidate_id
            if not payload.get("flag_country"):
                continue
            session.add(FlagDocument(**payload))

    if sea_service or clear_missing:
        session.query(SeaService).filter(SeaService.candidate_id == candidate.candidate_id).delete(synchronize_session=False)
        for raw in sea_service:
            payload = _coerce_model_payload(SeaService, raw, exclude={"sea_service_id", "candidate_id", "created_at"})
            payload["candidate_id"] = candidate.candidate_id
            has_meaningful_sea_data = any(
                payload.get(field)
                for field in (
                    "vessel_name",
                    "rank_on_vessel",
                    "sign_on_date",
                    "sign_off_date",
                    "contract_duration",
                    "employer",
                    "vessel_type",
                )
            )
            if not has_meaningful_sea_data:
                continue
            normalized_payload = apply_sea_service_defaults(payload)
            session.add(SeaService(**normalized_payload))

    if family_contacts or clear_missing:
        session.query(FamilyContact).filter(FamilyContact.candidate_id == candidate.candidate_id).delete(synchronize_session=False)
        for raw in family_contacts:
            payload = _coerce_model_payload(FamilyContact, raw, exclude={"family_contact_id", "candidate_id", "created_at"})
            payload["candidate_id"] = candidate.candidate_id
            if not payload.get("full_name"):
                full_name = raw.get("full_name") or " ".join(
                    part for part in (raw.get("first_name"), raw.get("surname")) if part
                )
                payload["full_name"] = full_name or "Unknown contact"
            session.add(FamilyContact(**payload))


def _merge_parsed_data_into_candidate(session: Session, candidate: Candidate, parsed_data: dict[str, Any]) -> Candidate:
    personal = parsed_data.get("personal_data", {}) or {}
    candidate_payload = _coerce_model_payload(Candidate, personal, exclude={"candidate_id", "created_at", "updated_at"})
    for key, value in candidate_payload.items():
        if _has_meaningful_value(value):
            setattr(candidate, key, value)
    _save_related_records_for_candidate(session, candidate, parsed_data, clear_missing=False)
    session.commit()
    session.refresh(candidate)
    return candidate


def _find_duplicate_candidate(session: Session, parsed_data: dict[str, Any]) -> Candidate | None:
    personal = parsed_data.get("personal_data") or {}
    surname = _normalize_name_part(personal.get("surname"))
    first_name = _normalize_name_part(personal.get("first_name"))
    date_of_birth = _coerce_to_date(personal.get("date_of_birth"))

    # Duplicate rule: surname + first name + DOB; middle name optional if omitted on one side.
    if not surname or not first_name or date_of_birth is None:
        return None

    candidates = session.query(Candidate).filter(Candidate.date_of_birth == date_of_birth).all()
    for candidate in candidates:
        if (
            _normalize_name_part(candidate.surname) == surname
            and _normalize_name_part(candidate.first_name) == first_name
            and _middle_names_duplicate_compatible(candidate.middle_name, personal.get("middle_name"))
        ):
            return candidate
    return None


def _save_parsed_data(parsed_data: dict[str, Any], parser: BaseParser, session: Session) -> int:
    try:
        if isinstance(parser, DocxParser):
            candidate = parser._map_and_save_to_db(parsed_data, session)
            return candidate.candidate_id

        personal = parsed_data.get("personal_data", {}) or {}
        candidate_payload = _coerce_model_payload(Candidate, personal, exclude={"candidate_id", "created_at", "updated_at"})
        candidate = Candidate(**candidate_payload)
        session.add(candidate)
        session.flush()
        _save_related_records_for_candidate(session, candidate, parsed_data)
        session.commit()
        session.refresh(candidate)
        return candidate.candidate_id
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save parsed result: {exc}") from exc


def _parse_manual_text_to_payload(raw_text: str) -> dict[str, Any]:
    """
    Best-effort parser for human-provided text blocks that already reference placeholders like:
    {{ surname }}: Prokopuk
    and section blocks for documents/certificates/sea_service.
    """
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("Text is empty")

    # If user pasted JSON, accept it as-is (variant A) and normalize it to contract.
    if text.startswith("{") and text.endswith("}"):
        try:
            as_obj = json.loads(text)
        except Exception:
            as_obj = None
        if isinstance(as_obj, dict) and (
            "personal_data" in as_obj
            or "documents" in as_obj
            or "certificates" in as_obj
            or "sea_service" in as_obj
            or "applications" in as_obj
        ):
            return BaseParser.ensure_result_contract(as_obj)

    result = BaseParser.empty_result()

    def _clean_line(raw_line: str) -> str:
        line = (raw_line or "").strip()
        if not line:
            return ""
        # remove trailing citations like [cite: 1]
        line = re.sub(r"\s*\[cite:\s*\d+\]\s*$", "", line, flags=re.IGNORECASE).strip()
        # remove markdown heading markers
        line = re.sub(r"^\s*#{1,6}\s*", "", line).strip()
        # remove leading list markers: "* ", "- ", "1. "
        line = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", line).strip()
        # drop markdown bold markers around tokens
        line = line.replace("**", "").strip()
        return line

    current_section: str | None = None
    for raw_line in text.splitlines():
        line = _clean_line(raw_line)
        if not line:
            continue

        low = line.lower().strip(":").strip()
        # section markers may include extra text like "documents (..)" or "sea_service (последние записи)".
        # IMPORTANT: do not match by substring "sea" because headings like "documents (Seaman ...)" would be misclassified.
        m_sec = re.match(
            r"^(applications|documents|certificates|sea[_ ]service|flag[_ ]documents|family[_ ]contacts)\b",
            low,
        )
        if m_sec:
            token = m_sec.group(1)
            if token in {"sea_service", "sea service"}:
                current_section = "sea_service"
            elif token in {"flag_documents", "flag documents"}:
                current_section = "flag_documents"
            elif token in {"family_contacts", "family contacts"}:
                current_section = "family_contacts"
            else:
                current_section = token
            continue

        # Placeholder line: {{ field }}: value
        m = re.match(r"^\{\{\s*(?P<key>[a-zA-Z0-9_]+)\s*\}\}\s*:\s*(?P<value>.+)$", line)
        if m:
            key = m.group("key").strip()
            value = m.group("value").strip()
            if key:
                # normalize common units and booleans
                v_clean = value
                v_clean = re.sub(r"\s+(cm|kg)\b", "", v_clean, flags=re.IGNORECASE).strip()
                # map mismatched field name from user text to schema field
                if key == "usa_visa_status_note":
                    key = "visa_status_note"
                # normalize date-like strings
                normalized = BaseParser._normalize_date_string(v_clean) if isinstance(v_clean, str) else v_clean
                # map "Validity for life..." to boolean
                if key == "yellow_fever_unlimited" and isinstance(normalized, str):
                    normalized = normalized.strip().lower() not in {"", "no", "false", "0", "n/a", "na"}
                # graduation_year sometimes provided as date
                if key == "graduation_year" and isinstance(normalized, str):
                    m_year = re.search(r"(\d{4})", normalized)
                    if m_year:
                        normalized = m_year.group(1)
                result["personal_data"][key] = normalized
            continue

        # Section-aware parsing
        if current_section == "documents":
            # Example: document_type: Passport | number: FZ... | expiry: 04.11.2030
            parts = [p.strip() for p in line.split("|") if p.strip()]
            item: dict[str, Any] = {}
            for part in parts:
                if ":" in part:
                    k, v = [x.strip() for x in part.split(":", 1)]
                    kl = k.lower()
                    if kl in {"document_type", "type"}:
                        item["document_type"] = v
                    elif kl in {"number", "document_number", "doc no", "doc number"}:
                        item["document_number"] = v
                    elif kl in {"expiry", "date_of_expiry", "exp"}:
                        item["date_of_expiry"] = BaseParser._normalize_date_string(v)
                    elif kl in {"issue", "date_of_issue"}:
                        item["date_of_issue"] = BaseParser._normalize_date_string(v)
            if item.get("document_type") or item.get("document_number"):
                result["documents"].append(item)
            continue

        if current_section == "applications":
            # Example: rank_applied_for: Second Officer
            if ":" in line:
                k, v = [x.strip() for x in line.split(":", 1)]
                kl = k.lower()
                item = result["applications"][0] if result["applications"] else {}
                if kl in {"rank_applied_for", "position_applied_for", "proposed_vessel"}:
                    item[kl] = v
                elif kl in {"date_available", "date_applied"}:
                    item[kl] = BaseParser._normalize_date_string(v)
                if item:
                    if not result["applications"]:
                        result["applications"].append(item)
            continue

        if current_section == "certificates":
            # Example: G.M.D.S.S.: 00633/2026 (Exp: 27.01.2031)
            cert_item: dict[str, Any] = {}
            if ":" in line:
                left, right = [x.strip() for x in line.split(":", 1)]
                cert_item["certificate_type"] = left
                # extract number + optional expiry
                num = right
                exp = None
                mexp = re.search(r"\(.*?exp\s*:\s*([0-9./-]+).*?\)", right, flags=re.IGNORECASE)
                if mexp:
                    exp = mexp.group(1).strip()
                    num = re.sub(r"\(.*?\)", "", right).strip()
                if num:
                    cert_item["certificate_number"] = num
                if exp:
                    cert_item["expiry_date"] = BaseParser._normalize_date_string(exp)
            if cert_item.get("certificate_type"):
                result["certificates"].append(cert_item)
            continue

        if current_section == "sea_service":
            # Example: vessel_name: AVON TRADER | rank: 2ND OFFICER | dates: 26.05.2025 – 22.12.2025 | type: BULK CARRIER
            parts = [p.strip() for p in line.split("|") if p.strip()]
            item: dict[str, Any] = {}
            for part in parts:
                if ":" not in part:
                    continue
                k, v = [x.strip() for x in part.split(":", 1)]
                kl = k.lower()
                if kl in {"vessel_name", "vessel"}:
                    item["vessel_name"] = v
                elif kl in {"type", "vessel_type"}:
                    item["vessel_type"] = v
                elif kl in {"rank", "rank_on_vessel"}:
                    item["rank_on_vessel"] = v
                elif kl in {"dates"}:
                    # support "A – B" or "A - B"
                    vv = v.replace("–", "-")
                    if "-" in vv:
                        a, b = [x.strip() for x in vv.split("-", 1)]
                        if a:
                            item["sign_on_date"] = BaseParser._normalize_date_string(a)
                        if b:
                            item["sign_off_date"] = BaseParser._normalize_date_string(b)
            if item.get("vessel_name"):
                result["sea_service"].append(item)
            continue

    return BaseParser.ensure_result_contract(result)


class ManualTextImportRequest(BaseModel):
    text: str


def _ensure_candidate(session: Any, candidate_id: int) -> Candidate:
    candidate = session.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id} not found")
    return candidate


def _verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def _create_access_token(user: User) -> str:
    payload = {
        "sub": str(user.user_id),
        "username": user.username,
        "role": user.role.name if user.role else None,
        "exp": datetime.utcnow() + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def _serialize_user(user: User) -> dict[str, Any]:
    return {
        "user_id": user.user_id,
        "username": user.username,
        "full_name": user.full_name,
        "is_active": user.is_active,
        "role": user.role.name if user.role else None,
    }


def _serialize_candidate_context(candidate: Candidate, db_session: Session | None = None) -> dict[str, Any]:
    context = _model_to_dict(candidate)
    raw_ukr = context.pop("ukr_contract_json", None)
    if raw_ukr and isinstance(raw_ukr, str) and raw_ukr.strip():
        try:
            ukr_data = json.loads(raw_ukr)
            if isinstance(ukr_data, dict):
                for key, value in ukr_data.items():
                    if isinstance(key, str) and key.startswith("ukr_"):
                        context[key] = "" if value is None else str(value)
        except json.JSONDecodeError:
            pass
    raw_salary = context.pop("salary_calculation_json", None)
    if isinstance(raw_salary, str):
        context.update(salary_placeholders_from_saved(parse_saved_calculation(raw_salary)))
    raw_contract = context.pop("contract_json", None)
    if isinstance(raw_contract, str) and raw_contract.strip():
        context.update(
            contract_placeholders_from_saved(parse_contract_json(raw_contract), db_session=db_session)
        )
    context["applications"] = [_model_to_dict(item) for item in candidate.applications]
    all_document_dicts = [_model_to_dict(item) for item in candidate.documents]
    non_visa_documents, visa_document_dicts = partition_documents_and_visas(all_document_dicts)
    context["documents"] = non_visa_documents
    context["visas"] = visa_document_dicts
    context["certificates"] = [_model_to_dict(item) for item in candidate.certificates]
    context["flag_documents"] = [_model_to_dict(item) for item in candidate.flag_documents]
    context["sea_service"] = [_model_to_dict(item) for item in candidate.sea_service]
    context["family_contacts"] = [_model_to_dict(item) for item in candidate.family_contacts]
    context["attachments"] = [_model_to_dict(item) for item in candidate.attachments]
    if db_session is not None:
        cid = candidate.candidate_id
        ensure_canonical_documents(db_session, cid)
        ensure_canonical_visas(db_session, cid)
        ensure_canonical_diplomas(db_session, cid)
        ensure_canonical_medical(db_session, cid)
        ensure_canonical_certificates(db_session, cid)
        all_certs = [
            _model_to_dict(row)
            for row in db_session.query(Certificate)
            .filter(Certificate.candidate_id == cid)
            .order_by(Certificate.certificate_id.asc())
            .all()
        ]
        context["diplomas"] = order_specs_for_response(all_certs, CANONICAL_DIPLOMA_SPECS)
        context["tanker_diplomas"] = order_specs_for_response(all_certs, CANONICAL_TANKER_DIPLOMA_SPECS)
        context["conventional_certificates"] = order_certificates_for_response(all_certs, CANONICAL_CONVENTIONAL_SPECS)
        context["ecdis_certificates"] = order_certificates_for_response(all_certs, CANONICAL_ECDIS_SPECS)
        context["company_certificates"] = order_certificates_for_response(all_certs, CANONICAL_COMPANY_SPECS)
        context["bwts_certificates"] = order_certificates_for_response(all_certs, CANONICAL_BWTS_SPECS)
        context["medical_documents"] = order_medical_for_response(all_certs)
        context["visas"] = order_visas_for_response(context.get("visas") or [])
    _augment_template_context(context)
    if db_session is not None:
        context.update(_build_company_placeholders(db_session))
    return _format_template_dates(context)


def _format_template_dates(value: Any) -> Any:
    """Recursively format template dates as dd-mm-yyyy strings."""
    if isinstance(value, datetime):
        return value.strftime("%d-%m-%Y")
    if isinstance(value, date):
        return value.strftime("%d-%m-%Y")
    if isinstance(value, list):
        return [_format_template_dates(item) for item in value]
    if isinstance(value, dict):
        return {key: _format_template_dates(item) for key, item in value.items()}
    return value


def _prepare_docx_template_context(context: dict[str, Any], template_path: Path) -> dict[str, Any]:
    from app.template_field_values import prepare_docx_template_context

    return prepare_docx_template_context(context, template_path)


def _first_non_empty(values: list[Any]) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return ""


def _upper_or_empty(value: Any) -> str:
    text = str(value or "").strip()
    return text.upper() if text else ""


def _pick_record_by_terms(records: list[dict[str, Any]], terms: list[str], fields: list[str]) -> dict[str, Any] | None:
    lowered_terms = [term.lower() for term in terms]
    for rec in records:
        text = " ".join(str(rec.get(field) or "").lower() for field in fields)
        if any(term in text for term in lowered_terms):
            return rec
    return None


def _sync_candidate_coc_rank_from_certificate(
    db_session: Session,
    candidate_id: int,
    certificate: Certificate,
    competency_rank: str | None,
) -> None:
    if not is_working_coc_diploma(certificate):
        return
    candidate = db_session.get(Candidate, candidate_id)
    if not candidate:
        return
    candidate.certificate_of_competency_rank = (
        str(competency_rank).strip() if competency_rank is not None and str(competency_rank).strip() else None
    )


def _assign_doc_fields(
    context: dict[str, Any],
    key_prefix: str,
    cert_terms: list[str] | None = None,
    doc_terms: list[str] | None = None,
) -> None:
    certificates = context.get("certificates") or []
    documents = context.get("documents") or []
    cert_rec = (
        _pick_record_by_terms(certificates, cert_terms or [], ["certificate_type", "certificate_name_raw", "certificate_group"])
        if cert_terms
        else None
    )
    doc_rec = (
        _pick_record_by_terms(documents, doc_terms or [], ["document_type", "document_name_raw", "document_category"])
        if doc_terms
        else None
    )

    from app.template_field_values import clean_document_number_field

    cert_num = clean_document_number_field(
        (cert_rec or {}).get("certificate_number"),
        cert_rec if isinstance(cert_rec, dict) else None,
    )
    doc_num = clean_document_number_field(
        (doc_rec or {}).get("document_number"),
        doc_rec if isinstance(doc_rec, dict) else None,
    )
    context[f"{key_prefix}_document_number"] = cert_num or doc_num or ""
    context[f"{key_prefix}_issue_date"] = _first_non_empty(
        [
            (cert_rec or {}).get("date_issued"),
            (doc_rec or {}).get("date_of_issue"),
        ]
    )
    context[f"{key_prefix}_expiry_date"] = _first_non_empty(
        [
            (cert_rec or {}).get("expiry_date"),
            (doc_rec or {}).get("date_of_expiry"),
        ]
    )
    context[f"{key_prefix}_issuing_authority"] = _first_non_empty(
        [
            (cert_rec or {}).get("issuing_authority"),
            (doc_rec or {}).get("issuing_authority"),
        ]
    )


def _augment_template_context(context: dict[str, Any]) -> None:
    # Aliases used by legacy external templates.
    context.setdefault("total_sea_service_years", context.get("total_years_of_sea_service") or "")
    context.setdefault("bulk_years_in_vessel_type", context.get("bulk_carrier_years_in_vessel_type") or "")
    context.setdefault("years_watch_officer", context.get("years_as_watch_officer") or "")
    context.setdefault("sts_experience_years", context.get("years_in_this_type_of_vessel") or 0)
    context.setdefault("coc_rank", context.get("certificate_of_competency_rank") or "")
    context.setdefault("coc_certificate_number", context.get("certificate_of_competency_number") or "")
    context.setdefault("usa_visa_issue_place", context.get("usa_visa_place_of_issue") or "")
    context.setdefault("passport_issue_place", context.get("passport_place_of_issue") or "")
    context.setdefault(
        "phone_mobile",
        _first_non_empty(
            [context.get("mobile_phone"), context.get("primary_phone"), context.get("telephone_no")]
        ),
    )
    context.setdefault("beneficiary_name", context.get("beneficiary_full_name") or "")
    context.setdefault("beneficiary_relation", context.get("beneficiary_relationship") or "")
    context.setdefault("children_under_18", context.get("children_under_18_count") or "")
    context.setdefault("highest_education", context.get("highest_educational_attainment") or "")
    context.setdefault("education_school", context.get("school_name") or "")
    context.setdefault("education_year", context.get("graduation_year") or "")
    # Uppercase aliases used by some COE templates.
    context.setdefault("SURNAME", _upper_or_empty(context.get("surname")))
    context.setdefault("FIRST_NAME", _upper_or_empty(context.get("first_name")))
    context.setdefault(
        "GIVEN_NAMES",
        _upper_or_empty(
            _first_non_empty([context.get("given_names"), context.get("first_name"), context.get("middle_name")])
        ),
    )
    context.setdefault("NATIONALITY", _upper_or_empty(context.get("nationality")))
    context.setdefault(
        "PERMANENT_ADDRESS",
        _upper_or_empty(
            _first_non_empty([context.get("permanent_address"), context.get("address"), context.get("full_home_address")])
        ),
    )

    # Derived from first sea service row (for application templates).
    sea_service = context.get("sea_service") or []
    first_service = sea_service[0] if sea_service else {}
    context.setdefault("vessel_name", first_service.get("vessel_name") or "")
    context.setdefault("vessel_type", first_service.get("vessel_type") or "")
    context.setdefault("ship_owner", first_service.get("employer") or "")
    context.setdefault("engine_type", first_service.get("main_engine") or "")
    context.setdefault("engine_hp", first_service.get("engine_power") or "")
    context.setdefault("vessel_grt", first_service.get("grt") or "")
    context.setdefault("sign_on_date", first_service.get("sign_on_date") or "")
    context.setdefault("sign_off_date", first_service.get("sign_off_date") or "")
    context.setdefault("discharge_reason", first_service.get("remarks") or "")
    context.setdefault("shipyard_experience_years", context.get("years_in_this_type_of_vessel") or 0)

    applications = context.get("applications") or []
    first_application = applications[0] if applications else {}
    context.setdefault("position_applied", first_application.get("position_applied_for") or "")
    context.setdefault("rank", context.get("current_rank") or first_application.get("rank_applied_for") or "")
    context.setdefault("candidate_for_vessel", first_application.get("proposed_vessel") or "")
    context.setdefault("application_date", first_application.get("date_applied") or "")

    # Map template certificate/document placeholders to CRM records by keyword.
    _assign_doc_fields(context, "gmdss", cert_terms=["gmdss"], doc_terms=["gmdss"])
    _assign_doc_fields(context, "ecdis", cert_terms=["ecdis"], doc_terms=["ecdis"])
    _assign_doc_fields(context, "sso", cert_terms=["sso", "ship security officer"], doc_terms=["sso", "ship security officer"])
    _assign_doc_fields(
        context,
        "safety_officer",
        cert_terms=["safety officer", "safety training for personnel"],
        doc_terms=["safety officer"],
    )
    _assign_doc_fields(
        context,
        "proficiency_survival_craft",
        cert_terms=["survival craft", "pscrb", "proficiency in survival craft"],
        doc_terms=["survival craft", "pscrb"],
    )
    _assign_doc_fields(
        context,
        "fire_fighting",
        cert_terms=["fire fighting", "firefighting", "advanced fire"],
        doc_terms=["fire fighting", "firefighting"],
    )
    _assign_doc_fields(
        context,
        "advanced_fire_fighting",
        cert_terms=["advanced fire", "advanced firefighting", "aff"],
        doc_terms=["advanced fire", "advanced firefighting"],
    )
    _assign_doc_fields(
        context,
        "medical_first_aid",
        cert_terms=["medical first aid", "first aid"],
        doc_terms=["medical first aid", "first aid"],
    )
    _assign_doc_fields(
        context,
        "medical_care",
        cert_terms=["medical care"],
        doc_terms=["medical care"],
    )
    _assign_doc_fields(context, "brm", cert_terms=["brm", "bridge resource management"], doc_terms=["brm"])
    _assign_doc_fields(context, "erm", cert_terms=["erm", "engine resource management"], doc_terms=["erm"])

    # COC dates can be in certificates/documents.
    _assign_doc_fields(
        context,
        "coc",
        cert_terms=["certificate of competency", "coc"],
        doc_terms=["certificate of competency", "coc"],
    )
    if not context.get("coc_certificate_number"):
        context["coc_certificate_number"] = context.get("certificate_of_competency_number") or ""

    apply_canonical_diploma_placeholders(context)
    apply_canonical_medical_placeholders(context)
    apply_canonical_certificate_placeholders(context)
    apply_canonical_document_placeholders(context)
    apply_canonical_visa_placeholders(context)


def _get_or_create_templates_root(db_session: Session) -> TemplateFolder:
    root = db_session.query(TemplateFolder).filter(TemplateFolder.parent_id.is_(None)).one_or_none()
    if root:
        return root
    root = TemplateFolder(name="Templates", parent_id=None)
    db_session.add(root)
    db_session.commit()
    db_session.refresh(root)
    return root


def _serialize_template_folder(folder: TemplateFolder) -> dict[str, Any]:
    return {
        "folder_id": folder.folder_id,
        "name": folder.name,
        "parent_id": folder.parent_id,
        "created_at": folder.created_at,
        "updated_at": folder.updated_at,
    }


def _serialize_template_file(item: TemplateFile) -> dict[str, Any]:
    return {
        "template_file_id": item.template_file_id,
        "folder_id": item.folder_id,
        "file_name": item.file_name,
        "file_type": item.file_type,
        "file_size_bytes": item.file_size_bytes,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _slugify_entity_name(name: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower())
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "item"


def _unique_company_slug(db_session: Session, base_slug: str, exclude_company_id: int | None = None) -> str:
    slug = base_slug
    suffix = 2
    while True:
        query = db_session.query(Company).filter(Company.slug == slug)
        if exclude_company_id is not None:
            query = query.filter(Company.company_id != exclude_company_id)
        if query.first() is None:
            return slug
        slug = f"{base_slug}_{suffix}"
        suffix += 1


def _unique_vessel_slug(
    db_session: Session,
    company_id: int,
    base_slug: str,
    exclude_vessel_id: int | None = None,
) -> str:
    slug = base_slug
    suffix = 2
    while True:
        query = db_session.query(Vessel).filter(Vessel.company_id == company_id, Vessel.slug == slug)
        if exclude_vessel_id is not None:
            query = query.filter(Vessel.vessel_id != exclude_vessel_id)
        if query.first() is None:
            return slug
        slug = f"{base_slug}_{suffix}"
        suffix += 1


def _vessel_placeholder_prefix(company_slug: str, vessel_slug: str) -> str:
    return f"company_{company_slug}_{vessel_slug}"


def _vessel_placeholder_display(company_slug: str, vessel_slug: str) -> dict[str, str]:
    prefix = _vessel_placeholder_prefix(company_slug, vessel_slug)
    result: dict[str, str] = {}
    for field_key, _label in VESSEL_FIELD_SPECS:
        token_key = "type" if field_key == "vessel_type" else field_key
        result[token_key] = vessel_placeholder_token(prefix, field_key)
    return result


def _build_company_placeholders(db_session: Session) -> dict[str, str]:
    rows = (
        db_session.query(Vessel, Company)
        .join(Company, Vessel.company_id == Company.company_id)
        .order_by(Company.slug.asc(), Vessel.slug.asc())
        .all()
    )
    placeholders: dict[str, str] = {}
    for vessel, company in rows:
        prefix = _vessel_placeholder_prefix(company.slug, vessel.slug)
        for field_key, _label in VESSEL_FIELD_SPECS:
            suffix = "type" if field_key == "vessel_type" else field_key
            placeholders[f"{prefix}_{suffix}"] = vessel_placeholder_value(vessel, field_key)
    return placeholders


def _normalize_vessel_optional_string(value: str | None) -> str | None:
    return (value or "").strip() or None


def _normalize_vessel_year_built(value: int | None) -> int | None:
    if value is None:
        return None
    if value < 1800 or value > 2100:
        raise HTTPException(status_code=400, detail="Year of Built must be between 1800 and 2100")
    return value


def _apply_vessel_fields(vessel: Vessel, payload: VesselFieldsBase) -> None:
    for field_name in VESSEL_OPTIONAL_STRING_FIELDS:
        setattr(
            vessel,
            field_name,
            _normalize_vessel_optional_string(getattr(payload, field_name, None)),
        )
    vessel.year_built = _normalize_vessel_year_built(payload.year_built)


def _get_or_create_companies_root(db_session: Session) -> CompanyFolder:
    root = db_session.query(CompanyFolder).filter(CompanyFolder.parent_id.is_(None)).one_or_none()
    if root:
        return root
    root = CompanyFolder(name="Companies", parent_id=None)
    db_session.add(root)
    db_session.commit()
    db_session.refresh(root)
    return root


def _ensure_initial_candidate_companies(db_session: Session) -> None:
    root = _get_or_create_companies_root(db_session)
    defaults = (("Marmaras", "marmaras"), ("Delta Tankers", "delta_tankers"))
    changed = False
    for name, slug in defaults:
        if db_session.query(Company).filter(Company.slug == slug).one_or_none():
            continue
        db_session.add(Company(folder_id=root.folder_id, name=name, slug=slug))
        changed = True
    if changed:
        db_session.commit()


def _serialize_company_folder(folder: CompanyFolder) -> dict[str, Any]:
    return {
        "folder_id": folder.folder_id,
        "name": folder.name,
        "parent_id": folder.parent_id,
        "created_at": folder.created_at,
        "updated_at": folder.updated_at,
    }


def _serialize_company(company: Company) -> dict[str, Any]:
    return {
        "company_id": company.company_id,
        "folder_id": company.folder_id,
        "name": company.name,
        "slug": company.slug,
        "created_at": company.created_at,
        "updated_at": company.updated_at,
    }


def _serialize_salary_template(row: SalaryComponentTemplate) -> dict[str, Any]:
    return {
        "template_id": row.template_id,
        "company_id": row.company_id,
        "rank": row.rank,
        "basic_monthly_wage": row.basic_monthly_wage,
        "monthly_overtime": row.monthly_overtime,
        "overtime_rate": row.overtime_rate,
        "sepf": row.sepf,
        "imtf": row.imtf,
        "leave": row.leave,
        "leave_sub": row.leave_sub,
        "various_extra_overtime": row.various_extra_overtime,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _serialize_vessel(vessel: Vessel, company_slug: str) -> dict[str, Any]:
    return {
        "vessel_id": vessel.vessel_id,
        "company_id": vessel.company_id,
        "name": vessel.name,
        "slug": vessel.slug,
        "imo": vessel.imo,
        "flag": vessel.flag,
        "port_of_registry": vessel.port_of_registry,
        "vessel_type": vessel.vessel_type,
        "registry_address": vessel.registry_address,
        "official_number": vessel.official_number,
        "call_sign": vessel.call_sign,
        "grt": vessel.grt,
        "deadweight": vessel.deadweight,
        "year_built": vessel.year_built,
        "engine_type": vessel.engine_type,
        "engine_hp": vessel.engine_hp,
        "classification_society": vessel.classification_society,
        "created_at": vessel.created_at,
        "updated_at": vessel.updated_at,
        "placeholders": _vessel_placeholder_display(company_slug, vessel.slug),
    }


def _collect_folder_descendants(db_session: Session, folder_id: int) -> set[int]:
    to_visit = [folder_id]
    result: set[int] = set()
    while to_visit:
        current = to_visit.pop()
        if current in result:
            continue
        result.add(current)
        children = db_session.query(TemplateFolder.folder_id).filter(TemplateFolder.parent_id == current).all()
        to_visit.extend(child_id for (child_id,) in children)
    return result


def _find_contracts_template_folder(db_session: Session) -> TemplateFolder | None:
    for folder in db_session.query(TemplateFolder).all():
        if folder.name.strip().lower() in CONTRACTS_FOLDER_NAMES:
            return folder
    return None


def _template_file_in_contracts_folder(db_session: Session, template_file_id: int) -> bool:
    folder = _find_contracts_template_folder(db_session)
    if not folder:
        return False
    allowed = _collect_folder_descendants(db_session, folder.folder_id)
    item = db_session.get(TemplateFile, template_file_id)
    return item is not None and item.folder_id in allowed


def _collect_company_folder_descendants(db_session: Session, folder_id: int) -> set[int]:
    to_visit = [folder_id]
    result: set[int] = set()
    while to_visit:
        current = to_visit.pop()
        if current in result:
            continue
        result.add(current)
        children = db_session.query(CompanyFolder.folder_id).filter(CompanyFolder.parent_id == current).all()
        to_visit.extend(child_id for (child_id,) in children)
    return result


def _write_audit_log(
    db_session: Session,
    user: User | None,
    *,
    action: str,
    entity_type: str | None = None,
    entity_id: str | int | None = None,
    details: str | None = None,
) -> None:
    try:
        db_session.add(
            AuditLog(
                user_id=user.user_id if user else None,
                username=user.username if user else None,
                role_name=user.role.name if user and user.role else None,
                action=action,
                entity_type=entity_type,
                entity_id=str(entity_id) if entity_id is not None else None,
                details=details,
            )
        )
        db_session.commit()
    except Exception:
        db_session.rollback()
        logger.exception("Failed to write audit log")


def _get_role_by_name(db_session: Session, role_name: str) -> Role | None:
    return db_session.query(Role).filter(Role.name == role_name).one_or_none()


def _is_active_admin(user: User | None) -> bool:
    return bool(user and user.is_active and user.role and user.role.name == "admin")


def _lock_active_admin_rows(db_session: Session) -> list[User]:
    return (
        db_session.query(User)
        .join(Role, User.role_id == Role.role_id)
        .filter(Role.name == "admin", User.is_active.is_(True))
        .with_for_update()
        .all()
    )


def _assert_not_last_active_admin_lockout(
    db_session: Session,
    *,
    target_user: User,
    remove_admin_privileges: bool,
) -> None:
    if not remove_admin_privileges:
        return
    if not _is_active_admin(target_user):
        return
    active_admins = _lock_active_admin_rows(db_session)
    if len(active_admins) <= 1:
        raise HTTPException(status_code=400, detail=LAST_ACTIVE_ADMIN_ERROR)


def _add_user_admin_action_audit_log(
    db_session: Session,
    *,
    actor: User | None,
    target_user: User,
    action: str,
    old_role: str | None,
    new_role: str | None,
    old_is_active: bool,
    new_is_active: bool,
) -> None:
    changed_at = datetime.utcnow().isoformat()
    details = (
        f"changed_by={actor.username if actor else '-'};"
        f"target_user_id={target_user.user_id};"
        f"target_username={target_user.username};"
        f"old_role={old_role or '-'};"
        f"new_role={new_role or '-'};"
        f"old_is_active={old_is_active};"
        f"new_is_active={new_is_active};"
        f"changed_at={changed_at}"
    )
    db_session.add(
        AuditLog(
            user_id=actor.user_id if actor else None,
            username=actor.username if actor else None,
            role_name=actor.role.name if actor and actor.role else None,
            action=action,
            entity_type="user",
            entity_id=str(target_user.user_id),
            details=details,
        )
    )


def _document_label_for_notification(document: Document) -> str:
    label = str(document.document_type or "").strip()
    return label if label else "документ"


def _certificate_label_for_notification(certificate: Certificate) -> str:
    raw = str(certificate.certificate_name_raw or "").strip()
    ctype = str(certificate.certificate_type or "").strip()
    return raw or ctype or "сертификат"


def _notification_exists(
    db_session: Session,
    *,
    candidate_id: int,
    message: str,
    document_id: int | None = None,
    certificate_id: int | None = None,
) -> bool:
    query = db_session.query(Notification).filter(
        Notification.candidate_id == candidate_id,
        Notification.message == message,
        Notification.sent.is_(False),
    )
    if document_id is not None:
        query = query.filter(Notification.document_id == document_id, Notification.certificate_id.is_(None))
    elif certificate_id is not None:
        query = query.filter(Notification.certificate_id == certificate_id, Notification.document_id.is_(None))
    else:
        query = query.filter(Notification.document_id.is_(None), Notification.certificate_id.is_(None))
    return query.first() is not None


def _create_notification_if_missing(
    db_session: Session,
    *,
    candidate_id: int,
    message: str,
    document_id: int | None = None,
    certificate_id: int | None = None,
) -> None:
    if _notification_exists(
        db_session,
        candidate_id=candidate_id,
        message=message,
        document_id=document_id,
        certificate_id=certificate_id,
    ):
        return
    db_session.add(
        Notification(
            candidate_id=candidate_id,
            document_id=document_id,
            certificate_id=certificate_id,
            message=message,
            sent=False,
        )
    )


def _collect_active_notification_keys_for_candidate(
    candidate: Candidate,
    *,
    today: date,
    warning_limit: date,
    db_session: Session,
) -> set[tuple[int, int | None, int | None, str]]:
    active_notification_keys: set[tuple[int, int | None, int | None, str]] = set()
    attachment_descriptions = {
        item.description
        for item in candidate.attachments
        if isinstance(item.description, str) and item.description
    }

    for document in candidate.documents:
        doc_l = _document_label_for_notification(document)
        if document.date_of_expiry:
            days_left = (document.date_of_expiry - today).days
            if days_left < 0:
                message = f"Документ просрочен: {doc_l}."
                active_notification_keys.add(
                    (candidate.candidate_id, document.document_id, None, message)
                )
                _create_notification_if_missing(
                    db_session,
                    candidate_id=candidate.candidate_id,
                    message=message,
                    document_id=document.document_id,
                )
            elif document.date_of_expiry < warning_limit:
                message = f"Документ скоро истечёт (ещё {days_left} дн.): {doc_l}."
                active_notification_keys.add(
                    (candidate.candidate_id, document.document_id, None, message)
                )
                _create_notification_if_missing(
                    db_session,
                    candidate_id=candidate.candidate_id,
                    message=message,
                    document_id=document.document_id,
                )

        expected_scan = f"document:{document.document_id}"
        if expected_scan not in attachment_descriptions:
            message = f"Нет скана документа: {doc_l}."
            active_notification_keys.add((candidate.candidate_id, document.document_id, None, message))
            _create_notification_if_missing(
                db_session,
                candidate_id=candidate.candidate_id,
                message=message,
                document_id=document.document_id,
            )

    for certificate in candidate.certificates:
        cert_l = _certificate_label_for_notification(certificate)
        if certificate.expiry_date:
            days_left = (certificate.expiry_date - today).days
            if days_left < 0:
                message = f"Сертификат просрочен: {cert_l}."
                active_notification_keys.add(
                    (candidate.candidate_id, None, certificate.certificate_id, message)
                )
                _create_notification_if_missing(
                    db_session,
                    candidate_id=candidate.candidate_id,
                    message=message,
                    certificate_id=certificate.certificate_id,
                )
            elif certificate.expiry_date < warning_limit:
                message = f"Сертификат скоро истечёт (ещё {days_left} дн.): {cert_l}."
                active_notification_keys.add(
                    (candidate.candidate_id, None, certificate.certificate_id, message)
                )
                _create_notification_if_missing(
                    db_session,
                    candidate_id=candidate.candidate_id,
                    message=message,
                    certificate_id=certificate.certificate_id,
                )

        expected_scan = f"certificate:{certificate.certificate_id}"
        if expected_scan not in attachment_descriptions:
            message = f"Нет скана сертификата: {cert_l}."
            active_notification_keys.add(
                (candidate.candidate_id, None, certificate.certificate_id, message)
            )
            _create_notification_if_missing(
                db_session,
                candidate_id=candidate.candidate_id,
                message=message,
                certificate_id=certificate.certificate_id,
            )

    return active_notification_keys


def _sync_notifications(db_session: Session, *, only_candidate_id: int | None = None) -> None:
    today = date.today()
    warning_limit = today + timedelta(days=240)
    active_notification_keys: set[tuple[int, int | None, int | None, str]] = set()

    if only_candidate_id is not None:
        candidate = (
            db_session.query(Candidate)
            .options(
                selectinload(Candidate.documents),
                selectinload(Candidate.certificates),
                selectinload(Candidate.attachments),
            )
            .filter(Candidate.candidate_id == only_candidate_id)
            .first()
        )
        candidates = [candidate] if candidate else []
    else:
        candidates = db_session.query(Candidate).all()

    for candidate in candidates:
        active_notification_keys.update(
            _collect_active_notification_keys_for_candidate(
                candidate,
                today=today,
                warning_limit=warning_limit,
                db_session=db_session,
            )
        )

    pending_query = db_session.query(Notification).filter(Notification.sent.is_(False))
    if only_candidate_id is not None:
        pending_query = pending_query.filter(Notification.candidate_id == only_candidate_id)
    for notification in pending_query.all():
        cid = getattr(notification, "certificate_id", None)
        key = (notification.candidate_id, notification.document_id, cid, notification.message)
        if key not in active_notification_keys:
            notification.sent = True

    db_session.commit()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db_session: Session = Depends(get_db_session),
) -> User:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required")

    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    user = db_session.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User is inactive or not found")
    return user


def require_roles(*roles: str):
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        role_name = current_user.role.name if current_user.role else None
        if role_name not in roles:
            raise HTTPException(status_code=403, detail="Not enough permissions")
        return current_user

    return role_checker


def require_admin(current_user: User = Depends(require_roles("admin"))) -> User:
    return current_user


require_crm_user = require_roles("admin", "recruiter", "viewer")


@app.post("/import/text/preview")
def import_text_preview(
    payload: ManualTextImportRequest,
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    try:
        parsed = _parse_manual_text_to_payload(payload.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"parsed": parsed}


@app.post("/import/text/create")
def import_text_create(
    payload: ManualTextImportRequest,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    try:
        parsed = _parse_manual_text_to_payload(payload.text)
        personal = parsed.get("personal_data", {}) or {}
        candidate_payload = _coerce_model_payload(Candidate, personal, exclude={"candidate_id", "created_at", "updated_at"})
        candidate = Candidate(**candidate_payload)
        if not candidate.source_form_type:
            candidate.source_form_type = "manual_text"
        if not candidate.record_status:
            candidate.record_status = "active"
        db_session.add(candidate)
        db_session.flush()
        _save_related_records_for_candidate(db_session, candidate, parsed)
        db_session.commit()
        db_session.refresh(candidate)
        _write_audit_log(
            db_session,
            _current_user,
            action="candidate.create_manual_text",
            entity_type="candidate",
            entity_id=candidate.candidate_id,
        )
        return {"candidate_id": candidate.candidate_id, "parsed": parsed}
    except HTTPException:
        raise
    except Exception as exc:
        db_session.rollback()
        logger.exception("Manual text import failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to import text and save candidate") from exc

# Mitigation of brute-force login attempts (in-process only; add proxy-level limits for multi-replica).
_LOGIN_THROTTLE_LOCK = threading.Lock()
_LOGIN_FAIL_COUNT: dict[tuple[str, str], int] = {}
_LOGIN_LOCKOUT_UNTIL: dict[tuple[str, str], float] = {}
LOGIN_MAX_FAILED_ATTEMPTS = max(1, int(os.getenv("LOGIN_MAX_FAILED_ATTEMPTS", "8")))
LOGIN_LOCKOUT_SECONDS = max(30, int(os.getenv("LOGIN_LOCKOUT_SECONDS", "900")))
LOGIN_TOO_MANY_ATTEMPTS_DETAIL = (
    "Слишком много неудачных попыток входа. Повторите позже или обратитесь к администратору."
)


def _login_throttle_client_identity(request: Request) -> str:
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        return x_forwarded_for.split(",", 1)[0].strip() or "unknown"
    client = getattr(request, "client", None)
    return getattr(client, "host", None) or "unknown"


def _login_throttle_key(request: Request, username: str) -> tuple[str, str]:
    uname = (username or "").strip().lower()
    return (_login_throttle_client_identity(request), uname)


def _login_throttle_apply_expired_unlocks(now: float) -> None:
    expired = [key for key, until in _LOGIN_LOCKOUT_UNTIL.items() if until is not None and now >= until]
    for key in expired:
        _LOGIN_LOCKOUT_UNTIL.pop(key, None)
        _LOGIN_FAIL_COUNT.pop(key, None)


def login_throttle_reset_for_testing() -> None:
    """Сбрасывает счётчики блокировки входа (только для тестов)."""
    with _LOGIN_THROTTLE_LOCK:
        _LOGIN_FAIL_COUNT.clear()
        _LOGIN_LOCKOUT_UNTIL.clear()


@app.post("/test/reset-login-throttle", include_in_schema=False)
def test_reset_login_throttle_endpoint() -> dict[str, bool]:
    """Сброс блокировки входа для E2E/pytest (не для production)."""
    login_throttle_reset_for_testing()
    return {"ok": True}


def _login_throttle_check_allowed(request: Request, username: str) -> None:
    key = _login_throttle_key(request, username)
    with _LOGIN_THROTTLE_LOCK:
        now = time.time()
        _login_throttle_apply_expired_unlocks(now)
        until = _LOGIN_LOCKOUT_UNTIL.get(key)
        if until is not None and now < until:
            seconds_left = max(1, int(until - now))
            raise HTTPException(
                status_code=429,
                detail=LOGIN_TOO_MANY_ATTEMPTS_DETAIL,
                headers={"Retry-After": str(seconds_left)},
            )


def _login_throttle_record_failure(request: Request, username: str) -> None:
    key = _login_throttle_key(request, username)
    with _LOGIN_THROTTLE_LOCK:
        count = _LOGIN_FAIL_COUNT.get(key, 0) + 1
        _LOGIN_FAIL_COUNT[key] = count
        if count >= LOGIN_MAX_FAILED_ATTEMPTS:
            _LOGIN_LOCKOUT_UNTIL[key] = time.time() + LOGIN_LOCKOUT_SECONDS
            _LOGIN_FAIL_COUNT.pop(key, None)


def _login_throttle_clear_success(request: Request, username: str) -> None:
    key = _login_throttle_key(request, username)
    with _LOGIN_THROTTLE_LOCK:
        _LOGIN_FAIL_COUNT.pop(key, None)
        _LOGIN_LOCKOUT_UNTIL.pop(key, None)


def _ensure_default_auth_data(session: Session) -> None:
    role_names = {"admin": "Full access", "recruiter": "Can manage records", "viewer": "Read only"}
    for name, description in role_names.items():
        if not session.query(Role).filter(Role.name == name).one_or_none():
            session.add(Role(name=name, description=description))
    session.flush()

    default_admin_username = os.getenv("DEFAULT_ADMIN_USERNAME", "admin").strip() or "admin"
    default_admin_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")
    default_admin_full_name = os.getenv("DEFAULT_ADMIN_FULL_NAME", "Default Admin").strip() or "Default Admin"

    admin_role = session.query(Role).filter(Role.name == "admin").one()
    admin_user = session.query(User).filter(User.username == default_admin_username).one_or_none()
    if not admin_user:
        session.add(
            User(
                username=default_admin_username,
                password_hash=pwd_context.hash(default_admin_password),
                full_name=default_admin_full_name,
                role_id=admin_role.role_id,
                is_active=True,
            )
        )
    session.commit()


@app.post("/auth/login", response_model=LoginResponse)
def login(
    request: Request,
    payload: LoginRequest,
    db_session: Session = Depends(get_db_session),
) -> LoginResponse:
    _login_throttle_check_allowed(request, payload.username)
    user = db_session.query(User).filter(User.username == payload.username).one_or_none()
    if not user or not _verify_password(payload.password, user.password_hash):
        _login_throttle_record_failure(request, payload.username)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not user.is_active:
        _login_throttle_record_failure(request, payload.username)
        raise HTTPException(status_code=403, detail="User is inactive")

    _login_throttle_clear_success(request, payload.username)
    token = _create_access_token(user)
    return LoginResponse(access_token=token, user=_serialize_user(user))


@app.post("/auth/refresh", response_model=LoginResponse)
def refresh_access_token(current_user: User = Depends(get_current_user)) -> LoginResponse:
    token = _create_access_token(current_user)
    return LoginResponse(access_token=token, user=_serialize_user(current_user))


@app.post("/auth/register")
def register_user(
    payload: RegisterRequest,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")

    if db_session.query(User).filter(User.username == username).one_or_none():
        raise HTTPException(status_code=409, detail="User with this username already exists")

    role_name = payload.role.strip().lower()
    role = db_session.query(Role).filter(Role.name == role_name).one_or_none()
    if not role:
        raise HTTPException(status_code=400, detail=f"Unknown role: {payload.role}")

    user = User(
        username=username,
        password_hash=pwd_context.hash(payload.password),
        full_name=payload.full_name,
        role_id=role.role_id,
        is_active=payload.is_active,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    _write_audit_log(
        db_session,
        _current_user,
        action="user.create",
        entity_type="user",
        entity_id=user.user_id,
        details=f"username={user.username};role={role_name}",
    )
    return {"user": _serialize_user(user)}


@app.get("/auth/users")
def list_users(
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    users = db_session.query(User).order_by(User.user_id.asc()).all()
    return {"items": [_serialize_user(item) for item in users]}


@app.put("/auth/users/{user_id}/role")
def update_user_role(
    user_id: int,
    payload: UpdateUserRoleRequest,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    user = db_session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    role_name = payload.role.strip().lower()
    role = _get_role_by_name(db_session, role_name)
    if not role:
        raise HTTPException(status_code=400, detail=f"Unknown role: {payload.role}")

    old_role = user.role.name if user.role else None
    old_is_active = bool(user.is_active)
    if user.user_id == _current_user.user_id and _is_active_admin(_current_user):
        raise HTTPException(status_code=400, detail=SELF_ACTIVE_ADMIN_ROLE_CHANGE_ERROR)
    remove_admin_privileges = old_role == "admin" and role_name != "admin"
    _assert_not_last_active_admin_lockout(
        db_session,
        target_user=user,
        remove_admin_privileges=remove_admin_privileges,
    )
    user.role_id = role.role_id
    _add_user_admin_action_audit_log(
        db_session,
        actor=_current_user,
        target_user=user,
        action="user.role_update",
        old_role=old_role,
        new_role=role_name,
        old_is_active=old_is_active,
        new_is_active=old_is_active,
    )
    db_session.commit()
    db_session.refresh(user)
    return {"user": _serialize_user(user)}


@app.put("/auth/users/{user_id}/password")
def update_user_password(
    user_id: int,
    payload: UpdateUserPasswordRequest,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    new_password = payload.password.strip()
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    user = db_session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    user.password_hash = pwd_context.hash(new_password)
    db_session.commit()
    db_session.refresh(user)
    _write_audit_log(
        db_session,
        _current_user,
        action="user.password_update",
        entity_type="user",
        entity_id=user.user_id,
        details="password_changed",
    )
    return {"user": _serialize_user(user)}


@app.delete("/auth/users/{user_id}")
def delete_user(
    user_id: int,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    user = db_session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    old_role = user.role.name if user.role else None
    old_is_active = bool(user.is_active)
    remove_admin_privileges = old_role == "admin" and old_is_active
    _assert_not_last_active_admin_lockout(
        db_session,
        target_user=user,
        remove_admin_privileges=remove_admin_privileges,
    )
    if user_id == _current_user.user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    deleted_username = user.username
    _add_user_admin_action_audit_log(
        db_session,
        actor=_current_user,
        target_user=user,
        action="user.delete",
        old_role=old_role,
        new_role=None,
        old_is_active=old_is_active,
        new_is_active=False,
    )
    db_session.delete(user)
    db_session.commit()
    return {"status": "ok", "user_id": user_id, "username": deleted_username}


@app.put("/auth/users/{user_id}/active")
def update_user_active(
    user_id: int,
    payload: UpdateUserActiveRequest,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    user = db_session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    old_role = user.role.name if user.role else None
    old_is_active = bool(user.is_active)
    new_is_active = bool(payload.is_active)
    remove_admin_privileges = old_role == "admin" and old_is_active and not new_is_active
    _assert_not_last_active_admin_lockout(
        db_session,
        target_user=user,
        remove_admin_privileges=remove_admin_privileges,
    )

    user.is_active = new_is_active
    _add_user_admin_action_audit_log(
        db_session,
        actor=_current_user,
        target_user=user,
        action="user.active_update",
        old_role=old_role,
        new_role=old_role,
        old_is_active=old_is_active,
        new_is_active=new_is_active,
    )
    db_session.commit()
    db_session.refresh(user)
    return {"user": _serialize_user(user)}


@app.get("/notifications")
def list_notifications(
    sent: bool | None = None,
    candidate_id: int | None = None,
    limit: int | None = None,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter", "viewer")),
) -> dict[str, Any]:
    if candidate_id is not None:
        _sync_notifications(db_session, only_candidate_id=candidate_id)
    elif limit is None:
        _sync_notifications(db_session)
    query = db_session.query(Notification).order_by(Notification.created_at.desc())
    if candidate_id is not None:
        query = query.filter(Notification.candidate_id == candidate_id)
    if sent is not None:
        query = query.filter(Notification.sent == sent)
    if limit is not None:
        if limit < 1:
            raise HTTPException(status_code=400, detail="limit must be >= 1")
        query = query.limit(limit)
    items = [_model_to_dict(item) for item in query.all()]
    return {"items": items}


@app.put("/notifications/{notification_id}")
def update_notification(
    notification_id: int,
    payload: NotificationSentUpdate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    notification = db_session.get(Notification, notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail=f"Notification {notification_id} not found")
    notification.sent = payload.sent
    db_session.commit()
    db_session.refresh(notification)
    _write_audit_log(
        db_session,
        _current_user,
        action="notification.update",
        entity_type="notification",
        entity_id=notification_id,
        details=f"sent={payload.sent}",
    )
    return {"notification": _model_to_dict(notification)}


@app.get("/dashboard/summary")
def dashboard_summary(
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter", "viewer")),
) -> dict[str, Any]:
    candidates_count = int(db_session.query(func.count(Candidate.candidate_id)).scalar() or 0)
    top_actor = (
        db_session.query(
            AuditLog.user_id.label("user_id"),
            AuditLog.username.label("username"),
            func.count(AuditLog.log_id).label("actions_count"),
        )
        .group_by(AuditLog.user_id, AuditLog.username)
        .order_by(func.count(AuditLog.log_id).desc())
        .first()
    )

    most_active_user: dict[str, Any] | None = None
    if top_actor is not None:
        most_active_user = {
            "user_id": top_actor.user_id,
            "username": top_actor.username,
            "actions_count": int(top_actor.actions_count or 0),
        }

    return {
        "candidates_count": candidates_count,
        "most_active_user": most_active_user,
    }


@app.get("/audit-logs")
def list_audit_logs(
    user_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    last_days: int | None = None,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    query = db_session.query(AuditLog).order_by(AuditLog.created_at.desc())
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if start_date is not None:
        query = query.filter(AuditLog.created_at >= datetime.combine(start_date, datetime.min.time()))
    if end_date is not None:
        query = query.filter(AuditLog.created_at <= datetime.combine(end_date, datetime.max.time()))
    if last_days is not None and last_days > 0:
        threshold = datetime.utcnow() - timedelta(days=last_days)
        query = query.filter(AuditLog.created_at >= threshold)
    items = [_model_to_dict(item) for item in query.limit(1000).all()]
    return {"items": items}


@app.get("/templates-manager")
def list_templates_manager(
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter", "viewer")),
) -> dict[str, Any]:
    root = _get_or_create_templates_root(db_session)
    folders = db_session.query(TemplateFolder).order_by(TemplateFolder.parent_id.asc(), TemplateFolder.name.asc()).all()
    files = db_session.query(TemplateFile).order_by(TemplateFile.updated_at.desc()).all()
    return {
        "root_folder_id": root.folder_id,
        "folders": [_serialize_template_folder(folder) for folder in folders],
        "files": [_serialize_template_file(item) for item in files],
    }


@app.post("/templates-manager/folders")
def create_template_folder(
    payload: TemplateFolderCreate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    root = _get_or_create_templates_root(db_session)
    parent_id = payload.parent_id if payload.parent_id is not None else root.folder_id
    parent = db_session.get(TemplateFolder, parent_id)
    if not parent:
        raise HTTPException(status_code=404, detail=f"Parent folder {parent_id} not found")
    folder = TemplateFolder(name=payload.name.strip(), parent_id=parent_id)
    db_session.add(folder)
    db_session.commit()
    db_session.refresh(folder)
    _write_audit_log(
        db_session,
        _current_user,
        action="template_folder.create",
        entity_type="template_folder",
        entity_id=folder.folder_id,
        details=f"name={folder.name};parent_id={folder.parent_id}",
    )
    return {"folder": _serialize_template_folder(folder)}


@app.put("/templates-manager/folders/{folder_id}")
def rename_template_folder(
    folder_id: int,
    payload: TemplateFolderUpdate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    folder = db_session.get(TemplateFolder, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail=f"Folder {folder_id} not found")
    if folder.parent_id is None:
        raise HTTPException(status_code=400, detail="Root folder cannot be renamed")
    folder.name = payload.name.strip()
    db_session.commit()
    db_session.refresh(folder)
    _write_audit_log(
        db_session,
        _current_user,
        action="template_folder.rename",
        entity_type="template_folder",
        entity_id=folder.folder_id,
        details=f"name={folder.name}",
    )
    return {"folder": _serialize_template_folder(folder)}


@app.delete("/templates-manager/folders/{folder_id}")
def delete_template_folder(
    folder_id: int,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    folder = db_session.get(TemplateFolder, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail=f"Folder {folder_id} not found")
    if folder.parent_id is None:
        raise HTTPException(status_code=400, detail="Root folder cannot be deleted")

    descendant_ids = _collect_folder_descendants(db_session, folder_id)
    files = db_session.query(TemplateFile).filter(TemplateFile.folder_id.in_(descendant_ids)).all()
    for item in files:
        target_path = TEMPLATES_MANAGER_DIR / item.relative_path
        target_path.unlink(missing_ok=True)

    db_session.delete(folder)
    db_session.commit()
    _write_audit_log(
        db_session,
        _current_user,
        action="template_folder.delete",
        entity_type="template_folder",
        entity_id=folder_id,
    )
    return {"status": "ok", "deleted_folder_id": folder_id}


@app.post("/templates-manager/files")
async def upload_template_file(
    folder_id: int = Form(...),
    file: UploadFile = File(...),
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    folder = db_session.get(TemplateFolder, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail=f"Folder {folder_id} not found")

    upload_basename = Path(str(file.filename or "").strip().replace("\\", "/")).name.strip()
    if not _is_allowed_template_manager_filename(upload_basename):
        raise HTTPException(status_code=400, detail=INVALID_TEMPLATE_FILE_TYPE_MESSAGE)

    content = await _read_upload_limited(file, MAX_TEMPLATE_MANAGER_UPLOAD_BYTES)
    if not content:
        raise HTTPException(status_code=400, detail="Bad Request: uploaded file is empty")

    suffix = Path(upload_basename).suffix or ".bin"
    stored_name = f"{uuid4().hex}{suffix}"
    target_path = TEMPLATES_MANAGER_DIR / stored_name
    target_path.write_bytes(content)

    record = TemplateFile(
        folder_id=folder_id,
        file_name=upload_basename,
        file_type=(str(file.content_type).strip()[:50] if file.content_type else None),
        stored_name=stored_name,
        relative_path=stored_name,
        file_size_bytes=len(content),
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    _write_audit_log(
        db_session,
        _current_user,
        action="template_file.upload",
        entity_type="template_file",
        entity_id=record.template_file_id,
        details=f"name={record.file_name};folder_id={record.folder_id}",
    )
    return {"file": _serialize_template_file(record)}


@app.get("/templates-manager/files/{template_file_id}/download")
def download_template_file(
    template_file_id: int,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> FileResponse:
    record = db_session.get(TemplateFile, template_file_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Template file {template_file_id} not found")

    target_path = TEMPLATES_MANAGER_DIR / record.relative_path
    if not target_path.exists():
        raise HTTPException(status_code=404, detail=f"Template binary not found for file {template_file_id}")

    download_name = record.file_name or target_path.name
    cd = _attachment_content_disposition(download_name)
    return FileResponse(
        path=str(target_path),
        media_type=record.file_type or "application/octet-stream",
        headers=_nosniff_headers({"Content-Disposition": cd}),
    )


@app.put("/templates-manager/files/{template_file_id}")
def rename_template_file(
    template_file_id: int,
    payload: TemplateFileUpdate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    record = db_session.get(TemplateFile, template_file_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Template file {template_file_id} not found")
    new_name = Path(str(payload.file_name or "").strip().replace("\\", "/")).name.strip()
    if not _is_allowed_template_manager_filename(new_name):
        raise HTTPException(status_code=400, detail=INVALID_TEMPLATE_FILE_TYPE_MESSAGE)
    record.file_name = new_name
    db_session.commit()
    db_session.refresh(record)
    _write_audit_log(
        db_session,
        _current_user,
        action="template_file.rename",
        entity_type="template_file",
        entity_id=record.template_file_id,
        details=f"name={record.file_name}",
    )
    return {"file": _serialize_template_file(record)}


@app.delete("/templates-manager/files/{template_file_id}")
def delete_template_file(
    template_file_id: int,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    record = db_session.get(TemplateFile, template_file_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Template file {template_file_id} not found")
    target_path = TEMPLATES_MANAGER_DIR / record.relative_path
    db_session.delete(record)
    db_session.commit()
    target_path.unlink(missing_ok=True)
    _write_audit_log(
        db_session,
        _current_user,
        action="template_file.delete",
        entity_type="template_file",
        entity_id=template_file_id,
    )
    return {"status": "ok", "deleted_template_file_id": template_file_id}


@app.get("/companies-manager")
def list_companies_manager(
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter", "viewer")),
) -> dict[str, Any]:
    try:
        root = _get_or_create_companies_root(db_session)
        _ensure_initial_candidate_companies(db_session)
    except Exception as exc:
        if "company_folders" in str(exc) or "no such table" in str(exc).lower():
            from models.db import _ensure_company_vessel_tables

            _ensure_company_vessel_tables()
            root = _get_or_create_companies_root(db_session)
            _ensure_initial_candidate_companies(db_session)
        else:
            raise
    folders = (
        db_session.query(CompanyFolder)
        .order_by(CompanyFolder.parent_id.asc(), CompanyFolder.name.asc())
        .all()
    )
    companies = db_session.query(Company).order_by(Company.name.asc()).all()
    vessels = (
        db_session.query(Vessel, Company)
        .join(Company, Vessel.company_id == Company.company_id)
        .order_by(Vessel.name.asc())
        .all()
    )
    company_by_id = {company.company_id: company for company in companies}
    payload = {
        "root_folder_id": root.folder_id,
        "folders": [_serialize_company_folder(folder) for folder in folders],
        "companies": [_serialize_company(company) for company in companies],
        "vessels": [
            _serialize_vessel(vessel, company_by_id[vessel.company_id].slug)
            for vessel, company in vessels
            if vessel.company_id in company_by_id
        ],
    }
    return payload


@app.post("/companies-manager/folders")
def create_company_folder(
    payload: CompanyFolderCreate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    root = _get_or_create_companies_root(db_session)
    parent_id = payload.parent_id if payload.parent_id is not None else root.folder_id
    parent = db_session.get(CompanyFolder, parent_id)
    if not parent:
        raise HTTPException(status_code=404, detail=f"Parent folder {parent_id} not found")
    folder = CompanyFolder(name=payload.name.strip(), parent_id=parent_id)
    db_session.add(folder)
    db_session.commit()
    db_session.refresh(folder)
    _write_audit_log(
        db_session,
        _current_user,
        action="company_folder.create",
        entity_type="company_folder",
        entity_id=folder.folder_id,
        details=f"name={folder.name};parent_id={folder.parent_id}",
    )
    return {"folder": _serialize_company_folder(folder)}


@app.put("/companies-manager/folders/{folder_id}")
def rename_company_folder(
    folder_id: int,
    payload: CompanyFolderUpdate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    folder = db_session.get(CompanyFolder, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail=f"Folder {folder_id} not found")
    if folder.parent_id is None:
        raise HTTPException(status_code=400, detail="Root folder cannot be renamed")
    folder.name = payload.name.strip()
    db_session.commit()
    db_session.refresh(folder)
    _write_audit_log(
        db_session,
        _current_user,
        action="company_folder.rename",
        entity_type="company_folder",
        entity_id=folder.folder_id,
        details=f"name={folder.name}",
    )
    return {"folder": _serialize_company_folder(folder)}


@app.delete("/companies-manager/folders/{folder_id}")
def delete_company_folder(
    folder_id: int,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    folder = db_session.get(CompanyFolder, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail=f"Folder {folder_id} not found")
    if folder.parent_id is None:
        raise HTTPException(status_code=400, detail="Root folder cannot be deleted")

    descendant_ids = _collect_company_folder_descendants(db_session, folder_id)
    companies_count = db_session.query(Company).filter(Company.folder_id.in_(descendant_ids)).count()
    if companies_count:
        raise HTTPException(
            status_code=400,
            detail="Folder contains companies. Move or delete companies before deleting the folder.",
        )

    db_session.delete(folder)
    db_session.commit()
    _write_audit_log(
        db_session,
        _current_user,
        action="company_folder.delete",
        entity_type="company_folder",
        entity_id=folder_id,
    )
    return {"status": "ok", "deleted_folder_id": folder_id}


@app.post("/companies-manager/companies")
def create_company(
    payload: CompanyCreate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    folder = db_session.get(CompanyFolder, payload.folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail=f"Folder {payload.folder_id} not found")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Company name is required")
    base_slug = _slugify_entity_name(name)
    slug = _unique_company_slug(db_session, base_slug)
    company = Company(folder_id=payload.folder_id, name=name, slug=slug)
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)
    _write_audit_log(
        db_session,
        _current_user,
        action="company.create",
        entity_type="company",
        entity_id=company.company_id,
        details=f"name={company.name};slug={company.slug}",
    )
    return {"company": _serialize_company(company)}


@app.put("/companies-manager/companies/{company_id}")
def update_company(
    company_id: int,
    payload: CompanyUpdate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    company = db_session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Company name is required")
    company.name = name
    base_slug = _slugify_entity_name(name)
    company.slug = _unique_company_slug(db_session, base_slug, exclude_company_id=company.company_id)
    db_session.commit()
    db_session.refresh(company)
    _write_audit_log(
        db_session,
        _current_user,
        action="company.update",
        entity_type="company",
        entity_id=company.company_id,
        details=f"name={company.name};slug={company.slug}",
    )
    return {"company": _serialize_company(company)}


@app.delete("/companies-manager/companies/{company_id}")
def delete_company(
    company_id: int,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    company = db_session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")
    db_session.delete(company)
    db_session.commit()
    _write_audit_log(
        db_session,
        _current_user,
        action="company.delete",
        entity_type="company",
        entity_id=company_id,
    )
    return {"status": "ok", "deleted_company_id": company_id}


@app.post("/companies-manager/vessels")
def create_vessel(
    payload: VesselCreate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    company = db_session.get(Company, payload.company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {payload.company_id} not found")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Vessel name is required")
    base_slug = _slugify_entity_name(name)
    slug = _unique_vessel_slug(db_session, company.company_id, base_slug)
    vessel = Vessel(company_id=company.company_id, name=name, slug=slug)
    _apply_vessel_fields(vessel, payload)
    db_session.add(vessel)
    db_session.commit()
    db_session.refresh(vessel)
    _write_audit_log(
        db_session,
        _current_user,
        action="vessel.create",
        entity_type="vessel",
        entity_id=vessel.vessel_id,
        details=f"name={vessel.name};company_id={vessel.company_id}",
    )
    return {"vessel": _serialize_vessel(vessel, company.slug)}


@app.put("/companies-manager/vessels/{vessel_id}")
def update_vessel(
    vessel_id: int,
    payload: VesselUpdate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    vessel = db_session.get(Vessel, vessel_id)
    if not vessel:
        raise HTTPException(status_code=404, detail=f"Vessel {vessel_id} not found")
    company = db_session.get(Company, vessel.company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {vessel.company_id} not found")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Vessel name is required")
    vessel.name = name
    base_slug = _slugify_entity_name(name)
    vessel.slug = _unique_vessel_slug(
        db_session,
        company.company_id,
        base_slug,
        exclude_vessel_id=vessel.vessel_id,
    )
    _apply_vessel_fields(vessel, payload)
    db_session.commit()
    db_session.refresh(vessel)
    _write_audit_log(
        db_session,
        _current_user,
        action="vessel.update",
        entity_type="vessel",
        entity_id=vessel.vessel_id,
        details=f"name={vessel.name};slug={vessel.slug}",
    )
    return {"vessel": _serialize_vessel(vessel, company.slug)}


@app.delete("/companies-manager/vessels/{vessel_id}")
def delete_vessel(
    vessel_id: int,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    vessel = db_session.get(Vessel, vessel_id)
    if not vessel:
        raise HTTPException(status_code=404, detail=f"Vessel {vessel_id} not found")
    db_session.delete(vessel)
    db_session.commit()
    _write_audit_log(
        db_session,
        _current_user,
        action="vessel.delete",
        entity_type="vessel",
        entity_id=vessel_id,
    )
    return {"status": "ok", "deleted_vessel_id": vessel_id}


@app.post("/companies-manager/import")
async def import_companies_manager_xlsx(
    file: UploadFile = File(...),
    folder_id: int | None = Form(None),
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    from app.companies_xlsx_import import CompaniesXlsxImportError, import_companies_vessels_from_bytes

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".xlsx", ".xls"}:
        raise HTTPException(
            status_code=400,
            detail="Допустимы только файлы Excel (.xlsx, .xls)",
        )

    try:
        content = await _read_upload_limited(file, MAX_COMPANIES_XLSX_UPLOAD_BYTES)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Не удалось прочитать файл: {exc}") from exc

    target_folder_id = folder_id
    if target_folder_id is None:
        target_folder_id = _get_or_create_companies_root(db_session).folder_id
    elif db_session.get(CompanyFolder, target_folder_id) is None:
        raise HTTPException(status_code=404, detail=f"Folder {target_folder_id} not found")

    try:
        stats = import_companies_vessels_from_bytes(
            db_session,
            content,
            folder_id=target_folder_id,
        )
    except CompaniesXlsxImportError as exc:
        db_session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db_session.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка импорта: {exc}") from exc

    _write_audit_log(
        db_session,
        _current_user,
        action="company.import_xlsx",
        entity_type="company_folder",
        entity_id=target_folder_id,
        details=(
            f"file={file.filename or ''};"
            f"created={stats.get('companies_created', 0)};"
            f"vessels={stats.get('vessels_created', 0)}"
        ),
    )
    return {"status": "ok", "folder_id": target_folder_id, "stats": stats}


@app.get("/companies-manager/companies/{company_id}/salary-ranks")
def list_company_salary_ranks(
    company_id: int,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter", "viewer")),
) -> dict[str, Any]:
    company = db_session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")
    return {"company_id": company_id, "ranks": list_ranks_for_company(db_session, company_id)}


@app.get("/companies-manager/companies/{company_id}/salary-templates")
def list_company_salary_templates(
    company_id: int,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter", "viewer")),
) -> dict[str, Any]:
    company = db_session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")
    rows = (
        db_session.query(SalaryComponentTemplate)
        .filter(SalaryComponentTemplate.company_id == company_id)
        .order_by(SalaryComponentTemplate.rank.asc())
        .all()
    )
    return {"items": [_serialize_salary_template(row) for row in rows]}


@app.post("/companies-manager/salary-templates")
def create_salary_template(
    payload: SalaryComponentTemplateCreate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    company = db_session.get(Company, payload.company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {payload.company_id} not found")
    rank = payload.rank.strip()
    if not rank:
        raise HTTPException(status_code=400, detail="Rank is required")
    existing = (
        db_session.query(SalaryComponentTemplate)
        .filter(SalaryComponentTemplate.company_id == payload.company_id, SalaryComponentTemplate.rank == rank)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail=f"Salary template for rank '{rank}' already exists")
    row = SalaryComponentTemplate(
        company_id=payload.company_id,
        rank=rank,
        basic_monthly_wage=payload.basic_monthly_wage,
        monthly_overtime=payload.monthly_overtime,
        overtime_rate=payload.overtime_rate,
        sepf=payload.sepf,
        imtf=payload.imtf,
        leave=payload.leave,
        leave_sub=payload.leave_sub,
        various_extra_overtime=payload.various_extra_overtime,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    _write_audit_log(
        db_session,
        _current_user,
        action="salary_template.create",
        entity_type="salary_template",
        entity_id=row.template_id,
        details=f"company_id={row.company_id};rank={row.rank}",
    )
    return {"template": _serialize_salary_template(row)}


@app.put("/companies-manager/salary-templates/{template_id}")
def update_salary_template(
    template_id: int,
    payload: SalaryComponentTemplateUpdate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    row = db_session.get(SalaryComponentTemplate, template_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Salary template {template_id} not found")
    incoming = payload.model_dump(exclude_unset=True)
    if "rank" in incoming:
        new_rank = str(incoming["rank"] or "").strip()
        if not new_rank:
            raise HTTPException(status_code=400, detail="Rank is required")
        conflict = (
            db_session.query(SalaryComponentTemplate)
            .filter(
                SalaryComponentTemplate.company_id == row.company_id,
                SalaryComponentTemplate.rank == new_rank,
                SalaryComponentTemplate.template_id != template_id,
            )
            .first()
        )
        if conflict:
            raise HTTPException(status_code=400, detail=f"Salary template for rank '{new_rank}' already exists")
        row.rank = new_rank
    for key in (
        "basic_monthly_wage",
        "monthly_overtime",
        "overtime_rate",
        "sepf",
        "imtf",
        "leave",
        "leave_sub",
        "various_extra_overtime",
    ):
        if key in incoming and incoming[key] is not None:
            setattr(row, key, incoming[key])
    db_session.commit()
    db_session.refresh(row)
    _write_audit_log(
        db_session,
        _current_user,
        action="salary_template.update",
        entity_type="salary_template",
        entity_id=template_id,
        details=f"company_id={row.company_id};rank={row.rank}",
    )
    return {"template": _serialize_salary_template(row)}


@app.delete("/companies-manager/salary-templates/{template_id}")
def delete_salary_template(
    template_id: int,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    row = db_session.get(SalaryComponentTemplate, template_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Salary template {template_id} not found")
    db_session.delete(row)
    db_session.commit()
    _write_audit_log(
        db_session,
        _current_user,
        action="salary_template.delete",
        entity_type="salary_template",
        entity_id=template_id,
    )
    return {"status": "ok", "deleted_template_id": template_id}


@app.post("/companies-manager/salary-scale/import")
async def import_salary_scale_xlsx_endpoint(
    file: UploadFile = File(...),
    company_slug: str | None = Form(None),
    db_session: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    from app.salary_scale_xlsx_import import SalaryScaleXlsxImportError, import_salary_scale_xlsx

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".xlsx", ".xls"}:
        raise HTTPException(
            status_code=400,
            detail="Допустимы только файлы Excel (.xlsx, .xls)",
        )

    try:
        content = await _read_upload_limited(file, MAX_COMPANIES_XLSX_UPLOAD_BYTES)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Не удалось прочитать файл: {exc}") from exc

    slug_filter: set[str] | None = None
    if company_slug and (slug := company_slug.strip().lower()):
        company = db_session.query(Company).filter(Company.slug == slug).one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail=f"Company slug '{slug}' not found")
        slug_filter = {slug}

    try:
        stats = import_salary_scale_xlsx(db_session, content, company_slugs=slug_filter)
    except SalaryScaleXlsxImportError as exc:
        db_session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db_session.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка импорта: {exc}") from exc

    if stats["created"] + stats["updated"] == 0:
        detail = "Не найдено строк для импорта."
        if stats["skipped"]:
            detail += " " + "; ".join(stats["skipped"])
        raise HTTPException(status_code=400, detail=detail)

    _write_audit_log(
        db_session,
        current_user,
        action="salary_scale.import",
        entity_type="company",
        entity_id=None,
        details=f"created={stats['created']};updated={stats['updated']};slug={company_slug or 'all'}",
    )
    return {"stats": stats}


@app.post("/candidates/{id}/salary-calculator/preview")
def preview_candidate_salary_calculation(
    id: int,
    payload: SalaryCalculatorPreviewRequest,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter", "viewer")),
) -> dict[str, Any]:
    _ensure_candidate(db_session, id)
    result = calculate_salary(
        db_session,
        company_id=payload.company_id,
        rank=payload.rank,
        total_wage=payload.total_wage,
        period_of_employment=payload.period_of_employment,
    )
    return {"calculation": result}


@app.put("/candidates/{id}/salary-calculator")
def save_candidate_salary_calculation(
    id: int,
    payload: SalaryCalculatorSaveRequest,
    db_session: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    candidate = _ensure_candidate(db_session, id)
    result = calculate_salary(
        db_session,
        company_id=payload.company_id,
        rank=payload.rank,
        total_wage=payload.total_wage,
        period_of_employment=payload.period_of_employment,
    )
    if not result["valid"]:
        raise HTTPException(status_code=400, detail={"errors": result["errors"]})
    saved = build_saved_calculation_payload(result, username=current_user.username)
    candidate.salary_calculation_json = json.dumps(saved, ensure_ascii=False)
    db_session.commit()
    db_session.refresh(candidate)
    _write_audit_log(
        db_session,
        current_user,
        action="candidate.salary_calculator.save",
        entity_type="candidate",
        entity_id=id,
        details=f"company_id={saved.get('company_id')};rank={saved.get('rank')}",
    )
    return {"calculation": saved, "candidate": _model_to_dict(candidate)}


@app.delete("/candidates/{id}/salary-calculator")
def reset_candidate_salary_calculation(
    id: int,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    candidate = _ensure_candidate(db_session, id)
    candidate.salary_calculation_json = None
    db_session.commit()
    db_session.refresh(candidate)
    _write_audit_log(
        db_session,
        _current_user,
        action="candidate.salary_calculator.reset",
        entity_type="candidate",
        entity_id=id,
    )
    return {"status": "ok", "candidate": _model_to_dict(candidate)}


@app.get("/candidates/{id}/contract-context")
def get_candidate_contract_context(
    id: int,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter", "viewer")),
) -> dict[str, Any]:
    candidate = _ensure_candidate(db_session, id)
    saved = parse_contract_json(candidate.contract_json)
    salary = parse_saved_calculation(candidate.salary_calculation_json)
    salary_matches = False
    if saved and salary:
        salary_matches = (
            int(saved.get("company_id") or 0) == int(salary.get("company_id") or 0)
            and str(saved.get("rank") or "").strip() == str(salary.get("rank") or "").strip()
        )
    company_id = saved.get("company_id")
    ranks: list[str] = []
    if company_id:
        ranks = list_ranks_for_company(db_session, int(company_id))
    vessel_snapshot: dict[str, Any] | None = None
    vessel_id = saved.get("vessel_id")
    if vessel_id:
        vessel = db_session.get(Vessel, int(vessel_id))
        if vessel:
            company = db_session.get(Company, vessel.company_id)
            vessel_snapshot = _serialize_vessel(vessel, company.slug if company else "")
    return {
        "contract": saved,
        "salary": salary,
        "salary_matches_selection": salary_matches,
        "ranks_for_saved_company": ranks,
        "vessel": vessel_snapshot,
    }


@app.put("/candidates/{id}/contract")
def save_candidate_contract(
    id: int,
    payload: ContractSaveRequest,
    db_session: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    candidate = _ensure_candidate(db_session, id)
    company = db_session.get(Company, payload.company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {payload.company_id} not found")
    rank = payload.rank.strip()
    if not rank:
        raise HTTPException(status_code=400, detail="Rank is required")
    vessel_name: str | None = None
    if payload.vessel_id is not None:
        vessel = db_session.get(Vessel, payload.vessel_id)
        if not vessel or vessel.company_id != company.company_id:
            raise HTTPException(status_code=400, detail="Vessel not found for selected company")
        vessel_name = vessel.name
    editable = payload.model_dump(
        exclude={"company_id", "vessel_id", "rank"},
        exclude_none=False,
    )
    saved = build_saved_contract_payload(
        company_id=company.company_id,
        company_name=company.name,
        vessel_id=payload.vessel_id,
        vessel_name=vessel_name,
        rank=rank,
        editable=editable,
        username=current_user.username,
    )
    candidate.contract_json = json.dumps(saved, ensure_ascii=False)
    home_airport = str(editable.get("contract_home_airport") or "").strip()
    departure_airport = str(editable.get("contract_departure_airport") or "").strip()
    candidate.home_airport = home_airport or None
    candidate.departure_airport = departure_airport or None
    db_session.commit()
    db_session.refresh(candidate)
    _write_audit_log(
        db_session,
        current_user,
        action="candidate.contract.save",
        entity_type="candidate",
        entity_id=id,
        details=f"company_id={company.company_id};vessel_id={payload.vessel_id};rank={rank}",
    )
    return {"contract": saved, "candidate": _model_to_dict(candidate)}


@app.get("/templates-manager/contracts-folder")
def list_contracts_templates(
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter", "viewer")),
) -> dict[str, Any]:
    folder = _find_contracts_template_folder(db_session)
    if not folder:
        return {
            "folder": None,
            "files": [],
            "message": "Создайте папку «Контракты» в Templates Manager",
        }
    allowed_ids = _collect_folder_descendants(db_session, folder.folder_id)
    files = (
        db_session.query(TemplateFile)
        .filter(TemplateFile.folder_id.in_(allowed_ids))
        .order_by(TemplateFile.file_name.asc())
        .all()
    )
    docx_files = [item for item in files if item.file_name.lower().endswith(".docx")]
    return {
        "folder": _serialize_template_folder(folder),
        "files": [_serialize_template_file(item) for item in docx_files],
    }


@app.post("/upload")
async def upload(
    file: UploadFile = File(...),
    confirm_duplicate_update: bool = Form(False),
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    suffix = Path(file.filename or "").suffix.lower()
    if not suffix:
        raise HTTPException(status_code=400, detail="File must have an extension")

    try:
        content = await _read_upload_limited(file, MAX_APPLICATION_UPLOAD_BYTES)
        if not content:
            raise HTTPException(status_code=400, detail="Bad Request: uploaded file is empty")

        with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(content)
            temp_path = Path(temp_file.name)

        parser = _get_parser(temp_path)
        parsed_data = parser.parse(temp_path)
        duplicate_candidate = _find_duplicate_candidate(db_session, parsed_data)
        if duplicate_candidate:
            if not confirm_duplicate_update:
                return {
                    "candidate_id": duplicate_candidate.candidate_id,
                    "result": parsed_data,
                    "duplicate": True,
                    "requires_confirmation": True,
                    "updated": False,
                    "message": "Такой кандидат уже существует. Хотите обновить его данные при помощи этой анкеты?",
                }

            duplicate_candidate = _merge_parsed_data_into_candidate(db_session, duplicate_candidate, parsed_data)
            _write_audit_log(
                db_session,
                _current_user,
                action="candidate.upload_merge",
                entity_type="candidate",
                entity_id=duplicate_candidate.candidate_id,
                details=f"source={file.filename or ''}",
            )
            return {
                "candidate_id": duplicate_candidate.candidate_id,
                "result": parsed_data,
                "duplicate": True,
                "requires_confirmation": False,
                "updated": True,
                "message": "Такой кандидат уже есть; существующая карточка обновлена новыми данными из анкеты",
            }

        candidate_id = _save_parsed_data(parsed_data, parser, db_session)
    except HTTPException:
        raise
    except ValueError as exc:
        logger.warning("Upload rejected: %s", exc)
        raise HTTPException(status_code=400, detail=f"Bad Request: {exc}") from exc
    except RuntimeError as exc:
        logger.warning("Upload runtime validation failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db_session.rollback()
        logger.exception("Upload processing failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to parse or save uploaded file") from exc
    finally:
        if "temp_path" in locals():
            temp_path.unlink(missing_ok=True)

    _write_audit_log(
        db_session,
        _current_user,
        action="candidate.upload_create",
        entity_type="candidate",
        entity_id=candidate_id,
        details=f"source={file.filename or ''}",
    )
    return {"candidate_id": candidate_id, "result": parsed_data, "duplicate": False}


@app.post("/upload_cv")
async def upload_cv(
    file: UploadFile = File(...),
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF CV files are supported")

    try:
        content = await _read_upload_limited(file, MAX_CV_UPLOAD_BYTES)
        if not content:
            raise HTTPException(status_code=400, detail="Bad Request: uploaded file is empty")

        with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(content)
            temp_path = Path(temp_file.name)

        nltk_stopwords_ready = _ensure_nltk_resource("corpora/stopwords", "stopwords")
        nltk_punkt_ready = _ensure_nltk_resource("tokenizers/punkt", "punkt")
        if not nltk_stopwords_ready or not nltk_punkt_ready:
            raise HTTPException(status_code=500, detail="NLTK resources are not available for CV parsing")

        try:
            from pyresparser import ResumeParser
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail="pyresparser is not available in environment",
            ) from exc

        parsed = ResumeParser(str(temp_path)).get_extracted_data() or {}
        candidate_payload = {
            "full_name": parsed.get("name"),
            "email": parsed.get("email"),
            "primary_phone": parsed.get("mobile_number"),
            "total_sea_service": str(parsed.get("total_experience")) if parsed.get("total_experience") is not None else None,
            "source_form_type": "cv_pdf",
            "source_file_name": file.filename,
            "record_status": "active",
            "cv_imported": True,
        }
        candidate = Candidate(**{k: v for k, v in candidate_payload.items() if v is not None})
        db_session.add(candidate)
        db_session.commit()
        db_session.refresh(candidate)
    except HTTPException:
        raise
    except Exception as exc:
        db_session.rollback()
        logger.exception("CV upload processing failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to parse CV and save candidate") from exc
    finally:
        if "temp_path" in locals():
            temp_path.unlink(missing_ok=True)

    _write_audit_log(
        db_session,
        _current_user,
        action="candidate.cv_upload_create",
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        details=f"source={file.filename or ''}",
    )
    return {
        "candidate_id": candidate.candidate_id,
        "cv_imported": candidate.cv_imported,
        "mapped_fields": {
            "full_name": candidate.full_name,
            "email": candidate.email,
            "primary_phone": candidate.primary_phone,
            "total_sea_service": candidate.total_sea_service,
        },
    }


@app.get("/candidates")
@app.get("/candidates/")
def list_candidates(
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_crm_user),
) -> dict[str, Any]:
    rows = (
        db_session.query(Candidate)
        .options(selectinload(Candidate.applications), selectinload(Candidate.sea_service), selectinload(Candidate.company))
        .order_by(Candidate.created_at.desc(), Candidate.candidate_id.desc())
        .all()
    )
    return {"items": [_candidate_row_to_list_item_dict(row) for row in rows]}


@app.get("/candidates/paged")
def list_candidates_paged(
    page: int = 1,
    page_size: int = 20,
    q: str | None = None,
    position: str | None = None,
    fleet: str | None = None,
    company_id: int | None = None,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_crm_user),
) -> dict[str, Any]:
    if page < 1:
        raise HTTPException(status_code=400, detail="page must be >= 1")
    if page_size < 1 or page_size > 100:
        raise HTTPException(status_code=400, detail="page_size must be between 1 and 100")

    query = db_session.query(Candidate)

    if q and (search_text := q.strip()):
        like_pattern = f"%{search_text}%"
        query = query.filter(
            or_(
                Candidate.surname.ilike(like_pattern),
                Candidate.first_name.ilike(like_pattern),
                Candidate.full_name.ilike(like_pattern),
            )
        )

    if position and (p := position.strip()):
        terms = position_search_terms(p)
        pos_clause = _position_filter_clauses(terms, include_sea_service=False)
        if pos_clause is not None:
            query = query.filter(pos_clause)

    if fleet and (fval := fleet.strip()):
        fleet_terms = fleet_search_terms(fval)
        fleet_clause = _fleet_filter_clauses(fleet_terms)
        if fleet_clause is not None:
            query = query.filter(fleet_clause)

    if company_id is not None:
        query = query.filter(Candidate.company_id == company_id)

    total = int(query.count() or 0)
    if total == 0:
        return {
            "data": [],
            "total": 0,
            "page": 1,
            "page_size": page_size,
            "total_pages": 0,
        }

    total_pages = (total + page_size - 1) // page_size
    effective_page = min(max(1, page), total_pages)

    rows = (
        query.options(
            selectinload(Candidate.applications),
            selectinload(Candidate.sea_service),
            selectinload(Candidate.company),
        )
        .order_by(Candidate.created_at.desc(), Candidate.candidate_id.desc())
        .offset((effective_page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "data": [_candidate_row_to_list_item_dict(row) for row in rows],
        "total": total,
        "page": effective_page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@app.post("/candidates")
@app.post("/candidates/")
def create_empty_candidate(
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    now = datetime.utcnow()
    candidate = Candidate(
        cv_imported=False,
        source_form_type="manual",
        record_status="active",
        created_at=now,
        updated_at=now,
    )
    db_session.add(candidate)
    db_session.commit()
    db_session.refresh(candidate)
    _write_audit_log(
        db_session,
        _current_user,
        action="candidate.create_manual",
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        details="empty_profile",
    )
    return {"candidate_id": candidate.candidate_id}


@app.get("/candidates/search")
def search_candidates(
    surname: str | None = None,
    q: str | None = None,
    position: str | None = None,
    rank: str | None = None,
    expiry_warning: bool | None = None,
    expiry_status: str | None = None,
    expires_in_days: int | None = None,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_crm_user),
) -> dict[str, Any]:
    query = db_session.query(Candidate)

    search_text = (q or surname or "").strip()
    if search_text:
        like_pattern = f"%{search_text}%"
        query = query.filter(
            or_(
                Candidate.surname.ilike(like_pattern),
                Candidate.first_name.ilike(like_pattern),
                Candidate.middle_name.ilike(like_pattern),
                Candidate.full_name.ilike(like_pattern),
            )
        )

    rank_or_position = (position or rank or "").strip()
    if rank_or_position:
        terms = position_search_terms(rank_or_position)
        pos_clause = _position_filter_clauses(terms, include_sea_service=False)
        if pos_clause is not None:
            query = query.filter(pos_clause)

    today = date.today()
    warning_limit = today + timedelta(days=240)
    warning_clause = or_(
        Candidate.documents.any(
            and_(
                Document.date_of_expiry.is_not(None),
                Document.date_of_expiry >= today,
                Document.date_of_expiry < warning_limit,
            )
        ),
        Candidate.certificates.any(
            and_(
                Certificate.expiry_date.is_not(None),
                Certificate.expiry_date >= today,
                Certificate.expiry_date < warning_limit,
            )
        ),
    )
    expired_clause = or_(
        Candidate.documents.any(
            and_(
                Document.date_of_expiry.is_not(None),
                Document.date_of_expiry < today,
            )
        ),
        Candidate.certificates.any(
            and_(
                Certificate.expiry_date.is_not(None),
                Certificate.expiry_date < today,
            )
        ),
    )
    has_expiry_date_clause = or_(
        Candidate.documents.any(Document.date_of_expiry.is_not(None)),
        Candidate.certificates.any(Certificate.expiry_date.is_not(None)),
    )
    ok_clause = and_(has_expiry_date_clause, not_(warning_clause), not_(expired_clause))

    if expires_in_days is not None:
        if expires_in_days < 0:
            raise HTTPException(status_code=400, detail="expires_in_days must be greater than or equal to 0")
        threshold = today + timedelta(days=expires_in_days)
        query = query.filter(
            or_(
                Candidate.documents.any(
                    and_(
                        Document.date_of_expiry.is_not(None),
                        Document.date_of_expiry >= today,
                        Document.date_of_expiry <= threshold,
                    )
                ),
                Candidate.certificates.any(
                    and_(
                        Certificate.expiry_date.is_not(None),
                        Certificate.expiry_date >= today,
                        Certificate.expiry_date <= threshold,
                    )
                ),
            )
        )

    if expiry_warning is True:
        query = query.filter(warning_clause)
    elif expiry_warning is False:
        query = query.filter(not_(warning_clause))

    if expiry_status:
        normalized_status = expiry_status.strip().lower()
        if normalized_status == "warning":
            query = query.filter(warning_clause)
        elif normalized_status == "expired":
            query = query.filter(expired_clause)
        elif normalized_status in {"ok", "valid"}:
            query = query.filter(ok_clause)
        elif normalized_status != "all":
            raise HTTPException(
                status_code=400,
                detail="expiry_status must be one of: all, warning, expired, ok",
            )

    rows = query.order_by(Candidate.candidate_id.desc()).all()
    items = []
    for row in rows:
        position = display_position_label(_raw_list_position_from_row(row))
        has_warning = any(
            doc.date_of_expiry and today <= doc.date_of_expiry < warning_limit for doc in row.documents
        ) or any(cert.expiry_date and today <= cert.expiry_date < warning_limit for cert in row.certificates)
        has_expired = any(doc.date_of_expiry and doc.date_of_expiry < today for doc in row.documents) or any(
            cert.expiry_date and cert.expiry_date < today for cert in row.certificates
        )
        items.append(
            {
                "id": row.candidate_id,
                "surname": row.surname,
                "position": position,
                "expiry_warning": has_warning,
                "expiry_expired": has_expired,
            }
        )
    return {"items": items}


@app.get("/candidates/{id}")
def get_candidate(
    id: int,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_crm_user),
) -> dict[str, Any]:
    candidate = db_session.get(Candidate, id)
    if not candidate:
        raise HTTPException(status_code=404, detail=f"Candidate {id} not found")
    sea_service_items = (
        db_session.query(SeaService)
        .filter(SeaService.candidate_id == id)
        .order_by(
            func.coalesce(SeaService.sign_off_date, SeaService.sign_on_date).desc(),
            SeaService.sign_on_date.desc(),
            SeaService.sea_service_id.desc(),
        )
        .all()
    )

    ensure_canonical_documents(db_session, id)
    ensure_canonical_visas(db_session, id)  # also deduplicates duplicate visa rows
    ensure_canonical_diplomas(db_session, id)
    ensure_canonical_medical(db_session, id)
    ensure_canonical_certificates(db_session, id)
    document_rows = (
        db_session.query(Document)
        .filter(Document.candidate_id == id)
        .order_by(Document.document_id.asc())
        .all()
    )
    all_document_dicts = _with_expiry_flags([_model_to_dict(item) for item in document_rows], "date_of_expiry")
    non_visa_documents, visa_document_dicts = partition_documents_and_visas(all_document_dicts)
    documents = order_documents_for_response(
        non_visa_documents,
        session=db_session,
        candidate_id=id,
    )
    visas = order_visas_for_response(
        visa_document_dicts,
        session=db_session,
        candidate_id=id,
    )
    visas = _with_expiry_flags(visas, "date_of_expiry")
    certificate_rows = (
        db_session.query(Certificate)
        .filter(Certificate.candidate_id == id)
        .order_by(Certificate.certificate_id.asc())
        .all()
    )
    all_certificates = _with_expiry_flags([_model_to_dict(item) for item in certificate_rows], "expiry_date")
    other_certificates = [
        item
        for item in all_certificates
        if not is_canonical_diploma_record(item)
        and not is_canonical_medical_record(item)
        and not is_canonical_certificate_record(item)
    ]
    diplomas = order_specs_for_response(
        all_certificates,
        CANONICAL_DIPLOMA_SPECS,
        session=db_session,
        candidate_id=id,
    )
    diplomas = _with_expiry_flags(diplomas, "expiry_date")
    tanker_diplomas = order_specs_for_response(
        all_certificates,
        CANONICAL_TANKER_DIPLOMA_SPECS,
        session=db_session,
        candidate_id=id,
    )
    tanker_diplomas = _with_expiry_flags(tanker_diplomas, "expiry_date")
    medical_documents = order_medical_for_response(
        all_certificates,
        session=db_session,
        candidate_id=id,
    )
    medical_documents = _with_expiry_flags(medical_documents, "expiry_date")
    conventional_certificates = order_certificates_for_response(
        all_certificates,
        CANONICAL_CONVENTIONAL_SPECS,
        session=db_session,
        candidate_id=id,
    )
    conventional_certificates = _with_expiry_flags(conventional_certificates, "expiry_date")
    ecdis_certificates = order_certificates_for_response(
        all_certificates,
        CANONICAL_ECDIS_SPECS,
        session=db_session,
        candidate_id=id,
    )
    ecdis_certificates = _with_expiry_flags(ecdis_certificates, "expiry_date")
    company_certificates = order_certificates_for_response(
        all_certificates,
        CANONICAL_COMPANY_SPECS,
        session=db_session,
        candidate_id=id,
    )
    company_certificates = _with_expiry_flags(company_certificates, "expiry_date")
    bwts_certificates = order_certificates_for_response(
        all_certificates,
        CANONICAL_BWTS_SPECS,
        session=db_session,
        candidate_id=id,
    )
    bwts_certificates = _with_expiry_flags(bwts_certificates, "expiry_date")
    comments = (
        db_session.query(CandidateComment)
        .filter(CandidateComment.candidate_id == id)
        .order_by(CandidateComment.created_at.desc(), CandidateComment.comment_id.desc())
        .all()
    )
    return {
        "candidate": _model_to_dict(candidate),
        "applications": [_model_to_dict(item) for item in candidate.applications],
        "documents": documents,
        "visas": visas,
        "certificates": other_certificates,
        "conventional_certificates": conventional_certificates,
        "ecdis_certificates": ecdis_certificates,
        "company_certificates": company_certificates,
        "bwts_certificates": bwts_certificates,
        "diplomas": diplomas,
        "tanker_diplomas": tanker_diplomas,
        "medical_documents": medical_documents,
        "flag_documents": [_model_to_dict(item) for item in candidate.flag_documents],
        "sea_service": [normalize_sea_service_dict(_model_to_dict(item)) for item in sea_service_items],
        "family_contacts": [_model_to_dict(item) for item in candidate.family_contacts],
        "attachments": [_model_to_dict(item) for item in candidate.attachments],
        "comments": [_serialize_candidate_comment(item) for item in comments],
    }


@app.post("/candidates/{id}/comments")
def add_candidate_comment(
    id: int,
    payload: CandidateCommentCreate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    _ensure_candidate(db_session, id)
    text = (payload.comment_text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Comment text is required")
    comment = CandidateComment(
        candidate_id=id,
        comment_text=text,
        created_at=datetime.utcnow(),
    )
    db_session.add(comment)
    db_session.commit()
    db_session.refresh(comment)
    _write_audit_log(
        db_session,
        _current_user,
        action="candidate.comment.create",
        entity_type="candidate",
        entity_id=id,
        details=f"comment_id={comment.comment_id}",
    )
    return {"comment": _serialize_candidate_comment(comment)}


@app.delete("/candidates/{id}")
def delete_candidate(
    id: int,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    candidate = db_session.get(Candidate, id)
    if not candidate:
        raise HTTPException(status_code=404, detail=f"Candidate {id} not found")
    db_session.delete(candidate)
    db_session.commit()
    _write_audit_log(
        db_session,
        _current_user,
        action="candidate.delete",
        entity_type="candidate",
        entity_id=id,
        details=None,
    )
    return {"status": "ok", "candidate_id": id}


@app.post("/candidates/{id}/generate/{template_name}")
def generate_document_from_template(
    id: int,
    template_name: str,
    template_file_id: int | None = Query(
        None,
        description="Managed template id (recommended when duplicate file names exist in different folders)",
    ),
    contracts_only: bool = Query(
        False,
        description="When true, template must belong to the Contracts/Контракты folder",
    ),
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter", "viewer")),
) -> FileResponse:
    candidate = db_session.get(Candidate, id)
    if not candidate:
        raise HTTPException(status_code=404, detail=f"Candidate {id} not found")

    if template_file_id is not None:
        managed = db_session.get(TemplateFile, template_file_id)
        if not managed:
            raise HTTPException(status_code=404, detail=f"Template file id {template_file_id} not found")
        if contracts_only and not _template_file_in_contracts_folder(db_session, template_file_id):
            raise HTTPException(
                status_code=400,
                detail="Template must be in the «Контракты» folder",
            )
        resolved = TEMPLATES_MANAGER_DIR / managed.relative_path
        if not resolved.exists():
            raise HTTPException(status_code=404, detail=f"Template file not found on disk: {managed.file_name}")
        if resolved.suffix.lower() != ".docx":
            raise HTTPException(
                status_code=400,
                detail="Only DOCX templates can be used for candidate document generation.",
            )
        safe_template_name = managed.file_name
        template_path = resolved
        try:
            doc = DocxTemplate(str(template_path))
            context = _prepare_docx_template_context(
                _serialize_candidate_context(candidate, db_session=db_session),
                template_path,
            )
            doc.render(context)

            applications = candidate.applications or []
            first_application = applications[0] if applications else None
            raw_position = (
                (first_application.position_applied_for if first_application else None)
                or candidate.current_rank
                or "position"
            )
            raw_surname = candidate.surname or "surname"
            raw_first_name = candidate.first_name or "name"

            def _safe_file_part(value: str) -> str:
                cleaned = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "", str(value or "").strip())
                cleaned = re.sub(r"\s+", "_", cleaned).strip("._")
                return cleaned or "unknown"

            output_name = (
                f"{_safe_file_part(raw_position)}_"
                f"{_safe_file_part(raw_surname)}_"
                f"{_safe_file_part(raw_first_name)}_"
                f"{_safe_file_part(Path(safe_template_name).stem)}_"
                f"{uuid4().hex[:8]}.docx"
            )
            output_path = GENERATED_DIR / output_name
            doc.save(output_path)
            from app.docx_template_jinja import strip_email_hyperlinks_from_docx

            strip_email_hyperlinks_from_docx(output_path)
        except Exception as exc:
            logger.exception("Template generation failed: %s", exc)
            raise HTTPException(status_code=500, detail="Failed to generate document from template") from exc

        safe_header_name = output_name.replace('"', "")
        content_disposition = _attachment_content_disposition(output_name)
        return FileResponse(
            path=output_path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=output_name,
            headers=_nosniff_headers({"Content-Disposition": content_disposition}),
        )

    template_file = Path(template_name)
    if template_file.suffix.lower() != ".docx":
        template_file = template_file.with_suffix(".docx")
    safe_template_name = template_file.name
    template_path = TEMPLATES_DIR / safe_template_name
    if not template_path.exists():
        managed_template = (
            db_session.query(TemplateFile)
            .filter(TemplateFile.file_name == safe_template_name)
            .order_by(TemplateFile.updated_at.desc(), TemplateFile.template_file_id.desc())
            .first()
        )
        if managed_template:
            candidate_path = TEMPLATES_MANAGER_DIR / managed_template.relative_path
            if candidate_path.exists():
                template_path = candidate_path
    if not template_path.exists():
        discovered_in_manager = next(TEMPLATES_MANAGER_DIR.rglob(f"*{safe_template_name}"), None)
        if discovered_in_manager and discovered_in_manager.exists():
            template_path = discovered_in_manager
    if not template_path.exists():
        discovered_in_templates = next(TEMPLATES_DIR.rglob(f"*{safe_template_name}"), None)
        if discovered_in_templates and discovered_in_templates.exists():
            template_path = discovered_in_templates
    if not template_path.exists():
        raise HTTPException(status_code=404, detail=f"Template not found: {safe_template_name}")

    try:
        doc = DocxTemplate(str(template_path))
        context = _prepare_docx_template_context(
            _serialize_candidate_context(candidate, db_session=db_session),
            template_path,
        )
        doc.render(context)

        applications = candidate.applications or []
        first_application = applications[0] if applications else None
        raw_position = (
            (first_application.position_applied_for if first_application else None)
            or candidate.current_rank
            or "position"
        )
        raw_surname = candidate.surname or "surname"
        raw_first_name = candidate.first_name or "name"

        def _safe_file_part(value: str) -> str:
            cleaned = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "", str(value or "").strip())
            cleaned = re.sub(r"\s+", "_", cleaned).strip("._")
            return cleaned or "unknown"

        output_name = (
            f"{_safe_file_part(raw_position)}_"
            f"{_safe_file_part(raw_surname)}_"
            f"{_safe_file_part(raw_first_name)}_"
            f"{_safe_file_part(Path(safe_template_name).stem)}_"
            f"{uuid4().hex[:8]}.docx"
        )
        output_path = GENERATED_DIR / output_name
        doc.save(output_path)
        from app.docx_template_jinja import strip_email_hyperlinks_from_docx

        strip_email_hyperlinks_from_docx(output_path)
    except Exception as exc:
        logger.exception("Template generation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to generate document from template") from exc

    content_disposition = _attachment_content_disposition(output_name)
    return FileResponse(
        path=output_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=output_name,
        headers=_nosniff_headers({"Content-Disposition": content_disposition}),
    )


def _load_candidate_for_templates(db_session: Session, candidate_id: int) -> Candidate:
    candidate = (
        db_session.query(Candidate)
        .options(
            selectinload(Candidate.applications),
            selectinload(Candidate.documents),
            selectinload(Candidate.certificates),
            selectinload(Candidate.flag_documents),
            selectinload(Candidate.sea_service),
            selectinload(Candidate.family_contacts),
            selectinload(Candidate.attachments),
        )
        .filter(Candidate.candidate_id == candidate_id)
        .one_or_none()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id} not found")
    return candidate


@app.post("/candidates/{id}/submission-pack")
def build_candidate_submission_pack(
    id: int,
    payload: SubmissionPackRequest,
    db_session: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "recruiter", "viewer")),
) -> FileResponse:
    candidate = _load_candidate_for_templates(db_session, id)
    zip_bytes, zip_name = build_submission_zip(
        db_session=db_session,
        candidate=candidate,
        templates_dir=TEMPLATES_DIR,
        templates_manager_dir=TEMPLATES_MANAGER_DIR,
        generated_dir=GENERATED_DIR,
        serialize_context=lambda cand: _serialize_candidate_context(cand, db_session=db_session),
        modal_fields={
            "opening_vessel": payload.opening_vessel,
            "previous_vessel": payload.previous_vessel,
        },
        template_file_ids=payload.template_file_ids,
        attachment_ids=payload.attachment_ids,
    )
    temp_path = GENERATED_DIR / zip_name
    temp_path.write_bytes(zip_bytes)
    content_disposition = _attachment_content_disposition(zip_name)
    _write_audit_log(
        db_session,
        current_user,
        action="candidate.submission_pack",
        entity_type="candidate",
        entity_id=id,
        details=(
            f"templates={payload.template_file_ids};attachments={payload.attachment_ids};"
            f"opening_vessel={payload.opening_vessel or ''}"
        ),
    )
    return FileResponse(
        path=temp_path,
        media_type="application/zip",
        filename=zip_name,
        headers=_nosniff_headers({"Content-Disposition": content_disposition}),
    )


@app.put("/candidates/{id}")
def update_candidate(
    id: int,
    payload: CandidateUpdate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    candidate = _ensure_candidate(db_session, id)
    updates = payload.model_dump(exclude_unset=True)

    allowed_fields = {column.name for column in Candidate.__table__.columns} - {"candidate_id", "created_at", "updated_at"}
    invalid_fields = [key for key in updates.keys() if key not in allowed_fields]
    if invalid_fields:
        raise HTTPException(status_code=400, detail=f"Unsupported candidate fields: {', '.join(invalid_fields)}")

    if "company_id" in updates:
        raw_company_id = updates["company_id"]
        if raw_company_id in ("", None):
            updates["company_id"] = None
        else:
            try:
                company_id = int(raw_company_id)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail="company_id must be an integer") from exc
            if not db_session.get(Company, company_id):
                raise HTTPException(status_code=404, detail=f"Company {company_id} not found")
            updates["company_id"] = company_id

    for key, value in updates.items():
        setattr(candidate, key, value)
    db_session.commit()
    db_session.refresh(candidate)
    _write_audit_log(
        db_session,
        _current_user,
        action="candidate.update",
        entity_type="candidate",
        entity_id=id,
        details=f"fields={','.join(sorted(updates.keys()))}",
    )
    return {"candidate": _model_to_dict(candidate)}


@app.post("/candidates/{id}/applications")
def add_application(
    id: int,
    payload: ApplicationUpdate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    _ensure_candidate(db_session, id)
    if db_session.query(Application).filter(Application.candidate_id == id).count() > 0:
        raise HTTPException(
            status_code=400,
            detail="Application already exists for this candidate; use PUT to update",
        )
    data = _normalize_application_rank_fields(payload.model_dump(exclude_none=True))
    row = Application(candidate_id=id, **data)
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    _write_audit_log(
        db_session,
        _current_user,
        action="application.create",
        entity_type="application",
        entity_id=row.application_id,
        details=f"candidate_id={id}",
    )
    return {"application": _model_to_dict(row)}


@app.put("/candidates/{id}/applications/{application_id}")
def update_application(
    id: int,
    application_id: int,
    payload: ApplicationUpdate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    _ensure_candidate(db_session, id)
    row = db_session.get(Application, application_id)
    if not row or row.candidate_id != id:
        raise HTTPException(status_code=404, detail=f"Application {application_id} not found for candidate {id}")
    updates = _normalize_application_rank_fields(payload.model_dump(exclude_unset=True))
    for key, value in updates.items():
        setattr(row, key, value)
    db_session.commit()
    db_session.refresh(row)
    _write_audit_log(
        db_session,
        _current_user,
        action="application.update",
        entity_type="application",
        entity_id=application_id,
        details=f"candidate_id={id}",
    )
    return {"application": _model_to_dict(row)}


@app.post("/candidates/{id}/documents")
def add_document(
    id: int,
    payload: DocumentCreate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    _ensure_candidate(db_session, id)
    if _expiry_before_issue(payload.date_of_issue, payload.date_of_expiry):
        raise HTTPException(status_code=400, detail=ISSUE_EXPIRY_ORDER_ERROR_MSG)
    document = Document(candidate_id=id, **payload.model_dump(exclude_none=True))
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    _sync_notifications(db_session, only_candidate_id=id)
    _write_audit_log(
        db_session,
        _current_user,
        action="document.create",
        entity_type="document",
        entity_id=document.document_id,
        details=f"candidate_id={id}",
    )
    return {"document": _model_to_dict(document)}


@app.put("/candidates/{id}/documents/{rec_id}")
def update_document(
    id: int,
    rec_id: int,
    payload: DocumentUpdate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    _ensure_candidate(db_session, id)
    document = db_session.get(Document, rec_id)
    if not document or document.candidate_id != id:
        raise HTTPException(status_code=404, detail=f"Document {rec_id} not found for candidate {id}")
    incoming = payload.model_dump(exclude_unset=True)
    next_issue = incoming.get("date_of_issue", document.date_of_issue)
    next_expiry = incoming.get("date_of_expiry", document.date_of_expiry)
    if _expiry_before_issue(next_issue, next_expiry):
        raise HTTPException(status_code=400, detail=ISSUE_EXPIRY_ORDER_ERROR_MSG)
    for key, value in incoming.items():
        setattr(document, key, value)
    db_session.commit()
    db_session.refresh(document)
    _sync_notifications(db_session)
    _write_audit_log(
        db_session,
        _current_user,
        action="document.update",
        entity_type="document",
        entity_id=rec_id,
        details=f"candidate_id={id}",
    )
    return {"document": _model_to_dict(document)}


@app.delete("/candidates/{id}/documents/{doc_id}")
def delete_document(
    id: int,
    doc_id: int,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    _ensure_candidate(db_session, id)
    document = db_session.get(Document, doc_id)
    if not document or document.candidate_id != id:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found for candidate {id}")
    db_session.delete(document)
    db_session.commit()
    _write_audit_log(
        db_session,
        _current_user,
        action="document.delete",
        entity_type="document",
        entity_id=doc_id,
        details=f"candidate_id={id}",
    )
    return {"status": "ok", "deleted_document_id": doc_id}


@app.post("/candidates/{id}/certificates")
def add_certificate(
    id: int,
    payload: CertificateCreate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    _ensure_candidate(db_session, id)
    data = apply_certificate_validity_defaults(payload.model_dump(exclude_none=True))
    if data.get("unlimited_validity") is not True and _expiry_before_issue(data.get("date_issued"), data.get("expiry_date")):
        raise HTTPException(status_code=400, detail=ISSUE_EXPIRY_ORDER_ERROR_MSG)
    certificate = Certificate(candidate_id=id, **data)
    db_session.add(certificate)
    db_session.flush()
    if "competency_rank" in data:
        _sync_candidate_coc_rank_from_certificate(db_session, id, certificate, data.get("competency_rank"))
    db_session.commit()
    db_session.refresh(certificate)
    _write_audit_log(
        db_session,
        _current_user,
        action="certificate.create",
        entity_type="certificate",
        entity_id=certificate.certificate_id,
        details=f"candidate_id={id}",
    )
    return {"certificate": _model_to_dict(certificate)}


@app.put("/candidates/{id}/certificates/{rec_id}")
def update_certificate(
    id: int,
    rec_id: int,
    payload: CertificateUpdate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    _ensure_candidate(db_session, id)
    certificate = db_session.get(Certificate, rec_id)
    if not certificate or certificate.candidate_id != id:
        raise HTTPException(status_code=404, detail=f"Certificate {rec_id} not found for candidate {id}")
    incoming_cert = payload.model_dump(exclude_unset=True)
    merged_for_validity = {
        "date_issued": incoming_cert.get("date_issued", certificate.date_issued),
        "expiry_date": incoming_cert.get("expiry_date", certificate.expiry_date),
        "unlimited_validity": incoming_cert.get("unlimited_validity", certificate.unlimited_validity),
    }
    if merged_for_validity.get("unlimited_validity") is not True:
        filled = apply_certificate_validity_defaults(dict(merged_for_validity))
        for key in ("date_issued", "expiry_date", "unlimited_validity"):
            if key not in incoming_cert and filled.get(key) is not None:
                incoming_cert[key] = filled[key]
    next_issued = incoming_cert.get("date_issued", certificate.date_issued)
    next_cexp = incoming_cert.get("expiry_date", certificate.expiry_date)
    if incoming_cert.get("unlimited_validity") is not True and _expiry_before_issue(next_issued, next_cexp):
        raise HTTPException(status_code=400, detail=ISSUE_EXPIRY_ORDER_ERROR_MSG)
    for key, value in incoming_cert.items():
        setattr(certificate, key, value)
    if "competency_rank" in incoming_cert:
        _sync_candidate_coc_rank_from_certificate(
            db_session, id, certificate, incoming_cert.get("competency_rank")
        )
    db_session.commit()
    db_session.refresh(certificate)
    _sync_notifications(db_session)
    _write_audit_log(
        db_session,
        _current_user,
        action="certificate.update",
        entity_type="certificate",
        entity_id=rec_id,
        details=f"candidate_id={id}",
    )
    return {"certificate": _model_to_dict(certificate)}


@app.delete("/candidates/{id}/certificates/{certificate_id}")
def delete_certificate(
    id: int,
    certificate_id: int,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    _ensure_candidate(db_session, id)
    certificate = db_session.get(Certificate, certificate_id)
    if not certificate or certificate.candidate_id != id:
        raise HTTPException(status_code=404, detail=f"Certificate {certificate_id} not found for candidate {id}")
    db_session.delete(certificate)
    db_session.commit()
    _write_audit_log(
        db_session,
        _current_user,
        action="certificate.delete",
        entity_type="certificate",
        entity_id=certificate_id,
        details=f"candidate_id={id}",
    )
    return {"status": "ok", "deleted_certificate_id": certificate_id}


@app.post("/candidates/{id}/sea-service")
def add_sea_service(
    id: int,
    payload: SeaServiceCreate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    _ensure_candidate(db_session, id)
    data = apply_sea_service_defaults(payload.model_dump(exclude_none=True))
    sea_item = SeaService(candidate_id=id, **data)
    db_session.add(sea_item)
    db_session.commit()
    db_session.refresh(sea_item)
    _write_audit_log(
        db_session,
        _current_user,
        action="sea_service.create",
        entity_type="sea_service",
        entity_id=sea_item.sea_service_id,
        details=f"candidate_id={id}",
    )
    return {"sea_service": _model_to_dict(sea_item)}


@app.post("/candidates/{id}/sea_service")
def add_sea_service_with_underscore(
    id: int,
    payload: SeaServiceCreate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    return add_sea_service(id=id, payload=payload, db_session=db_session)


@app.put("/candidates/{id}/sea_service/{rec_id}")
def update_sea_service(
    id: int,
    rec_id: int,
    payload: SeaServiceUpdate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    _ensure_candidate(db_session, id)
    sea_item = db_session.get(SeaService, rec_id)
    if not sea_item or sea_item.candidate_id != id:
        raise HTTPException(status_code=404, detail=f"Sea service {rec_id} not found for candidate {id}")
    incoming_ss = apply_contract_duration_to_payload(payload.model_dump(exclude_unset=True))
    for key, value in incoming_ss.items():
        setattr(sea_item, key, value)
    if "sign_on_date" not in incoming_ss or "sign_off_date" not in incoming_ss:
        merged = apply_contract_duration_to_payload(
            {
                "sign_on_date": sea_item.sign_on_date,
                "sign_off_date": sea_item.sign_off_date,
            }
        )
        if merged.get("contract_duration"):
            sea_item.contract_duration = merged["contract_duration"]
    db_session.commit()
    db_session.refresh(sea_item)
    _write_audit_log(
        db_session,
        _current_user,
        action="sea_service.update",
        entity_type="sea_service",
        entity_id=rec_id,
        details=f"candidate_id={id}",
    )
    return {"sea_service": _model_to_dict(sea_item)}


@app.put("/candidates/{id}/sea-service/{rec_id}")
def update_sea_service_with_hyphen(
    id: int,
    rec_id: int,
    payload: SeaServiceUpdate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    return update_sea_service(id=id, rec_id=rec_id, payload=payload, db_session=db_session)


@app.delete("/candidates/{id}/sea_service/{rec_id}")
def delete_sea_service_with_underscore(
    id: int,
    rec_id: int,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    _ensure_candidate(db_session, id)
    sea_item = db_session.get(SeaService, rec_id)
    if not sea_item or sea_item.candidate_id != id:
        raise HTTPException(status_code=404, detail=f"Sea service {rec_id} not found for candidate {id}")
    db_session.delete(sea_item)
    db_session.commit()
    _write_audit_log(
        db_session,
        _current_user,
        action="sea_service.delete",
        entity_type="sea_service",
        entity_id=rec_id,
        details=f"candidate_id={id}",
    )
    return {"status": "ok", "deleted_sea_service_id": rec_id}


@app.delete("/candidates/{id}/sea-service/{sea_service_id}")
def delete_sea_service(
    id: int,
    sea_service_id: int,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    _ensure_candidate(db_session, id)
    sea_item = db_session.get(SeaService, sea_service_id)
    if not sea_item or sea_item.candidate_id != id:
        raise HTTPException(status_code=404, detail=f"Sea service {sea_service_id} not found for candidate {id}")
    db_session.delete(sea_item)
    db_session.commit()
    _write_audit_log(
        db_session,
        _current_user,
        action="sea_service.delete",
        entity_type="sea_service",
        entity_id=sea_service_id,
        details=f"candidate_id={id}",
    )
    return {"status": "ok", "deleted_sea_service_id": sea_service_id}


@app.post("/candidates/{id}/family-contacts")
def add_family_contact(
    id: int,
    payload: FamilyContactCreate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    _ensure_candidate(db_session, id)
    contact = FamilyContact(candidate_id=id, **payload.model_dump(exclude_none=True))
    db_session.add(contact)
    db_session.commit()
    db_session.refresh(contact)
    _write_audit_log(
        db_session,
        _current_user,
        action="family_contact.create",
        entity_type="family_contact",
        entity_id=contact.family_contact_id,
        details=f"candidate_id={id}",
    )
    return {"family_contact": _model_to_dict(contact)}


@app.put("/candidates/{id}/family-contacts/{family_contact_id}")
def update_family_contact(
    id: int,
    family_contact_id: int,
    payload: FamilyContactUpdate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    _ensure_candidate(db_session, id)
    contact = db_session.get(FamilyContact, family_contact_id)
    if not contact or contact.candidate_id != id:
        raise HTTPException(status_code=404, detail=f"Family contact {family_contact_id} not found for candidate {id}")
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(contact, key, value)
    db_session.commit()
    db_session.refresh(contact)
    _write_audit_log(
        db_session,
        _current_user,
        action="family_contact.update",
        entity_type="family_contact",
        entity_id=family_contact_id,
        details=f"candidate_id={id}",
    )
    return {"family_contact": _model_to_dict(contact)}


@app.delete("/candidates/{id}/family-contacts/{family_contact_id}")
def delete_family_contact(
    id: int,
    family_contact_id: int,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    _ensure_candidate(db_session, id)
    contact = db_session.get(FamilyContact, family_contact_id)
    if not contact or contact.candidate_id != id:
        raise HTTPException(status_code=404, detail=f"Family contact {family_contact_id} not found for candidate {id}")
    db_session.delete(contact)
    db_session.commit()
    _write_audit_log(
        db_session,
        _current_user,
        action="family_contact.delete",
        entity_type="family_contact",
        entity_id=family_contact_id,
        details=f"candidate_id={id}",
    )
    return {"status": "ok", "deleted_family_contact_id": family_contact_id}


@app.post("/candidates/{id}/flag-documents")
def add_flag_document(
    id: int,
    payload: FlagDocumentCreate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    _ensure_candidate(db_session, id)
    if _expiry_before_issue(payload.date_of_issuance, payload.date_of_expiry):
        raise HTTPException(status_code=400, detail=ISSUE_EXPIRY_ORDER_ERROR_MSG)
    row = FlagDocument(candidate_id=id, **payload.model_dump(exclude_none=True))
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    _write_audit_log(
        db_session,
        _current_user,
        action="flag_document.create",
        entity_type="flag_document",
        entity_id=row.flag_document_id,
        details=f"candidate_id={id}",
    )
    return {"flag_document": _model_to_dict(row)}


@app.put("/candidates/{id}/flag-documents/{flag_document_id}")
def update_flag_document(
    id: int,
    flag_document_id: int,
    payload: FlagDocumentUpdate,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    _ensure_candidate(db_session, id)
    row = db_session.get(FlagDocument, flag_document_id)
    if not row or row.candidate_id != id:
        raise HTTPException(status_code=404, detail=f"Flag document {flag_document_id} not found for candidate {id}")
    updates = payload.model_dump(exclude_unset=True)
    next_issuance = updates.get("date_of_issuance", row.date_of_issuance)
    next_fexp = updates.get("date_of_expiry", row.date_of_expiry)
    if _expiry_before_issue(next_issuance, next_fexp):
        raise HTTPException(status_code=400, detail=ISSUE_EXPIRY_ORDER_ERROR_MSG)
    for key, value in updates.items():
        setattr(row, key, value)
    db_session.commit()
    db_session.refresh(row)
    _write_audit_log(
        db_session,
        _current_user,
        action="flag_document.update",
        entity_type="flag_document",
        entity_id=flag_document_id,
        details=f"candidate_id={id}",
    )
    return {"flag_document": _model_to_dict(row)}


@app.delete("/candidates/{id}/flag-documents/{flag_document_id}")
def delete_flag_document(
    id: int,
    flag_document_id: int,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    _ensure_candidate(db_session, id)
    row = db_session.get(FlagDocument, flag_document_id)
    if not row or row.candidate_id != id:
        raise HTTPException(status_code=404, detail=f"Flag document {flag_document_id} not found for candidate {id}")
    db_session.delete(row)
    db_session.commit()
    _write_audit_log(
        db_session,
        _current_user,
        action="flag_document.delete",
        entity_type="flag_document",
        entity_id=flag_document_id,
        details=f"candidate_id={id}",
    )
    return {"status": "ok", "deleted_flag_document_id": flag_document_id}


@app.post("/candidates/{id}/attachments")
async def add_attachment(
    id: int,
    file: UploadFile = File(...),
    attachment_type: str | None = Form(default=None),
    relation_id: int | None = Form(default=None),
    description: str | None = Form(default=None),
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    try:
        _ensure_candidate(db_session, id)
        suffix = Path(file.filename or "").suffix.lower()
        if not suffix or suffix not in ALLOWED_ATTACHMENT_SUFFIXES:
            raise HTTPException(
                status_code=400,
                detail="Unsupported file type. Allowed extensions: .jpeg, .jpg, .png, .pdf",
            )
        content = await _read_upload_limited(file, MAX_ATTACHMENT_UPLOAD_BYTES)
        if not content:
            raise HTTPException(status_code=400, detail="Bad Request: uploaded file is empty")
        stored_bytes, stored_suffix, stored_media_type = prepare_attachment_bytes(suffix, content)
        stored_name = f"{uuid4().hex}{stored_suffix}"
        target_path = UPLOADS_DIR / stored_name
        target_path.write_bytes(stored_bytes)

        resolved_description = description or (
            f"{attachment_type}:{relation_id}" if attachment_type and relation_id else attachment_type
        )
        candidate = _load_candidate_for_templates(db_session, id)
        attachment = Attachment(
            candidate_id=id,
            file_name=file.filename or stored_name,
            file_type=stored_media_type,
            file_path=str(target_path),
            file_size_bytes=len(stored_bytes),
            source=attachment_type or "frontend_upload",
            description=resolved_description,
        )
        attachment.file_name = attachment_download_filename(db_session, candidate, attachment)
        db_session.add(attachment)
        db_session.commit()
        db_session.refresh(attachment)
        _sync_notifications(db_session)
        _write_audit_log(
            db_session,
            _current_user,
            action="attachment.upload",
            entity_type="attachment",
            entity_id=attachment.attachment_id,
            details=f"candidate_id={id};source={attachment.source or ''}",
        )
        return {"attachment": _model_to_dict(attachment)}
    except HTTPException:
        raise
    except Exception as exc:
        db_session.rollback()
        logger.exception("Attachment upload failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to upload attachment") from exc


@app.delete("/attachments/{attach_id}")
def delete_attachment(
    attach_id: int,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_roles("admin", "recruiter")),
) -> dict[str, Any]:
    attachment = db_session.get(Attachment, attach_id)
    if not attachment:
        raise HTTPException(status_code=404, detail=f"Attachment {attach_id} not found")

    file_path = Path(attachment.file_path)
    db_session.delete(attachment)
    db_session.commit()
    file_path.unlink(missing_ok=True)
    _write_audit_log(
        db_session,
        _current_user,
        action="attachment.delete",
        entity_type="attachment",
        entity_id=attach_id,
        details=f"candidate_id={attachment.candidate_id}",
    )
    return {"status": "ok", "deleted_attachment_id": attach_id}


@app.get("/attachments/{attach_id}/download")
def download_attachment(
    attach_id: int,
    db_session: Session = Depends(get_db_session),
    _current_user: User = Depends(require_crm_user),
) -> FileResponse:
    attachment = db_session.get(Attachment, attach_id)
    if not attachment:
        raise HTTPException(status_code=404, detail=f"Attachment {attach_id} not found")

    file_path = Path(attachment.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Attachment file does not exist")

    candidate = _load_candidate_for_templates(db_session, attachment.candidate_id)
    raw_name = attachment_download_filename(db_session, candidate, attachment)
    safe_disp = raw_name.replace('"', "")
    content_disposition = f"attachment; filename=\"{safe_disp}\"; filename*=UTF-8''{quote(raw_name)}"
    return FileResponse(
        path=file_path,
        media_type=attachment.file_type or "application/octet-stream",
        headers=_nosniff_headers({"Content-Disposition": content_disposition}),
    )
