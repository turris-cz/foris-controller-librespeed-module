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

"""librespeed-common on OpenWrt: its ubus object and its UCI config.

Measurements run in librespeed-run, started detached by ubus start, so they
outlive foris-controller and LuCI's stop reaches them. Nothing here keeps
state of its own.
"""

import logging
import os
import time

from foris_controller_backends.ubus import UbusBackend
from foris_controller_backends.uci import UciBackend

from foris_controller_librespeed_module import model

logger = logging.getLogger(__name__)

CONFIG = "librespeed"


class LibreSpeedUnavailable(Exception):
    """The librespeed ubus object did not answer."""


def call(method, data=None):
    reply = UbusBackend.call_ubus("librespeed", method, data)
    if reply is None:
        raise LibreSpeedUnavailable(method)
    return reply


class LibreSpeedUci:
    @staticmethod
    def _path(backend):
        return os.path.join(backend.config_dir, CONFIG)

    @classmethod
    def _sections(cls, backend):
        """A missing file reads as the defaults; a broken one is an error."""
        if not os.path.exists(cls._path(backend)):
            return []
        return backend.read(CONFIG).get(CONFIG, [])

    def read(self):
        with UciBackend() as backend:
            return model.config_from_uci(self._sections(backend))

    def update(self, update, link_of):
        """(result, error, message); writes only what differs, so a no-op commits nothing."""
        with UciBackend() as backend:
            sections = self._sections(backend)
            error = model.validate_update(model.config_from_uci(sections), update, link_of)
            if error:
                return False, error[0], error[1]
            ops = model.plan_update(sections, update)
            if ops and not os.path.exists(self._path(backend)):
                open(self._path(backend), "a").close()  # uci writes only to an existing file
            for op in ops:
                if op[0] == "set":
                    backend.set_option(CONFIG, op[1], op[2], op[3])
                elif op[0] == "del":
                    backend.del_option(CONFIG, op[1], op[2], fail_on_error=False)
                elif op[0] == "add_named":
                    backend.add_section(CONFIG, op[1], op[2])
                elif op[0] == "add_schedule":
                    name = backend.add_section(CONFIG, "schedule")
                    for option, value in op[1].items():
                        backend.set_option(CONFIG, name, option, value)
                elif op[0] == "delete":
                    backend.del_section(CONFIG, op[1])
        return True, None, None


class LibreSpeedRunner:
    START_WAIT = 5.0
    POLL = 0.25

    def status(self):
        return model.status_reply(call("status"))

    def start(self, interface):
        """Waits until the measurement runs or has ended, at most START_WAIT.

        It has ended when last_finished changes: a time comparison would take a
        run that ended in the second this one started for this one.
        """
        try:
            previous = call("status").get("last_finished")
            reply = call("start", {"interface": interface} if interface else None)
        except LibreSpeedUnavailable:
            return {"started": False, "error": "backend_unavailable"}
        if reply.get("started") is not True:
            message = reply.get("error") if isinstance(reply.get("error"), str) else ""
            out = {"started": False, "error": model.start_error(message)}
            if message:
                out["message"] = message
            return out

        deadline = time.monotonic() + self.START_WAIT
        while time.monotonic() < deadline:
            try:
                status = call("status")
            except LibreSpeedUnavailable:
                break
            finished = status.get("last_finished")
            if status.get("running") is True or (finished is not None and finished != previous):
                break
            time.sleep(self.POLL)
        return {"started": True}

    def stop(self):
        running = call("status").get("running") is True
        call("stop")
        return {"stopped": running}

    def result(self):
        return {"measurement": model.result_reply(call("result"))}

    def history(self, query):
        return model.history_reply(call("history", query or None))

    def links(self):
        links = model.links_reply(call("links"))
        if links is None:
            raise LibreSpeedUnavailable("links")
        return links

    def link_of(self):
        """Interface to link, or {} when netifd cannot say; validation then compares names."""
        try:
            links = model.links_reply(call("links"))
        except LibreSpeedUnavailable:
            links = None
        return links["interfaces"] if links else {}

    def applied_schedules(self):
        """What cron runs; [] when the ubus object does not answer, so settings still load."""
        try:
            return model.applied_schedules_reply(call("config"))
        except LibreSpeedUnavailable:
            logger.warning("librespeed ubus object did not answer; no applied schedules to show")
            return []
