"""Tests for claude_advisor.py — strategy recommendation parsing and logic."""
import json
import pytest
from unittest.mock import patch, MagicMock


SAMPLE_TRADE = {
    "txDate": "2026-04-20",
    "txType": "Buy",
    "size": "$100,001 - $250,000",
    "politician": {"name": "Michael McCaul", "id": "P001"},
    "asset": {"ticker": "NVDA"},
}

SAMPLE_CONTEXT = {
    "price": 875.50,
    "buying_power": 25_000.0,
    "existing_positions": [],
    "days_since_disclosure": 2,
}


def _mock_claude_response(strategy: str, confidence: int, reasoning: str):
    """Build a mock Anthropic API response."""
    payload = {
        "strategy": strategy,
        "confidence": confidence,
        "reasoning": reasoning,
        "suggested_position_size_pct": 0.08,
        "key_risk": "Test risk",
    }
    content_block = MagicMock()
    content_block.type = "text"
    content_block.text = json.dumps(payload)

    usage = MagicMock()
    usage.cache_read_input_tokens = 0
    usage.cache_creation_input_tokens = 1200

    response = MagicMock()
    response.content = [content_block]
    response.usage = usage
    return response


class TestGetRecommendation:
    @patch("agents.claude_advisor.anthropic.Anthropic")
    @patch("agents.claude_advisor.CREDS_FILE")
    def test_returns_trailing_stop(self, mock_creds_file, mock_anthropic_cls):
        mock_creds_file.read_text.return_value = json.dumps(
            {"anthropic": {"api_key": "sk-test"}}
        )
        client = MagicMock()
        mock_anthropic_cls.return_value = client
        client.messages.create.return_value = _mock_claude_response(
            "TRAILING_STOP", 85, "High-momentum semiconductor stock."
        )

        from agents.claude_advisor import get_recommendation
        rec = get_recommendation(SAMPLE_TRADE, SAMPLE_CONTEXT)

        assert rec["strategy"] == "TRAILING_STOP"
        assert rec["confidence"] == 85
        assert "semiconductor" in rec["reasoning"].lower()

    @patch("agents.claude_advisor.anthropic.Anthropic")
    @patch("agents.claude_advisor.CREDS_FILE")
    def test_returns_wheel(self, mock_creds_file, mock_anthropic_cls):
        mock_creds_file.read_text.return_value = json.dumps(
            {"anthropic": {"api_key": "sk-test"}}
        )
        client = MagicMock()
        mock_anthropic_cls.return_value = client
        client.messages.create.return_value = _mock_claude_response(
            "WHEEL", 72, "Stable blue-chip with liquid options."
        )

        from agents.claude_advisor import get_recommendation
        rec = get_recommendation(SAMPLE_TRADE, SAMPLE_CONTEXT)

        assert rec["strategy"] == "WHEEL"
        assert rec["confidence"] == 72

    @patch("agents.claude_advisor.anthropic.Anthropic")
    @patch("agents.claude_advisor.CREDS_FILE")
    def test_handles_markdown_fenced_json(self, mock_creds_file, mock_anthropic_cls):
        """Claude sometimes wraps JSON in ```json ... ``` fences."""
        mock_creds_file.read_text.return_value = json.dumps(
            {"anthropic": {"api_key": "sk-test"}}
        )
        payload = json.dumps({
            "strategy": "SKIP",
            "confidence": 30,
            "reasoning": "Stale disclosure.",
            "suggested_position_size_pct": 0.0,
            "key_risk": "Old news",
        })
        fenced_text = f"```json\n{payload}\n```"

        content_block = MagicMock()
        content_block.type = "text"
        content_block.text = fenced_text
        usage = MagicMock()
        usage.cache_read_input_tokens = 0
        usage.cache_creation_input_tokens = 1200
        resp = MagicMock()
        resp.content = [content_block]
        resp.usage = usage

        client = MagicMock()
        mock_anthropic_cls.return_value = client
        client.messages.create.return_value = resp

        from agents.claude_advisor import get_recommendation
        rec = get_recommendation(SAMPLE_TRADE, SAMPLE_CONTEXT)

        assert rec["strategy"] == "SKIP"

    @patch("agents.claude_advisor.anthropic.Anthropic")
    @patch("agents.claude_advisor.CREDS_FILE")
    def test_bad_json_defaults_to_skip(self, mock_creds_file, mock_anthropic_cls):
        """Malformed Claude response must default to SKIP, never crash."""
        mock_creds_file.read_text.return_value = json.dumps(
            {"anthropic": {"api_key": "sk-test"}}
        )
        content_block = MagicMock()
        content_block.type = "text"
        content_block.text = "I cannot decide right now."
        usage = MagicMock()
        usage.cache_read_input_tokens = 0
        usage.cache_creation_input_tokens = 0
        resp = MagicMock()
        resp.content = [content_block]
        resp.usage = usage

        client = MagicMock()
        mock_anthropic_cls.return_value = client
        client.messages.create.return_value = resp

        from agents.claude_advisor import get_recommendation
        rec = get_recommendation(SAMPLE_TRADE, SAMPLE_CONTEXT)

        assert rec["strategy"] == "SKIP"
        assert rec["confidence"] == 0

    @patch("agents.claude_advisor.anthropic.Anthropic")
    @patch("agents.claude_advisor.CREDS_FILE")
    def test_cache_hit_tracked(self, mock_creds_file, mock_anthropic_cls):
        mock_creds_file.read_text.return_value = json.dumps(
            {"anthropic": {"api_key": "sk-test"}}
        )
        client = MagicMock()
        mock_anthropic_cls.return_value = client
        resp = _mock_claude_response("TRAILING_STOP", 80, "Test")
        resp.usage.cache_read_input_tokens = 1500   # simulate cache hit
        client.messages.create.return_value = resp

        from agents.claude_advisor import get_recommendation
        rec = get_recommendation(SAMPLE_TRADE, SAMPLE_CONTEXT)

        assert rec["_cache_hit"] is True
        assert rec["_tokens_saved"] == 1500
