"""Flask entry point for the CMSC 495 campus navigation frontend."""

import heapq
import uuid

from flask import Flask, jsonify, render_template, request

from config import Config
from db import get_db, init_app as init_database_app, initialize_database


WALKING_SPEED_METERS_PER_MINUTE = 75.0


def _shortest_path(connection, start_id, destination_id, accessible):
    query = """
        SELECT pathway_id, start_building_id, end_building_id, distance_meters
        FROM Pathways
    """
    if accessible:
        query += " WHERE wheelchair_accessible = 1 AND has_stairs = 0"

    graph = {}
    for pathway in connection.execute(query):
        start = pathway["start_building_id"]
        end = pathway["end_building_id"]
        distance = pathway["distance_meters"]
        pathway_id = pathway["pathway_id"]
        graph.setdefault(start, []).append((end, distance, pathway_id))
        graph.setdefault(end, []).append((start, distance, pathway_id))

    distances = {start_id: 0.0}
    previous = {}
    queue = [(0.0, start_id)]

    while queue:
        distance_so_far, building_id = heapq.heappop(queue)
        if distance_so_far != distances.get(building_id):
            continue
        if building_id == destination_id:
            break

        for neighbor, edge_distance, pathway_id in graph.get(building_id, []):
            new_distance = distance_so_far + edge_distance
            if new_distance < distances.get(neighbor, float("inf")):
                distances[neighbor] = new_distance
                previous[neighbor] = (building_id, pathway_id)
                heapq.heappush(queue, (new_distance, neighbor))

    if destination_id not in distances:
        return None

    pathway_ids = []
    current_id = destination_id
    while current_id != start_id:
        previous_id, pathway_id = previous[current_id]
        pathway_ids.append(pathway_id)
        current_id = previous_id
    pathway_ids.reverse()

    return distances[destination_id], pathway_ids


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    initialize_database(app.config["DATABASE_NAME"])
    init_database_app(app)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/locations")
    def locations():
        rows = get_db().execute(
            """
            SELECT building_id, building_name, latitude, longitude, description,
                   wheelchair_accessible
            FROM Buildings
            ORDER BY building_name
            """
        )
        return jsonify(
            locations=[
                {
                    "id": row["building_id"],
                    "name": row["building_name"],
                    "latitude": row["latitude"],
                    "longitude": row["longitude"],
                    "description": row["description"],
                    "accessible": bool(row["wheelchair_accessible"]),
                }
                for row in rows
            ]
        )

    @app.post("/api/route")
    def route():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _error("INVALID_REQUEST", "A JSON request body is required.", 400)

        start_id = payload.get("startId")
        destination_id = payload.get("destinationId")
        accessible = payload.get("accessible", False)
        if (
            isinstance(start_id, bool)
            or not isinstance(start_id, int)
            or start_id <= 0
            or isinstance(destination_id, bool)
            or not isinstance(destination_id, int)
            or destination_id <= 0
            or not isinstance(accessible, bool)
        ):
            return _error(
                "INVALID_REQUEST",
                "startId and destinationId must be positive integers, and "
                "accessible must be a boolean.",
                400,
            )
        if start_id == destination_id:
            return _error(
                "INVALID_REQUEST",
                "Start and destination must be different buildings.",
                400,
            )

        connection = get_db()
        found_ids = {
            row["building_id"]
            for row in connection.execute(
                "SELECT building_id FROM Buildings WHERE building_id IN (?, ?)",
                (start_id, destination_id),
            )
        }
        if start_id not in found_ids or destination_id not in found_ids:
            return _error(
                "LOCATION_NOT_FOUND",
                "The start or destination building does not exist.",
                404,
            )

        if accessible:
            inaccessible_buildings = connection.execute(
                """
                SELECT COUNT(*)
                FROM Buildings
                WHERE building_id IN (?, ?) AND wheelchair_accessible = 0
                """,
                (start_id, destination_id),
            ).fetchone()[0]
            if inaccessible_buildings:
                return _error(
                    "ROUTE_NOT_FOUND",
                    "A selected building is not marked wheelchair-accessible.",
                    404,
                )

        result = _shortest_path(connection, start_id, destination_id, accessible)
        if result is None:
            return _error(
                "ROUTE_NOT_FOUND",
                "No route was found for the selected locations and preferences.",
                404,
            )

        distance_meters, pathway_ids = result
        return jsonify(
            routeId=uuid.uuid4().hex,
            pathwayIds=pathway_ids,
            distanceMeters=distance_meters,
            accessible=accessible,
            estimatedMinutes=distance_meters / WALKING_SPEED_METERS_PER_MINUTE,
            predictionSource="distance-based",
        )

    return app


def _error(code, message, status):
    return jsonify(error={"code": code, "message": message}), status


app = create_app()


if __name__ == "__main__":
    app.run(debug=app.config["DEBUG"])
