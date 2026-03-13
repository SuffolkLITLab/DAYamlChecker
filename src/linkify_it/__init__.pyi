from typing import Any


class SchemaError(Exception): ...


class Match:
    schema: str
    index: int
    last_index: int
    raw: str
    text: str
    url: str


class LinkifyIt:
    def __init__(
        self,
        schemas: dict[str, Any] | None = ...,
        options: dict[str, bool] | None = ...,
    ) -> None: ...
    def match(self, text: str) -> list[Match] | None: ...
