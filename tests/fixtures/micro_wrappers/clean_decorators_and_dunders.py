import abc


class BaseProcessor(abc.ABC):
    def __init__(self, name: str):
        self.name = name

    @property
    def processor_name(self) -> str:
        return self.name

    @abc.abstractmethod
    def process(self, data: str) -> str:
        pass


def test_example():
    pass


def main():
    return 0
