#
# foris-controller-librespeed-module
# Copyright (C) 2026 CZ.NIC, z.s.p.o. (http://www.nic.cz/)
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

"""The schema on its own: what it accepts and what it refuses.

Replies must accept whatever UCI may hold, requests only what librespeed can
run; these cases pin both down without starting foris-controller.
"""

import pytest
from foris_controller.utils import get_validator_dirs
from foris_schema import ForisValidator


@pytest.fixture(scope="module")
def validator():
    return ForisValidator(*get_validator_dirs(["librespeed"]))


def msg(kind, action, data=None):
    m = {"module": "librespeed", "kind": kind, "action": action}
    if data is not None:
        m["data"] = data
    return m


MEASUREMENT = {
    "timestamp": "2026-11-16T16:39:02.674123091Z",
    "started": 1794847111,
    "finished": 1794847142,
    "interface": "wan",
    "server": {"id": 2, "name": "Local", "url": "http://192.0.2.2:8080/cgi-bin/"},
    "client": {"ip": "192.0.2.1", "org": "Example"},
    "family": "ipv4",
    "proto": "http",
    "download_mbps": 912.5,
    "upload_mbps": 410.25,
    "ping_ms": 3.1,
    "jitter_ms": 0.4,
    "bytes_sent": 512000000,
    "bytes_received": 1100000000,
    "share": "",
}
CONFIG = {
    "interface": "wan",
    "server": "auto",
    "scheme": "auto",
    "server_list": "https://librespeed.turris.cz/servers.json",
    "schedule": {"enabled": True, "interface": None, "interval": "1d", "days": [], "hours": {"from": 2, "to": 5}},
    "interface_schedules": [{"enabled": False, "interface": "lte", "interval": "7d", "days": [1, 3], "hours": None}],
    "applied_schedules": [
        {"interface": "wan", "cron": "37 3 * * * /usr/libexec/librespeed-run wan", "next_runs": [1794880620]}
    ],
    "history": {
        "enabled": True,
        "path": "/tmp/librespeed/history.jsonl",
        "retention_days": 30,
        "archive_path": "",
        "archive_retention_days": 365,
    },
}
JUNK_CONFIG = {
    "interface": "wan;x",
    "server": "prague",
    "scheme": "auto",
    "server_list": "ftp://example.org/list",
    "schedule": {"enabled": True, "interface": None, "interval": "90m", "days": [], "hours": None},
    "interface_schedules": [{"enabled": False, "interface": "bad name", "interval": "0h", "days": [], "hours": None}],
    "applied_schedules": [],
    "history": {
        "enabled": True,
        "path": "relative",
        "retention_days": 0,
        "archive_path": "x",
        "archive_retention_days": 365,
    },
}


def row(**kw):
    return dict({"enabled": True, "interface": "wan", "interval": "1d", "days": [], "hours": None}, **kw)


ACCEPTED = [
    msg("request", "get_status"),
    msg("reply", "get_status", {"running": False, "phase": "", "last_error": "", "failures": []}),
    msg(
        "reply",
        "get_status",
        {
            "running": True,
            "phase": "download",
            "interface": "wan",
            "started": 1794847111,
            "elapsed_seconds": 12,
            "speed_mbps": 93.4,
            "phase_progress_percent": 40,
            "last_error": "",
            "failures": [{"interface": "lte", "error": "interface is down", "finished": 1794840000}],
        },
    ),
    msg("request", "start"),
    msg("request", "start", {"interface": "wan"}),
    msg("reply", "start", {"started": True}),
    msg("reply", "start", {"started": False, "error": "already_running", "message": "already running"}),
    msg("request", "stop"),
    msg("reply", "stop", {"stopped": True}),
    msg("reply", "get_result", {"measurement": None}),
    msg("reply", "get_result", {"measurement": MEASUREMENT}),
    msg("reply", "get_result", {"measurement": {k: v for k, v in MEASUREMENT.items() if k != "interface"}}),
    msg("request", "get_history", {"from": 1794000000, "to": 1794900000, "limit": 50}),
    msg(
        "reply",
        "get_history",
        {
            "resolution": "1d",
            "entries": [
                {
                    "timestamp": "2026-11-15",
                    "epoch": 1794783600,
                    "interface": "wan",
                    "samples": 4,
                    "download_mbps": 900.1,
                    "download_mbps_min": 850.0,
                    "download_mbps_max": 950.2,
                }
            ],
        },
    ),
    msg("reply", "get_config", CONFIG),
    msg("reply", "get_config", JUNK_CONFIG),
    msg("reply", "get_config", dict(CONFIG, schedule=None)),
    msg("request", "update_config", {"scheme": "http"}),
    msg("request", "update_config", {"interface_schedules": [row(interface="lte", interval="6h", days=[0, 6])]}),
    msg("request", "update_config", {"schedule": row(interface=None, hours={"from": 1, "to": 4})}),
    msg("request", "update_config", {"schedule": None}),
    msg("request", "update_config", {"history": {"archive_path": "/srv/librespeed/daily.jsonl"}}),
    msg("reply", "update_config", {"result": False, "error": "duplicate_link", "message": "wan"}),
    msg("notification", "update_config", {"scheme": "http"}),
    msg(
        "reply",
        "get_links",
        {"links": ["wan", "lte"], "interfaces": {"wan": "wan", "wan6": "wan", "lte": "lte"}, "down": ["lte"]},
    ),
]

REFUSED = {
    "a field librespeed does not have": msg(
        "reply", "get_status", {"running": False, "phase": "", "last_error": "", "failures": [], "pid": 1}
    ),
    "a phase outside the enum": msg(
        "reply", "get_status", {"running": True, "phase": "warmup", "last_error": "", "failures": []}
    ),
    "a shell in an interface": msg("request", "start", {"interface": "wan;reboot"}),
    "an unknown start error": msg("reply", "start", {"started": False, "error": "busy"}),
    "an empty update": msg("request", "update_config", {}),
    "an interval cron cannot run": msg("request", "update_config", {"interface_schedules": [row(interval="24h")]}),
    "day 7": msg("request", "update_config", {"interface_schedules": [row(days=[7])]}),
    "half a window": msg("request", "update_config", {"schedule": row(interface=None, hours={"from": 22})}),
    "a further schedule without its interface": msg(
        "request", "update_config", {"interface_schedules": [row(interface=None)]}
    ),
    "an ftp server list": msg("request", "update_config", {"server_list": "ftp://example.org/servers.json"}),
    "a server by name": msg("request", "update_config", {"server": "prague"}),
    "limit 0": msg("request", "get_history", {"limit": 0}),
    "a relative archive": msg("request", "update_config", {"history": {"archive_path": "srv/x"}}),
    # Python's re.search lets "$" match before a final newline.
    "an interface ending in a newline": msg("request", "start", {"interface": "wan\n"}),
    "an interval ending in a newline": msg("request", "update_config", {"interface_schedules": [row(interval="1d\n")]}),
    "a server id ending in a newline": msg("request", "update_config", {"server": "5\n"}),
    "a history file with a newline": msg("request", "update_config", {"history": {"path": "/tmp/h.jsonl\n"}}),
    "a retention past ten years": msg("request", "update_config", {"history": {"retention_days": 3651}}),
    "a start notification": msg("notification", "start", {"interface": "wan"}),
    "a scheme outside the enum in a reply": msg("reply", "get_config", dict(CONFIG, scheme="ftp")),
    "a reply without the schedule": msg(
        "reply", "get_config", {k: v for k, v in CONFIG.items() if k != "schedule"}
    ),
}


@pytest.mark.parametrize("message", ACCEPTED, ids=lambda m: "%s-%s" % (m["action"], m["kind"]))
def test_schema_accepts(validator, message):
    validator.validate(message)


@pytest.mark.parametrize("message", REFUSED.values(), ids=REFUSED.keys())
def test_schema_refuses(validator, message):
    with pytest.raises(Exception):
        validator.validate(message)
