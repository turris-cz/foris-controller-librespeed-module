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

import os
import subprocess
import time

import pytest

TESTS_DIR = os.path.dirname(os.path.realpath(__file__))
UCI_FILE = "/tmp/uci_configs/librespeed"
SCHEDULE = {"enabled": False, "interface": None, "interval": "1d", "days": [], "hours": {"from": 2, "to": 5}}


def call(infrastructure, action, data=None):
    msg = {"module": "librespeed", "action": action, "kind": "request"}
    if data is not None:
        msg["data"] = data
    return infrastructure.process_message(msg)


def uci_show():
    out = subprocess.run(
        ["uci", "-c", "/tmp/uci_configs", "show", "librespeed"], capture_output=True, text=True, check=True
    ).stdout
    return {k: v.strip("'") for k, v in (line.split("=", 1) for line in out.splitlines())}


# --- status ---------------------------------------------------------------------


def test_get_status(uci_configs_init, infrastructure, start_buses):
    data = call(infrastructure, "get_status")["data"]
    assert isinstance(data["running"], bool)
    assert data["phase"] in ("", "ping", "download", "upload")
    assert isinstance(data["failures"], list)


@pytest.mark.only_backends(["openwrt"])
def test_status_while_running(uci_configs_init, infrastructure, start_buses, ubus):
    ubus.scenario(status="running-download-status")
    raw = ubus.reply("running-download-status")
    assert call(infrastructure, "get_status")["data"] == {
        "running": True,
        "phase": "download",
        "interface": "wan",
        "started": raw["started"],
        "elapsed_seconds": raw["elapsed"],
        "speed_mbps": pytest.approx(raw["mbps"]),
        "phase_progress_percent": raw["progress"],
        "last_error": "",
        "failures": [],
    }


@pytest.mark.only_backends(["openwrt"])
def test_status_after_a_failure(uci_configs_init, infrastructure, start_buses, ubus):
    ubus.scenario(status="failed-status")
    raw = ubus.reply("failed-status")
    assert call(infrastructure, "get_status")["data"] == {
        "running": False,
        "phase": "",
        "interface": "wan",
        "last_error": raw["last_error"],
        "last_finished": raw["last_finished"],
        "failures": raw["failures"],
    }


@pytest.mark.only_backends(["openwrt"])
def test_status_without_the_backend(uci_configs_init, infrastructure, start_buses, ubus):
    ubus.scenario(fail=["status"])
    assert "errors" in call(infrastructure, "get_status")


# --- start and stop -------------------------------------------------------------


@pytest.mark.only_backends(["openwrt"])
@pytest.mark.parametrize(
    "fixture,code",
    [
        ("start-already-running", "already_running"),
        ("start-refused-down", "interface_down"),
        ("start-refused-unknown", "unknown_interface"),
        ("start-refused-notconfigured", "interface_not_configured"),
        ("start-refused-netifd", "netifd_unavailable"),
        ("start-refused-notinstalled", "not_installed"),
    ],
)
def test_start_refusals(uci_configs_init, infrastructure, start_buses, ubus, fixture, code):
    ubus.scenario(start=fixture)
    assert call(infrastructure, "start", {"interface": "wan"})["data"] == {
        "started": False,
        "error": code,
        "message": ubus.reply(fixture)["error"],
    }


@pytest.mark.only_backends(["openwrt"])
def test_start_with_a_refusal_it_does_not_know(uci_configs_init, infrastructure, start_buses, ubus):
    ubus.scenario(start={"error": "something new"})
    assert call(infrastructure, "start")["data"] == {
        "started": False,
        "error": "backend_unavailable",
        "message": "something new",
    }
    assert ubus.calls("start")[-1]["data"] == {}, "no interface asks for the default one"


@pytest.mark.only_backends(["openwrt"])
def test_start_without_the_backend(uci_configs_init, infrastructure, start_buses, ubus):
    ubus.scenario(fail=["start"])
    assert call(infrastructure, "start")["data"] == {"started": False, "error": "backend_unavailable"}


@pytest.mark.only_backends(["openwrt"])
def test_start_waits_until_it_runs(uci_configs_init, infrastructure, start_buses, ubus):
    # One status before start, then idle twice before the run holds its lock.
    ubus.scenario(start="start-ok", status=["idle-status", "idle-status", "idle-status", "running-download-status"])
    assert call(infrastructure, "start", {"interface": "wan"})["data"] == {"started": True}
    assert ubus.calls("start") == [{"method": "start", "data": {"interface": "wan"}}]
    assert len(ubus.calls("status")) == 4
    assert call(infrastructure, "get_status")["data"]["running"] is True


@pytest.mark.only_backends(["openwrt"])
def test_start_returns_after_a_quick_failure(uci_configs_init, infrastructure, start_buses, ubus):
    ubus.scenario(start="start-ok", status=["finished-status", "failed-status"])
    begun = time.monotonic()
    assert call(infrastructure, "start")["data"] == {"started": True}
    assert time.monotonic() - begun < 4
    assert len(ubus.calls("status")) == 2, "a changed last_finished ends the wait"


@pytest.mark.only_backends(["openwrt"])
def test_start_does_not_take_the_last_run_for_its_own(uci_configs_init, infrastructure, start_buses, ubus):
    # The last run ended just now, in the second this start comes; its
    # last_finished stays as it was, so the wait goes on.
    finished = dict(ubus.reply("finished-status"), last_finished=int(time.time()))
    ubus.scenario(start="start-ok", status=[finished, finished, "running-download-status"])
    assert call(infrastructure, "start")["data"] == {"started": True}
    assert len(ubus.calls("status")) == 3


@pytest.mark.only_backends(["openwrt"])
def test_start_waits_5_s_at_most(uci_configs_init, infrastructure, start_buses, ubus):
    ubus.scenario(start="start-ok", status="idle-status")
    begun = time.monotonic()
    assert call(infrastructure, "start")["data"] == {"started": True}
    assert 4.5 <= time.monotonic() - begun < 10


@pytest.mark.only_backends(["openwrt"])
def test_stop(uci_configs_init, infrastructure, start_buses, ubus):
    ubus.scenario(status="running-download-status")
    assert call(infrastructure, "stop")["data"] == {"stopped": True}
    ubus.scenario(status="idle-status")
    assert call(infrastructure, "stop")["data"] == {"stopped": False}
    assert len(ubus.calls("stop")) == 2


# --- results ---------------------------------------------------------------------


@pytest.mark.only_backends(["openwrt"])
def test_get_result(uci_configs_init, infrastructure, start_buses, ubus):
    assert call(infrastructure, "get_result")["data"] == {"measurement": None}
    ubus.scenario(result="finished-result")
    raw = ubus.reply("finished-result")
    measurement = call(infrastructure, "get_result")["data"]["measurement"]
    assert measurement["server"] == {"name": "Local", "url": raw["server"]["url"]}, "the Go client reports no id"
    assert measurement["client"] == {"ip": "192.0.2.10", "org": "Example Networks"}
    assert (measurement["interface"], measurement["family"], measurement["proto"]) == ("wan", "ipv4", "http")
    assert measurement["download_mbps"] == pytest.approx(raw["download_mbps"])
    assert measurement["bytes_sent"] == raw["bytes_sent"]


@pytest.mark.only_backends(["openwrt"])
def test_get_history(uci_configs_init, infrastructure, start_buses, ubus):
    ubus.scenario(history="history-archive")
    data = call(infrastructure, "get_history")["data"]
    assert data["resolution"] == "1d"
    day = data["entries"][0]
    assert (day["samples"], day["interface"]) == (3, "wan")
    assert day["download_mbps_min"] == pytest.approx(900.5)
    assert "server" not in day

    ubus.scenario(history="history-limit")
    data = call(infrastructure, "get_history", {"from": 1794000000, "limit": 2})["data"]
    assert data["resolution"] == "raw"
    assert len(data["entries"]) == 2
    assert ubus.calls("history")[-1]["data"] == {"from": 1794000000, "limit": 2}


# --- settings ----------------------------------------------------------------------


@pytest.mark.only_backends(["openwrt"])
def test_get_config(uci_configs_init, infrastructure, start_buses, ubus):
    ubus.scenario(config="scheduled-config")
    data = call(infrastructure, "get_config")["data"]
    assert {k: data[k] for k in ("interface", "server", "scheme", "server_list")} == {
        "interface": "wan",
        "server": "auto",
        "scheme": "auto",
        "server_list": "",
    }
    assert data["schedule"] == SCHEDULE
    assert data["interface_schedules"] == []
    assert data["history"] == {
        "enabled": True,
        "path": "/tmp/librespeed/history.jsonl",
        "retention_days": 30,
        "archive_path": "",
        "archive_retention_days": 365,
    }
    assert [a["interface"] for a in data["applied_schedules"]] == ["wan", "lte"]
    assert data["applied_schedules"][1]["cron"] == "45 5 * * 3 /usr/libexec/librespeed-run lte"
    assert len(data["applied_schedules"][1]["next_runs"]) == 3


@pytest.mark.only_backends(["openwrt"])
@pytest.mark.uci_config_path(os.path.join(TESTS_DIR, "uci_configs_junk"))
def test_get_config_with_junk_in_every_option(uci_configs_init, infrastructure, start_buses):
    assert call(infrastructure, "get_config")["data"] == {
        "interface": "wan;reboot",
        "server": "prague",
        "scheme": "auto",
        "server_list": "ftp://example.org/servers.json",
        "schedule": {"enabled": False, "interface": None, "interval": "90m", "days": [], "hours": None},
        "interface_schedules": [{"enabled": False, "interface": "", "interval": "0h", "days": [], "hours": None}],
        "applied_schedules": [],
        "history": {
            "enabled": True,
            "path": "relative/history.jsonl",
            "retention_days": 0,
            "archive_path": "x",
            "archive_retention_days": 365,
        },
    }


@pytest.mark.only_backends(["openwrt"])
def test_update_config_writes_only_what_changes(uci_configs_init, infrastructure, start_buses):
    with open(UCI_FILE) as f:
        before = f.read()
    same = {
        "interface": "wan",
        "server": "auto",
        "scheme": "auto",
        "server_list": "",
        "schedule": SCHEDULE,
        "history": {"retention_days": 30, "archive_path": ""},
    }
    assert call(infrastructure, "update_config", same)["data"] == {"result": True}
    with open(UCI_FILE) as f:
        assert f.read() == before, "nothing was committed, so the daily time is not drawn again"

    schedule = {"enabled": True, "interface": None, "interval": "7d", "days": [3, 1], "hours": {"from": 1, "to": 4}}
    assert call(infrastructure, "update_config", {"schedule": schedule})["data"] == {"result": True}
    uci = uci_show()
    assert [uci["librespeed.schedule." + o] for o in ("enabled", "interval", "days", "hours")] == ["1", "7d", "1,3", "1-4"]
    assert call(infrastructure, "get_config")["data"]["schedule"] == dict(schedule, days=[1, 3])


@pytest.mark.only_backends(["openwrt"])
def test_update_config_without_the_config_file(uci_configs_init, infrastructure, start_buses):
    os.remove(UCI_FILE)
    assert call(infrastructure, "get_config")["data"]["interface"] == "wan"
    assert call(infrastructure, "update_config", {"server": "5"})["data"] == {"result": True}
    assert uci_show()["librespeed.main.server"] == "5"


@pytest.mark.only_backends(["openwrt"])
def test_get_config_with_a_broken_config_file(uci_configs_init, infrastructure, start_buses):
    with open(UCI_FILE, "w") as f:
        f.write("config librespeed 'main\n")
    assert "errors" in call(infrastructure, "get_config"), "a broken file is not shown as the defaults"


@pytest.mark.only_backends(["openwrt"])
def test_update_config_interface_schedules(uci_configs_init, infrastructure, start_buses):
    rows = [
        {"enabled": True, "interface": "lte", "interval": "6h", "days": [], "hours": None},
        {"enabled": False, "interface": "wan6", "interval": "1d", "days": [0, 6], "hours": {"from": 3, "to": 3}},
    ]
    assert call(infrastructure, "update_config", {"interface_schedules": rows})["data"] == {"result": True}
    uci = uci_show()
    assert uci["librespeed.@schedule[0].interface"] == "lte"
    assert "librespeed.@schedule[0].days" not in uci
    assert (uci["librespeed.@schedule[1].days"], uci["librespeed.@schedule[1].hours"]) == ("0,6", "3")
    assert call(infrastructure, "get_config")["data"]["interface_schedules"] == rows

    rows = [dict(rows[0], interval="12h")]
    assert call(infrastructure, "update_config", {"interface_schedules": rows})["data"] == {"result": True}
    uci = uci_show()
    assert "librespeed.@schedule[1]" not in uci
    assert uci["librespeed.@schedule[0].interval"] == "12h"

    assert call(infrastructure, "update_config", {"interface_schedules": []})["data"] == {"result": True}
    assert not any(k.startswith("librespeed.@schedule") for k in uci_show())


@pytest.mark.only_backends(["openwrt"])
def test_update_config_removes_the_schedule(uci_configs_init, infrastructure, start_buses):
    assert call(infrastructure, "update_config", {"schedule": None})["data"] == {"result": True}
    assert "librespeed.schedule" not in uci_show()
    assert call(infrastructure, "get_config")["data"]["schedule"] is None


@pytest.mark.only_backends(["openwrt"])
@pytest.mark.uci_config_path(os.path.join(TESTS_DIR, "uci_configs_duplicate"))
def test_a_stored_duplicate_does_not_block_other_changes(uci_configs_init, infrastructure, start_buses):
    assert call(infrastructure, "update_config", {"scheme": "http"})["data"] == {"result": True}
    assert call(infrastructure, "update_config", {"history": {"retention_days": 7}})["data"] == {"result": True}
    rows = call(infrastructure, "get_config")["data"]["interface_schedules"]
    res = call(infrastructure, "update_config", {"interface_schedules": rows})
    assert res["data"]["error"] == "duplicate_link", "touching the schedules checks them"


@pytest.mark.only_backends(["openwrt"])
@pytest.mark.uci_config_path(os.path.join(TESTS_DIR, "uci_configs_rows"))
def test_one_update_removes_the_schedule_and_edits_rows(uci_configs_init, infrastructure, start_buses):
    # Removing a section renumbers the anonymous ones after it within the same
    # uncommitted session, so the order of the writes matters here.
    row = {"enabled": True, "interface": "lte", "interval": "12h", "days": [], "hours": None}
    res = call(infrastructure, "update_config", {"schedule": None, "interface_schedules": [row]})
    assert res["data"] == {"result": True}
    uci = uci_show()
    assert "librespeed.schedule" not in uci
    assert (uci["librespeed.@schedule[0].interface"], uci["librespeed.@schedule[0].interval"]) == ("lte", "12h")
    assert "librespeed.@schedule[1]" not in uci
    assert call(infrastructure, "get_config")["data"]["interface_schedules"] == [row]


@pytest.mark.only_backends(["openwrt"])
@pytest.mark.uci_config_path(os.path.join(TESTS_DIR, "uci_configs_noschedule"))
def test_one_update_adds_the_schedule_and_edits_rows(uci_configs_init, infrastructure, start_buses):
    schedule = {"enabled": True, "interface": None, "interval": "1d", "days": [], "hours": {"from": 1, "to": 4}}
    rows = [
        {"enabled": True, "interface": "lte", "interval": "6h", "days": [1], "hours": None},
        {"enabled": False, "interface": "wan6", "interval": "1d", "days": [0, 6], "hours": None},
    ]
    res = call(infrastructure, "update_config", {"schedule": schedule, "interface_schedules": rows})
    assert res["data"] == {"result": True}
    uci = uci_show()
    assert (uci["librespeed.schedule.enabled"], uci["librespeed.schedule.hours"]) == ("1", "1-4")
    assert (uci["librespeed.@schedule[0].interface"], uci["librespeed.@schedule[0].days"]) == ("lte", "1")
    assert uci["librespeed.@schedule[1].interface"] == "wan6"
    config = call(infrastructure, "get_config")["data"]
    assert (config["schedule"], config["interface_schedules"]) == (schedule, rows)


@pytest.mark.only_backends(["openwrt"])
@pytest.mark.uci_config_path(os.path.join(TESTS_DIR, "uci_configs_empty"))
def test_an_empty_config(uci_configs_init, infrastructure, start_buses):
    config = call(infrastructure, "get_config")["data"]
    assert {k: config[k] for k in ("interface", "server", "scheme", "server_list", "schedule")} == {
        "interface": "wan",
        "server": "auto",
        "scheme": "auto",
        "server_list": "",
        "schedule": None,
    }
    assert config["history"]["retention_days"] == 30
    schedule = dict(SCHEDULE, enabled=True)
    res = call(infrastructure, "update_config", {"schedule": schedule, "server": "5"})
    assert res["data"] == {"result": True}
    uci = uci_show()
    assert (uci["librespeed.schedule.enabled"], uci["librespeed.schedule.hours"]) == ("1", "2-5")
    assert uci["librespeed.main.server"] == "5"
    assert call(infrastructure, "get_config")["data"]["schedule"] == schedule


def test_update_config_refuses_two_schedules_on_one_link(uci_configs_init, infrastructure, start_buses):
    res = call(
        infrastructure,
        "update_config",
        {
            "schedule": dict(SCHEDULE, enabled=True),
            "interface_schedules": [{"enabled": True, "interface": "wan6", "interval": "6h", "days": [], "hours": None}],
        },
    )
    assert (res["data"]["result"], res["data"]["error"]) == (False, "duplicate_link"), "wan6 is wan's link"


def test_update_config_refuses_a_backwards_window(uci_configs_init, infrastructure, start_buses):
    row = {"enabled": True, "interface": "lte", "interval": "1d", "days": [], "hours": {"from": 5, "to": 2}}
    res = call(infrastructure, "update_config", {"interface_schedules": [row]})
    assert (res["data"]["result"], res["data"]["error"]) == (False, "invalid_hours")


def test_update_config_notifies(uci_configs_init, infrastructure, start_buses):
    notifications = infrastructure.get_notifications()
    assert call(infrastructure, "update_config", {"scheme": "http"})["data"] == {"result": True}
    notifications = infrastructure.get_notifications(notifications, filters=[("librespeed", "update_config")])
    assert notifications[-1]["data"] == {"scheme": "http"}
    assert call(infrastructure, "get_config")["data"]["scheme"] == "http"


def test_get_links(uci_configs_init, infrastructure, start_buses):
    data = call(infrastructure, "get_links")["data"]
    assert data["interfaces"]["wan6"] == "wan"
    assert "lte" in data["down"]
    assert "lan" not in data["links"], "a link without a gateway is not offered"


@pytest.mark.only_backends(["openwrt"])
def test_get_links_without_netifd(uci_configs_init, infrastructure, start_buses, ubus):
    ubus.scenario(links="links-netifd")
    assert "errors" in call(infrastructure, "get_links")


# --- the mock, as reForis development sees it -----------------------------------


@pytest.mark.only_backends(["mock"])
def test_mock_measurement_walks_its_stages(uci_configs_init, infrastructure, start_buses):
    deadline = time.monotonic() + 10
    while call(infrastructure, "get_status")["data"]["running"] and time.monotonic() < deadline:
        time.sleep(0.2)
    history_before = len(call(infrastructure, "get_history")["data"]["entries"])

    assert call(infrastructure, "start")["data"] == {"started": True}
    assert call(infrastructure, "start")["data"]["error"] == "already_running"
    order = ["", "ping", "download", "upload"]
    phases = []
    while time.monotonic() < deadline:
        status = call(infrastructure, "get_status")["data"]
        if not status["running"]:
            break
        if not phases or phases[-1] != status["phase"]:
            phases.append(status["phase"])
        time.sleep(0.25)
    # Polling may miss the short stages, but never sees them out of order.
    assert phases == sorted(phases, key=order.index) and len(set(phases)) == len(phases)
    assert {"download", "upload"} <= set(phases)
    assert status["last_error"] == ""
    assert call(infrastructure, "get_result")["data"]["measurement"]["interface"] == "wan"
    assert len(call(infrastructure, "get_history")["data"]["entries"]) == history_before + 1
    assert call(infrastructure, "start", {"interface": "lte"})["data"]["error"] == "interface_down"
