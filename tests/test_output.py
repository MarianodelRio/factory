import json

from factory.output import EXIT_PRECONDITION, FactoryError, error_envelope, ok_envelope, render


def test_ok_envelope():
    assert ok_envelope({"a": 1}, ["w"]) == {"ok": True, "data": {"a": 1}, "warnings": ["w"]}


def test_error_envelope():
    err = FactoryError("not_approved", "CHG-0012 is not approved", EXIT_PRECONDITION)
    assert error_envelope(err) == {
        "ok": False,
        "error": {"code": "not_approved", "message": "CHG-0012 is not approved"},
        "warnings": [],
    }


def test_render_json_is_one_line_object():
    text = render(ok_envelope({"a": [1, 2]}), as_json=True)
    assert "\n" not in text
    assert json.loads(text)["data"] == {"a": [1, 2]}


def test_render_human_nested():
    data = {"task": "CHG-0001-01", "acceptance": {"AC-01": "verified"}}
    text = render(ok_envelope(data, ["careful"]), as_json=False)
    assert "task: CHG-0001-01" in text
    assert "  AC-01: verified" in text
    assert "warning: careful" in text
