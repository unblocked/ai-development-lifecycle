import re

BOT_TOKEN = re.compile(r"(^|[^A-Za-z0-9])(svc|service|robot|bot)([^A-Za-z0-9]|$)", re.IGNORECASE)
AI_AGENT_TOKEN = re.compile(r"(claude|copilot|codex|cursor|anthropic|openai|gemini|devin|windsurf|aider|amp)", re.IGNORECASE)
KNOWN_BOT_LOGINS = frozenset(
    {
        "dependabot",
        "renovate",
        "renovate-bot",
        "github-actions",
        "codecov",
        "codecov-commenter",
        "codecov-io",
        "coderabbit",
        "coderabbitai",
        "sonarcloud",
        "sonarqube",
        "snyk-bot",
        "greenkeeper",
        "imgbot",
        "stale",
        "mergify",
        "netlify",
        "vercel",
        "circleci",
        "travis-ci",
        "jenkins",
        "copyberry",
    }
)
DEPENDENCY_BOT_LOGINS = frozenset({"dependabot", "renovate", "renovate-bot", "greenkeeper"})


def normalize(login: str) -> str:
    return login.strip().lower().removeprefix("app/").removesuffix("[bot]")


def is_bot_login(login: str, is_bot_flag: bool = False) -> bool:
    if is_bot_flag:
        return True
    raw = login.strip().lower()
    if raw.startswith("app/") or raw.endswith("[bot]"):
        return True
    return normalize(raw) in KNOWN_BOT_LOGINS or bool(BOT_TOKEN.search(raw))


def is_dependency_bot(login: str) -> bool:
    return normalize(login) in DEPENDENCY_BOT_LOGINS


def is_ai_agent_login(login: str, is_bot_flag: bool = False) -> bool:
    return is_bot_login(login, is_bot_flag) and bool(AI_AGENT_TOKEN.search(normalize(login)))


def is_automation_login(login: str, is_bot_flag: bool = False) -> bool:
    return is_bot_login(login, is_bot_flag) and not is_ai_agent_login(login, is_bot_flag)
