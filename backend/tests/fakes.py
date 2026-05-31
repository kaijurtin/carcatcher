"""Test doubles for the Anthropic SDK surface used by AIClient + Firecrawl."""

from __future__ import annotations

from pathlib import Path

_FIXTURE = Path(__file__).parent / "fixtures" / "kleinanzeigen_search.html"


class FakeFirecrawl:
    """Returns the fixture HTML for the first page, then empty (pagination stop)."""

    def __init__(self) -> None:
        self.calls = 0

    async def scrape(self, url: str, *, formats=None, only_main_content=True) -> dict:
        self.calls += 1
        if self.calls == 1:
            return {"html": _FIXTURE.read_text(encoding="utf-8")}
        return {"html": ""}

    async def aclose(self) -> None:  # match FirecrawlClient surface
        return None


class FakeBlock:
    def __init__(self, type: str, name: str | None = None, input: dict | None = None):
        self.type = type
        self.name = name
        self.input = input or {}


class FakeUsage:
    def __init__(self, input_tokens: int = 100, output_tokens: int = 30):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class FakeResponse:
    def __init__(self, content: list, usage: FakeUsage | None = None):
        self.content = content
        self.usage = usage or FakeUsage()


class FakeAPIError(Exception):
    def __init__(self, status_code: int = 503):
        super().__init__(f"fake api error {status_code}")
        self.status_code = status_code


class FakeMessages:
    def __init__(self, response: FakeResponse, exc_sequence: list | None = None):
        self._response = response
        self._exc = list(exc_sequence or [])
        self.calls = 0
        self.last_kwargs: dict | None = None

    async def create(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        if self._exc:
            exc = self._exc.pop(0)
            if exc is not None:
                raise exc
        return self._response


class FakeAnthropic:
    def __init__(self, tool_input: dict, *, tool_name: str = "extract_listing",
                 usage: FakeUsage | None = None, exc_sequence: list | None = None):
        response = FakeResponse(
            content=[FakeBlock("text", input=None),
                     FakeBlock("tool_use", name=tool_name, input=tool_input)],
            usage=usage,
        )
        self.messages = FakeMessages(response, exc_sequence)
