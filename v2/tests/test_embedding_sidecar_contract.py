import pytest

from embedding_sidecar.contract import cosine_similarity, validate_text, validate_texts


def test_validate_text_strips_and_rejects_blank():
    assert validate_text("  hello  ") == "hello"
    with pytest.raises(ValueError, match="must not be empty"):
        validate_text("   ")


def test_validate_texts_limits_batch_size():
    with pytest.raises(ValueError, match="at most 32"):
        validate_texts(["x"] * 33)


def test_cosine_similarity():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_rejects_dimension_mismatch():
    with pytest.raises(ValueError, match="dimensions"):
        cosine_similarity([1.0], [1.0, 2.0])
