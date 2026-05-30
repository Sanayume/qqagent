import asyncio

import pytest

from src.session.scheduler import ScheduledMessageStore


class FakeEvent:
    group_id = 10001
    user_id = 20002


class FakeAdapter:
    def __init__(self):
        self.sent = []

    async def send_rich_to_target(self, **kwargs):
        self.sent.append(kwargs)


@pytest.mark.asyncio
async def test_scheduled_message_survives_restart(tmp_path):
    db_path = tmp_path / "scheduled_messages.db"
    command = {
        "text": "hello later",
        "image": "",
        "record": "",
        "at_users": [20002],
        "reply_to": 123,
        "delay_minutes": 0,
    }

    first = ScheduledMessageStore(str(db_path))
    schedule_id = first.schedule_from_event(FakeEvent(), command)
    assert schedule_id > 0

    adapter = FakeAdapter()
    restarted = ScheduledMessageStore(str(db_path))
    await restarted.start(adapter)
    try:
        for _ in range(20):
            if adapter.sent:
                break
            await asyncio.sleep(0.05)
    finally:
        await restarted.stop()

    assert adapter.sent == [
        {
            "target_type": "group",
            "target_id": 10001,
            "text": "hello later",
            "image": "",
            "record": "",
            "at_users": [20002],
            "reply_to": 123,
        }
    ]
    assert restarted.get_stats()["sent"] == 1
