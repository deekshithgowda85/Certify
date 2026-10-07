"""Small test data helpers shared by the API and dispatcher test-suites."""
from datetime import date, timedelta


def make_recipient(index: int = 0, **overrides) -> dict:
    data = {
        "name": f"Learner {index}",
        "email": f"learner{index}@example.com",
        "course_name": "Python Bootcamp",
        "completion_date": (date.today() - timedelta(days=1)).isoformat(),
    }
    data.update(overrides)
    return data


def make_recipients(count: int) -> list[dict]:
    return [make_recipient(i) for i in range(count)]
