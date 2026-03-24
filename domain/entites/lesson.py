from dataclasses import dataclass

@dataclass
class Lesson:
    id: int
    start_time = None
    end_time = None
    created_at = None
    updated_at = None
    comment = None
