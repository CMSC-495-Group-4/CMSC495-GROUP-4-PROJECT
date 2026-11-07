import sqlite3


def initialize_database(database_path="campus.db"):
    """Create the initial buildings and pathways tables."""
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS Buildings (
                building_id INTEGER PRIMARY KEY,
                building_name TEXT NOT NULL,
                is_accessible BOOLEAN NOT NULL CHECK (is_accessible IN (0, 1))
            );

            CREATE TABLE IF NOT EXISTS Pathways (
                pathway_id INTEGER PRIMARY KEY,
                start_building_id INTEGER NOT NULL,
                end_building_id INTEGER NOT NULL,
                distance_meters REAL NOT NULL CHECK (distance_meters >= 0),
                is_accessible BOOLEAN NOT NULL CHECK (is_accessible IN (0, 1)),
                FOREIGN KEY (start_building_id) REFERENCES Buildings (building_id),
                FOREIGN KEY (end_building_id) REFERENCES Buildings (building_id)
            );
            """
        )
