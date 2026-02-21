"""AI-powered interview agent for knowledge capture with stage-specific prompts (ML-P2-1).

SEC-009: Supports per-user rate limiting by passing user_id to LLM calls.
"""

from enum import Enum
from typing import AsyncIterator

from models.schemas import Entity
from services.extractor import DecisionExtractor
from services.llm import get_llm_client
from utils.json_extraction import extract_json_from_response
from utils.logging import get_logger

logger = get_logger(__name__)


class InterviewState(str, Enum):
    OPENING = "opening"
    TRIGGER = "trigger"
    CONTEXT = "context"
    OPTIONS = "options"
    DECISION = "decision"
    RATIONALE = "rationale"
    SUMMARIZING = "summarizing"


# Stage-specific prompts with detailed guidance (ML-P2-1)
# Each stage has specific goals, focus areas, and example questions
STAGE_PROMPTS = {
    InterviewState.OPENING: {
        "goal": "Understand what decision the user wants to document",
        "focus": [
            "Welcome the user warmly",
            "Ask an open-ended question about what they want to capture",
            "Be encouraging and make them feel comfortable sharing",
        ],
        "questions": [
            "What decision or choice would you like to document today?",
            "Tell me about a recent decision you made that you'd like to preserve.",
            "What technical choice or trade-off is on your mind?",
        ],
        "avoid": [
            "Asking multiple questions at once",
            "Being too formal or robotic",
            "Jumping ahead to details before understanding the topic",
        ],
    },
    InterviewState.TRIGGER: {
        "goal": "Understand what prompted this decision - the problem or need",
        "focus": [
            "What problem or need prompted this decision?",
            "When did this come up? What was the timeline or urgency?",
            "Who identified the need? What stakeholders were involved?",
            "How severe or important was the problem?",
        ],
        "questions": [
            "What problem were you trying to solve?",
            "What prompted this decision? Was there a specific event or deadline?",
            "How did you first notice this was needed?",
            "Who brought this issue to your attention?",
            "How urgent was this decision? What was the timeline?",
        ],
        "avoid": [
            "Moving on without understanding the root cause",
            "Assuming you understand the problem without clarification",
            "Skipping the 'why now' question",
        ],
    },
    InterviewState.CONTEXT: {
        "goal": "Capture the background, constraints, and environment",
        "focus": [
            "What was the existing system or situation?",
            "What constraints existed (time, budget, team skills, tech stack)?",
            "What requirements or goals had to be met?",
            "What organizational factors influenced the situation?",
        ],
        "questions": [
            "What was already in place before this decision?",
            "What constraints did you have to work within?",
            "Were there any non-negotiable requirements?",
            "What was the team's experience level with the options?",
            "Were there budget or timeline constraints?",
            "What was the technical environment like?",
        ],
        "avoid": [
            "Assuming context from the trigger alone",
            "Missing important constraints that shaped the decision",
            "Not asking about organizational or team factors",
        ],
    },
    InterviewState.OPTIONS: {
        "goal": "Explore ALL alternatives considered, including rejected ones",
        "focus": [
            "What alternatives were considered?",
            "Why were certain options rejected?",
            "Were there options that seemed obvious but were ruled out?",
            "What research or evaluation was done?",
        ],
        "questions": [
            "What alternatives did you consider?",
            "Were there any options you ruled out early? Why?",
            "Did you do any proof-of-concepts or research?",
            "What other approaches did the team suggest?",
            "Was there an obvious option that you decided against?",
            "Did you consider doing nothing or deferring the decision?",
        ],
        "avoid": [
            "Accepting just 2 options without probing for more",
            "Not asking why alternatives were rejected",
            "Missing the 'do nothing' option consideration",
        ],
    },
    InterviewState.DECISION: {
        "goal": "Clearly capture what was ultimately decided",
        "focus": [
            "What was the final decision?",
            "When was it made and by whom?",
            "Was there consensus or disagreement?",
            "What specific choice or implementation was selected?",
        ],
        "questions": [
            "So what did you ultimately decide?",
            "Can you state the decision clearly in one sentence?",
            "Was this a team decision or individual?",
            "Was there disagreement? How was it resolved?",
            "When did you make the final call?",
        ],
        "avoid": [
            "Conflating the decision with the rationale",
            "Not getting a clear, quotable decision statement",
            "Missing who actually made the decision",
        ],
    },
    InterviewState.RATIONALE: {
        "goal": "Understand why this decision was made over alternatives",
        "focus": [
            "Why was this option chosen over others?",
            "What trade-offs were accepted?",
            "What risks were considered?",
            "What would change this decision in the future?",
        ],
        "questions": [
            "Why did you choose this over the alternatives?",
            "What trade-offs did you accept with this choice?",
            "What risks did you consider?",
            "What would make you revisit this decision?",
            "Was there anything that almost changed your mind?",
            "What's the biggest downside of this choice?",
        ],
        "avoid": [
            "Accepting vague rationale like 'it was best'",
            "Not probing for trade-offs and risks",
            "Missing the conditions for revisiting the decision",
        ],
    },
    InterviewState.SUMMARIZING: {
        "goal": "Confirm the complete decision trace with the user",
        "focus": [
            "Summarize all captured information clearly",
            "Confirm accuracy with the user",
            "Ask if anything is missing",
            "Thank them for their time",
        ],
        "questions": [
            "Let me summarize what I captured. Does this look correct?",
            "Is there anything I missed or got wrong?",
            "Any additional context you'd like to add?",
        ],
        "avoid": [
            "Not reading back the captured information",
            "Ending abruptly without confirmation",
            "Missing important details in the summary",
        ],
    },
}


def _format_stage_guidance(state: InterviewState) -> str:
    """Format the stage-specific guidance into a prompt section.

    Args:
        state: The current interview state

    Returns:
        Formatted guidance string for the LLM
    """
    stage_info = STAGE_PROMPTS.get(state, STAGE_PROMPTS[InterviewState.OPENING])

    guidance_parts = [
        f"CURRENT STAGE: {state.value.upper()}",
        f"GOAL: {stage_info['goal']}",
        "",
        "FOCUS AREAS:",
    ]

    for focus in stage_info["focus"]:
        guidance_parts.append(f"  - {focus}")

    guidance_parts.extend(
        [
            "",
            "EXAMPLE QUESTIONS (pick ONE that fits the context):",
        ]
    )

    for question in stage_info["questions"][:3]:  # Limit to avoid prompt bloat
        guidance_parts.append(f'  - "{question}"')

    guidance_parts.extend(
        [
            "",
            "AVOID:",
        ]
    )

    for avoid in stage_info["avoid"]:
        guidance_parts.append(f"  - {avoid}")

    return "\n".join(guidance_parts)


class InterviewAgent:
    """AI-powered interview agent for knowledge capture using NVIDIA Llama.

    Features:
    - Enhanced stage-specific prompts (ML-P2-1) with goals, focus areas,
      example questions, and anti-patterns to avoid
    - Per-user rate limiting (SEC-009) via user_id parameter
    - Fast mode for instant pre-written responses
    """

    def __init__(self, fast_mode: bool = False, user_id: str | None = None):
        """Initialize the interview agent.

        Args:
            fast_mode: If True, uses pre-written responses for faster interaction.
                      If False, uses LLM for each response (slower but more dynamic).
            user_id: User ID for per-user rate limiting (SEC-009).
        """
        self.llm = get_llm_client()
        self.extractor = DecisionExtractor()
        self.state = InterviewState.OPENING
        self.fast_mode = fast_mode
        self.user_id = user_id

    def _get_system_prompt(self) -> str:
        return """You are a knowledge capture assistant helping engineers document their decisions.

Your goal is to extract a complete decision trace with these components:
1. TRIGGER - What prompted the decision (problem, need, event)
2. CONTEXT - Background, constraints, environment
3. OPTIONS - Alternatives considered (including rejected ones)
4. DECISION - What was ultimately chosen
5. RATIONALE - Why this choice was made over others

INTERVIEW GUIDELINES:
- Ask ONE question at a time (never multiple questions)
- Keep responses concise (2-3 sentences max)
- Be conversational and encouraging
- Listen carefully and reference what the user has said
- Probe deeper when answers are vague
- Move to the next stage when you have enough detail

You will receive stage-specific guidance for what to focus on."""

    def _get_stage_prompt(self, state: InterviewState) -> str:
        """Get the detailed prompt guidance for a specific interview stage.

        ML-P2-1: Returns rich guidance including goal, focus areas,
        example questions, and anti-patterns.

        Args:
            state: The current interview state

        Returns:
            Formatted stage guidance string
        """
        return _format_stage_guidance(state)

    def _determine_next_state_heuristic(self, history: list[dict]) -> InterviewState:
        """Determine the next state using simple response count heuristic.

        This is a fast, deterministic fallback used when:
        - fast_mode is enabled
        - LLM-based detection fails
        - Conversation is very short

        Args:
            history: List of conversation messages

        Returns:
            The appropriate next state
        """
        # Count substantial user responses (>20 chars indicates real content)
        user_responses = [
            m for m in history if m["role"] == "user" and len(m["content"]) > 20
        ]

        response_count = len(user_responses)

        if response_count == 0:
            return InterviewState.TRIGGER
        elif response_count == 1:
            return InterviewState.CONTEXT
        elif response_count == 2:
            return InterviewState.OPTIONS
        elif response_count == 3:
            return InterviewState.DECISION
        elif response_count == 4:
            return InterviewState.RATIONALE
        else:
            return InterviewState.SUMMARIZING

    def _analyze_content_coverage(self, history: list[dict]) -> dict[str, float]:
        """Analyze what decision components are covered in the conversation.

        Uses keyword and pattern matching to estimate coverage of each stage.
        ML-P2-2: This provides fast, local analysis without LLM calls.

        Args:
            history: List of conversation messages

        Returns:
            Dict mapping stage names to coverage scores (0.0 to 1.0)
        """
        # Combine all user messages for analysis
        user_text = " ".join(
            m["content"].lower() for m in history if m["role"] == "user"
        )

        coverage = {}

        # TRIGGER indicators - problem, need, event that started the decision
        trigger_patterns = [
            "problem",
            "issue",
            "need",
            "require",
            "had to",
            "wanted to",
            "because",
            "since",
            "when",
            "started",
            "began",
            "noticed",
            "realized",
            "discovered",
            "faced",
            "encountered",
            "challenge",
        ]
        trigger_score = sum(1 for p in trigger_patterns if p in user_text)
        coverage["trigger"] = min(1.0, trigger_score / 5)

        # CONTEXT indicators - background, constraints, environment
        context_patterns = [
            "already",
            "existing",
            "current",
            "before",
            "had",
            "constraint",
            "limit",
            "budget",
            "deadline",
            "team",
            "experience",
            "skill",
            "environment",
            "stack",
            "using",
            "requirement",
            "needed to",
            "had to support",
        ]
        context_score = sum(1 for p in context_patterns if p in user_text)
        coverage["context"] = min(1.0, context_score / 5)

        # OPTIONS indicators - alternatives considered
        options_patterns = [
            "option",
            "alternative",
            "considered",
            "looked at",
            "evaluated",
            "compared",
            "versus",
            "vs",
            "or",
            "could have",
            "might have",
            "other",
            "different",
            "instead",
            "also thought",
            "ruled out",
        ]
        options_score = sum(1 for p in options_patterns if p in user_text)
        coverage["options"] = min(1.0, options_score / 4)

        # DECISION indicators - what was chosen
        decision_patterns = [
            "decided",
            "chose",
            "went with",
            "picked",
            "selected",
            "ended up",
            "final",
            "ultimately",
            "concluded",
            "settled on",
            "we use",
            "we're using",
            "implemented",
            "adopted",
        ]
        decision_score = sum(1 for p in decision_patterns if p in user_text)
        coverage["decision"] = min(1.0, decision_score / 3)

        # RATIONALE indicators - why the choice was made
        rationale_patterns = [
            "because",
            "since",
            "reason",
            "why",
            "benefit",
            "advantage",
            "better",
            "easier",
            "faster",
            "cheaper",
            "simpler",
            "more",
            "trade-off",
            "tradeoff",
            "downside",
            "risk",
            "concern",
            "weighed",
            "balanced",
            "considered",
        ]
        rationale_score = sum(1 for p in rationale_patterns if p in user_text)
        coverage["rationale"] = min(1.0, rationale_score / 4)

        return coverage

    def _determine_next_state(self, history: list[dict]) -> InterviewState:
        """Determine the next state based on conversation analysis (ML-P2-2).

        Enhanced state determination using content analysis:
        1. Analyze what decision components have been covered
        2. Identify gaps in the decision trace
        3. Determine the most appropriate next stage

        Falls back to count-based heuristic for very short conversations
        or when fast_mode is enabled.

        Args:
            history: List of conversation messages

        Returns:
            The appropriate next state
        """
        # For very short conversations, use simple heuristic
        user_responses = [
            m for m in history if m["role"] == "user" and len(m["content"]) > 20
        ]
        if len(user_responses) <= 1:
            return self._determine_next_state_heuristic(history)

        # Analyze content coverage
        coverage = self._analyze_content_coverage(history)

        # Determine which stage needs the most attention
        # Threshold for considering a stage "covered enough"
        coverage_threshold = 0.4

        # Check stages in order - find the first one that's not well covered
        stage_order = [
            ("trigger", InterviewState.TRIGGER),
            ("context", InterviewState.CONTEXT),
            ("options", InterviewState.OPTIONS),
            ("decision", InterviewState.DECISION),
            ("rationale", InterviewState.RATIONALE),
        ]

        for stage_name, stage_enum in stage_order:
            if coverage.get(stage_name, 0) < coverage_threshold:
                logger.debug(
                    f"Stage {stage_name} coverage: {coverage.get(stage_name, 0):.2f} < {coverage_threshold}, "
                    f"focusing on this stage"
                )
                return stage_enum

        # All stages have reasonable coverage - time to summarize
        total_coverage = sum(coverage.values()) / len(coverage)
        if total_coverage >= 0.5:
            return InterviewState.SUMMARIZING

        # Fallback to heuristic if analysis is inconclusive
        return self._determine_next_state_heuristic(history)

    async def _determine_state_with_llm(self, history: list[dict]) -> InterviewState:
        """Use LLM to determine the most appropriate next stage (ML-P2-2).

        This method uses the LLM to analyze the conversation and determine
        which decision component needs the most attention.

        Note: This is more expensive than heuristic methods. Use only when
        content analysis is ambiguous.

        Args:
            history: List of conversation messages

        Returns:
            The appropriate next state
        """
        if not history:
            return InterviewState.TRIGGER

        # Format conversation for LLM
        conversation_text = "\n".join(
            f"{m['role'].title()}: {m['content']}" for m in history[-8:]
        )

        prompt = f"""Analyze this interview conversation and determine what information is still needed
to complete a decision trace.

A complete decision trace needs:
1. TRIGGER - What problem or need prompted the decision
2. CONTEXT - Background, constraints, environment
3. OPTIONS - Alternatives that were considered
4. DECISION - What was ultimately chosen
5. RATIONALE - Why this choice was made

Conversation:
{conversation_text}

Based on what's been discussed, which component needs the most attention next?
Respond with ONLY one of: TRIGGER, CONTEXT, OPTIONS, DECISION, RATIONALE, or COMPLETE

If all components are well-covered, respond with COMPLETE."""

        try:
            response = await self.llm.generate(
                prompt,
                temperature=0.1,  # Low temperature for deterministic output
                max_tokens=20,
                user_id=self.user_id,
                sanitize_input=False,  # Internal prompt, no need to sanitize
            )

            # Parse response
            response_upper = response.strip().upper()

            state_mapping = {
                "TRIGGER": InterviewState.TRIGGER,
                "CONTEXT": InterviewState.CONTEXT,
                "OPTIONS": InterviewState.OPTIONS,
                "DECISION": InterviewState.DECISION,
                "RATIONALE": InterviewState.RATIONALE,
                "COMPLETE": InterviewState.SUMMARIZING,
            }

            for key, state in state_mapping.items():
                if key in response_upper:
                    logger.debug(f"LLM determined stage: {state.value}")
                    return state

            # Couldn't parse response, fall back to content analysis
            logger.warning(f"Could not parse LLM stage response: {response}")
            return self._determine_next_state(history)

        except Exception as e:
            logger.warning(f"LLM state determination failed: {e}, using heuristic")
            return self._determine_next_state_heuristic(history)

    async def process_message(
        self,
        user_message: str,
        history: list[dict],
    ) -> tuple[str, list[Entity]]:
        """Process a user message and generate a response.

        Args:
            user_message: The user's message
            history: Previous conversation history

        Returns:
            Tuple of (response text, extracted entities)
        """
        # Determine current state
        self.state = self._determine_next_state(history)

        # Fast mode: use pre-written responses for instant feedback
        if self.fast_mode:
            return self._generate_fallback_response(user_message, history), []

        # Build prompt with stage-specific guidance (ML-P2-1)
        system_prompt = self._get_system_prompt()
        stage_guidance = self._get_stage_prompt(self.state)

        # Format conversation history (keep last 10 for context)
        history_text = "\n".join(
            f"{m['role'].title()}: {m['content']}" for m in history[-10:]
        )

        prompt = f"""{stage_guidance}

---

CONVERSATION HISTORY:
{history_text}

User: {user_message}

---

Based on the stage guidance above, respond naturally as the interview assistant.
- Ask only ONE follow-up question relevant to the current stage
- Keep your response concise (2-3 sentences)
- Reference something specific the user said to show you're listening"""

        try:
            # SEC-009: Pass user_id for per-user rate limiting
            response_text = await self.llm.generate(
                prompt,
                system_prompt=system_prompt,
                temperature=0.7,
                user_id=self.user_id,
            )

            # Skip entity extraction during chat for faster responses
            # Entities will be extracted when the session is completed
            return response_text, []

        except (TimeoutError, ConnectionError) as e:
            logger.error(f"LLM connection error: {e}")
            return self._generate_fallback_response(user_message, history), []

    def _generate_fallback_response(
        self,
        user_message: str,
        history: list[dict],
    ) -> str:
        """Generate a context-aware fallback response for fast-mode or LLM-unavailable state.

        Improved version (Part 13): references the user's last message to provide
        conversational continuity instead of generic stage-script strings.

        Args:
            user_message: The user's most recent message
            history: Previous conversation history

        Returns:
            Context-aware response appropriate for the current stage
        """
        self.state = self._determine_next_state(history)

        # Extract key noun phrases from the user's message to reference back
        # Simple extraction: first meaningful 6 words of user message
        user_words = user_message.strip().split()
        topic_hint = " ".join(user_words[:6]) if user_words else ""
        topic_suffix = f' — "{topic_hint}"' if topic_hint else ""

        responses = {
            InterviewState.TRIGGER: (
                f"Thanks for sharing{topic_suffix}. "
                "To capture this properly: what was the underlying problem or need that "
                "prompted this decision? Was there a specific event, deadline, or pain point?"
            ),
            InterviewState.CONTEXT: (
                "That helps set the scene. "
                "What constraints were you working within at the time — "
                "team size, existing tech stack, timeline, or budget considerations?"
            ),
            InterviewState.OPTIONS: (
                "Understood. What alternatives did you actually evaluate? "
                "Even if you quickly ruled some out, it's valuable to capture them "
                "as rejected paths. What other approaches came up?"
            ),
            InterviewState.DECISION: (
                "Good. And what was the final decision — "
                "the specific choice you made from those options?"
            ),
            InterviewState.RATIONALE: (
                "Almost done. Why did you choose this over the alternatives? "
                "What were the 1–3 key reasons or trade-offs that tipped the balance?"
            ),
            InterviewState.SUMMARIZING: (
                "I have everything I need. Saving this decision to your knowledge graph now. "
                "You can view it in the Timeline or Graph view, or capture another decision."
            ),
        }

        return responses.get(
            self.state,
            "Thanks for sharing! What decision would you like to document today? "
            "Start by telling me what problem you were trying to solve.",
        )

    async def stream_response(
        self,
        user_message: str,
        history: list[dict],
    ) -> AsyncIterator[tuple[str, list[Entity]]]:
        """Stream a response (for WebSocket use).

        Args:
            user_message: The user's message
            history: Previous conversation history

        Yields:
            Tuples of (response chunk, extracted entities)
        """
        # Determine current state
        self.state = self._determine_next_state(history)

        # Fast mode: return pre-written response immediately
        if self.fast_mode:
            response = self._generate_fallback_response(user_message, history)
            yield response, []
            return

        # Build prompt with stage-specific guidance (ML-P2-1)
        system_prompt = self._get_system_prompt()
        stage_guidance = self._get_stage_prompt(self.state)

        # Format conversation history
        history_text = "\n".join(
            f"{m['role'].title()}: {m['content']}" for m in history[-10:]
        )

        prompt = f"""{stage_guidance}

---

CONVERSATION HISTORY:
{history_text}

User: {user_message}

---

Based on the stage guidance above, respond naturally as the interview assistant.
- Ask only ONE follow-up question relevant to the current stage
- Keep your response concise (2-3 sentences)
- Reference something specific the user said to show you're listening"""

        try:
            full_response = ""
            # SEC-009: Pass user_id for per-user rate limiting
            async for chunk in self.llm.generate_stream(
                prompt,
                system_prompt=system_prompt,
                temperature=0.7,
                user_id=self.user_id,
            ):
                full_response += chunk
                yield chunk, []

            # Skip entity extraction for faster responses
            yield "", []

        except (TimeoutError, ConnectionError) as e:
            logger.error(f"LLM connection error during streaming: {e}")
            yield self._generate_fallback_response(user_message, history), []

    async def synthesize_decision(self, history: list[dict]) -> dict:
        """Synthesize a complete decision trace from the conversation.

        Args:
            history: The complete conversation history

        Returns:
            Decision trace dict with trigger, context, options, decision, rationale, confidence
        """
        conversation_text = "\n".join(
            f"{m['role'].title()}: {m['content']}" for m in history
        )

        prompt = f"""Based on this interview conversation, synthesize a complete decision trace.

Conversation:
{conversation_text}

Return a JSON object with:
{{
  "trigger": "What prompted the decision",
  "context": "Background and constraints",
  "options": ["Option 1", "Option 2", ...],
  "decision": "What was decided",
  "rationale": "Why this was chosen",
  "confidence": 0.0-1.0 (how complete is this trace)
}}

Return ONLY valid JSON."""

        try:
            # SEC-009: Pass user_id for per-user rate limiting
            response = await self.llm.generate(
                prompt,
                temperature=0.3,
                user_id=self.user_id,
            )

            # Use robust JSON extraction
            result = extract_json_from_response(response)

            if result is None:
                logger.warning("Failed to parse synthesized decision from LLM response")
                return self._create_default_decision(history)

            # Validate required fields and add defaults
            return {
                "trigger": result.get("trigger", "Unknown trigger"),
                "context": result.get("context", ""),
                "options": result.get("options", []),
                "decision": result.get("decision", ""),
                "rationale": result.get("rationale", ""),
                "confidence": result.get("confidence", 0.5),
            }

        except (TimeoutError, ConnectionError) as e:
            logger.error(f"LLM connection error during synthesis: {e}")
            return self._create_default_decision(history)
        except Exception as e:
            logger.error(f"Unexpected error during synthesis: {e}")
            return self._create_default_decision(history)

    def _create_default_decision(self, history: list[dict]) -> dict:
        """Create a default decision structure from conversation history.

        Used as fallback when LLM synthesis fails.

        Args:
            history: The conversation history

        Returns:
            Default decision trace dict
        """
        # Extract user messages as raw content
        user_messages = [m["content"] for m in history if m["role"] == "user"]

        return {
            "trigger": user_messages[0]
            if len(user_messages) > 0
            else "Unknown trigger",
            "context": user_messages[1] if len(user_messages) > 1 else "",
            "options": [],
            "decision": user_messages[3] if len(user_messages) > 3 else "",
            "rationale": user_messages[4] if len(user_messages) > 4 else "",
            "confidence": 0.3,  # Low confidence for fallback
        }
