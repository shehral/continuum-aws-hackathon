"""Tests for interview state determination (ML-P2-2)."""

import pytest

from agents.interview import InterviewAgent, InterviewState


class TestContentCoverageAnalysis:
    """Test the content coverage analysis."""

    @pytest.fixture
    def agent(self):
        """Create an interview agent for testing."""
        return InterviewAgent(fast_mode=True)

    def test_empty_history_zero_coverage(self, agent):
        """Empty history should have zero coverage."""
        coverage = agent._analyze_content_coverage([])
        assert all(v == 0 for v in coverage.values())

    def test_trigger_keywords_detected(self, agent):
        """Should detect trigger-related keywords."""
        history = [
            {
                "role": "user",
                "content": "We had a problem with our database performance. "
                "We needed to improve response times because users were complaining.",
            }
        ]
        coverage = agent._analyze_content_coverage(history)
        assert coverage["trigger"] > 0

    def test_context_keywords_detected(self, agent):
        """Should detect context-related keywords."""
        history = [
            {
                "role": "user",
                "content": "We already had PostgreSQL in our existing stack. "
                "The team had experience with it. Our budget was limited and "
                "we had a strict deadline.",
            }
        ]
        coverage = agent._analyze_content_coverage(history)
        assert coverage["context"] > 0

    def test_options_keywords_detected(self, agent):
        """Should detect options-related keywords."""
        history = [
            {
                "role": "user",
                "content": "We considered several options. We looked at "
                "MongoDB as an alternative. We also evaluated Redis versus Memcached.",
            }
        ]
        coverage = agent._analyze_content_coverage(history)
        assert coverage["options"] > 0

    def test_decision_keywords_detected(self, agent):
        """Should detect decision-related keywords."""
        history = [
            {
                "role": "user",
                "content": "We ultimately decided to use PostgreSQL. "
                "We chose it because we ended up selecting the familiar option.",
            }
        ]
        coverage = agent._analyze_content_coverage(history)
        assert coverage["decision"] > 0

    def test_rationale_keywords_detected(self, agent):
        """Should detect rationale-related keywords."""
        history = [
            {
                "role": "user",
                "content": "We chose this because it was better for our needs. "
                "The trade-off was complexity, but the benefit outweighed the risk.",
            }
        ]
        coverage = agent._analyze_content_coverage(history)
        assert coverage["rationale"] > 0


class TestHeuristicStateDetermination:
    """Test the heuristic state determination."""

    @pytest.fixture
    def agent(self):
        """Create an interview agent for testing."""
        return InterviewAgent(fast_mode=True)

    def test_empty_history_trigger_state(self, agent):
        """Empty history should return TRIGGER state."""
        state = agent._determine_next_state_heuristic([])
        assert state == InterviewState.TRIGGER

    def test_one_response_context_state(self, agent):
        """One response should move to CONTEXT state."""
        history = [
            {"role": "user", "content": "We had a performance problem with our API."}
        ]
        state = agent._determine_next_state_heuristic(history)
        assert state == InterviewState.CONTEXT

    def test_two_responses_options_state(self, agent):
        """Two responses should move to OPTIONS state."""
        history = [
            {"role": "user", "content": "We had a performance problem with our API."},
            {
                "role": "user",
                "content": "We were using PostgreSQL and had budget constraints.",
            },
        ]
        state = agent._determine_next_state_heuristic(history)
        assert state == InterviewState.OPTIONS

    def test_many_responses_summarizing_state(self, agent):
        """Many responses should move to SUMMARIZING state."""
        history = [
            {"role": "user", "content": f"Response {i} with enough content to count."}
            for i in range(6)
        ]
        state = agent._determine_next_state_heuristic(history)
        assert state == InterviewState.SUMMARIZING

    def test_short_responses_not_counted(self, agent):
        """Short responses (<20 chars) should not count."""
        history = [
            {"role": "user", "content": "yes"},
            {"role": "user", "content": "no"},
            {"role": "user", "content": "ok"},
        ]
        state = agent._determine_next_state_heuristic(history)
        assert state == InterviewState.TRIGGER  # Should still be at trigger


class TestEnhancedStateDetermination:
    """Test the enhanced content-based state determination."""

    @pytest.fixture
    def agent(self):
        """Create an interview agent for testing."""
        return InterviewAgent(fast_mode=True)

    def test_short_conversation_uses_heuristic(self, agent):
        """Short conversations should fall back to heuristic."""
        history = [{"role": "user", "content": "Just starting the conversation."}]
        state = agent._determine_next_state(history)
        # Should use heuristic for short conversations
        assert state == InterviewState.CONTEXT

    def test_missing_trigger_focuses_trigger(self, agent):
        """If trigger is missing, should focus on trigger."""
        # History discusses options and decision but no trigger
        history = [
            {"role": "user", "content": "This is a long enough response for testing."},
            {
                "role": "user",
                "content": "We considered several alternatives and options.",
            },
            {"role": "user", "content": "We decided to use PostgreSQL."},
        ]
        state = agent._determine_next_state(history)
        # Should identify trigger as missing
        assert state == InterviewState.TRIGGER

    def test_complete_coverage_summarizes(self, agent):
        """Complete coverage should move to summarizing."""
        # Comprehensive history covering all aspects
        history = [
            {
                "role": "user",
                "content": "This is enough text to be counted as a response.",
            },
            {
                "role": "user",
                "content": (
                    "We had a problem and needed to address an issue. "
                    "The challenge was significant."
                ),
            },
            {
                "role": "user",
                "content": (
                    "We already had an existing system with constraints. "
                    "Our team had experience and there was a budget limit."
                ),
            },
            {
                "role": "user",
                "content": (
                    "We considered several options and alternatives. "
                    "We evaluated and compared different approaches."
                ),
            },
            {
                "role": "user",
                "content": (
                    "We decided to use this approach. We chose and selected it. "
                    "We ultimately went with this option."
                ),
            },
            {
                "role": "user",
                "content": (
                    "We chose this because of the benefits. "
                    "The reason was it was better and had advantages. "
                    "We accepted the trade-off."
                ),
            },
        ]
        state = agent._determine_next_state(history)
        assert state == InterviewState.SUMMARIZING


class TestFallbackResponses:
    """Test fallback response generation."""

    @pytest.fixture
    def agent(self):
        """Create an interview agent in fast mode."""
        return InterviewAgent(fast_mode=True)

    def test_trigger_fallback(self, agent):
        """Should generate appropriate trigger-stage response."""
        agent.state = InterviewState.TRIGGER
        response = agent._generate_fallback_response("initial message", [])
        # Response should be about gathering context
        assert "context" in response.lower() or "situation" in response.lower()

    def test_context_fallback(self, agent):
        """Should generate appropriate context-stage response."""
        history = [
            {
                "role": "user",
                "content": "We had a database performance issue that needed addressing.",
            }
        ]
        agent.state = InterviewState.CONTEXT
        response = agent._generate_fallback_response("context info", history)
        # Response should be about exploring options
        assert "option" in response.lower() or "alternative" in response.lower()

    def test_summarizing_fallback(self, agent):
        """Should generate appropriate summarizing response when all stages covered."""
        # Create comprehensive history that covers all stages
        history = [
            {
                "role": "user",
                "content": "We had a problem and needed to solve an issue urgently.",
            },
            {
                "role": "user",
                "content": "We already had an existing system with budget constraints.",
            },
            {
                "role": "user",
                "content": "We considered several options and alternatives to evaluate.",
            },
            {
                "role": "user",
                "content": "We decided to choose PostgreSQL and selected this approach.",
            },
            {
                "role": "user",
                "content": "We chose this because it was better with clear benefits.",
            },
            {
                "role": "user",
                "content": "The trade-off was acceptable given our rationale.",
            },
        ]
        response = agent._generate_fallback_response("final input", history)
        # Response should indicate completion/capture since all stages covered
        assert (
            "captured" in response.lower()
            or "saved" in response.lower()
            or "knowledge graph" in response.lower()
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
