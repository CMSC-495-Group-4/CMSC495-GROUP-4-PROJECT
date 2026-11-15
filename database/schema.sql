PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS Buildings (
    building_id INTEGER PRIMARY KEY,
    building_name TEXT NOT NULL,
    latitude REAL NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude REAL NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    description TEXT,
    wheelchair_accessible INTEGER NOT NULL
        CHECK (wheelchair_accessible IN (0, 1))
);

CREATE TABLE IF NOT EXISTS Pathways (
    pathway_id INTEGER PRIMARY KEY,
    start_building_id INTEGER NOT NULL,
    end_building_id INTEGER NOT NULL,
    distance_meters REAL NOT NULL CHECK (distance_meters >= 0),
    foot_traffic TEXT NOT NULL
        CHECK (foot_traffic IN ('low', 'medium', 'high')),
    has_stairs INTEGER NOT NULL CHECK (has_stairs IN (0, 1)),
    wheelchair_accessible INTEGER NOT NULL
        CHECK (wheelchair_accessible IN (0, 1)),
    FOREIGN KEY (start_building_id) REFERENCES Buildings (building_id),
    FOREIGN KEY (end_building_id) REFERENCES Buildings (building_id)
);

CREATE TABLE IF NOT EXISTS TravelTimeObservations (
    observation_id INTEGER PRIMARY KEY,
    pathway_id INTEGER NOT NULL,
    foot_traffic TEXT NOT NULL
        CHECK (foot_traffic IN ('low', 'medium', 'high')),
    travel_time_seconds REAL NOT NULL CHECK (travel_time_seconds > 0),
    observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pathway_id) REFERENCES Pathways (pathway_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pathways_start_building
    ON Pathways (start_building_id);

CREATE INDEX IF NOT EXISTS idx_pathways_end_building
    ON Pathways (end_building_id);

CREATE INDEX IF NOT EXISTS idx_travel_time_observations_pathway
    ON TravelTimeObservations (pathway_id);
