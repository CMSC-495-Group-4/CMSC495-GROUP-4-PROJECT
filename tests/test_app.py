import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import create_app
from db import get_db, initialize_database


class CampusNavigationApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        database_path = str(Path(self.temporary_directory.name) / "test.db")
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE_NAME": database_path,
            }
        )
        self.client = self.app.test_client()

        with self.app.app_context():
            connection = get_db()
            connection.executemany(
                """
                INSERT INTO Buildings
                    (building_id, building_name, latitude, longitude,
                     wheelchair_accessible)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (1, "Library", 39.0, -76.0, 1),
                    (2, "Science", 39.1, -76.1, 1),
                    (3, "Center", 39.2, -76.2, 1),
                    (4, "Hall", 39.3, -76.3, 1),
                ],
            )
            connection.executemany(
                """
                INSERT INTO Pathways
                    (pathway_id, start_building_id, end_building_id,
                     distance_meters, foot_traffic, has_stairs,
                     wheelchair_accessible)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (10, 1, 2, 100, "low", 0, 1),
                    (11, 2, 3, 100, "medium", 0, 1),
                    (12, 1, 3, 500, "high", 0, 1),
                    (13, 3, 4, 30, "low", 1, 0),
                ],
            )
            connection.commit()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_locations_endpoint_returns_database_buildings(self):
        response = self.client.get("/api/locations")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["locations"][0],
            {
                "id": 3,
                "name": "Center",
                "latitude": 39.2,
                "longitude": -76.2,
                "description": None,
                "accessible": True,
            },
        )

    def test_route_endpoint_returns_shortest_path(self):
        response = self.client.post(
            "/api/route",
            json={"startId": 1, "destinationId": 3, "accessible": False},
        )
        route = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(route["pathwayIds"], [10, 11])
        self.assertEqual(route["distanceMeters"], 200)
        self.assertAlmostEqual(route["estimatedMinutes"], 200 / 75)
        self.assertEqual(route["predictionSource"], "distance-based")

    def test_travel_time_observations_join_to_model_features(self):
        with self.app.app_context():
            connection = get_db()
            connection.execute(
                """
                INSERT INTO TravelTimeObservations
                    (pathway_id, foot_traffic, travel_time_seconds)
                VALUES (10, 'high', 105)
                """
            )
            observation = connection.execute(
                """
                SELECT p.distance_meters, o.foot_traffic, p.has_stairs,
                       p.wheelchair_accessible, o.travel_time_seconds
                FROM TravelTimeObservations AS o
                JOIN Pathways AS p USING (pathway_id)
                """
            ).fetchone()

        self.assertEqual(
            tuple(observation),
            (100.0, "high", 0, 1, 105.0),
        )

    def test_route_is_bidirectional_and_accessibility_filters_pathways(self):
        standard_route = self.client.post(
            "/api/route",
            json={"startId": 4, "destinationId": 1, "accessible": False},
        )
        accessible_route = self.client.post(
            "/api/route",
            json={"startId": 4, "destinationId": 1, "accessible": True},
        )

        self.assertEqual(standard_route.status_code, 200)
        self.assertEqual(standard_route.get_json()["pathwayIds"], [13, 11, 10])
        self.assertEqual(accessible_route.status_code, 404)
        self.assertEqual(
            accessible_route.get_json()["error"]["code"], "ROUTE_NOT_FOUND"
        )

    def test_route_rejects_invalid_request(self):
        response = self.client.post(
            "/api/route",
            json={"startId": True, "destinationId": 2, "accessible": False},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"]["code"], "INVALID_REQUEST")

    def test_accessible_route_rejects_inaccessible_building(self):
        with self.app.app_context():
            connection = get_db()
            connection.execute(
                "UPDATE Buildings SET wheelchair_accessible = 0 WHERE building_id = 4"
            )
            connection.execute(
                "UPDATE Pathways SET wheelchair_accessible = 1, has_stairs = 0 "
                "WHERE pathway_id = 13"
            )
            connection.commit()

        response = self.client.post(
            "/api/route",
            json={"startId": 1, "destinationId": 4, "accessible": True},
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn(
            "building", response.get_json()["error"]["message"].lower()
        )

    def test_legacy_database_is_not_silently_modified(self):
        database_path = Path(self.temporary_directory.name) / "legacy.db"
        connection = sqlite3.connect(database_path)
        try:
            connection.executescript(
                """
                CREATE TABLE Buildings (
                    building_id INTEGER PRIMARY KEY,
                    building_name TEXT NOT NULL,
                    is_accessible BOOLEAN NOT NULL
                );
                CREATE TABLE Pathways (
                    pathway_id INTEGER PRIMARY KEY,
                    start_building_id INTEGER NOT NULL,
                    end_building_id INTEGER NOT NULL,
                    distance_meters REAL NOT NULL,
                    is_accessible BOOLEAN NOT NULL
                );
                """
            )
        finally:
            connection.close()

        with self.assertRaisesRegex(RuntimeError, "was not changed"):
            initialize_database(str(database_path))

        connection = sqlite3.connect(database_path)
        try:
            table_names = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        finally:
            connection.close()
        self.assertNotIn("TravelTimeObservations", table_names)


if __name__ == "__main__":
    unittest.main()
