from sqlalchemy import create_engine, text
from app.core.config import settings

e = create_engine(settings.database_url)
stmts = [
    """
    CREATE TABLE IF NOT EXISTS fire_orders (
      id SERIAL PRIMARY KEY,
      tenant_id INTEGER NOT NULL REFERENCES tenants(id),
      created_by_user_id INTEGER REFERENCES users(id),
      request_name VARCHAR(255) NOT NULL,
      department VARCHAR(255),
      applicant_name VARCHAR(255) NOT NULL,
      applicant_email VARCHAR(255) NOT NULL DEFAULT '',
      applicant_phone VARCHAR(50) NOT NULL DEFAULT '',
      company VARCHAR(255),
      geometry_geojson JSON NOT NULL,
      pre_start DATE NOT NULL,
      pre_end DATE NOT NULL,
      post_start DATE NOT NULL,
      post_end DATE NOT NULL,
      max_cloud_cover INTEGER NOT NULL DEFAULT 95,
      status VARCHAR(32) NOT NULL DEFAULT 'pendiente',
      download_task_id VARCHAR(255),
      download_message TEXT,
      download_manifest JSON,
      data_root VARCHAR(1024),
      source_key VARCHAR(255) UNIQUE,
      extra_notes TEXT,
      created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_fire_orders_tenant_id ON fire_orders (tenant_id)",
    "CREATE INDEX IF NOT EXISTS ix_fire_orders_status ON fire_orders (status)",
    "CREATE INDEX IF NOT EXISTS ix_fire_orders_source_key ON fire_orders (source_key)",
    "CREATE INDEX IF NOT EXISTS ix_fire_orders_created_by_user_id ON fire_orders (created_by_user_id)",
    "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)",
]
with e.begin() as conn:
    for s in stmts:
        conn.execute(text(s))
    conn.execute(text("DELETE FROM alembic_version"))
    conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('20260904_fire_orders')"))
print("OK fire_orders")
