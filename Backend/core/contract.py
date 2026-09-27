"""Turn model output into the shapes the frontend already validates."""

from __future__ import annotations

import json
import re
from typing import Any

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

_NEXT_FR = "Comparez cette explication avec le document original et posez vos questions au pharmacien."
_NEXT_ARY = "قارن هاد الشرح مع الوثيقة الأصلية وسول الصيدلي."
_URGENT_FR = "Contactez immédiatement les urgences ou un professionnel de santé."
_URGENT_ARY = "تاصل دابا بالإسعاف ولا بشي مهني صحي."


def parse_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("no json object")
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("json is not an object")
    return data


def _clean_time(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    token = re.sub(r"\s+", "", value.strip().lower().replace(".", ":"))
    hour = re.fullmatch(r"(\d{1,2})h(\d{2})?", token)
    if hour:
        normalized = f"{int(hour.group(1)):02d}:{hour.group(2) or '00'}"
    else:
        token = token.replace("h", ":")
        match = re.fullmatch(r"(\d{1,2}):(\d{2})", token)
        if not match:
            return None
        normalized = f"{int(match.group(1)):02d}:{match.group(2)}"
    return normalized if TIME_RE.fullmatch(normalized) else None


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _whole_days(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, int) and 0 < value <= 365:
        return value
    return None


def normalize_explanation(data: dict[str, Any], language: str) -> dict[str, Any]:
    fr = language != "ary"
    summary = data.get("summary")
    summary = summary.strip() if isinstance(summary, str) else ""
    if not summary:
        raise ValueError("empty summary")

    document_type = data.get("document_type")
    if isinstance(document_type, str) and document_type.strip():
        document_type = document_type.strip()
    else:
        document_type = "Document" if fr else "وثيقة"

    items: list[dict[str, str]] = []
    raw_items = data.get("items")
    if isinstance(raw_items, list):
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            title, detail = item.get("title"), item.get("detail")
            if isinstance(title, str) and isinstance(detail, str) and title.strip() and detail.strip():
                items.append({"title": title.strip(), "detail": detail.strip()})
    if not items:
        items.append({"title": document_type, "detail": summary})

    next_steps = _strings(data.get("next_steps")) or [_NEXT_FR if fr else _NEXT_ARY]
    uncertainties = _strings(data.get("uncertainties"))

    emergency_in = data.get("emergency") if isinstance(data.get("emergency"), dict) else {}
    detected = bool(emergency_in.get("detected"))
    message = emergency_in.get("message") if isinstance(emergency_in.get("message"), str) else ""
    message = message.strip()
    if not detected:
        message = ""
    elif not message:
        message = _URGENT_FR if fr else _URGENT_ARY

    medicines: list[dict[str, Any]] = []
    raw_medicines = data.get("medicines")
    if isinstance(raw_medicines, list):
        for med in raw_medicines:
            if not isinstance(med, dict):
                continue
            name = med.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            instructions = med.get("instructions") if isinstance(med.get("instructions"), str) else ""
            entry: dict[str, Any] = {"name": name.strip(), "instructions": instructions.strip()}
            dose = med.get("dose")
            if isinstance(dose, str) and dose.strip():
                entry["dose"] = dose.strip()

            raw_times = med.get("times")
            if isinstance(raw_times, str):
                raw_times = [raw_times]
            times: list[str] = []
            if isinstance(raw_times, list):
                for value in raw_times:
                    cleaned = _clean_time(value)
                    if cleaned and cleaned not in times:
                        times.append(cleaned)
                if raw_times and not times:
                    uncertainties.append(
                        f"Horaires non confirmés pour {entry['name']}."
                        if fr
                        else f"الأوقات ما تأكدوش بالنسبة لـ {entry['name']}."
                    )
            if times:
                entry["times"] = times

            days = _whole_days(med.get("duration_days"))
            if days is not None:
                entry["duration_days"] = days
            medicines.append(entry)

    return {
        "document_type": document_type,
        "summary": summary,
        "items": items,
        "next_steps": next_steps,
        "uncertainties": uncertainties,
        "emergency": {"detected": detected, "message": message},
        "medicines": medicines,
    }


def normalize_chat(data: dict[str, Any], language: str) -> dict[str, Any]:
    fr = language != "ary"
    reply = data.get("reply")
    reply = reply.strip() if isinstance(reply, str) else ""
    if not reply:
        raise ValueError("empty reply")

    emergency_in = data.get("emergency") if isinstance(data.get("emergency"), dict) else {}
    detected = bool(emergency_in.get("detected"))
    message = emergency_in.get("message") if isinstance(emergency_in.get("message"), str) else ""
    message = message.strip()
    if not detected:
        message = ""
    elif not message:
        message = _URGENT_FR if fr else _URGENT_ARY
    return {"reply": reply, "emergency": {"detected": detected, "message": message}}
