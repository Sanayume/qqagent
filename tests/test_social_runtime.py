from dataclasses import dataclass

from src.session.social import SocialRuntime


@dataclass
class FakeEvent:
    user_id: int = 10001
    group_id: int | None = 20002
    sender_nickname: str = "Sana"
    is_group: bool = True
    is_private: bool = False


def test_social_runtime_observes_user_and_builds_prompt(tmp_path):
    runtime = SocialRuntime(
        db_path=str(tmp_path / "social.db"),
        config={"familiar_threshold": 2, "quiet_hour_start": 25, "quiet_hour_end": 26},
    )
    event = FakeEvent()

    runtime.observe_message(event, "哈哈这个也太乐了", "Sana")
    runtime.observe_message(event, "救命这个报错怎么办", "Sana")

    prompt = runtime.build_prompt(event, session_id="group_20002", message_count=2, participant_count=1)

    assert "社交运行时" in prompt
    assert "群聊" in prompt
    assert "Sana" in prompt
    assert "熟悉" in prompt
    assert "回复策略" in prompt


def test_social_runtime_can_be_disabled(tmp_path):
    runtime = SocialRuntime(
        db_path=str(tmp_path / "social.db"),
        config={"enabled": False},
    )

    runtime.observe_message(FakeEvent(), "hello", "Sana")

    assert runtime.build_prompt(FakeEvent(), session_id="group_20002") == ""
    assert runtime.get_stats()["observed_messages"] == 0
