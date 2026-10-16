"""Unit tests for tokenizer, stemmer, mock embedder, cosine similarity, and Gemini factory."""

from __future__ import annotations

import math
from unittest.mock import MagicMock
import pytest

from memory_core.embedder import (
    GeminiEmbedder,
    MockEmbedder,
    cosine,
    get_embedder,
    mock_embed,
    stem,
    tokens,
)


def test_stem_examples_from_spec_section_5_1() -> None:
    """Assert stemming rules produce exact stems for canonical domain terms."""
    assert stem("charged") == "charg"
    assert stem("charge") == "charg"
    assert stem("invoice") == "invoic"
    assert stem("billing") == "bill"
    assert stem("refunded") == "refund"
    assert stem("duplicate") == "duplicat"


def test_tokens_stripping_and_splitting() -> None:
    """Assert tokenizing splits non-alphanumerics, lowercases, and strips stopwords."""
    assert tokens("INV-1042") == ["inv", "1042"]
    assert tokens("Hello, my card was charged!") == ["hello", "card", "charged"]


def test_mock_embed_deterministic_and_unit_length() -> None:
    """Assert mock embedder output is deterministic and unit length."""
    text = "Verify duplicate charge on invoice INV-1042"
    v1 = mock_embed(text, dim=4096)
    v2 = mock_embed(text, dim=4096)
    assert v1 == v2
    assert len(v1) == 4096

    norm = math.sqrt(sum(x * x for x in v1))
    assert abs(norm - 1.0) < 1e-6


def test_cosine_similarity_golden_recall_values() -> None:
    """Assert cosine similarities between Q1 and seed episodes match Section 3 G2 goldens."""
    q1 = "Hello, my card shows a duplicate charge again on invoice INV-1042."
    ep1 = "Priya reported a duplicate charge on invoice INV-1042; Billing refunded the duplicate; resolved."
    ep2 = "Priya could not log in to the VPN client; Tech reset her token; resolved."
    ep3 = "Priya asked about a late fee on invoice INV-1042; Billing explained the fee policy; resolved."

    v_q1 = mock_embed(q1, dim=4096)
    v_ep1 = mock_embed(ep1, dim=4096)
    v_ep2 = mock_embed(ep2, dim=4096)
    v_ep3 = mock_embed(ep3, dim=4096)

    cos_q1_ep1 = cosine(v_q1, v_ep1)
    cos_q1_ep2 = cosine(v_q1, v_ep2)
    cos_q1_ep3 = cosine(v_q1, v_ep3)

    assert abs(cos_q1_ep1 - 0.555) < 0.02
    assert cos_q1_ep2 == 0.0
    assert abs(cos_q1_ep3 - 0.267) < 0.02


def test_embedder_factory_routing() -> None:
    """Assert get_embedder returns MockEmbedder for mock and GeminiEmbedder otherwise."""
    mock_inst = get_embedder(provider="mock", dim=4096)
    assert isinstance(mock_inst, MockEmbedder)
    assert mock_inst.dim == 4096

    stub_client = MagicMock()
    stub_response = MagicMock()
    stub_response.embedding.values = [1.0, 0.0, 0.0]
    stub_client.models.embed_content.return_value = stub_response

    gemini_inst = get_embedder(provider="gemini", dim=768, client=stub_client)
    assert isinstance(gemini_inst, GeminiEmbedder)
    assert gemini_inst.dim == 768

    vec = gemini_inst.embed("test text")
    assert abs(math.sqrt(sum(x * x for x in vec)) - 1.0) < 1e-6
    assert stub_client.models.embed_content.called
