from abc import ABC, abstractmethod

class EmailProvider(ABC):
    @abstractmethod
    def send(self, *, to: str, subject: str, html: str, text: str | None = None) -> None:
        ...