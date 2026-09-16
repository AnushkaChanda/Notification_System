import re

PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def render(template: str, payload: dict) -> str:
    def repl(match: re.Match) -> str:
        key = match.group(1)
        return str(payload.get(key, match.group(0)))

    return PLACEHOLDER.sub(repl, template)
