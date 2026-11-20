"""Turn a lease register into critical dates and an iCalendar file."""
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

REQUIRED = ["lease", "tenant", "expiry"]


@dataclass(frozen=True)
class Event:
    """One critical date for one lease."""

    when: date
    lease: str
    tenant: str
    kind: str

    def days_from(self, today: date) -> int:
        """Days until the event (negative when it has passed)."""
        return (self.when - today).days


def _parse(value: str, label: str, row: int) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise ValueError(f"row {row}: {label} '{value}' is not YYYY-MM-DD") from None


def _days(value: str, label: str, row: int) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    if not value.isdigit():
        raise ValueError(f"row {row}: {label} '{value}' is not a whole number of days")
    return int(value)


def read_register(path: str | Path) -> list[Event]:
    """Read the lease register CSV and return every critical date.

    Columns: lease, tenant, expiry (required); renewal_notice_days, termination_notice_days,
    rent_review (optional). A notice deadline is the expiry date minus the notice days.
    """
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: missing column(s) {', '.join(missing)}")
        events: list[Event] = []
        for n, row in enumerate(reader, start=2):
            expiry = _parse(row["expiry"], "expiry", n)
            events.append(Event(expiry, row["lease"], row["tenant"], "Lease expires"))
            renewal = _days(row.get("renewal_notice_days", ""), "renewal_notice_days", n)
            if renewal is not None:
                events.append(Event(expiry - timedelta(days=renewal), row["lease"], row["tenant"], "Renewal notice deadline"))
            term = _days(row.get("termination_notice_days", ""), "termination_notice_days", n)
            if term is not None:
                events.append(Event(expiry - timedelta(days=term), row["lease"], row["tenant"], "Termination notice deadline"))
            if (row.get("rent_review") or "").strip():
                events.append(Event(_parse(row["rent_review"], "rent_review", n), row["lease"], row["tenant"], "Rent review"))
    return sorted(events, key=lambda e: (e.when, e.lease, e.kind))


def upcoming(events: list[Event], today: date, within_days: int | None = None, include_past: bool = False) -> list[Event]:
    """Filter events: future only (unless include_past), and within a number of days when given."""
    if within_days is not None and within_days < 0:
        raise ValueError("within must not be negative")
    result = []
    for e in events:
        d = e.days_from(today)
        if d < 0 and not include_past:
            continue
        if within_days is not None and d > within_days:
            continue
        result.append(e)
    return result


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def to_ics(events: list[Event]) -> str:
    """Render events as an iCalendar (.ics) text with one all-day event each and a 7 day reminder."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//lease-expiry-calendar//EN", "CALSCALE:GREGORIAN"]
    for e in events:
        uid = hashlib.sha1(f"{e.when}|{e.lease}|{e.kind}".encode()).hexdigest()[:16] + "@lease-expiry-calendar"
        lines += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{e.when.strftime('%Y%m%d')}T000000Z",
                  f"DTSTART;VALUE=DATE:{e.when.strftime('%Y%m%d')}",
                  f"DTEND;VALUE=DATE:{(e.when + timedelta(days=1)).strftime('%Y%m%d')}",
                  f"SUMMARY:{_escape(e.kind + ': ' + e.lease + ' (' + e.tenant + ')')}",
                  "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Lease date in 7 days", "TRIGGER:-P7D", "END:VALARM",
                  "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
