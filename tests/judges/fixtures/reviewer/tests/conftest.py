"""Fakes shared by the tests."""

from attrs import define, field


@define
class FakeItem:
    """Queue message that records whether it was resized."""

    kind: str
    ok: bool
    resized: bool = field(default=False, init=False)

    def resize(self) -> None:
        self.resized = True
