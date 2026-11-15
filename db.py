import sqlite3
from pathlib import Path

from flask import current_app, g

from config import Config


_REQUIRED_COLUMNS = {
    "buildings": {
        "building_id",
        "building_name",
        "latitude",
        "longitude",
        "description",
        "wheelchair_accessible",
    },
    "pathways": {
        "pathway_id",
        "start_building_id",
        "end_building_id",
        "distance_meters",
        "foot_traffic",
        "has_stairs",
        "wheelchair_accessible",
    },
    "traveltimeobservations": {
        "observation_id",
        "pathway_id",
        "foot_traffic",
        "travel_time_seconds",
        "observed_at",
    },
}


def _validate_existing_schema(connection):
    existing_tables = {
        row["name"].lower()
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }

    for table_name, required_columns in _REQUIRED_COLUMNS.items():
        if table_name not in existing_tables:
            continue

        columns = {
            row["name"].lower()
            for row in connection.execute(f"PRAGMA table_info({table_name})")
        }
        missing_columns = required_columns - columns
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise RuntimeError(
                f"The existing {table_name} table is missing columns: {missing}. "
                "Back up and migrate the database, or choose a new DATABASE_NAME. "
                "The existing database was not changed."
            )


def initialize_database(database_path=None):
    """Create the configured database schema without overwriting existing tables."""
    database_path = database_path or Config.DATABASE_NAME
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    schema_path = Path(__file__).resolve().parent / "database" / "schema.sql"

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        _validate_existing_schema(connection)
        connection.executescript(schema_path.read_text(encoding="utf-8"))
    finally:
        connection.close()


def get_db():
    """Return one SQLite connection for the current Flask request."""
    if "database" not in g:
        connection = sqlite3.connect(current_app.config["DATABASE_NAME"])
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        g.database = connection
    return g.database


def close_db(exception=None):
    connection = g.pop("database", None)
    if connection is not None:
        connection.close()


def init_app(app):
    app.teardown_appcontext(close_db)
