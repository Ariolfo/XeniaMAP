from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.session import Base


class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False, default="")
    role = Column(String(20), nullable=False, default="cliente")
    is_active = Column(Boolean, nullable=False, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class UserAuditLog(Base):
    __tablename__ = "user_audit_log"
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    target_user_id = Column(Integer, nullable=True, index=True)
    action = Column(String(40), nullable=False, index=True)
    details = Column(JSON, default=dict)


class StudyOrder(Base):
    __tablename__ = "study_orders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    applicant_name = Column(String(255), nullable=False)
    applicant_phone = Column(String(50), nullable=False)
    company = Column(String(255), nullable=True)
    crop = Column(String(255), nullable=True)
    age_years = Column(Integer, nullable=True)
    study_date_start = Column(Date, nullable=False)
    study_date_end = Column(Date, nullable=False)
    has_weather_data = Column(Boolean, nullable=False, default=False)
    has_soil_data = Column(Boolean, nullable=False, default=False)
    extra_notes = Column(Text, nullable=True)
    geometry_geojson = Column(JSON, nullable=False)
    status = Column(String(32), nullable=False, default="pendiente")
    assigned_admin_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    processing_started_at = Column(DateTime, nullable=True)
    processing_completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class FireOrder(Base):
    """Solicitud independiente de análisis de severidad de incendios (módulo Fire)."""

    __tablename__ = "fire_orders"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, index=True)
    request_name = Column(String(255), nullable=False)
    department = Column(String(255), nullable=True)
    applicant_name = Column(String(255), nullable=False)
    applicant_email = Column(String(255), nullable=False, default="")
    applicant_phone = Column(String(50), nullable=False, default="")
    company = Column(String(255), nullable=True)
    geometry_geojson = Column(JSON, nullable=False)
    pre_start = Column(Date, nullable=False)
    pre_end = Column(Date, nullable=False)
    post_start = Column(Date, nullable=False)
    post_end = Column(Date, nullable=False)
    max_cloud_cover = Column(Integer, nullable=False, default=95)
    status = Column(String(32), nullable=False, default="pendiente", index=True)
    download_task_id = Column(String(255), nullable=True)
    download_message = Column(Text, nullable=True)
    download_manifest = Column(JSON, nullable=True)
    data_root = Column(String(1024), nullable=True)
    results_root = Column(String(1024), nullable=True)
    process_task_id = Column(String(255), nullable=True)
    process_message = Column(Text, nullable=True)
    process_manifest = Column(JSON, nullable=True)
    firms_task_id = Column(String(255), nullable=True)
    firms_message = Column(Text, nullable=True)
    firms_manifest = Column(JSON, nullable=True)
    source_key = Column(String(255), nullable=True, unique=True, index=True)
    extra_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ProjectShare(Base):
    """Acceso de lectura de un cliente a un proyecto de otro usuario (mismo tenant)."""
    __tablename__ = "project_shares"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    granted_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="pendiente")
    # Dominio/módulo: agro | fire | og | ch4 (cada módulo lista solo los suyos)
    module = Column(String(32), nullable=False, default="agro", index=True)
    processed_by_admin_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    approved_by_admin_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    processing_started_at = Column(DateTime, nullable=True)
    processing_completed_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    layers = relationship("Layer", back_populates="project")
    rasters = relationship("RasterLayer", back_populates="project")


class Layer(Base):
    __tablename__ = "layers"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False)
    geom_type = Column(String(50), nullable=False, default="Geometry")
    layer_metadata = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    project = relationship("Project", back_populates="layers")


class RasterLayer(Base):
    __tablename__ = "raster_layers"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False)
    cog_path = Column(Text)
    raster_metadata = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    project = relationship("Project", back_populates="rasters")


class AIResult(Base):
    __tablename__ = "ai_results"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    model_type = Column(String(120), nullable=False)
    status = Column(String(50), nullable=False, default="queued")
    output_path = Column(Text)
    metrics = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ProjectLandingText(Base):
    """Textos narrativos por subsección de la landing (borrador vs publicado)."""

    __tablename__ = "project_landing_texts"
    __table_args__ = (UniqueConstraint("project_id", "section_key", name="uq_project_landing_texts_project_section"),)
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    section_key = Column(String(120), nullable=False, index=True)
    draft_body = Column(Text, nullable=False, default="")
    published_body = Column(Text, nullable=False, default="")
    updated_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ProjectProcessingLog(Base):
    __tablename__ = "project_processing_log"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("study_orders.id"), nullable=True, index=True)
    actor_admin_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    stage = Column(String(40), nullable=False, index=True)
    status = Column(String(24), nullable=False, default="ok")
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
