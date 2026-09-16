from app.services.policy import is_retryable
from app.services.render import render


def test_render_placeholders():
    out = render("Hi {{ user_name }}, order {{order_id}}", {"user_name": "Anushka", "order_id": "991"})
    assert out == "Hi Anushka, order 991"


def test_render_keeps_unknown_placeholder():
    assert "{{missing}}" in render("{{missing}}", {})


def test_retryable_timeout():
    assert is_retryable("connection timeout") is True
    assert is_retryable("503 unavailable") is True
    assert is_retryable("429 too many") is True


def test_permanent_client_errors():
    assert is_retryable("invalid destination 400") is False
    assert is_retryable("permanent bounce") is False
