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

import logging

from foris_controller.handler_base import wrap_required_functions
from foris_controller.module_base import BaseModule


class LibreSpeedModule(BaseModule):
    logger = logging.getLogger(__name__)

    # Measurements: get_status is the state of record, polled by clients.

    def action_get_status(self, data):
        return self.handler.get_status()

    def action_start(self, data):
        return self.handler.start(data.get("interface"))

    def action_stop(self, data):
        return self.handler.stop()

    def action_get_result(self, data):
        return self.handler.get_result()

    def action_get_history(self, data):
        return self.handler.get_history(data)

    # Settings

    def action_get_config(self, data):
        return self.handler.get_config()

    def action_update_config(self, data):
        res = self.handler.update_config(data)
        if res["result"]:
            self.notify("update_config", data)
        return res

    def action_get_links(self, data):
        return self.handler.get_links()


@wrap_required_functions(
    [
        "get_status",
        "start",
        "stop",
        "get_result",
        "get_history",
        "get_config",
        "update_config",
        "get_links",
    ]
)
class Handler:
    pass
