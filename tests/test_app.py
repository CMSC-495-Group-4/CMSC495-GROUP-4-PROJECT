import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
                "OPENAI_API_KEY": "test-key",
                "OPENAI_MODEL": "test-model",
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

    def test_homepage_includes_campus_assistant(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Campus assistant", response.data)
        self.assertIn(b"chat-input", response.data)
        self.assertIn(b"Step-by-step directions", response.data)

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
        self.assertEqual(
            route["directions"],
            [
                {
                    "stepNumber": 1,
                    "instruction": "Start at Library, head toward Science.",
                    "distanceMeters": 100,
                },
                {
                    "stepNumber": 2,
                    "instruction": "At Science, continue toward Center.",
                    "distanceMeters": 100,
                },
            ],
        )
        self.assertAlmostEqual(route["estimatedMinutes"], 200 / 75)
        self.assertEqual(route["predictionSource"], "distance-based")

    def test_time_period_traffic_can_change_the_route(self):
        with self.app.app_context():
            get_db().executemany(
                """
                INSERT INTO PathwayTraffic (pathway_id, time_period, foot_traffic)
                VALUES (?, 'midday', ?)
                """,
                [(10, "high"), (11, "high"), (12, "low")],
            )
            get_db().commit()

        response = self.client.post(
            "/api/route",
            json={
                "startId": 1,
                "destinationId": 3,
                "accessible": False,
                "timePeriod": "midday",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["pathwayIds"], [12])
        self.assertEqual(response.get_json()["distanceMeters"], 500)
        self.assertEqual(response.get_json()["timePeriod"], "midday")

    def test_chat_route_request_uses_existing_route_api_logic(self):
        provider_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "intent": "route",
                                "answer": "",
                                "start": "Library",
                                "destination": "Center",
                                "accessible": False,
                                "timePeriod": None,
                            }
                        )
                    }
                }
            ]
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return json.dumps(provider_response).encode("utf-8")

        with patch("chatbot.urllib.request.urlopen", return_value=FakeResponse()):
            response = self.client.post(
                "/api/chat",
                json={"message": "Get me from the Library to Center"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["route"]["pathwayIds"], [10, 11])
        self.assertIn("Library to Center", response.get_json()["reply"])

    def test_chat_answers_supported_faq(self):
        provider_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "intent": "faq",
                                "answer": (
                                    "Route distance sums stored segment distances. "
                                    "Walking time uses a 75 meters per minute baseline "
                                    "and illustrative traffic weights when selected."
                                ),
                                "start": None,
                                "destination": None,
                                "accessible": None,
                                "timePeriod": None,
                            }
                        )
                    }
                }
            ]
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return json.dumps(provider_response).encode("utf-8")

        with patch(
            "chatbot.urllib.request.urlopen", return_value=FakeResponse()
        ) as openai_request:
            response = self.client.post(
                "/api/chat",
                json={"message": "How are route distance and walking time calculated?"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(openai_request.call_args.kwargs["timeout"], 10)
        self.assertEqual(
            response.get_json()["reply"],
            (
                "Route distance sums stored segment distances. Walking time uses "
                "a 75 meters per minute baseline and illustrative traffic weights "
                "when selected."
            ),
        )
        request_payload = json.loads(
            openai_request.call_args.args[0].data.decode("utf-8")
        )
        assistant_context = request_payload["messages"][1]["content"]
        self.assertIn(
            "Route distance is the sum of the stored distances", assistant_context
        )
        self.assertIn("75 meters per minute", assistant_context)
        self.assertIn("low 1, medium 1.5, high 3", assistant_context)

    def test_chat_requires_api_key(self):
        self.app.config["OPENAI_API_KEY"] = None

        response = self.client.post(
            "/api/chat",
            json={"message": "What does this app do?"},
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json()["error"]["code"], "CHAT_NOT_CONFIGURED"
        )

    def test_chat_rejects_oversized_message(self):
        response = self.client.post(
            "/api/chat",
            json={"message": "x" * 501},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"]["code"], "INVALID_REQUEST")

    def test_chat_is_rate_limited_per_remote_ip(self):
        self.app.config["CHAT_RATE_LIMIT"] = 2
        provider_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "intent": "clarify",
                                "answer": "I don't know.",
                                "start": None,
                                "destination": None,
                                "accessible": None,
                                "timePeriod": None,
                            }
                        )
                    }
                }
            ]
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return json.dumps(provider_response).encode("utf-8")

        with patch("chatbot.urllib.request.urlopen", return_value=FakeResponse()):
            first = self.client.post("/api/chat", json={"message": "What is CampusPath?"})
            second = self.client.post("/api/chat", json={"message": "What is CampusPath?"})
            third = self.client.post("/api/chat", json={"message": "What is CampusPath?"})
            another_ip = self.client.post(
                "/api/chat",
                json={"message": "What is CampusPath?"},
                environ_base={"REMOTE_ADDR": "192.0.2.1"},
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(third.status_code, 429)
        self.assertEqual(third.get_json()["error"]["code"], "RATE_LIMITED")
        self.assertEqual(another_ip.status_code, 200)

    def test_chat_timeout_returns_safe_provider_error(self):
        with patch(
            "chatbot.urllib.request.urlopen",
            side_effect=TimeoutError("provider timeout"),
        ):
            response = self.client.post(
                "/api/chat",
                json={"message": "How are route distance and walking time calculated?"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("75 meters per minute", response.get_json()["reply"])
        self.assertNotIn("provider timeout", response.get_data(as_text=True))

    def test_chat_timeout_falls_back_to_local_route_calculation(self):
        with patch(
            "chatbot.urllib.request.urlopen",
            side_effect=TimeoutError("provider timeout"),
        ):
            response = self.client.post(
                "/api/chat",
                json={"message": "Get me from the Library to Center at midday"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["route"]["pathwayIds"], [10, 11])
        self.assertEqual(response.get_json()["route"]["timePeriod"], "midday")

    def test_chat_malformed_provider_response_returns_safe_error(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return b'{"unexpected": "payload"}'

        with patch("chatbot.urllib.request.urlopen", return_value=FakeResponse()):
            response = self.client.post(
                "/api/chat",
                json={"message": "What is CampusPath?"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["reply"], "CampusPath is an academic prototype for campus walking routes.")

    def test_chat_and_route_return_consistent_route_data(self):
        provider_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "intent": "route",
                                "answer": "",
                                "start": "Library",
                                "destination": "Center",
                                "accessible": False,
                                "timePeriod": "midday",
                            }
                        )
                    }
                }
            ]
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return json.dumps(provider_response).encode("utf-8")

        direct = self.client.post(
            "/api/route",
            json={
                "startId": 1,
                "destinationId": 3,
                "accessible": False,
                "timePeriod": "midday",
            },
        )
        with patch("chatbot.urllib.request.urlopen", return_value=FakeResponse()):
            through_chat = self.client.post(
                "/api/chat",
                json={"message": "Get me from Library to Center at midday"},
            )

        direct_route = direct.get_json()
        chat_route = through_chat.get_json()["route"]
        self.assertEqual(direct.status_code, 200)
        self.assertEqual(through_chat.status_code, 200)
        self.assertEqual(chat_route["pathwayIds"], direct_route["pathwayIds"])
        self.assertEqual(chat_route["distanceMeters"], direct_route["distanceMeters"])
        self.assertEqual(chat_route["accessible"], direct_route["accessible"])
        self.assertEqual(chat_route["timePeriod"], direct_route["timePeriod"])

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

    def test_demo_seed_file_is_repeatable_and_has_valid_relations(self):
        database_path = Path(self.temporary_directory.name) / "seed.db"
        initialize_database(str(database_path))
        seed_sql = (
            Path(__file__).resolve().parents[1]
            / "database"
            / "seed_demo_data.sql"
        ).read_text(encoding="utf-8")
        connection = sqlite3.connect(database_path)
        try:
            connection.executescript(seed_sql)
            connection.executescript(seed_sql)

            building_count = connection.execute(
                "SELECT COUNT(*) FROM Buildings"
            ).fetchone()[0]
            pathway_count = connection.execute(
                "SELECT COUNT(*) FROM Pathways"
            ).fetchone()[0]
            traffic_count = connection.execute(
                "SELECT COUNT(*) FROM PathwayTraffic"
            ).fetchone()[0]
            foreign_key_violations = connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
            community_center = connection.execute(
                "SELECT building_name FROM Buildings WHERE building_id = 97"
            ).fetchone()[0]
        finally:
            connection.close()

        self.assertEqual(building_count, 6)
        self.assertEqual(pathway_count, 8)
        self.assertEqual(traffic_count, 24)
        self.assertEqual(foreign_key_violations, [])
        self.assertEqual(
            community_center, "Cambridge Community Center (097 CCC)"
        )


if __name__ == "__main__":
    unittest.main()
