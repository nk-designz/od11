#!/usr/bin/env python3
import argparse
import json
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import websocket  # pip/pkg: websocket-client


def make_headers(cookie: Optional[str]) -> List[str]:
    headers: List[str] = []
    if cookie:
        headers.append(f"Cookie: {cookie}")  # e.g. orthoplay=...
    headers += [
        "Cache-Control: no-cache",
        "Pragma: no-cache",
        "Accept-Language: en-US,en;q=0.9",
        "Accept-Encoding: gzip, deflate",
    ]
    return headers


def parse_group_joined(payload: Dict[str, Any]) -> Tuple[Optional[int], Dict[int, str], Optional[int], Optional[int]]:
    """Returns (sid, sources_map, current_vol, current_source_id)."""
    sid = payload.get("sid")
    sources_map: Dict[int, str] = {}
    for s in payload.get("sources", []) or []:
        try:
            sources_map[int(s.get("id"))] = str(s.get("name"))
        except Exception:
            pass

    current_vol: Optional[int] = None
    current_src: Optional[int] = None
    for item in payload.get("state", []) or []:
        if isinstance(item, dict):
            if item.get("update") == "group_volume_changed" and "vol" in item:
                try:
                    current_vol = int(item.get("vol"))
                except Exception:
                    pass
            if item.get("update") == "group_input_source_changed" and "source" in item:
                try:
                    current_src = int(item.get("source"))
                except Exception:
                    pass
    return sid, sources_map, current_vol, current_src


def now_ms() -> int:
    return int(time.time() * 1000)


def run(
    url: str,
    origin: Optional[str],
    cookie: Optional[str],
    set_input: Optional[int],
    set_input_name: Optional[str],
    set_volume: Optional[int],
    nudge: Optional[int],
    listen: bool,
    sid_arg: Optional[int],
    show_sources: bool,
    keepalive: Optional[int],
    # handshake params:
    proto_major: int,
    proto_minor: int,
    join_name: str,
    join_uid: str,
    color_index: int,
    realtime_data: bool,
):
    # Origin must be http(s), not ws://
    if origin and origin.startswith("ws://"):
        print("Origin must be http(s), e.g. --origin http://<ip>", file=sys.stderr)
        sys.exit(2)

    headers = make_headers(cookie)

    # Desired ops
    want = {
        "set_input_id": set_input,
        "set_input_name": set_input_name.lower() if set_input_name else None,
        "set_volume_abs": None if set_volume is None else max(0, min(100, int(set_volume))),
        "nudge": nudge,
        "show_sources": show_sources,
    }

    # Connection-local state
    state: Dict[str, Any] = {
        "sid": sid_arg,              # will be set from group_joined if not provided
        "vol": None,                 # from snapshot/updates
        "src": None,                 # from snapshot/updates
        "sources_map": {},           # id -> name
        "did_send": False,           # have we sent our control message(s)?
        "waiting_for_state": False,  # when we need a vol frame to compute delta
        "last_ping_sent": None,      # ms timestamp of last app-level ping
        "stop_pinger": False,        # stop flag
        "handshake_phase": "start",  # start -> sent_global_join -> got_global_joined -> sent_group_join -> ready
    }

    # default keepalive if listening and not explicitly set
    if keepalive is None and listen:
        keepalive = 25
    if keepalive is not None and keepalive <= 0:
        keepalive = None

    def _print_summary():
        smap = state["sources_map"]
        pairs = ", ".join(f"{i}:{name}" for i, name in sorted(smap.items())) if smap else "(none)"
        print(f"SID: {state['sid']}, Volume: {state['vol']}, Source: {state['src']}")
        print(f"Sources: {pairs}")

    def _resolve_input_id() -> Optional[int]:
        if want["set_input_id"] is not None:
            return int(want["set_input_id"])
        if want["set_input_name"]:
            target = want["set_input_name"]
            for i, name in state["sources_map"].items():
                if name.lower() == target:
                    return i
        return None

    def _send(ws, msg: Dict[str, Any], log: bool = True):
        # include sid if we have one and caller didn't set it
        if state["sid"] is not None and "sid" not in msg:
            msg["sid"] = int(state["sid"])
        ws.send(json.dumps(msg))
        if log:
            print(f"-> {msg}")

    def _start_keepalive(ws, interval: int):
        def _loop():
            while not state["stop_pinger"]:
                payload = {"action": "speaker_ping", "value": now_ms()}
                try:
                    ws.send(json.dumps(payload))
                    state["last_ping_sent"] = payload["value"]
                    # print(f"-> {payload}")
                except Exception as e:
                    print(f"Keepalive send failed: {e}", file=sys.stderr)
                    return
                time.sleep(interval)
        threading.Thread(target=_loop, daemon=True).start()

    # ---- websocket-client callbacks ----

    def on_open(ws):
        print("Connected. Sending global_join…")
        state["handshake_phase"] = "sent_global_join"
        _send(
            ws,
            {
                "protocol_major_version": proto_major,
                "protocol_minor_version": proto_minor,
                "action": "global_join",
            },
        )
        if keepalive:
            _start_keepalive(ws, keepalive)

    def on_message(ws, message):
        try:
            data = json.loads(message)
        except Exception:
            print(f"<- {message}")
            return

        print(f"<- {data}")

        # 1) global_joined
        if isinstance(data, dict) and data.get("response") == "global_joined":
            state["handshake_phase"] = "got_global_joined"
            # Immediately send group_join
            print("Sending group_join…")
            state["handshake_phase"] = "sent_group_join"
            _send(
                ws,
                {
                    "color_index": int(color_index),
                    "name": join_name,
                    "realtime_data": bool(realtime_data),
                    "uid": join_uid,
                    "action": "group_join",
                },
            )
            return

        # 2) speaker_pong (app-level ping)
        if isinstance(data, dict) and data.get("response") == "speaker_pong":
            val = data.get("value")
            if isinstance(val, int) and state["last_ping_sent"] == val:
                rtt = now_ms() - val
                print(f"speaker_pong (matched): ~{rtt} ms RTT")
            else:
                print("speaker_pong")
            return

        # 3) group_joined snapshot
        if isinstance(data, dict) and data.get("response") == "group_joined":
            state["handshake_phase"] = "ready"
            sid, smap, vol, src = parse_group_joined(data)
            if sid is not None:
                state["sid"] = state["sid"] or sid
            state["sources_map"] = smap or state["sources_map"]
            state["vol"] = vol if vol is not None else state["vol"]
            state["src"] = src if src is not None else state["src"]
            _print_summary()

            if want["show_sources"] and not any([want["nudge"], want["set_volume_abs"] is not None, want["set_input_id"] is not None, want["set_input_name"]]):
                if not listen:
                    threading.Thread(target=lambda: (time.sleep(0.3), ws.close()), daemon=True).start()
                return

            send_controls(ws)
            return

        # 4) subsequent notifications
        if isinstance(data, dict):
            upd = data.get("update")
            if upd == "group_volume_changed" and "vol" in data:
                try:
                    state["vol"] = int(data["vol"])
                except Exception:
                    pass
                if state["waiting_for_state"]:
                    send_controls(ws)
            elif upd == "group_input_source_changed" and "source" in data:
                try:
                    state["src"] = int(data["source"])
                except Exception:
                    pass

    def send_controls(ws):
        if state["did_send"]:
            return

        # Input switch
        target_input_id = _resolve_input_id()
        if target_input_id is not None:
            _send(ws, {"action": "group_set_input_source", "source": int(target_input_id)})

        # Volume nudge (delta)
        if want["nudge"] is not None:
            _send(ws, {"action": "group_change_volume", "amount": int(want["nudge"])})

        # Absolute volume (compute delta from known current volume)
        if want["set_volume_abs"] is not None:
            if state["vol"] is None:
                state["waiting_for_state"] = True
                print("Waiting for volume state to compute delta…")
            else:
                delta = int(want["set_volume_abs"]) - int(state["vol"])
                if delta != 0:
                    _send(ws, {"action": "group_change_volume", "amount": delta})
                else:
                    print("Target volume already set.")

        state["did_send"] = True

        if not listen:
            threading.Thread(target=lambda: (time.sleep(0.6), ws.close()), daemon=True).start()

    def on_error(ws, error):
        print(f"WebSocket error: {error}", file=sys.stderr)

    def on_close(ws, code, reason):
        state["stop_pinger"] = True
        if code or reason:
            print(f"Disconnected (code={code}, reason={reason}).")
        else:
            print("Disconnected.")

    ws = websocket.WebSocketApp(
        url,
        header=headers,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )

    # Pass Origin here so it isn't duplicated in headers
    ws.run_forever(origin=(origin.rstrip("/") if origin else None))


def main():
    ap = argparse.ArgumentParser(
        description="Teenage Engineering OD‑11 WebSocket controller (global_join → group_join)."
    )
    ap.add_argument("--ws-url", required=True, help="ws://<ip>:<port>/<path> (e.g. ws://10.13.12.212/ws)")
    ap.add_argument("--origin", help="HTTP Origin header, e.g. http://10.13.12.212")
    ap.add_argument("--cookie", help="Cookie header, e.g. orthoplay=...")

    # Actions
    modes = ap.add_mutually_exclusive_group(required=True)
    modes.add_argument("--set-input", type=int, help="Switch input by ID (try --show-sources first)")
    modes.add_argument("--set-input-name", help='Switch input by name, e.g. "Optical"')
    modes.add_argument("--set-volume", type=int, help="Set absolute volume (0..100)")
    modes.add_argument("--nudge", type=int, help="Change volume by delta (e.g. --nudge +5)")
    modes.add_argument("--listen", action="store_true", help="Keep socket open and print incoming messages")
    modes.add_argument("--show-sources", action="store_true", help="Print sources map then exit")

    # Optional: override sid (normally discovered from group_joined)
    ap.add_argument("--sid", type=int, help="Optional sid; auto‑filled from snapshot if omitted")

    # Keepalive
    ap.add_argument("--keepalive", type=int, help="App-level ping every N seconds (default 25s with --listen)")

    # Handshake params
    ap.add_argument("--protocol-major", type=int, default=0, help="Protocol major version for global_join (default 0)")
    ap.add_argument("--protocol-minor", type=int, default=4, help="Protocol minor version for global_join (default 4)")
    ap.add_argument("--name", default="guest", help='Client name for group_join (default "guest")')
    ap.add_argument("--uid", default="uid-od11ctl", help='Client uid for group_join (default "uid-od11ctl")')
    ap.add_argument("--color-index", type=int, default=0, help="Client color_index for group_join (default 0)")
    ap.add_argument("--realtime-data", action="store_true", default=True, help="Request realtime_data on group_join (default true)")
    ap.add_argument("--no-realtime-data", action="store_false", dest="realtime_data", help="Disable realtime_data")

    args = ap.parse_args()
    run(
        url=args.ws_url,
        origin=args.origin,
        cookie=args.cookie,
        set_input=args.set_input,
        set_input_name=args.set_input_name,
        set_volume=args.set_volume,
        nudge=args.nudge,
        listen=args.listen,
        sid_arg=args.sid,
        show_sources=args.show_sources,
        keepalive=args.keepalive,
        proto_major=args.protocol_major,
        proto_minor=args.protocol_minor,
        join_name=args.name,
        join_uid=args.uid,
        color_index=args.color_index,
        realtime_data=args.realtime_data,
    )


if __name__ == "__main__":
    main()

