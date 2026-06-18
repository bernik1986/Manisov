from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .candidate_names import normalize_candidate_name_instance


class Role(Base):
    __tablename__ = "roles"

    role_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255))

    users: Mapped[list["User"]] = relationship(back_populates="role")


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(150))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.role_id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    role: Mapped[Role | None] = relationship(back_populates="users")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user")


class Candidate(Base):
    __tablename__ = "candidates"

    # A. Candidate profile / identification
    candidate_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.company_id", ondelete="SET NULL"), index=True)
    application_id: Mapped[int | None] = mapped_column(Integer, index=True)
    erp_no: Mapped[str | None] = mapped_column(String(100), index=True)
    e_registration_no: Mapped[str | None] = mapped_column(String(100), index=True)
    application_form_no: Mapped[str | None] = mapped_column(String(100))
    cv_prepared_by: Mapped[str | None] = mapped_column(String(100))
    record_status: Mapped[str | None] = mapped_column(String(50), default="active")
    source_form_type: Mapped[str | None] = mapped_column(String(100))
    source_file_name: Mapped[str | None] = mapped_column(String(255))
    cv_imported: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # JSON object of ukr_* string fields for Ukrainian labour contract (docxtpl placeholders).
    ukr_contract_json: Mapped[str | None] = mapped_column(Text)
    # JSON object of saved salary calculator result (COE / contract placeholders).
    salary_calculation_json: Mapped[str | None] = mapped_column(Text)
    # JSON object of sea contract tab selections and editable contract fields.
    contract_json: Mapped[str | None] = mapped_column(Text)

    # C. Personal data
    surname: Mapped[str | None] = mapped_column(String(100), index=True)
    first_name: Mapped[str | None] = mapped_column(String(100), index=True)
    middle_name: Mapped[str | None] = mapped_column(String(100))
    full_name: Mapped[str | None] = mapped_column(String(255), index=True)
    latin_full_name: Mapped[str | None] = mapped_column(String(255))
    native_full_name: Mapped[str | None] = mapped_column(String(255))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    place_of_birth: Mapped[str | None] = mapped_column(String(150))
    country_of_birth: Mapped[str | None] = mapped_column(String(100))
    nationality: Mapped[str | None] = mapped_column(String(100))
    citizenship: Mapped[str | None] = mapped_column(String(100))
    age: Mapped[int | None] = mapped_column(Integer)
    gender: Mapped[str | None] = mapped_column(String(50))
    marital_status: Mapped[str | None] = mapped_column(String(50))
    father_name: Mapped[str | None] = mapped_column(String(150))
    mother_name: Mapped[str | None] = mapped_column(String(150))
    primary_phone: Mapped[str | None] = mapped_column(String(50))
    secondary_phone: Mapped[str | None] = mapped_column(String(50))
    mobile_phone: Mapped[str | None] = mapped_column(String(50))
    telephone_no: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    secondary_email: Mapped[str | None] = mapped_column(String(255))
    skype_id: Mapped[str | None] = mapped_column(String(100))
    permanent_address: Mapped[str | None] = mapped_column(String(255))
    home_address: Mapped[str | None] = mapped_column(String(255))
    current_address: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(30))
    country: Mapped[str | None] = mapped_column(String(100))

    # D. Family / dependants / kin / beneficiary
    spouse_name: Mapped[str | None] = mapped_column(String(150))
    number_of_children: Mapped[int | None] = mapped_column(Integer)
    children_under_18_count: Mapped[int | None] = mapped_column(Integer)
    dependants_count: Mapped[int | None] = mapped_column(Integer)
    sons_count: Mapped[int | None] = mapped_column(Integer)
    daughters_count: Mapped[int | None] = mapped_column(Integer)
    beneficiary_full_name: Mapped[str | None] = mapped_column(String(150))
    beneficiary_relationship: Mapped[str | None] = mapped_column(String(100))
    beneficiary_address: Mapped[str | None] = mapped_column(String(255))
    beneficiary_phone: Mapped[str | None] = mapped_column(String(50))
    next_of_kin_relationship: Mapped[str | None] = mapped_column(String(100))
    next_of_kin_surname: Mapped[str | None] = mapped_column(String(100))
    next_of_kin_first_name: Mapped[str | None] = mapped_column(String(100))
    next_of_kin_full_name: Mapped[str | None] = mapped_column(String(150))
    next_of_kin_address: Mapped[str | None] = mapped_column(String(255))
    next_of_kin_phone: Mapped[str | None] = mapped_column(String(50))

    # E. Education & languages
    highest_educational_attainment: Mapped[str | None] = mapped_column(String(150))
    school_name: Mapped[str | None] = mapped_column(String(150))
    graduation_year: Mapped[int | None] = mapped_column(Integer)
    education_notes: Mapped[str | None] = mapped_column(Text)
    native_language: Mapped[str | None] = mapped_column(String(100))
    english_level: Mapped[str | None] = mapped_column(String(100))
    english_certificate: Mapped[str | None] = mapped_column(String(150))
    other_languages: Mapped[str | None] = mapped_column(Text)

    # F. Physical data
    height_cm: Mapped[float | None] = mapped_column(Float)
    height_m: Mapped[float | None] = mapped_column(Float)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    distinctive_marks: Mapped[str | None] = mapped_column(Text)

    # G. Professional summary
    current_rank: Mapped[str | None] = mapped_column(String(100), index=True)
    certificate_of_competency_rank: Mapped[str | None] = mapped_column(String(100))
    certificate_of_competency_number: Mapped[str | None] = mapped_column(String(100))
    watchkeeping_capacity: Mapped[str | None] = mapped_column(String(100))
    total_sea_service: Mapped[str | None] = mapped_column(String(100))
    total_sea_service_in_rank: Mapped[str | None] = mapped_column(String(100))
    years_in_rank: Mapped[float | None] = mapped_column(Float)
    years_in_this_type_of_vessel: Mapped[float | None] = mapped_column(Float)
    years_in_all_types_of_tankers: Mapped[float | None] = mapped_column(Float)
    years_as_watch_officer: Mapped[float | None] = mapped_column(Float)
    total_years_of_sea_service: Mapped[float | None] = mapped_column(Float)
    rank_experience_summary: Mapped[str | None] = mapped_column(Text)

    # H. Vessel experience summary
    bulk_carrier_years_in_rank: Mapped[float | None] = mapped_column(Float)
    bulk_carrier_years_in_vessel_type: Mapped[float | None] = mapped_column(Float)
    tanker_years_in_rank: Mapped[float | None] = mapped_column(Float)
    tanker_years_in_this_tanker_type: Mapped[float | None] = mapped_column(Float)
    tanker_years_in_all_tanker_types: Mapped[float | None] = mapped_column(Float)
    watch_officer_since_year: Mapped[int | None] = mapped_column(Integer)
    oil_tanker_experience: Mapped[bool | None] = mapped_column(Boolean)
    chemical_tanker_experience: Mapped[bool | None] = mapped_column(Boolean)
    gas_tanker_experience: Mapped[bool | None] = mapped_column(Boolean)
    lng_experience: Mapped[bool | None] = mapped_column(Boolean)
    lpg_experience: Mapped[bool | None] = mapped_column(Boolean)
    container_experience: Mapped[bool | None] = mapped_column(Boolean)
    bulk_carrier_experience: Mapped[bool | None] = mapped_column(Boolean)
    general_cargo_experience: Mapped[bool | None] = mapped_column(Boolean)
    offshore_experience: Mapped[bool | None] = mapped_column(Boolean)

    # M. Medical / visa summary
    medical_fitness_certificate_number: Mapped[str | None] = mapped_column(String(100))
    medical_fitness_issue_date: Mapped[date | None] = mapped_column(Date)
    medical_fitness_expiry_date: Mapped[date | None] = mapped_column(Date)
    yellow_fever_issue_date: Mapped[date | None] = mapped_column(Date)
    yellow_fever_expiry_date: Mapped[date | None] = mapped_column(Date)
    yellow_fever_unlimited: Mapped[bool | None] = mapped_column(Boolean)
    usa_visa_number: Mapped[str | None] = mapped_column(String(100))
    usa_visa_issue_date: Mapped[date | None] = mapped_column(Date)
    usa_visa_expiry_date: Mapped[date | None] = mapped_column(Date)
    usa_visa_place_of_issue: Mapped[str | None] = mapped_column(String(150))
    visa_status_note: Mapped[str | None] = mapped_column(Text)

    # Submission / info-list (ПОДАЧА); also edited on Contract tab
    home_airport: Mapped[str | None] = mapped_column(String(255))
    departure_airport: Mapped[str | None] = mapped_column(String(255))
    desirable_salary_usd: Mapped[float | None] = mapped_column(Float)
    rejoin_bonus_usd: Mapped[float | None] = mapped_column(Float)
    submission_contract_duration_text: Mapped[str | None] = mapped_column(String(100))
    ecdis_systems_text: Mapped[str | None] = mapped_column(Text)
    vaccination_summary: Mapped[str | None] = mapped_column(Text)
    leaving_reason: Mapped[str | None] = mapped_column(Text)
    employer_reference_note: Mapped[str | None] = mapped_column(Text)
    passport_visa_status_note: Mapped[str | None] = mapped_column(Text)
    coc_gmdss_expiry_note: Mapped[str | None] = mapped_column(Text)
    coc_has_qr_codes: Mapped[bool | None] = mapped_column(Boolean)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    seaman_book_number: Mapped[str | None] = mapped_column(String(100))
    passport_number: Mapped[str | None] = mapped_column(String(100))
    passport_issue_date: Mapped[date | None] = mapped_column(Date)
    passport_expiry_date: Mapped[date | None] = mapped_column(Date)
    passport_place_of_issue: Mapped[str | None] = mapped_column(String(150))

    applications: Mapped[list["Application"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")
    documents: Mapped[list["Document"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")
    certificates: Mapped[list["Certificate"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")
    flag_documents: Mapped[list["FlagDocument"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")
    sea_service: Mapped[list["SeaService"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")
    family_contacts: Mapped[list["FamilyContact"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")
    comments: Mapped[list["CandidateComment"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")
    company: Mapped["Company | None"] = relationship(back_populates="candidates")


@event.listens_for(Candidate, "before_insert")
@event.listens_for(Candidate, "before_update")
def _uppercase_candidate_names_before_save(_mapper, _connection, candidate: Candidate) -> None:
    normalize_candidate_name_instance(candidate)


class Application(Base):
    __tablename__ = "applications"

    application_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.candidate_id"), nullable=False, index=True)
    position_applied_for: Mapped[str | None] = mapped_column(String(150), index=True)
    rank_applied_for: Mapped[str | None] = mapped_column(String(100), index=True)
    willing_to_accept_lower_rank: Mapped[bool | None] = mapped_column(Boolean)
    proposed_vessel: Mapped[str | None] = mapped_column(String(150))
    date_applied: Mapped[date | None] = mapped_column(Date)
    date_available: Mapped[date | None] = mapped_column(Date)
    last_salary_usd: Mapped[float | None] = mapped_column(Float)
    applicant_type: Mapped[str | None] = mapped_column(String(50))
    recommended_by_ex_crew: Mapped[bool | None] = mapped_column(Boolean)
    recommended_by_ex_crew_name: Mapped[str | None] = mapped_column(String(150))
    recommended_by_others: Mapped[bool | None] = mapped_column(Boolean)
    recommended_by_others_name: Mapped[str | None] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    candidate: Mapped["Candidate"] = relationship(back_populates="applications")


class Document(Base):
    __tablename__ = "documents"

    document_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.candidate_id"), nullable=False, index=True)
    document_category: Mapped[str | None] = mapped_column(String(100))
    document_type: Mapped[str] = mapped_column(String(100), nullable=False)
    document_name_raw: Mapped[str | None] = mapped_column(String(255))
    document_number: Mapped[str | None] = mapped_column(String(100))
    issuing_authority: Mapped[str | None] = mapped_column(String(150))
    place_of_issue: Mapped[str | None] = mapped_column(String(150))
    date_of_issue: Mapped[date | None] = mapped_column(Date)
    date_of_expiry: Mapped[date | None] = mapped_column(Date, index=True)
    validity_status: Mapped[str | None] = mapped_column(String(50))
    unlimited_validity: Mapped[bool | None] = mapped_column(Boolean)
    country_of_issue: Mapped[str | None] = mapped_column(String(100))
    remarks: Mapped[str | None] = mapped_column(Text)
    scan_file: Mapped[str | None] = mapped_column(String(255))
    verified: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    candidate: Mapped["Candidate"] = relationship(back_populates="documents")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="document")


class Certificate(Base):
    __tablename__ = "certificates"

    certificate_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.candidate_id"), nullable=False, index=True)
    certificate_group: Mapped[str | None] = mapped_column(String(100))
    certificate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    certificate_name_raw: Mapped[str | None] = mapped_column(String(255))
    certificate_code: Mapped[str | None] = mapped_column(String(100))
    certificate_number: Mapped[str | None] = mapped_column(String(100))
    # Rank / capacity on COC (Diploma slot); maps to docxtpl coc_competency_rank.
    competency_rank: Mapped[str | None] = mapped_column(String(150))
    issuing_authority: Mapped[str | None] = mapped_column(String(150))
    date_issued: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date, index=True)
    unlimited_validity: Mapped[bool | None] = mapped_column(Boolean)
    country_of_issue: Mapped[str | None] = mapped_column(String(100))
    is_present: Mapped[bool | None] = mapped_column(Boolean)
    remarks: Mapped[str | None] = mapped_column(Text)
    scan_file: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    candidate: Mapped["Candidate"] = relationship(back_populates="certificates")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="certificate")


class FlagDocument(Base):
    __tablename__ = "flag_documents"

    flag_document_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.candidate_id"), nullable=False, index=True)
    flag_country: Mapped[str] = mapped_column(String(100), nullable=False)
    flag_document_type: Mapped[str | None] = mapped_column(String(100))
    rank: Mapped[str | None] = mapped_column(String(100))
    doc_number: Mapped[str | None] = mapped_column(String(100))
    date_of_issuance: Mapped[date | None] = mapped_column(Date)
    date_of_expiry: Mapped[date | None] = mapped_column(Date, index=True)
    remarks: Mapped[str | None] = mapped_column(Text)
    scan_file: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    candidate: Mapped["Candidate"] = relationship(back_populates="flag_documents")


class SeaService(Base):
    __tablename__ = "sea_services"

    sea_service_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.candidate_id"), nullable=False, index=True)
    vessel_name: Mapped[str | None] = mapped_column(String(150))
    vessel_type: Mapped[str | None] = mapped_column(String(100))
    vessel_subtype: Mapped[str | None] = mapped_column(String(100))
    flag: Mapped[str | None] = mapped_column(String(100))
    imo_number: Mapped[str | None] = mapped_column(String(50))
    year_built: Mapped[int | None] = mapped_column(Integer)
    dwt: Mapped[float | None] = mapped_column(Float)
    grt: Mapped[float | None] = mapped_column(Float)
    main_engine: Mapped[str | None] = mapped_column(String(150))
    engine_power: Mapped[str | None] = mapped_column(String(100))
    ecdis_dg_maker: Mapped[str | None] = mapped_column(String(150))
    rank_on_vessel: Mapped[str | None] = mapped_column(String(100))
    sign_on_date: Mapped[date | None] = mapped_column(Date)
    sign_off_date: Mapped[date | None] = mapped_column(Date)
    contract_duration: Mapped[str | None] = mapped_column(String(100))
    employer: Mapped[str | None] = mapped_column(String(150))
    manning_agency: Mapped[str | None] = mapped_column(String(150))
    trade_area: Mapped[str | None] = mapped_column(String(150))
    cargo_type: Mapped[str | None] = mapped_column(String(100))
    remarks: Mapped[str | None] = mapped_column(Text)

    # Calculated fields (optional persisted cache)
    total_sea_service_duration: Mapped[str | None] = mapped_column(String(100))
    total_sea_service_by_rank: Mapped[str | None] = mapped_column(String(100))
    total_sea_service_by_vessel_type: Mapped[str | None] = mapped_column(String(100))
    tanker_service_duration: Mapped[str | None] = mapped_column(String(100))
    bulk_service_duration: Mapped[str | None] = mapped_column(String(100))
    watch_officer_experience_duration: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    candidate: Mapped["Candidate"] = relationship(back_populates="sea_service")


class FamilyContact(Base):
    __tablename__ = "family_contacts"

    family_contact_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.candidate_id"), nullable=False, index=True)
    contact_type: Mapped[str | None] = mapped_column(String(50))
    surname: Mapped[str | None] = mapped_column(String(100))
    first_name: Mapped[str | None] = mapped_column(String(100))
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    relationship_to_candidate: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(255))
    beneficiary_full_name: Mapped[str | None] = mapped_column(String(150))
    beneficiary_relationship: Mapped[str | None] = mapped_column(String(100))
    beneficiary_address: Mapped[str | None] = mapped_column(String(255))
    beneficiary_phone: Mapped[str | None] = mapped_column(String(50))
    next_of_kin_relationship: Mapped[str | None] = mapped_column(String(100))
    is_emergency_contact: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    candidate: Mapped["Candidate"] = relationship(back_populates="family_contacts")


class Attachment(Base):
    __tablename__ = "attachments"

    attachment_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.candidate_id"), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(50))
    file_path: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str | None] = mapped_column(String(100))
    checksum: Mapped[str | None] = mapped_column(String(100))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    candidate: Mapped["Candidate"] = relationship(back_populates="attachments")


class CandidateComment(Base):
    __tablename__ = "candidate_comments"

    comment_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.candidate_id"), nullable=False, index=True)
    comment_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    candidate: Mapped["Candidate"] = relationship(back_populates="comments")


class CompanyFolder(Base):
    __tablename__ = "company_folders"

    folder_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("company_folders.folder_id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    parent: Mapped["CompanyFolder | None"] = relationship(
        "CompanyFolder",
        remote_side=[folder_id],
        back_populates="children",
    )
    children: Mapped[list["CompanyFolder"]] = relationship(
        "CompanyFolder",
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    companies: Mapped[list["Company"]] = relationship(back_populates="folder", cascade="all, delete-orphan")


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("slug", name="uq_companies_slug"),)

    company_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    folder_id: Mapped[int] = mapped_column(ForeignKey("company_folders.folder_id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    folder: Mapped["CompanyFolder"] = relationship(back_populates="companies")
    vessels: Mapped[list["Vessel"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    salary_templates: Mapped[list["SalaryComponentTemplate"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
    candidates: Mapped[list["Candidate"]] = relationship(back_populates="company", passive_deletes=True)


class SalaryComponentTemplate(Base):
    __tablename__ = "salary_component_templates"
    __table_args__ = (UniqueConstraint("company_id", "rank", name="uq_salary_template_company_rank"),)

    template_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id"), nullable=False, index=True)
    rank: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    basic_monthly_wage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    monthly_overtime: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    overtime_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sepf: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    imtf: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    leave: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    leave_sub: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    various_extra_overtime: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    company: Mapped["Company"] = relationship(back_populates="salary_templates")


class Vessel(Base):
    __tablename__ = "vessels"
    __table_args__ = (UniqueConstraint("company_id", "slug", name="uq_vessels_company_slug"),)

    vessel_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    imo: Mapped[str | None] = mapped_column(String(50))
    flag: Mapped[str | None] = mapped_column(String(100))
    port_of_registry: Mapped[str | None] = mapped_column(String(150))
    vessel_type: Mapped[str | None] = mapped_column(String(100))
    registry_address: Mapped[str | None] = mapped_column(String(255))
    official_number: Mapped[str | None] = mapped_column(String(80))
    call_sign: Mapped[str | None] = mapped_column(String(50))
    grt: Mapped[str | None] = mapped_column(String(50))
    deadweight: Mapped[str | None] = mapped_column(String(50))
    year_built: Mapped[int | None] = mapped_column(Integer)
    engine_type: Mapped[str | None] = mapped_column(String(150))
    engine_hp: Mapped[str | None] = mapped_column(String(80))
    classification_society: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    company: Mapped["Company"] = relationship(back_populates="vessels")


class TemplateFolder(Base):
    __tablename__ = "template_folders"

    folder_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("template_folders.folder_id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    parent: Mapped["TemplateFolder | None"] = relationship(
        "TemplateFolder",
        remote_side=[folder_id],
        back_populates="children",
    )
    children: Mapped[list["TemplateFolder"]] = relationship(
        "TemplateFolder",
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    files: Mapped[list["TemplateFile"]] = relationship(back_populates="folder", cascade="all, delete-orphan")


class TemplateFile(Base):
    __tablename__ = "template_files"

    template_file_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    folder_id: Mapped[int] = mapped_column(ForeignKey("template_folders.folder_id"), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(50))
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    folder: Mapped["TemplateFolder"] = relationship(back_populates="files")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"), index=True)
    username: Mapped[str | None] = mapped_column(String(100))
    role_name: Mapped[str | None] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(120), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(120), index=True)
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    user: Mapped["User | None"] = relationship(back_populates="audit_logs")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.candidate_id"), nullable=False, index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.document_id"), nullable=True, index=True)
    certificate_id: Mapped[int | None] = mapped_column(ForeignKey("certificates.certificate_id"), nullable=True, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    candidate: Mapped["Candidate"] = relationship(back_populates="notifications")
    document: Mapped["Document | None"] = relationship(back_populates="notifications")
    certificate: Mapped["Certificate | None"] = relationship(back_populates="notifications")
