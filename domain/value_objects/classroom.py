from dataclasses import dataclass

@dataclass
class Classroom:
    number: str

    def _validate(self):
        if not self.number or len(self.number) == 0:
            raise AttributeError("The number is required")

        if len(self.number) > 50:
            raise AttributeError("The number is too long")

    def __post_init__(self):
        self._validate()

