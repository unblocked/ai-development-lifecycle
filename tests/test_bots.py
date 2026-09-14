import pytest

from adlc.bots import is_ai_agent_login, is_automation_login, is_bot_login, is_dependency_bot


@pytest.mark.parametrize(
    "login",
    [
        "bot",
        "acme-bot-user",
        "ci-robot",
        "ci_robot",
        "claude[bot]",
        "deploy_bot",
        "reporting_mcp_svc",
        "acme-ci-helper[bot]",
        "acme-robot",
        "acme-service-account",
        "service_account_group_12345",
        "svc-cd-deployer",
        "svc_ci",
        "svc_devin_ai",
        "unblocked-code[bot]",
        "app/copyberry",
        "codecov-commenter",
        "mergify",
        "github-actions[bot]",
    ],
)
def test_bot_logins(login):
    assert is_bot_login(login) is True


@pytest.mark.parametrize("login", ["alice", "abbot", "robotics-team-lead", "bobby", "botsford"])
def test_human_logins(login):
    assert is_bot_login(login) is False


def test_is_bot_flag_wins():
    assert is_bot_login("plain-name", is_bot_flag=True) is True


def test_agent_bots_are_ai_and_other_bots_are_automation():
    assert is_ai_agent_login("claude[bot]") is True
    assert is_ai_agent_login("svc_devin_ai") is True
    assert is_ai_agent_login("chatgpt-codex-connector[bot]") is True
    assert is_ai_agent_login("svc-ci") is False
    assert is_automation_login("svc-ci") is True
    assert is_automation_login("app/copyberry") is True
    assert is_automation_login("claude[bot]") is False
    assert is_automation_login("alice") is False


def test_dependency_bots():
    assert is_dependency_bot("dependabot[bot]") is True
    assert is_dependency_bot("app/renovate") is True
    assert is_dependency_bot("codecov") is False
