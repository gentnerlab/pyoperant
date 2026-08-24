#!/usr/bin/env python3

"""
Basic MagPi -> Open Ephys HTTP control test.

What this tests:
- Can the MagPi reach the Open Ephys GUI on asfour?
- Can it start acquisition?
- Can it start recording?
- Can it send timestamped text messages?
- Can it stop recording / return to IDLE?

This is not a precision timing test. Hardware TTLs/audio/mic come later.
"""

import argparse
import json
import socket
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import requests


class OpenEphysHTTPError(RuntimeError):
    pass


class OpenEphysHTTPClient:
    def __init__(self, host: str, port: int = 37497, timeout_s: float = 3.0):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.timeout_s = timeout_s

    def _get(self, endpoint: str) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        try:
            r = requests.get(url, timeout=self.timeout_s)
            r.raise_for_status()
            return r.json() if r.text else {}
        except Exception as exc:
            raise OpenEphysHTTPError(f"GET {url} failed: {exc}") from exc

    def _put(self, endpoint: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        try:
            r = requests.put(url, json=payload or {}, timeout=self.timeout_s)
            r.raise_for_status()
            return r.json() if r.text else {}
        except Exception as exc:
            raise OpenEphysHTTPError(f"PUT {url} failed with {payload}: {exc}") from exc

    def status(self) -> str:
        data = self._get("/api/status")
        return data.get("mode", "UNKNOWN")

    def set_mode(self, mode: str) -> str:
        mode = mode.upper()
        if mode not in {"IDLE", "ACQUIRE", "RECORD"}:
            raise ValueError(f"Invalid Open Ephys mode: {mode}")

        self._put("/api/status", {"mode": mode})
        time.sleep(0.25)
        return self.status()

    def recording_config(self) -> Dict[str, Any]:
        return self._get("/api/recording")

    def configure_recording(
        self,
        parent_directory: Optional[str] = None,
        base_text: Optional[str] = None,
        prepend_text: Optional[str] = None,
        append_text: Optional[str] = None,
        start_new_directory: bool = False,
    ) -> None:
        payload: Dict[str, Any] = {}

        if parent_directory:
            payload["parent_directory"] = parent_directory
        if base_text:
            payload["base_text"] = base_text
        if prepend_text:
            payload["prepend_text"] = prepend_text
        if append_text:
            payload["append_text"] = append_text
        if start_new_directory:
            # Open Ephys docs show this as a string field.
            payload["start_new_directory"] = "true"

        if payload:
            self._put("/api/recording", payload)

    def message(self, event: str, **fields: Any) -> None:
        payload = {
            "event": event,
            "time_iso": datetime.now().isoformat(timespec="milliseconds"),
            "perf_counter_ns": time.perf_counter_ns(),
            "magpi_host": socket.gethostname(),
            **fields,
        }

        # Compact JSON string makes downstream parsing easier than free text.
        text = json.dumps(payload, separators=(",", ":"))
        self._put("/api/message", {"text": text})


def write_jsonl(path: Path, record: Dict[str, Any]) -> None:
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")
        f.flush()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test MagPi HTTP control of Open Ephys."
    )
    parser.add_argument(
        "--host",
        default="asfour",
        help="Open Ephys computer hostname or IP. Default: asfour",
    )
    parser.add_argument("--port", type=int, default=37497)
    parser.add_argument(
        "--record",
        action="store_true",
        help="Actually enter RECORD mode. Requires a Record Node in Open Ephys.",
    )
    parser.add_argument(
        "--parent-dir",
        default=None,
        help="Optional Open Ephys recording parent directory on asfour, e.g. D:/OpenEphysData",
    )
    parser.add_argument(
        "--base-text",
        default=None,
        help="Optional Open Ephys base_text for recording folder naming.",
    )
    parser.add_argument(
        "--append-text",
        default=None,
        help="Optional Open Ephys append_text for recording folder naming.",
    )
    parser.add_argument(
        "--n-events",
        type=int,
        default=5,
        help="Number of fake trial messages to send.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Seconds between fake trial messages.",
    )
    parser.add_argument(
        "--leave-acquiring",
        action="store_true",
        help="After test, leave GUI in ACQUIRE instead of returning to IDLE.",
    )
    parser.add_argument(
        "--log",
        default="oe_http_test_log.jsonl",
        help="Local JSONL log written on the MagPi.",
    )

    args = parser.parse_args()
    log_path = Path(args.log)

    oe = OpenEphysHTTPClient(args.host, args.port)

    try:
        print(f"[connect] {oe.base_url}")
        print(f"[status] {oe.status()}")

        rec_cfg = oe.recording_config()
        print("[recording config] endpoint responded")
        if "record_nodes" in rec_cfg:
            print(f"[record nodes] {len(rec_cfg['record_nodes'])}")
        else:
            print("[warning] No record_nodes field found in /api/recording response.")

        if args.parent_dir or args.base_text or args.append_text:
            print("[configure] updating recording settings")
            oe.configure_recording(
                parent_directory=args.parent_dir,
                base_text=args.base_text,
                append_text=args.append_text,
                start_new_directory=True,
            )

        print("[mode] setting ACQUIRE")
        mode = oe.set_mode("ACQUIRE")
        print(f"[status] {mode}")
        if mode != "ACQUIRE":
            raise RuntimeError(f"Expected ACQUIRE, got {mode}")

        if args.record:
            print("[mode] setting RECORD")
            mode = oe.set_mode("RECORD")
            print(f"[status] {mode}")
            if mode != "RECORD":
                raise RuntimeError(
                    f"Expected RECORD, got {mode}. "
                    "Check that Open Ephys has a Record Node."
                )

        session_start = {
            "event": "session_start",
            "host": socket.gethostname(),
            "open_ephys_host": args.host,
            "time_iso": datetime.now().isoformat(timespec="milliseconds"),
            "perf_counter_ns": time.perf_counter_ns(),
        }
        oe.message("session_start", open_ephys_host=args.host)
        write_jsonl(log_path, session_start)
        print("[message] session_start")

        for i in range(1, args.n_events + 1):
            fake_stim = f"fake_stim_{i:03d}.wav"

            trial_msg = {
                "event": "fake_trial",
                "trial_index": i,
                "stimulus": fake_stim,
                "time_iso": datetime.now().isoformat(timespec="milliseconds"),
                "perf_counter_ns": time.perf_counter_ns(),
            }

            oe.message(
                "fake_trial",
                trial_index=i,
                stimulus=fake_stim,
                note="software_message_only_not_precision_ttl",
            )
            write_jsonl(log_path, trial_msg)
            print(f"[message] fake_trial {i}: {fake_stim}")

            time.sleep(args.interval)

        oe.message("session_end")
        write_jsonl(
            log_path,
            {
                "event": "session_end",
                "time_iso": datetime.now().isoformat(timespec="milliseconds"),
                "perf_counter_ns": time.perf_counter_ns(),
            },
        )
        print("[message] session_end")

        if args.leave_acquiring:
            print("[done] leaving Open Ephys in ACQUIRE mode")
        else:
            print("[mode] setting IDLE")
            mode = oe.set_mode("IDLE")
            print(f"[status] {mode}")

        print(f"[local log] {log_path.resolve()}")
        return 0

    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        print("[safety] attempting to return Open Ephys to IDLE", file=sys.stderr)
        try:
            oe.set_mode("IDLE")
        except Exception as idle_exc:
            print(f"[warning] could not set IDLE: {idle_exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())