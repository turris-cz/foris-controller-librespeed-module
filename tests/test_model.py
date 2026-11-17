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


"""The pure readers and planners on their own, against what librespeed-common's
shell and ucode code would make of the same UCI values."""

from foris_controller_librespeed_module import model


def section(name, data, section_type="librespeed"):
    return {"name": name, "type": section_type, "anonymous": False, "data": data}


def test_bools_are_read_as_config_get_bool_reads_them():
    assert model.parse_bool("yes", False) is True
    # functions.sh compares case and all, so the init script reads "Yes" as unset.
    assert model.parse_bool("Yes", False) is False
    assert model.parse_bool("No", True) is True


def test_a_list_of_days_is_every_day_as_for_the_init_script():
    # functions.sh joins it as "1 2", which the init script does not take.
    assert model.parse_days(["1", "2"]) == []
    assert model.parse_days("1,2") == [1, 2]


def test_a_retention_in_other_digits_is_no_retention():
    assert model.raw_retention_days("30d") == 30
    assert model.raw_retention_days("²d") == 0


def test_links_of_the_wrong_type_are_none():
    links = model.links_reply({"interfaces": {"wan": "wan"}, "links": None, "down": "lte"})
    assert links == {"links": [], "interfaces": {"wan": "wan"}, "down": []}


def test_schedules_cron_skips_do_not_count_as_duplicates():
    current = {
        "interface": "wan",
        "schedule": {"enabled": True, "interface": None, "interval": "2d", "days": [], "hours": None},
        "interface_schedules": [
            {"enabled": True, "interface": "", "interval": "1d", "days": [], "hours": None},
            {"enabled": True, "interface": "", "interval": "1d", "days": [], "hours": None},
        ],
    }
    assert model.validate_update(current, {"interface": "wan"}, {}) is None
    current["schedule"]["interval"] = "1d"
    current["interface_schedules"][0]["interface"] = "wan"
    assert model.validate_update(current, {"interface": "wan"}, {})[0] == "duplicate_link"


def test_an_update_that_changes_nothing_adds_no_section():
    assert model.plan_update([], {"interface": "wan", "history": {"enabled": True}}) == []
    assert model.plan_update([], {"interface": "lte"}) == [
        ("add_named", "librespeed", "main"),
        ("set", "main", "interface", "lte"),
    ]


def test_a_result_from_before_interfaces_is_still_a_result():
    result = {
        "timestamp": "2026-11-16T17:25:47Z",
        "started": 1794849916,
        "finished": 1794849947,
        "server": {"name": "Local", "url": "http://192.0.2.2:8080/"},
        "download_mbps": 1.0,
        "upload_mbps": 1.0,
        "ping_ms": 1.0,
        "jitter_ms": 0.1,
    }
    reply = model.result_reply(result)
    assert reply is not None and "interface" not in reply
    assert model.result_reply(dict(result, interface="wan;reboot")) is None
