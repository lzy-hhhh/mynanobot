"""Test script to start nanobot web UI."""

import sys
import asyncio

# Add current directory to path
sys.path.insert(0, '.')

try:
    import uvicorn
    print("✓ uvicorn imported")
except ImportError as e:
    print(f"✗ uvicorn not installed: {e}")
    print("  Install with: pip install nanobot-ai[web]")
    sys.exit(1)

try:
    from fastapi import FastAPI
    print("✓ fastapi imported")
except ImportError as e:
    print(f"✗ fastapi not installed: {e}")
    print("  Install with: pip install nanobot-ai[web]")
    sys.exit(1)

try:
    from nanobot.web.app import create_app
    print("✓ nanobot.web.app imported")

    app = create_app()
    print("✓ App created successfully")

    print("\nStarting server on http://localhost:18791")
    print("Press Ctrl+C to stop\n")

    uvicorn.run(app, host="0.0.0.0", port=18791)

except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
