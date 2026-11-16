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

"""librespeed-common's data in the shapes of this module's API, and back.

Pure functions without foris-controller imports, shared by the openwrt and the
mock handler. Replies are built field by field: the schema admits no other
fields, librespeed may add some, and stored values may be anything.

UCI is read the way librespeed-common reads it (its init script, librespeed-run
and librespeed-aggregate), so a reply says what librespeed actually does.
"""

import re

IFACE_RE = re.compile(r"[A-Za-z0-9_]+")
# The intervals the init script turns into cron lines.
INTERVAL_RE = re.compile(r"(([1-9]|[1-5][0-9])m|([1-9]|1[0-9]|2[0-3])h|1d|7d)")
PHASES = ("", "ping", "download", "upload")
SCHEMES = ("auto", "https", "http")
TRUE_VALUES = ("1", "on", "true", "yes", "enabled")
FALSE_VALUES = ("0", "off", "false", "no", "disabled")

DEFAULT_INTERFACE = "wan"
DEFAULT_HISTORY_PATH = "/tmp/librespeed/history.jsonl"
DEFAULT_RAW_DAYS = 30
DEFAULT_ARCHIVE_DAYS = 365
# The schedule section as librespeed-common ships it.
DEFAULT_SCHEDULE = {"enabled": False, "interface": None, "interval": "1d", "days": [], "hours": {"from": 2, "to": 5}}

# ubus start's refusals in librespeed.uc's words, and their codes.
START_ERRORS = {
    "already running": "already_running",
    "not installed": "not_installed",
    "unknown interface": "unknown_interface",
    "interface disabled or not configured": "interface_not_configured",
    "interface is down": "interface_down",
    "netifd did not answer": "netifd_unavailable",
}
METRICS = ("download_mbps", "upload_mbps", "ping_ms", "jitter_ms")


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_iface(value):
    return isinstance(value, str) and bool(IFACE_RE.fullmatch(value))


def parse_bool(value, default):
    """config_get_bool, case and all: other values keep the default."""
    if isinstance(value, str):
        if value in TRUE_VALUES:
            return True
        if value in FALSE_VALUES:
            return False
    return default


def _field(value):
    """A UCI list is joined with spaces, as functions.sh hands it to the init script."""
    if isinstance(value, list):
        return " ".join(value)
    return value


def parse_days(value):
    """Weekdays of a days option; [] for every day, also for what cron would refuse."""
    value = _field(value)
    if not isinstance(value, str) or value in ("", "*") or value.endswith(","):
        return []
    days = set()
    for part in value.split(","):
        m = re.fullmatch(r"([0-9]+)(?:-([0-9]+))?", part)
        if not m:
            return []
        first = int(m.group(1))
        last = int(m.group(2)) if m.group(2) is not None else first
        if first > 6 or last > 6 or first > last:
            return []
        days.update(range(first, last + 1))
    return sorted(days)


def format_days(days):
    """None when every day: the option is then removed, as LuCI does."""
    return ",".join(str(d) for d in sorted(set(days))) if days else None


def parse_hours(value):
    """{"from", "to"} of an hours option; None for any time, also for an invalid window."""
    value = _field(value)
    if not isinstance(value, str):
        return None
    m = re.fullmatch(r"([0-9]+)(?:-([0-9]+))?", value)
    if not m:
        return None
    first = int(m.group(1))
    last = int(m.group(2)) if m.group(2) is not None else first
    if first > 23 or last > 23 or first > last:
        return None
    return {"from": first, "to": last}


def format_hours(hours):
    if hours is None:
        return None
    if hours["from"] == hours["to"]:
        return str(hours["from"])
    return "%d-%d" % (hours["from"], hours["to"])


def raw_retention_days(value):
    """librespeed-run's reading: one trailing d dropped, digits or 0 (nothing is trimmed)."""
    value = _field(value)
    if value is None:
        return DEFAULT_RAW_DAYS
    value = str(value)
    if value.endswith("d"):
        value = value[:-1]
    # isdigit() alone takes digits such as "²", which int() refuses.
    return int(value) if value.isascii() and value.isdigit() else 0


def _leading_int(value):
    m = re.match(r"\s*([0-9]+)", str(_field(value)) if value is not None else "")
    return int(m.group(1)) if m else 0


def archive_retention_days(value):
    """librespeed-aggregate's reading: leading digits, 365 for none or 0."""
    return _leading_int(value) or DEFAULT_ARCHIVE_DAYS


# --- UCI sections -------------------------------------------------------------
#
# Sections are UciBackend.read()'s: {"type", "name", "data", "anonymous"}.


def named_section(sections, name, section_type="librespeed"):
    for section in sections:
        if section["name"] == name and section["type"] == section_type:
            return section
    return None


def schedule_rows(sections):
    """The further schedules: every section of type schedule, in file order."""
    return [s for s in sections if s["type"] == "schedule"]


def _opt(section, option):
    return section["data"].get(option) if section else None


def main_from_uci(sections):
    main = named_section(sections, "main")
    scheme = _field(_opt(main, "scheme"))
    return {
        "interface": _field(_opt(main, "interface")) or DEFAULT_INTERFACE,
        "server": _field(_opt(main, "server")) or "auto",
        "scheme": scheme if scheme in SCHEMES else "auto",
        "server_list": _field(_opt(main, "server_list")) or "",
    }


def schedule_from_uci(section, named):
    """A schedule section as the init script reads it."""
    data = section["data"]
    interface = _field(data.get("interface")) or ""
    if named:
        interface = interface or None
    return {
        "enabled": parse_bool(_field(data.get("enabled")), False),
        "interface": interface,
        "interval": _field(data.get("interval")) or "1d",
        "days": parse_days(data.get("days")),
        "hours": parse_hours(data.get("hours")),
    }


def history_from_uci(sections):
    history = named_section(sections, "history")
    return {
        "enabled": parse_bool(_field(_opt(history, "enabled")), True),
        "path": _field(_opt(history, "path")) or DEFAULT_HISTORY_PATH,
        "retention_days": raw_retention_days(_opt(history, "retention")),
        "archive_path": _field(_opt(history, "archive_path")) or "",
        "archive_retention_days": archive_retention_days(_opt(history, "archive_retention")),
    }


def config_from_uci(sections):
    """get_config's reply without applied_schedules, which comes from ubus."""
    config = main_from_uci(sections)
    named = named_section(sections, "schedule")
    config["schedule"] = schedule_from_uci(named, True) if named else None
    config["interface_schedules"] = [schedule_from_uci(s, False) for s in schedule_rows(sections)]
    config["history"] = history_from_uci(sections)
    return config


# --- update_config ------------------------------------------------------------

# What decides which link each schedule measures.
LINK_KEYS = ("interface", "schedule", "interface_schedules")


def touches_links(update):
    return any(key in update for key in LINK_KEYS)


def validate_update(current, update, link_of):
    """(error, message) when update_config must change nothing, else None.

    link_of maps an interface to the link it is measured as (wan6 to wan);
    an interface it does not know stands for itself. Links are checked only
    when the update touches what decides them, so a duplicate already stored
    (by hand, or wan6 joining wan's link later) does not block other changes.
    """
    rows = []
    if update.get("schedule") is not None:
        rows.append(update["schedule"])
    rows.extend(update.get("interface_schedules", []))
    for row in rows:
        if row["hours"] is not None and row["hours"]["from"] > row["hours"]["to"]:
            return "invalid_hours", "The window %d-%d ends before it starts." % (
                row["hours"]["from"],
                row["hours"]["to"],
            )

    if not touches_links(update):
        return None
    default = update.get("interface", current["interface"])
    named = update["schedule"] if "schedule" in update else current["schedule"]
    others = update["interface_schedules"] if "interface_schedules" in update else current["interface_schedules"]
    seen = set()
    # Only what the init script turns into a cron line measures anything.
    measured = []
    if named is not None and _runs(named, named["interface"] or default):
        measured.append(named["interface"] or default)
    measured.extend(row["interface"] for row in others if _runs(row, row["interface"]))
    for interface in measured:
        link = link_of.get(interface, interface)
        if link in seen:
            return "duplicate_link", "Two enabled schedules would measure %s." % link
        seen.add(link)
    return None


def _runs(row, interface):
    return bool(row["enabled"] and is_iface(interface) and INTERVAL_RE.fullmatch(str(row["interval"])))


def _schedule_ops(section, current, new, named):
    """Options to write so the section holds new; current is None for a new section."""
    ops = []

    def put(option, value):
        if value is None:
            if current is not None:
                ops.append(("del", section, option))
        else:
            ops.append(("set", section, option, value))

    if current is None or current["enabled"] != new["enabled"]:
        ops.append(("set", section, "enabled", "1" if new["enabled"] else "0"))
    if current is None or current["interface"] != new["interface"]:
        if named:
            put("interface", new["interface"])
        else:
            ops.append(("set", section, "interface", new["interface"]))
    if current is None or current["interval"] != new["interval"]:
        ops.append(("set", section, "interval", new["interval"]))
    if current is None or current["days"] != sorted(set(new["days"])):
        put("days", format_days(new["days"]))
    if current is None or current["hours"] != new["hours"]:
        put("hours", format_hours(new["hours"]))
    return ops


def plan_update(sections, update):
    """UCI operations for update_config; empty when nothing changes.

    ("set", section, option, value), ("del", section, option),
    ("add_named", type, name), ("add_schedule", options) and
    ("delete", section). libuci names an anonymous section by its position
    among all sections, and a deletion renumbers every section after it, also
    within one uncommitted session. So further schedules are matched by
    position and changed in place, new sections are appended, and deletions
    come last, the highest position first.
    """
    ops = []
    deletions = []  # (position, section)
    position = {s["name"]: i for i, s in enumerate(sections)}
    main_keys = [k for k in ("interface", "server", "scheme", "server_list") if k in update]
    if main_keys:
        current = main_from_uci(sections)
        main_ops = []
        for key in main_keys:
            if current[key] != update[key]:
                if key == "server_list" and update[key] == "":
                    main_ops.append(("del", "main", key))
                else:
                    main_ops.append(("set", "main", key, update[key]))
        ops.extend(_in_named(sections, "main", main_ops))

    if "schedule" in update:
        section = named_section(sections, "schedule")
        if update["schedule"] is None:
            if section is not None:
                deletions.append((position["schedule"], "schedule"))
        else:
            if section is None:
                ops.append(("add_named", "librespeed", "schedule"))
            current = schedule_from_uci(section, True) if section else None
            ops.extend(_schedule_ops("schedule", current, update["schedule"], True))

    if "interface_schedules" in update:
        rows = schedule_rows(sections)
        new_rows = update["interface_schedules"]
        for row, new in zip(rows, new_rows):
            ops.extend(_schedule_ops(row["name"], schedule_from_uci(row, False), new, False))
        for new in new_rows[len(rows):]:
            options = {"enabled": "1" if new["enabled"] else "0", "interface": new["interface"], "interval": new["interval"]}
            if new["days"]:
                options["days"] = format_days(new["days"])
            if new["hours"] is not None:
                options["hours"] = format_hours(new["hours"])
            ops.append(("add_schedule", options))
        for row in rows[len(new_rows):]:
            deletions.append((position[row["name"]], row["name"]))

    if "history" in update:
        current = history_from_uci(sections)
        history_ops = []
        for key, value in update["history"].items():
            if current[key] == value:
                continue
            if key == "enabled":
                history_ops.append(("set", "history", "enabled", "1" if value else "0"))
            elif key == "path":
                history_ops.append(("set", "history", "path", value))
            elif key == "retention_days":
                history_ops.append(("set", "history", "retention", "%dd" % value))
            elif key == "archive_path":
                if value:
                    history_ops.append(("set", "history", "archive_path", value))
                else:
                    history_ops.append(("del", "history", "archive_path"))
            elif key == "archive_retention_days":
                history_ops.append(("set", "history", "archive_retention", "%dd" % value))
        ops.extend(_in_named(sections, "history", history_ops))
    ops.extend(("delete", name) for _, name in sorted(deletions, reverse=True))
    return ops


def _in_named(sections, name, section_ops):
    """The ops, after adding the named section when one sets something in it."""
    if named_section(sections, name) is None and any(op[0] == "set" for op in section_ops):
        return [("add_named", "librespeed", name)] + [op for op in section_ops if op[0] == "set"]
    return section_ops


# --- ubus replies -------------------------------------------------------------


def start_error(message):
    """The code of a refusal; a refusal this module does not know counts as the backend's."""
    return START_ERRORS.get(message, "backend_unavailable")


def failures_reply(failures):
    out = []
    for f in failures if isinstance(failures, list) else []:
        if (
            isinstance(f, dict)
            and is_iface(f.get("interface"))
            and isinstance(f.get("error"), str)
            and is_int(f.get("finished"))
            and f["finished"] >= 0
        ):
            out.append({"interface": f["interface"], "error": f["error"], "finished": f["finished"]})
    return out


def status_reply(status):
    running = status.get("running") is True
    out = {"running": running, "phase": "", "last_error": "", "failures": failures_reply(status.get("failures"))}
    if is_iface(status.get("interface")):
        out["interface"] = status["interface"]
    if running:
        if status.get("phase") in PHASES:
            out["phase"] = status["phase"]
        if is_int(status.get("started")) and status["started"] >= 0:
            out["started"] = status["started"]
        if is_int(status.get("elapsed")):
            out["elapsed_seconds"] = max(0, status["elapsed"])
        if is_number(status.get("mbps")):
            out["speed_mbps"] = float(status["mbps"])
        if is_number(status.get("progress")):
            out["phase_progress_percent"] = min(100, max(0, int(status["progress"])))
    else:
        if isinstance(status.get("last_error"), str):
            out["last_error"] = status["last_error"]
        if is_int(status.get("last_finished")) and status["last_finished"] >= 0:
            out["last_finished"] = status["last_finished"]
    return out


def server_reply(server):
    if not isinstance(server, dict) or not isinstance(server.get("name"), str) or not isinstance(server.get("url"), str):
        return None
    out = {"name": server["name"], "url": server["url"]}
    if is_int(server.get("id")):
        out["id"] = server["id"]
    return out


def _optional_enums(src, out):
    if src.get("family") in ("ipv4", "ipv6"):
        out["family"] = src["family"]
    if src.get("proto") in ("http", "https"):
        out["proto"] = src["proto"]


def result_reply(result):
    """The last measurement, or None when there is none or it lacks what a result needs."""
    if not isinstance(result, dict) or not result:
        return None
    server = server_reply(result.get("server"))
    client = result.get("client") if isinstance(result.get("client"), dict) else {}
    if (
        server is None
        or not isinstance(result.get("timestamp"), str)
        or not all(is_int(result.get(k)) and result[k] >= 0 for k in ("started", "finished"))
        or ("interface" in result and not is_iface(result["interface"]))
        or not all(is_number(result.get(k)) for k in METRICS)
    ):
        return None
    out = {
        "timestamp": result["timestamp"],
        "started": result["started"],
        "finished": result["finished"],
        "server": server,
        "client": {
            "ip": client["ip"] if isinstance(client.get("ip"), str) else "",
            "org": client["org"] if isinstance(client.get("org"), str) else "",
        },
    }
    if "interface" in result:
        out["interface"] = result["interface"]
    _optional_enums(result, out)
    for key in METRICS:
        out[key] = float(result[key])
    for key in ("bytes_sent", "bytes_received"):
        out[key] = result[key] if is_int(result.get(key)) and result[key] >= 0 else 0
    out["share"] = result["share"] if isinstance(result.get("share"), str) else ""
    return out


def history_entry_reply(entry):
    if not isinstance(entry, dict) or not isinstance(entry.get("timestamp"), str):
        return None
    if not is_int(entry.get("epoch")) or entry["epoch"] < 0:
        return None
    out = {"timestamp": entry["timestamp"], "epoch": entry["epoch"]}
    if is_iface(entry.get("interface")):
        out["interface"] = entry["interface"]
    server = server_reply(entry.get("server"))
    if server is not None:
        out["server"] = server
    _optional_enums(entry, out)
    if is_int(entry.get("samples")) and entry["samples"] >= 1:
        out["samples"] = entry["samples"]
    for metric in METRICS:
        for key in (metric, metric + "_min", metric + "_max"):
            if is_number(entry.get(key)):
                out[key] = float(entry[key])
    return out


def history_reply(history):
    entries = history.get("entries") if isinstance(history.get("entries"), list) else []
    return {
        "resolution": "1d" if history.get("resolution") == "1d" else "raw",
        "entries": [e for e in (history_entry_reply(x) for x in entries) if e is not None],
    }


def links_reply(links):
    """None when librespeed could not ask netifd."""
    if "error" in links or not isinstance(links.get("interfaces"), dict):
        return None

    def names(key):
        value = links.get(key)
        return [i for i in value if is_iface(i)] if isinstance(value, list) else []

    return {
        "links": names("links"),
        "interfaces": {k: v for k, v in links["interfaces"].items() if is_iface(k) and is_iface(v)},
        "down": names("down"),
    }


def applied_schedules_reply(config):
    out = []
    for entry in config.get("schedules", []) if isinstance(config.get("schedules"), list) else []:
        if isinstance(entry, dict) and is_iface(entry.get("interface")) and isinstance(entry.get("cron"), str):
            runs = entry.get("next_runs") if isinstance(entry.get("next_runs"), list) else []
            out.append(
                {
                    "interface": entry["interface"],
                    "cron": entry["cron"],
                    "next_runs": [r for r in runs if is_int(r) and r >= 0],
                }
            )
    return out
