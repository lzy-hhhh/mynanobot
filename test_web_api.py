#!/usr/bin/env python
"""Test script for nanobot web API."""

import requests
import json

BASE_URL = "http://localhost:18790"

def test_status():
    """Test /api/status endpoint."""
    print("Testing /api/status...")
    try:
        resp = requests.get(f"{BASE_URL}/api/status")
        resp.raise_for_status()
        data = resp.json()
        print(f"  Version: {data.get('version')}")
        print(f"  Model: {data.get('model')}")
        print(f"  Uptime: {data.get('uptime_seconds')}s")
        print(f"  System: {data.get('system')}")
        print("  ✓ OK")
    except Exception as e:
        print(f"  ✗ Failed: {e}")

def test_config():
    """Test /api/config endpoints."""
    print("\nTesting /api/config...")
    try:
        # GET
        resp = requests.get(f"{BASE_URL}/api/config")
        resp.raise_for_status()
        data = resp.json()
        print(f"  Current model: {data.get('agents', {}).get('defaults', {}).get('model')}")

        # POST - update temperature
        resp = requests.post(
            f"{BASE_URL}/api/config",
            json={"agents": {"defaults": {"temperature": 0.7}}}
        )
        resp.raise_for_status()
        print("  ✓ Update OK")
    except Exception as e:
        print(f"  ✗ Failed: {e}")

def test_channels():
    """Test /api/channels endpoints."""
    print("\nTesting /api/channels...")
    try:
        # GET all channels
        resp = requests.get(f"{BASE_URL}/api/channels")
        resp.raise_for_status()
        data = resp.json()
        print(f"  Channels: {len(data.get('channels', []))}")

        # Update channel config
        resp = requests.put(
            f"{BASE_URL}/api/channels/web/config",
            json={"enabled": True}
        )
        resp.raise_for_status()
        print("  ✓ Update channel config OK")
    except Exception as e:
        print(f"  ✗ Failed: {e}")

def test_sessions():
    """Test /api/sessions endpoints."""
    print("\nTesting /api/sessions...")
    try:
        # GET all sessions
        resp = requests.get(f"{BASE_URL}/api/sessions")
        resp.raise_for_status()
        data = resp.json()
        print(f"  Sessions: {len(data.get('sessions', []))}")

        # Create new session
        resp = requests.post(
            f"{BASE_URL}/api/sessions",
            json={"key": "web:test123", "title": "Test Session"}
        )
        resp.raise_for_status()
        print("  ✓ Create session OK")
    except Exception as e:
        print(f"  ✗ Failed: {e}")

def test_session_groups():
    """Test /api/session-groups endpoints."""
    print("\nTesting /api/session-groups...")
    try:
        # GET all groups
        resp = requests.get(f"{BASE_URL}/api/session-groups")
        resp.raise_for_status()
        data = resp.json()
        print(f"  Groups: {len(data.get('groups', []))}")

        # Create new group
        resp = requests.post(
            f"{BASE_URL}/api/session-groups",
            json={"name": "测试分组", "icon": "🧪"}
        )
        resp.raise_for_status()
        group = resp.json().get('group', {})
        print(f"  ✓ Create group OK: {group.get('name')}")

        # Add session to group
        if group.get('id'):
            resp = requests.post(
                f"{BASE_URL}/api/session-groups/{group['id']}/sessions",
                json={"session_key": "web:test123"}
            )
            resp.raise_for_status()
            print("  ✓ Add session to group OK")

        # Delete group
        if group.get('id'):
            resp = requests.delete(f"{BASE_URL}/api/session-groups/{group['id']}")
            resp.raise_for_status()
            print("  ✓ Delete group OK")

    except Exception as e:
        print(f"  ✗ Failed: {e}")

def main():
    """Run all tests."""
    print("=" * 50)
    print("nanobot Web API Tests")
    print("=" * 50)

    test_status()
    test_config()
    test_channels()
    test_sessions()
    test_session_groups()

    print("\n" + "=" * 50)
    print("Tests completed!")
    print("=" * 50)

if __name__ == "__main__":
    main()
