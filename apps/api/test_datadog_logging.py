"""Test script to verify Datadog logging integration."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from services.datadog_logger import DatadogLLMLogger


async def test_datadog_log():
    """Send a test log to Datadog."""
    print("Sending test log to Datadog...")
    
    await DatadogLLMLogger.log_llm_call(
        model="nvidia/llama-3.3-nemotron-super-49b-v1.5",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        latency_ms=1234.56,
        operation="test",
        streaming=False,
        user_id="test-user",
        success=True,
        test_message="This is a test log from Continuum API",
    )
    
    print("✅ Test log sent successfully!")
    print("\nNow check Datadog Logs:")
    print("1. Go to Logs → Explorer")
    print("2. Search for: source:continuum-api")
    print("3. Or search for: @llm.operation:test")
    print("\nIt may take 10-30 seconds for logs to appear.")


if __name__ == "__main__":
    asyncio.run(test_datadog_log())
