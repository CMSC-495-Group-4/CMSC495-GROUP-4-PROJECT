"""Flask entry point for the CMSC 495 campus navigation frontend."""

import heapq
import uuid

from flask import Flask, jsonify, render_template, request

from chatbot import (
    ChatConfigurationError,
    ChatProviderError,
    interpret_message,
)
from config import Config
from db import get_db, init_app as init_database_app, initialize_database


WALKING_SPEED_METERS_PER_MINUTE = 75.0
TRAFFIC_COST_FACTORS = {"low": 1.0, "medium": 1.5, "high": 3.0}


def _shortest_path(connection, start_id, destination_id, accessible, time_period=None):
    query = """
        SELECT p.pathway_id, p.start_building_id, p.end_building_id,
               p.distance_meters, COALESCE(t.foot_traffic, p.foot_traffic)
                   AS foot_traffic
        FROM Pathways AS p
        LEFT JOIN PathwayTraffic AS t
          ON t.pathway_id = p.pathway_id AND t.time_period = ?
    """
    parameters = [time_period]
    if accessible:
        query += " WHERE p.wheelchair_accessible = 1 AND p.has_stairs = 0"

    graph = {}
    for pathway in connection.execute(query, parameters):
        start = pathway["start_building_id"]
        end = pathway["end_building_id"]
        distance = pathway["distance_meters"]
        pathway_id = pathway["pathway_id"]
        traffic = pathway["foot_traffic"]
        cost = (
            distance * TRAFFIC_COST_FACTORS[traffic]
            if time_period
            else distance
        )
        graph.setdefault(start, []).append((end, distance, cost, pathway_id))
        graph.setdefault(end, []).append((start, distance, cost, pathway_id))

    distances = {start_id: 0.0}
    previous = {}
    edge_distances = {}
    queue = [(0.0, start_id)]

    while queue:
        distance_so_far, building_id = heapq.heappop(queue)
        if distance_so_far != distances.get(building_id):
            continue
        if building_id == destination_id:
            break

        for neighbor, edge_distance, edge_cost, pathway_id in graph.get(
            building_id, []
        ):
            new_distance = distance_so_far + edge_cost
            if new_distance < distances.get(neighbor, float("inf")):
                distances[neighbor] = new_distance
                previous[neighbor] = (building_id, pathway_id, edge_distance)
                heapq.heappush(queue, (new_distance, neighbor))

    if destination_id not in distances:
        return None

    pathway_ids = []
    path_segments = []
    current_id = destination_id
    total_distance = 0.0
    while current_id != start_id:
        previous_id, pathway_id, edge_distance = previous[current_id]
        pathway_ids.append(pathway_id)
        path_segments.append(
            {
                "startBuildingId": previous_id,
                "endBuildingId": current_id,
                "distanceMeters": edge_distance,
            }
        )
        total_distance += edge_distance
        current_id = previous_id
    pathway_ids.reverse()
    path_segments.reverse()

    estimated_minutes = distances[destination_id] / WALKING_SPEED_METERS_PER_MINUTE
    return total_distance, estimated_minutes, pathway_ids, path_segments


def _find_route(connection, start_id, destination_id, accessible, time_period=None):
    if start_id == destination_id:
        return None, (
            "INVALID_REQUEST",
            "Start and destination must be different buildings.",
            400,
        )

    found_ids = {
        row["building_id"]
        for row in connection.execute(
            "SELECT building_id FROM Buildings WHERE building_id IN (?, ?)",
            (start_id, destination_id),
        )
    }
    if start_id not in found_ids or destination_id not in found_ids:
        return None, (
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
            return None, (
                "ROUTE_NOT_FOUND",
                "A selected building is not marked wheelchair-accessible.",
                404,
            )

    result = _shortest_path(
        connection, start_id, destination_id, accessible, time_period
    )
    if result is None:
        return None, (
            "ROUTE_NOT_FOUND",
            "No route was found for the selected locations and preferences.",
            404,
        )

    distance_meters, estimated_minutes, pathway_ids, path_segments = result
    route_building_ids = {start_id, destination_id}
    for segment in path_segments:
        route_building_ids.add(segment["startBuildingId"])
        route_building_ids.add(segment["endBuildingId"])
    placeholders = ", ".join("?" for _ in route_building_ids)
    building_names = {
        row["building_id"]: row["building_name"]
        for row in connection.execute(
            f"""
            SELECT building_id, building_name
            FROM Buildings
            WHERE building_id IN ({placeholders})
            """,
            tuple(route_building_ids),
        )
    }
    directions = [
        {
            "stepNumber": index,
            "instruction": (
                f"{'Start at' if index == 1 else 'At'} "
                f"{building_names[segment['startBuildingId']]}, "
                f"{'head' if index == 1 else 'continue'} toward "
                f"{building_names[segment['endBuildingId']]}."
            ),
            "distanceMeters": segment["distanceMeters"],
        }
        for index, segment in enumerate(path_segments, start=1)
    ]
    return (
        {
            "routeId": uuid.uuid4().hex,
            "pathwayIds": pathway_ids,
            "directions": directions,
            "distanceMeters": distance_meters,
            "accessible": accessible,
            "estimatedMinutes": estimated_minutes,
            "predictionSource": "distance-based",
            "timePeriod": time_period,
        },
        None,
    )


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
        time_period = payload.get("timePeriod")
        if (
            isinstance(start_id, bool)
            or not isinstance(start_id, int)
            or start_id <= 0
            or isinstance(destination_id, bool)
            or not isinstance(destination_id, int)
            or destination_id <= 0
            or not isinstance(accessible, bool)
            or (
                time_period is not None
                and (
                    not isinstance(time_period, str)
                    or time_period not in {"morning", "midday", "evening"}
                )
            )
        ):
            return _error(
                "INVALID_REQUEST",
                "startId and destinationId must be positive integers, and "
                "accessible must be a boolean and timePeriod must be "
                "morning, midday, evening, or omitted.",
                400,
            )
        route_data, error = _find_route(
            get_db(), start_id, destination_id, accessible, time_period
        )
        if error:
            return _error(*error)
        return jsonify(route_data)

    @app.post("/api/chat")
    def chat():
        payload = request.get_json(silent=True)
        message = payload.get("message") if isinstance(payload, dict) else None
        if not isinstance(message, str) or not message.strip() or len(message) > 500:
            return _error(
                "INVALID_REQUEST",
                "A message of 1 to 500 characters is required.",
                400,
            )

        locations = [
            {"id": row["building_id"], "name": row["building_name"]}
            for row in get_db().execute(
                "SELECT building_id, building_name FROM Buildings ORDER BY building_name"
            )
        ]
        try:
            interpretation = interpret_message(
                message.strip(),
                locations,
                app.config.get("OPENAI_API_KEY"),
                app.config["OPENAI_MODEL"],
            )
        except ChatConfigurationError:
            return _error(
                "CHAT_NOT_CONFIGURED",
                "The campus assistant is not configured. Set OPENAI_API_KEY to enable it.",
                503,
            )
        except ChatProviderError:
            return _error(
                "CHAT_UNAVAILABLE",
                "The campus assistant could not respond. Please try again.",
                502,
            )

        if interpretation["intent"] != "route":
            answer = interpretation["answer"].strip()
            return jsonify(
                reply=answer
                or "I don't have enough verified information to answer that."
            )

        if (
            not interpretation["start"]
            or not interpretation["destination"]
            or interpretation["accessible"] is None
        ):
            return jsonify(
                reply=(
                    "To plan a route, tell me the starting building, destination, "
                    "and whether you need an accessible route."
                )
            )

        start = _match_location(interpretation["start"], locations)
        destination = _match_location(interpretation["destination"], locations)
        if not start or not destination:
            names = ", ".join(location["name"] for location in locations)
            if not names:
                return jsonify(
                    reply="No campus locations are configured yet, so I can't plan a route."
                )
            return jsonify(
                reply=f"I couldn't match those buildings. Choose from: {names}."
            )

        time_period = interpretation["timePeriod"]
        route_data, error = _find_route(
            get_db(),
            start["id"],
            destination["id"],
            interpretation["accessible"],
            time_period,
        )
        if error:
            return jsonify(reply=error[1])

        route_data.update(
            startId=start["id"],
            destinationId=destination["id"],
        )
        period_label = f" for {time_period}" if time_period else ""
        reply = (
            f"Route from {start['name']} to {destination['name']}{period_label}: "
            f"demo distance about {route_data['distanceMeters']:.0f} m, about "
            f"{route_data['estimatedMinutes']:.1f} minutes. "
            "This is an estimate based on the configured route data, not live "
            "traffic or verified accessibility information."
        )
        return jsonify(reply=reply, route=route_data)

    return app


def _match_location(candidate, locations):
    normalized = " ".join(candidate.casefold().split())
    exact_matches = [
        location
        for location in locations
        if " ".join(location["name"].casefold().split()) == normalized
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]

    partial_matches = [
        location
        for location in locations
        if normalized in location["name"].casefold()
        or location["name"].casefold() in normalized
    ]
    return partial_matches[0] if len(partial_matches) == 1 else None


def _error(code, message, status):
    return jsonify(error={"code": code, "message": message}), status


app = create_app()


if __name__ == "__main__":
    app.run(debug=app.config["DEBUG"])
