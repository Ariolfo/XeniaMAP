"""Ensure fire_orders exists and has pipeline columns (idempotent).

Does NOT stamp/clobber alembic_version. Use Alembic for version history:
  cd backend && alembic upgrade head
"""

from sqlalchemy import create_engine, inspect, text

from app.core.config import settings

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS fire_orders (
  id SERIAL PRIMARY KEY,
  tenant_id INTEGER NOT NULL REFERENCES tenants(id),
  created_by_user_id INTEGER REFERENCES users(id),
  project_id INTEGER REFERENCES projects(id),
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
  results_root VARCHAR(1024),
  process_task_id VARCHAR(255),
  process_message TEXT,
  process_manifest JSON,
  firms_task_id VARCHAR(255),
  firms_message TEXT,
  firms_manifest JSON,
  source_key VARCHAR(255) UNIQUE,
  extra_notes TEXT,
  created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
)
"""

ADD_COLUMNS = [
    ("project_id", "ALTER TABLE fire_orders ADD COLUMN IF NOT EXISTS project_id INTEGER"),
    ("results_root", "ALTER TABLE fire_orders ADD COLUMN IF NOT EXISTS results_root VARCHAR(1024)"),
    ("process_task_id", "ALTER TABLE fire_orders ADD COLUMN IF NOT EXISTS process_task_id VARCHAR(255)"),
    ("process_message", "ALTER TABLE fire_orders ADD COLUMN IF NOT EXISTS process_message TEXT"),
    ("process_manifest", "ALTER TABLE fire_orders ADD COLUMN IF NOT EXISTS process_manifest JSON"),
    ("firms_task_id", "ALTER TABLE fire_orders ADD COLUMN IF NOT EXISTS firms_task_id VARCHAR(255)"),
    ("firms_message", "ALTER TABLE fire_orders ADD COLUMN IF NOT EXISTS firms_message TEXT"),
    ("firms_manifest", "ALTER TABLE fire_orders ADD COLUMN IF NOT EXISTS firms_manifest JSON"),
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_fire_orders_tenant_id ON fire_orders (tenant_id)",
    "CREATE INDEX IF NOT EXISTS ix_fire_orders_status ON fire_orders (status)",
    "CREATE INDEX IF NOT EXISTS ix_fire_orders_source_key ON fire_orders (source_key)",
    "CREATE INDEX IF NOT EXISTS ix_fire_orders_created_by_user_id ON fire_orders (created_by_user_id)",
    "CREATE INDEX IF NOT EXISTS ix_fire_orders_project_id ON fire_orders (project_id)",
]


def main() -> None:
    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE))
        for _, stmt in ADD_COLUMNS:
            conn.execute(text(stmt))
        for stmt in INDEXES:
            conn.execute(text(stmt))

        # FK project_id if missing (Postgres).
        insp = inspect(conn)
        fk_names = {fk.get("name") for fk in insp.get_foreign_keys("fire_orders")}
        if "fire_orders_project_id_fkey" not in fk_names:
            conn.execute(
                text(
                    """
                    DO $$
                    BEGIN
                      IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'fire_orders_project_id_fkey'
                      ) THEN
                        ALTER TABLE fire_orders
                          ADD CONSTRAINT fire_orders_project_id_fkey
                          FOREIGN KEY (project_id) REFERENCES projects(id);
                      END IF;
                    END $$;
                    """
                )
            )

    print("OK fire_orders schema aligned (no alembic_version stamp)")


if __name__ == "__main__":
    main()
