#!/usr/bin/env python3
"""
wctl — Nexus terminal orchestration CLI.

Usage:
  wctl.py --url URL --cookie COOKIE sessions
  wctl.py --url URL --cookie COOKIE states
  wctl.py --url URL --cookie COOKIE state  SESSION_ID
  wctl.py --url URL --cookie COOKIE buffer SESSION_ID [--lines N]
  wctl.py --url URL --cookie COOKIE send   SESSION_ID "text"
  wctl.py --url URL --cookie COOKIE wait   SESSION_ID STATE [--timeout N]
  wctl.py --url URL --cookie COOKIE broadcast "text"

Authentication:
  Pass the access_token cookie value obtained after login.
  Example: --cookie "eyJhbGciOi..."
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error


def _req(url: str, cookie: str, data: dict | None = None) -> dict:
    """Make an authenticated request."""
    headers = {
        "Cookie": f"access_token={cookie}",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}", file=sys.stderr)
        sys.exit(1)


def cmd_sessions(base: str, cookie: str, _args):
    data = _req(f"{base}/api/sessions", cookie)
    for s in data:
        print(f"  {s['id'][:8]}  {s['status']:8s}  {s['name']}  ({s['image']})")


def cmd_states(base: str, cookie: str, _args):
    data = _req(f"{base}/api/orchestration/sessions/states", cookie)
    for s in data:
        print(f"  {s['session_id'][:8]}  {s['state']:8s}  idle={s['idle_seconds']:.0f}s  {s['name']}")


def cmd_state(base: str, cookie: str, args):
    data = _req(f"{base}/api/orchestration/sessions/{args.session_id}/state", cookie)
    print(f"  {data['state']}  idle={data['idle_seconds']:.0f}s")


def cmd_buffer(base: str, cookie: str, args):
    lines = args.lines or 100
    data = _req(f"{base}/api/orchestration/sessions/{args.session_id}/buffer?lines={lines}", cookie)
    print(data["buffer"])


def cmd_send(base: str, cookie: str, args):
    text = args.text
    _req(f"{base}/api/orchestration/sessions/{args.session_id}/input", cookie, {"data": text})
    print(f"Sent {len(text)} chars to {args.session_id[:8]}")


def cmd_wait(base: str, cookie: str, args):
    target = args.target_state.upper()
    timeout = args.timeout or 120
    start = time.time()
    while time.time() - start < timeout:
        data = _req(f"{base}/api/orchestration/sessions/{args.session_id}/state", cookie)
        if data["state"] == target:
            print(f"Session reached {target}")
            return
        time.sleep(2)
    print(f"Timeout after {timeout}s (last state: {data['state']})", file=sys.stderr)
    sys.exit(1)


def cmd_broadcast(base: str, cookie: str, args):
    states = _req(f"{base}/api/orchestration/sessions/states", cookie)
    waiting = [s for s in states if s["state"] == "WAITING"]
    if not waiting:
        print("No WAITING sessions")
        return
    for s in waiting:
        _req(f"{base}/api/orchestration/sessions/{s['session_id']}/input", cookie, {"data": args.text})
        print(f"  Sent to {s['session_id'][:8]} ({s['name']})")
    print(f"Broadcast to {len(waiting)} session(s)")


def main():
    parser = argparse.ArgumentParser(description="Nexus terminal orchestration CLI")
    parser.add_argument("--url", required=True, help="Base URL (e.g., https://nexus.example.com)")
    parser.add_argument("--cookie", required=True, help="access_token cookie value")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("sessions", help="List all sessions")
    sub.add_parser("states", help="Show classified state for all running sessions")

    p = sub.add_parser("state", help="Show state for one session")
    p.add_argument("session_id")

    p = sub.add_parser("buffer", help="Print terminal buffer")
    p.add_argument("session_id")
    p.add_argument("--lines", type=int, default=100)

    p = sub.add_parser("send", help="Send keystrokes to a session")
    p.add_argument("session_id")
    p.add_argument("text")

    p = sub.add_parser("wait", help="Wait until session reaches target state")
    p.add_argument("session_id")
    p.add_argument("target_state")
    p.add_argument("--timeout", type=int, default=120)

    p = sub.add_parser("broadcast", help="Send text to all WAITING sessions")
    p.add_argument("text")

    args = parser.parse_args()
    base = args.url.rstrip("/")

    commands = {
        "sessions": cmd_sessions,
        "states": cmd_states,
        "state": cmd_state,
        "buffer": cmd_buffer,
        "send": cmd_send,
        "wait": cmd_wait,
        "broadcast": cmd_broadcast,
    }
    commands[args.command](base, args.cookie, args)


if __name__ == "__main__":
    main()
