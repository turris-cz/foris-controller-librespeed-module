#
# foris-controller-librespeed-module
# Copyright (C) 2022-2026 CZ.NIC, z.s.p.o. (http://www.nic.cz/)
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA
#

"""A router with librespeed-common, for reForis development and the tests.

A measurement walks through its stages on the wall clock and finishes on its
own, deterministically: FORIS_LIBRESPEED_MOCK_SECONDS sets its length (15 s).
wan and wan6 are one link, lte is down and lan has no gateway, as on the
router the module's ubus fixtures were captured from.
"""

import copy
import logging
import os
import random
import threading
import time
from datetime import datetime, timezone

from foris_controller.handler_base import BaseMockHandler
from foris_controller.utils import logger_wrapper
from foris_controller_librespeed_module import model

from .. import Handler

logger = logging.getLogger(__name__)

SECONDS = float(os.environ.get("FORIS_LIBRESPEED_MOCK_SECONDS", "15"))
# Share of a measurement each stage takes: connecting, ping, download, upload.
STAGES = (("", 0.05), ("ping", 0.10), ("download", 0.40), ("upload", 0.45))
SERVER = {"id": 2, "name": "Prague, CZ.NIC", "url": "https://librespeed.turris.cz/backend/"}
RESULT = {"download_mbps": 312.4, "upload_mbps": 104.8, "ping_ms": 4.2, "jitter_ms": 0.8}
LINKS = {
    "links": ["lte", "wan"],
    "interfaces": {"lan": "lan", "lte": "lte", "wan": "wan", "wan6": "wan"},
    "down": ["lte"],
}


def _iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")


def _seed_history(now):
    """A week of results every 6 hours, oldest first."""
    entries = []
    base = int(now) - int(now) % 3600
    for i in reversed(range(28)):
        epoch = base - i * 6 * 3600
        entries.append(
            {
                "timestamp": _iso(epoch),
                "epoch": epoch,
                "interface": "wan",
                "server": dict(SERVER),
                "family": "ipv4",
                "proto": "https",
                "download_mbps": 280.0 + (i % 5) * 7.5,
                "upload_mbps": 95.0 + (i % 3) * 2.5,
                "ping_ms": 4.0 + (i % 4) * 0.3,
                "jitter_ms": 0.5 + (i % 2) * 0.2,
            }
        )
    return entries


def _aggregate(entries, today):
    """librespeed-aggregate's daily lines: completed days only, mean, min and max."""
    days = {}
    for e in entries:
        day = time.strftime("%Y-%m-%d", time.localtime(e["epoch"]))
        if day < today:
            days.setdefault((day, e.get("interface", "")), []).append(e)
    out = []
    for (day, iface), group in sorted(days.items()):
        entry = {
            "timestamp": day,
            "epoch": int(time.mktime(time.strptime(day, "%Y-%m-%d"))),
            "samples": len(group),
        }
        if iface:
            entry["interface"] = iface
        for m in model.METRICS:
            values = [g[m] for g in group]
            entry[m] = round(sum(values) / len(values), 2)
            entry[m + "_min"] = min(values)
            entry[m + "_max"] = max(values)
        out.append(entry)
    return out


class MockLibreSpeedHandler(Handler, BaseMockHandler):
    lock = threading.Lock()
    config = {
        "interface": "wan",
        "server": "auto",
        "scheme": "auto",
        "server_list": "https://librespeed.turris.cz/servers.json",
        "schedule": copy.deepcopy(model.DEFAULT_SCHEDULE),
        "interface_schedules": [],
        "history": {
            "enabled": True,
            "path": model.DEFAULT_HISTORY_PATH,
            "retention_days": model.DEFAULT_RAW_DAYS,
            "archive_path": "",
            "archive_retention_days": model.DEFAULT_ARCHIVE_DAYS,
        },
    }
    # Mutated in place, never rebound: rebinding through self would leave the
    # class attribute behind for other handler instances.
    state = {
        "run": None,  # {"interface", "started"}
        "last": {"error": "", "finished": None, "interface": None},
        # As left by a scheduled run of the down link; start refusals record nothing.
        "failures": {"lte": ("interface is down", int(time.time()) - 3600)},
        "result": None,
        "history": _seed_history(time.time()),
    }

    def _advance(self):
        """Finishes the running measurement once its time is up."""
        st = self.state
        run = st["run"]
        if run is None or time.time() - run["started"] < SECONDS:
            return
        finished = int(run["started"] + SECONDS)
        iface = run["interface"]
        st["result"] = dict(
            RESULT,
            timestamp=_iso(run["started"]),
            started=int(run["started"]),
            finished=finished,
            interface=iface,
            server=dict(SERVER),
            client={"ip": "192.0.2.10", "org": "Example Networks"},
            family="ipv4",
            proto="https",
            bytes_sent=1300000000,
            bytes_received=3900000000,
            share="",
        )
        if self.config["history"]["enabled"]:
            skip = ("started", "finished", "client", "share", "bytes_sent", "bytes_received")
            entry = {k: v for k, v in st["result"].items() if k not in skip}
            entry["epoch"] = finished
            st["history"].append(entry)
        for name in [k for k in st["failures"] if LINKS["interfaces"].get(k, k) == iface]:
            del st["failures"][name]
        st["last"] = {"error": "", "finished": finished, "interface": None}
        st["run"] = None

    @logger_wrapper(logger)
    def get_status(self):
        with self.lock:
            self._advance()
            failures = [
                {"interface": k, "error": v[0], "finished": v[1]}
                for k, v in sorted(self.state["failures"].items(), key=lambda x: -x[1][1])
            ]
            run, last = self.state["run"], self.state["last"]
            if run is None:
                out = {"running": False, "phase": "", "last_error": last["error"], "failures": failures}
                if last["finished"] is not None:
                    out["last_finished"] = last["finished"]
                if last["interface"]:
                    out["interface"] = last["interface"]
                return out
            elapsed = time.time() - run["started"]
            out = {
                "running": True,
                "phase": "",
                "interface": run["interface"],
                "started": int(run["started"]),
                "elapsed_seconds": int(elapsed),
                "last_error": "",
                "failures": failures,
            }
            share = elapsed / SECONDS
            for phase, part in STAGES:
                if share < part:
                    out["phase"] = phase
                    progress = share / part
                    if phase in ("download", "upload"):
                        final = RESULT[phase + "_mbps"]
                        out["speed_mbps"] = round(final * (0.6 + 0.4 * progress), 2)
                        out["phase_progress_percent"] = int(progress * 100)
                    break
                share -= part
            return out

    @logger_wrapper(logger)
    def start(self, interface=None):
        with self.lock:
            self._advance()
            iface = interface or self.config["interface"]
            if self.state["run"] is not None:
                return {"started": False, "error": "already_running", "message": "already running"}
            if iface not in LINKS["interfaces"]:
                return {"started": False, "error": "unknown_interface", "message": "unknown interface"}
            if iface in LINKS["down"]:
                return {"started": False, "error": "interface_down", "message": "interface is down"}
            self.state["run"] = {"interface": LINKS["interfaces"][iface], "started": time.time()}
            return {"started": True}

    @logger_wrapper(logger)
    def stop(self):
        with self.lock:
            self._advance()
            run = self.state["run"]
            if run is None:
                return {"stopped": False}
            self.state["last"] = {"error": "stopped", "finished": int(time.time()), "interface": run["interface"]}
            self.state["run"] = None
            return {"stopped": True}

    @logger_wrapper(logger)
    def get_result(self):
        with self.lock:
            self._advance()
            return {"measurement": copy.deepcopy(self.state["result"])}

    @logger_wrapper(logger)
    def get_history(self, query):
        with self.lock:
            self._advance()
            history = self.config["history"]
            frm, to, limit = query.get("from", 0), query.get("to", 0), query.get("limit", 0)
            raw_from = time.time() - history["retention_days"] * 86400 - 3600
            if history["archive_path"] and (frm == 0 or frm < raw_from):
                resolution = "1d"
                entries = _aggregate(self.state["history"], time.strftime("%Y-%m-%d"))
            else:
                resolution = "raw"
                entries = self.state["history"]
            entries = [e for e in entries if (not frm or e["epoch"] >= frm) and (not to or e["epoch"] <= to)]
            if limit:
                entries = entries[-limit:]
            return {"resolution": resolution, "entries": copy.deepcopy(entries)}

    @logger_wrapper(logger)
    def get_config(self):
        with self.lock:
            config = copy.deepcopy(self.config)
            applied = []
            now = int(time.time())
            rows = [config["schedule"]] if config["schedule"] else []
            rows += config["interface_schedules"]
            for row in rows:
                if not row["enabled"]:
                    continue
                iface = row["interface"] or ""
                unit = row["interval"][-1]
                step = int(row["interval"][:-1]) * {"m": 60, "h": 3600, "d": 86400}[unit]
                hour = row["hours"]["from"] if row["hours"] else 0
                first = now - now % 3600 + 3600 if unit in "mh" else now - now % 86400 + 86400 + hour * 3600
                applied.append(
                    {
                        "interface": iface or config["interface"],
                        "cron": "%d %d * * * /usr/libexec/librespeed-run%s"
                        % (random.Random(iface).randrange(60), hour, " " + iface if iface else ""),
                        "next_runs": [first + k * step for k in range(3)],
                    }
                )
            config["applied_schedules"] = applied
            return config

    @logger_wrapper(logger)
    def update_config(self, update):
        with self.lock:
            error = model.validate_update(self.config, update, LINKS["interfaces"])
            if error:
                return {"result": False, "error": error[0], "message": error[1]}
            for key, value in update.items():
                if key == "history":
                    self.config["history"].update(value)
                elif key in ("schedule", "interface_schedules"):
                    value = copy.deepcopy(value)
                    for row in value if isinstance(value, list) else [value] if value else []:
                        row["days"] = sorted(set(row["days"]))
                    self.config[key] = value
                else:
                    self.config[key] = value
            return {"result": True}

    @logger_wrapper(logger)
    def get_links(self):
        return copy.deepcopy(LINKS)
