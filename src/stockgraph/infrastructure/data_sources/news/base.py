from abc import ABC, abstractmethod

from stockgraph.domain.news import NewsBatch


class NewsSource(ABC):
    name: str

    @abstractmethod
    def fetch(self, limit: int = 50) -> NewsBatch:
        raise NotImplementedError
