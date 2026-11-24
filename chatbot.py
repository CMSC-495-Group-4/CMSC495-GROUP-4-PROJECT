"""Grounded OpenAI assistant for campus FAQs and route requests."""

import json
import urllib.error
import urllib.request

from route_rules import (
    TIME_PERIODS,
    TRAFFIC_COST_FACTORS,
    WALKING_SPEED_METERS_PER_MINUTE,
)


_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
_OPENAI_TIMEOUT_SECONDS = 10
_TIME_PERIODS_TEXT = ", ".join(TIME_PERIODS)
_TRAFFIC_COST_FACTORS_TEXT = ", ".join(
    f"{level} {factor:g}" for level, factor in TRAFFIC_COST_FACTORS.items()
)

FAQ_KNOWLEDGE = [
    "CampusPath is an academic prototype for campus walking routes.",
    "To calculate a route, select a start and destination, optionally choose "
    "a time period and accessible routing, and submit the route form.",
    "Route distance is the sum of the stored distances for each pathway "
    "segment in the selected route. Distances in the included demo dataset "
    "are simulated, not measured walking distances.",
    f"Walking time uses a fixed baseline of "
    f"{WALKING_SPEED_METERS_PER_MINUTE:g} meters per minute. Without a "
    f"time period, estimated minutes are the route distance divided by "
    f"{WALKING_SPEED_METERS_PER_MINUTE:g}. "
    "When a time period is selected, each segment's distance is weighted by "
    f"its configured traffic level ({_TRAFFIC_COST_FACTORS_TEXT}); estimated "
    f"minutes are the total weighted distance divided by "
    f"{WALKING_SPEED_METERS_PER_MINUTE:g}. These traffic "
    "weights and the resulting time are illustrative, not live measurements "
    "or a trained AI prediction.",
    "Accessible routing filters pathways using the accessibility and stairs "
    "fields in the database. Those records must be verified before relying "
    "on them for real-world accessibility needs.",
    "The assistant can answer only from these facts and the current building "
    "list. It must say when it does not know.",
]


class ChatConfigurationError(Exception):
    """Raised when the required AI service configuration is unavailable."""


class ChatProviderError(Exception):
    """Raised when the AI provider cannot return a valid response."""


def interpret_message_fallback(message, locations):
    """Provide a deterministic response when the AI provider is unavailable."""
    normalized = " ".join(message.lower().split())
    location_names = [
        location["name"] for location in locations
    ]

    time_period = next(
        (period for period in TIME_PERIODS if period in normalized),
        None,
    )

    mentioned_locations = sorted(
        (
            location
            for location in locations
            if location["name"].lower() in normalized
        ),
        key=lambda location: normalized.find(location["name"].lower()),
    )

    route_request = (
        bool(mentioned_locations)
        or any(
            phrase in normalized
            for phrase in (
                "directions",
                "how do i get",
                "get me",
                "take me",
            )
        )
    )
    if route_request:
        start = mentioned_locations[0]["name"] if len(mentioned_locations) > 0 else None
        destination = (
            mentioned_locations[1]["name"]
            if len(mentioned_locations) > 1
            else None
        )
        if len(mentioned_locations) == 1:
            if normalized.startswith(("to ", "go to ", "get me to ", "take me to ")):
                destination = mentioned_locations[0]["name"]
                start = None
            else:
                start = mentioned_locations[0]["name"]

        return {
            "intent": "route",
            "answer": "",
            "start": start,
            "destination": destination,
            "accessible": any(
                term in normalized
                for term in ("accessible", "wheelchair", "ada")
            ),
            "timePeriod": time_period,
        }

    if any(
        phrase in normalized
        for phrase in (
            "walking time",
            "travel time",
            "how long",
            "distance",
            "meter",
            "calculate",
            "traffic",
        )
    ):
        answer = (
            f"Route distance sums stored segment distances. Walking time uses "
            f"a {WALKING_SPEED_METERS_PER_MINUTE:g} meters per minute baseline "
            "and illustrative traffic weights when a time period is selected."
        )
        return {
            "intent": "faq",
            "answer": answer,
            "start": None,
            "destination": None,
            "accessible": None,
            "timePeriod": None,
        }

    if "campuspath" in normalized or "what does this app do" in normalized:
        answer = (
            "CampusPath is an academic prototype for campus walking routes."
        )
        return {
            "intent": "faq",
            "answer": answer,
            "start": None,
            "destination": None,
            "accessible": None,
            "timePeriod": None,
        }

    return {
        "intent": "clarify",
        "answer": "I don't know.",
        "start": None,
        "destination": None,
        "accessible": None,
        "timePeriod": None,
    }


def interpret_message(message, locations, api_key, model):
    """Interpret a chat message through OpenAI and validate the provider result."""
    if not api_key:
        raise ChatConfigurationError

    knowledge = {
        "facts": FAQ_KNOWLEDGE,
        "locations": [
            {"id": location["id"], "name": location["name"]}
            for location in locations
        ],
        "time_periods": list(TIME_PERIODS),
    }
    instructions = (
        "You are CampusPath's campus assistant. Treat the supplied knowledge "
        "as the complete and authoritative source; do not use outside facts "
        "or invent building, route, traffic, or accessibility information. "
        "If the answer is unsupported, use intent 'clarify' and say you do "
        "not know. For route requests, use intent 'route', return exact "
        "building names from the supplied list, and set accessible to true "
        "only when an accessible route is requested; otherwise use false. "
        "Return null for missing start or destination so the app can ask a "
        "follow-up. Map time-of-day phrases "
        f"to {_TIME_PERIODS_TEXT} only when clear; otherwise use null. "
        "Respond only as a JSON object with keys intent, answer, start, "
        "destination, accessible, and timePeriod. intent must be faq, route, "
        "or clarify; accessible must be true or false; timePeriod must "
        f"be {_TIME_PERIODS_TEXT}, or null. For faq/clarify, answer must "
        "be a concise plain-text response. When asked how distance or walking "
        "time is calculated, state the stored-segment distance method, the "
        f"{WALKING_SPEED_METERS_PER_MINUTE:g} meters per minute baseline, "
        "and the simulated traffic weights "
        "when relevant."
    )
    payload = {
        "model": model,
        "temperature": 0.1,
        "max_tokens": 300,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": instructions},
            {
                "role": "user",
                "content": f"Knowledge:\n{json.dumps(knowledge)}\n\n"
                f"User message:\n{message}",
            },
        ],
    }
    request = urllib.request.Request(
        _CHAT_COMPLETIONS_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request, timeout=_OPENAI_TIMEOUT_SECONDS
        ) as response:
            provider_response = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        raise ChatProviderError from error

    try:
        content = provider_response["choices"][0]["message"]["content"]
        result = json.loads(content)
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise ChatProviderError from error

    if not isinstance(result, dict) or result.get("intent") not in {
        "faq",
        "route",
        "clarify",
    }:
        raise ChatProviderError

    answer = result.get("answer", "")
    if not isinstance(answer, str) or len(answer) > 1200:
        raise ChatProviderError

    start = result.get("start")
    destination = result.get("destination")
    accessible = result.get("accessible")
    time_period = result.get("timePeriod")
    if (
        (start is not None and not isinstance(start, str))
        or (destination is not None and not isinstance(destination, str))
        or (accessible is not None and not isinstance(accessible, bool))
        or (
            time_period is not None
            and (
                not isinstance(time_period, str)
                or time_period not in TIME_PERIODS
            )
        )
    ):
        raise ChatProviderError

    return {
        "intent": result["intent"],
        "answer": answer,
        "start": start,
        "destination": destination,
        "accessible": accessible,
        "timePeriod": time_period,
    }
