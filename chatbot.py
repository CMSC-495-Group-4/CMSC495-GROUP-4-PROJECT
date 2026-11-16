"""Grounded OpenAI assistant for campus FAQs and route requests."""

import json
import urllib.error
import urllib.request


_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
_TIME_PERIODS = {"morning", "midday", "evening"}

FAQ_KNOWLEDGE = [
    "CampusPath is an academic prototype for campus walking routes.",
    "To calculate a route, select a start and destination, optionally choose "
    "a time period and accessible routing, and submit the route form.",
    "Routes use pathway distances. When a time period is selected, stored "
    "foot-traffic levels can affect route selection and the estimated time.",
    "Walking time is an estimate based on a fixed speed and is not a live "
    "traffic measurement or a trained AI prediction.",
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


def interpret_message(message, locations, api_key, model):
    if not api_key:
        raise ChatConfigurationError

    knowledge = {
        "facts": FAQ_KNOWLEDGE,
        "locations": [
            {"id": location["id"], "name": location["name"]}
            for location in locations
        ],
        "time_periods": sorted(_TIME_PERIODS),
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
        "to morning, midday, or evening only when clear; otherwise use null. "
        "Respond only as a JSON object with keys intent, answer, start, "
        "destination, accessible, and timePeriod. intent must be faq, route, "
        "or clarify; accessible must be true or false; timePeriod must "
        "be morning, midday, evening, or null. For faq/clarify, answer must "
        "be a concise plain-text response."
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
        with urllib.request.urlopen(request, timeout=20) as response:
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
                or time_period not in _TIME_PERIODS
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
