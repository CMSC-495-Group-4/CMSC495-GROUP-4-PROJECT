"""Measure repeated in-process routing requests before considering caching."""

import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from db import get_db


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--output", default="route-benchmark.json")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as directory:
        database_path = str(Path(directory) / "benchmark.db")
        app = create_app(
            {
                "TESTING": True,
                "DATABASE_NAME": database_path,
            }
        )
        with app.app_context():
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

        durations = []
        client = app.test_client()
        for _ in range(args.iterations):
            started = time.perf_counter()
            response = client.post(
                "/api/route",
                json={
                    "startId": 1,
                    "destinationId": 3,
                    "accessible": False,
                    "timePeriod": "midday",
                },
            )
            durations.append((time.perf_counter() - started) * 1000)
            if response.status_code != 200:
                raise RuntimeError(
                    f"Benchmark route failed with status {response.status_code}"
                )

    summary = {
        "iterations": args.iterations,
        "averageMilliseconds": statistics.fmean(durations),
        "medianMilliseconds": statistics.median(durations),
        "maximumMilliseconds": max(durations),
    }
    output_path = Path(args.output)
    output_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
