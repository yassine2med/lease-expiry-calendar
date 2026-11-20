from datetime import date

import pytest

from lease_calendar import core
from lease_calendar.cli import main

CSV = ("lease,tenant,expiry,renewal_notice_days,termination_notice_days,rent_review\n"
       "L1,Acme,2026-12-31,90,30,2026-07-01\nL2,Beta,2027-01-31,,,\n")


@pytest.fixture
def register(tmp_path):
    path = tmp_path / "r.csv"
    path.write_text(CSV)
    return path


def test_all_event_kinds_created(register):
    kinds = [e.kind for e in core.read_register(register)]
    assert sorted(kinds) == ["Lease expires", "Lease expires", "Renewal notice deadline",
                             "Rent review", "Termination notice deadline"]


def test_notice_deadline_is_expiry_minus_days(register):
    events = {e.kind: e.when for e in core.read_register(register) if e.lease == "L1"}
    assert events["Renewal notice deadline"] == date(2026, 10, 2)
    assert events["Termination notice deadline"] == date(2026, 12, 1)


def test_events_sorted_by_date(register):
    dates = [e.when for e in core.read_register(register)]
    assert dates == sorted(dates)


def test_upcoming_hides_past_by_default(register):
    events = core.read_register(register)
    assert all(e.when >= date(2026, 8, 1) for e in core.upcoming(events, date(2026, 8, 1)))
    assert len(core.upcoming(events, date(2026, 8, 1), include_past=True)) == len(events)


def test_within_window(register):
    events = core.upcoming(core.read_register(register), date(2026, 6, 1), within_days=40)
    assert [e.kind for e in events] == ["Rent review"]


def test_negative_within_rejected(register):
    with pytest.raises(ValueError, match="within"):
        core.upcoming(core.read_register(register), date(2026, 1, 1), within_days=-5)


def test_bad_date_and_bad_days(tmp_path):
    p = tmp_path / "b.csv"
    p.write_text(CSV.replace("2026-12-31", "12/31/2026"))
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        core.read_register(p)
    p.write_text(CSV.replace(",90,", ",ninety,"))
    with pytest.raises(ValueError, match="whole number"):
        core.read_register(p)


def test_missing_column(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text("lease,tenant\nL1,Acme\n")
    with pytest.raises(ValueError, match="missing column"):
        core.read_register(p)


def test_ics_structure(register):
    text = core.to_ics(core.read_register(register))
    assert text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n")
    assert text.count("BEGIN:VEVENT") == 5
    assert "DTSTART;VALUE=DATE:20261231" in text and "DTEND;VALUE=DATE:20270101" in text


def test_ics_escapes_special_characters():
    event = core.Event(date(2026, 1, 1), "L1", "Smith, Jones; Co", "Lease expires")
    assert "Smith\\, Jones\\; Co" in core.to_ics([event])


def test_ics_uids_are_unique_and_stable(register):
    first = core.to_ics(core.read_register(register))
    uids = [l for l in first.splitlines() if l.startswith("UID:")]
    assert len(set(uids)) == len(uids) and first == core.to_ics(core.read_register(register))


def test_cli_list_and_ics(register, tmp_path, capsys):
    assert main(["list", str(register), "--today", "2026-06-15"]) == 0
    assert "5 dates" in capsys.readouterr().out
    out = tmp_path / "x.ics"
    assert main(["ics", str(register), "--today", "2026-06-15", "--out", str(out)]) == 0
    assert out.read_text().startswith("BEGIN:VCALENDAR")
    assert main(["list", "nope.csv"]) == 1
