from datetime import date, timedelta

import pytest

from app.schemas.recipient import RecipientValidated, fallback_recipient_fields, validate_recipient
from helpers import make_recipient


def test_valid_recipient_passes():
    validated, error = validate_recipient(make_recipient(1))
    assert error is None
    assert validated.name == "Learner 1"
    assert str(validated.email) == "learner1@example.com"


def test_name_is_stripped():
    validated, _ = validate_recipient(make_recipient(1, name="  Ada Lovelace  "))
    assert validated.name == "Ada Lovelace"


@pytest.mark.parametrize("name", ["", "   ", None, 123])
def test_invalid_name_rejected(name):
    validated, error = validate_recipient(make_recipient(1, name=name))
    assert validated is None
    assert "name" in error


def test_name_longer_than_255_rejected():
    validated, error = validate_recipient(make_recipient(1, name="x" * 256))
    assert validated is None and "name" in error


@pytest.mark.parametrize("email", ["not-an-email", "a@", "@b.com", "", None])
def test_invalid_email_rejected(email):
    validated, error = validate_recipient(make_recipient(1, email=email))
    assert validated is None and "email" in error


def test_missing_course_name_rejected():
    raw = make_recipient(1)
    del raw["course_name"]
    validated, error = validate_recipient(raw)
    assert validated is None and "course_name" in error


def test_future_date_rejected():
    future = (date.today() + timedelta(days=2)).isoformat()
    validated, error = validate_recipient(make_recipient(1, completion_date=future))
    assert validated is None and "future" in error


def test_today_is_allowed():
    validated, error = validate_recipient(make_recipient(1, completion_date=date.today().isoformat()))
    assert error is None and validated is not None


@pytest.mark.parametrize("value", ["2024-13-45", "yesterday", "", None])
def test_unparseable_date_rejected(value):
    validated, error = validate_recipient(make_recipient(1, completion_date=value))
    assert validated is None and "completion_date" in error


def test_non_object_rejected():
    validated, error = validate_recipient("just a string")
    assert validated is None and error


def test_fallback_fields_are_storable_for_garbage_input():
    fields = fallback_recipient_fields({"name": None, "email": 5, "completion_date": "nope"})
    assert fields["name"] == ""
    assert fields["email"] == "5"
    assert fields["course_name"] == ""
    assert fields["completion_date"] == date(1970, 1, 1)


def test_model_can_be_used_directly():
    model = RecipientValidated(
        name="A", email="a@example.com", course_name="C", completion_date=date.today()
    )
    assert model.name == "A"
