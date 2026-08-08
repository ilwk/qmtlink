import pytest

from qmtlink.bridge.events import EventJournal
from qmtlink.errors import QMTLinkError


def test_event_journal_uses_resumable_monotonic_cursor() -> None:
    journal = EventJournal()
    first = journal.publish("quote", {"symbol": "000001.SZ"})
    second = journal.publish("order", {"order_id": "1"})

    batch = journal.poll(after_sequence=first.sequence, timeout=0)

    assert [event.event_type for event in batch.events] == ["order"]
    assert batch.next_sequence == second.sequence


def test_event_journal_rejects_expired_cursor() -> None:
    journal = EventJournal(max_events=2)
    journal.publish("quote", {"n": 1})
    journal.publish("quote", {"n": 2})
    journal.publish("quote", {"n": 3})

    with pytest.raises(QMTLinkError, match="cursor"):
        journal.poll(after_sequence=0, timeout=0)


def test_event_journal_rejects_cursor_from_previous_process() -> None:
    journal = EventJournal()

    with pytest.raises(QMTLinkError, match="ahead") as error:
        journal.poll(after_sequence=10, timeout=0)

    assert error.value.code == "EVENT_CURSOR_INVALID"
    assert error.value.status_code == 409
