from abc import ABC, abstractmethod

from stockgraph.domain.dragon_tiger import DragonTigerBatch


class DragonTigerSource(ABC):
    name: str

    @abstractmethod
    def fetch(self, trade_date: str) -> DragonTigerBatch | None:
        raise NotImplementedError
