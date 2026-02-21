"""Test if Datadog config is loaded correctly."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import get_settings

settings = get_settings()

print("Datadog Configuration:")
print(f"  datadog_integration_enabled: {settings.datadog_integration_enabled}")
print(f"  datadog_api_key: {'SET' if settings.datadog_api_key.get_secret_value() else 'NOT SET'}")
print(f"  datadog_site: {settings.datadog_site}")
print(f"  dd_trace_enabled: {settings.dd_trace_enabled}")

if settings.datadog_integration_enabled and settings.datadog_api_key.get_secret_value():
    print("\n✅ Datadog is properly configured!")
else:
    print("\n❌ Datadog is NOT configured properly!")
    if not settings.datadog_integration_enabled:
        print("   - datadog_integration_enabled is False")
    if not settings.datadog_api_key.get_secret_value():
        print("   - datadog_api_key is not set")
