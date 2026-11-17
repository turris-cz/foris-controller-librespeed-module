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

import json
import os

import pytest

TESTS_DIR = os.path.dirname(os.path.realpath(__file__))
UBUS_STATE = "/tmp/foris-librespeed-ubus.json"
UBUS_CALLS = "/tmp/foris-librespeed-ubus-calls.jsonl"


@pytest.fixture(scope="session")
def uci_config_default_path():
    return os.path.join(TESTS_DIR, "uci_configs")


@pytest.fixture(scope="session")
def cmdline_script_root():
    return os.path.join(TESTS_DIR, "test_root")


@pytest.fixture(scope="session")
def file_root():
    return os.path.join(TESTS_DIR, "test_root")


@pytest.fixture(scope="module")
def controller_modules():
    return ["remote", "librespeed"]


@pytest.fixture(scope="module")
def env_overrides():
    # The mock's measurement walks its stages in 3 s instead of 15 s.
    return {"FORIS_LIBRESPEED_MOCK_SECONDS": "3"}


class FakeUbus:
    """Steers tests/test_root/bin/ubus, which the openwrt backend calls."""

    @staticmethod
    def reply(name):
        with open(os.path.join(TESTS_DIR, "ubus_replies", name + ".json")) as f:
            return json.load(f)

    def scenario(self, fail=(), **replies):
        """Replies by method; a fixture name is loaded, a list is a sequence."""
        resolved = {}
        for method, reply in replies.items():
            items = reply if isinstance(reply, list) else [reply]
            items = [self.reply(r) if isinstance(r, str) else r for r in items]
            resolved[method] = items if isinstance(reply, list) else items[0]
        with open(UBUS_STATE, "w") as f:
            json.dump({"replies": resolved, "fail": list(fail)}, f)

    @staticmethod
    def calls(method=None):
        if not os.path.exists(UBUS_CALLS):
            return []
        with open(UBUS_CALLS) as f:
            calls = [json.loads(line) for line in f]
        return [c for c in calls if method is None or c["method"] == method]


@pytest.fixture(autouse=True)
def ubus():
    for path in (UBUS_STATE, UBUS_CALLS):
        if os.path.exists(path):
            os.unlink(path)
    yield FakeUbus()


def pytest_addoption(parser):
    parser.addoption(
        "--backend",
        action="append",
        default=[],
        help=("Set test backend here. available values = (mock, openwrt)"),
    )
    parser.addoption(
        "--message-bus",
        action="append",
        default=[],
        help=("Set test bus here. available values = (unix-socket, ubus, mqtt)"),
    )
    parser.addoption(
        "--debug-output",
        action="store_true",
        default=False,
        help=("Whether show output of foris-controller cmd"),
    )


def pytest_generate_tests(metafunc):
    if "backend" in metafunc.fixturenames:
        backend = metafunc.config.option.backend
        if not backend:
            backend = ["openwrt"]
        metafunc.parametrize("backend_param", backend, scope="module")

    if "message_bus" in metafunc.fixturenames:
        message_bus = metafunc.config.option.message_bus
        if not message_bus:
            message_bus = ["mqtt"]
        metafunc.parametrize("message_bus_param", message_bus, scope="module")
