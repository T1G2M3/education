from abc import ABC, abstractmethod

class BaseStrategy(ABC):
    @abstractmethod
    def analyze(self, data):
        pass

    @abstractmethod
    def get_params(self):
        pass

    @abstractmethod
    def set_params(self, **kwargs):
        pass
