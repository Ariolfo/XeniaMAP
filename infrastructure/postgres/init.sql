-- XeniaMAP cold-start schema (Docker /docker-entrypoint-initdb.d).
-- Runs only on empty Postgres volume. Always follow with: alembic upgrade head
-- See docs/ops/bootstrap.md

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_raster;

CREATE TABLE IF NOT EXISTS tenants (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'cliente',
    tenant_id INT NOT NULL REFERENCES tenants(id),
    created_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'cliente';
ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;

CREATE TABLE IF NOT EXISTS user_audit_log (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    actor_user_id INT REFERENCES users(id) ON DELETE SET NULL,
    target_user_id INT,
    action VARCHAR(40) NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_user_audit_log_created_at ON user_audit_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_audit_log_action ON user_audit_log (action);

-- projects before study_orders / fire_orders (FK targets)
CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    owner_user_id INT REFERENCES users(id),
    status VARCHAR(32) NOT NULL DEFAULT 'pendiente',
    module VARCHAR(32) NOT NULL DEFAULT 'agro',
    processed_by_admin_id INT REFERENCES users(id),
    approved_by_admin_id INT REFERENCES users(id),
    processing_started_at TIMESTAMP,
    processing_completed_at TIMESTAMP,
    published_at TIMESTAMP,
    tenant_id INT NOT NULL REFERENCES tenants(id),
    created_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE projects ADD COLUMN IF NOT EXISTS owner_user_id INT REFERENCES users(id);
ALTER TABLE projects ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'pendiente';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS module VARCHAR(32) NOT NULL DEFAULT 'agro';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS processed_by_admin_id INT REFERENCES users(id);
ALTER TABLE projects ADD COLUMN IF NOT EXISTS approved_by_admin_id INT REFERENCES users(id);
ALTER TABLE projects ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMP;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS processing_completed_at TIMESTAMP;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS published_at TIMESTAMP;
CREATE INDEX IF NOT EXISTS ix_projects_module ON projects (module);

CREATE TABLE IF NOT EXISTS study_orders (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id),
    project_id INT REFERENCES projects(id),
    tenant_id INT NOT NULL REFERENCES tenants(id),
    applicant_name VARCHAR(255) NOT NULL,
    applicant_phone VARCHAR(50) NOT NULL,
    company VARCHAR(255),
    crop VARCHAR(255),
    age_years INT,
    study_date_start DATE NOT NULL,
    study_date_end DATE NOT NULL,
    has_weather_data BOOLEAN NOT NULL DEFAULT false,
    has_soil_data BOOLEAN NOT NULL DEFAULT false,
    extra_notes TEXT,
    geometry_geojson JSONB NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pendiente',
    assigned_admin_id INT REFERENCES users(id),
    processing_started_at TIMESTAMP,
    processing_completed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_study_orders_user ON study_orders (user_id);
CREATE INDEX IF NOT EXISTS idx_study_orders_status ON study_orders (status);
CREATE INDEX IF NOT EXISTS idx_study_orders_created ON study_orders (created_at DESC);

ALTER TABLE study_orders ADD COLUMN IF NOT EXISTS project_id INT REFERENCES projects(id);
ALTER TABLE study_orders ADD COLUMN IF NOT EXISTS assigned_admin_id INT REFERENCES users(id);
ALTER TABLE study_orders ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMP;
ALTER TABLE study_orders ADD COLUMN IF NOT EXISTS processing_completed_at TIMESTAMP;

-- Fire (full pipeline shape; mirrors Alembic 20260904 + 20260905)
CREATE TABLE IF NOT EXISTS fire_orders (
    id SERIAL PRIMARY KEY,
    tenant_id INT NOT NULL REFERENCES tenants(id),
    created_by_user_id INT REFERENCES users(id),
    project_id INT REFERENCES projects(id),
    request_name VARCHAR(255) NOT NULL,
    department VARCHAR(255),
    applicant_name VARCHAR(255) NOT NULL,
    applicant_email VARCHAR(255) NOT NULL DEFAULT '',
    applicant_phone VARCHAR(50) NOT NULL DEFAULT '',
    company VARCHAR(255),
    geometry_geojson JSONB NOT NULL,
    pre_start DATE NOT NULL,
    pre_end DATE NOT NULL,
    post_start DATE NOT NULL,
    post_end DATE NOT NULL,
    max_cloud_cover INT NOT NULL DEFAULT 95,
    status VARCHAR(32) NOT NULL DEFAULT 'pendiente',
    download_task_id VARCHAR(255),
    download_message TEXT,
    download_manifest JSONB,
    data_root VARCHAR(1024),
    results_root VARCHAR(1024),
    process_task_id VARCHAR(255),
    process_message TEXT,
    process_manifest JSONB,
    firms_task_id VARCHAR(255),
    firms_message TEXT,
    firms_manifest JSONB,
    source_key VARCHAR(255),
    extra_notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_fire_orders_source_key UNIQUE (source_key)
);
CREATE INDEX IF NOT EXISTS ix_fire_orders_tenant_id ON fire_orders (tenant_id);
CREATE INDEX IF NOT EXISTS ix_fire_orders_status ON fire_orders (status);
CREATE INDEX IF NOT EXISTS ix_fire_orders_source_key ON fire_orders (source_key);
CREATE INDEX IF NOT EXISTS ix_fire_orders_created_by_user_id ON fire_orders (created_by_user_id);
CREATE INDEX IF NOT EXISTS ix_fire_orders_project_id ON fire_orders (project_id);

CREATE TABLE IF NOT EXISTS project_shares (
    id SERIAL PRIMARY KEY,
    project_id INT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    granted_by_user_id INT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_project_shares_user ON project_shares (user_id);
CREATE INDEX IF NOT EXISTS idx_project_shares_project ON project_shares (project_id);

CREATE TABLE IF NOT EXISTS project_processing_log (
    id SERIAL PRIMARY KEY,
    project_id INT NOT NULL REFERENCES projects(id),
    order_id INT REFERENCES study_orders(id),
    actor_admin_id INT REFERENCES users(id),
    stage VARCHAR(40) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'ok',
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_project_processing_log_project ON project_processing_log (project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_project_processing_log_order ON project_processing_log (order_id, created_at DESC);

CREATE TABLE IF NOT EXISTS layers (
    id SERIAL PRIMARY KEY,
    project_id INT NOT NULL REFERENCES projects(id),
    tenant_id INT NOT NULL REFERENCES tenants(id),
    name VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    geom_type VARCHAR(50) DEFAULT 'Geometry',
    geom geometry,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS raster_layers (
    id SERIAL PRIMARY KEY,
    project_id INT NOT NULL REFERENCES projects(id),
    tenant_id INT NOT NULL REFERENCES tenants(id),
    name VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    cog_path TEXT,
    rast raster,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ai_results (
    id SERIAL PRIMARY KEY,
    project_id INT NOT NULL REFERENCES projects(id),
    tenant_id INT NOT NULL REFERENCES tenants(id),
    model_type VARCHAR(120) NOT NULL,
    status VARCHAR(50) NOT NULL,
    output_path TEXT,
    metrics JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS project_landing_texts (
    id SERIAL PRIMARY KEY,
    project_id INT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    tenant_id INT NOT NULL REFERENCES tenants(id),
    section_key VARCHAR(120) NOT NULL,
    draft_body TEXT NOT NULL DEFAULT '',
    published_body TEXT NOT NULL DEFAULT '',
    updated_by_user_id INT REFERENCES users(id) ON DELETE SET NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    published_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, section_key)
);
CREATE INDEX IF NOT EXISTS idx_project_landing_texts_project ON project_landing_texts (project_id);
CREATE INDEX IF NOT EXISTS idx_project_landing_texts_section ON project_landing_texts (project_id, section_key);

CREATE INDEX IF NOT EXISTS idx_layers_geom_gist ON layers USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_raster_layers_rast_gist ON raster_layers USING GIST (st_convexhull(rast));
