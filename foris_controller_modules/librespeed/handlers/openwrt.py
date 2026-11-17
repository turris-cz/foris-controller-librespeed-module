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

from foris_controller.handler_base import BaseOpenwrtHandler
from foris_controller.utils import logger_wrapper
from foris_controller_backends.librespeed import LibreSpeedRunner, LibreSpeedUci
from foris_controller_librespeed_module import model

from .. import Handler

logger = logging.getLogger(__name__)


class OpenwrtLibreSpeedHandler(Handler, BaseOpenwrtHandler):
    uci = LibreSpeedUci()
    runner = LibreSpeedRunner()

    @logger_wrapper(logger)
    def get_status(self):
        return self.runner.status()

    @logger_wrapper(logger)
    def start(self, interface=None):
        return self.runner.start(interface)

    @logger_wrapper(logger)
    def stop(self):
        return self.runner.stop()

    @logger_wrapper(logger)
    def get_result(self):
        return self.runner.result()

    @logger_wrapper(logger)
    def get_history(self, query):
        return self.runner.history(query)

    @logger_wrapper(logger)
    def get_config(self):
        config = self.uci.read()
        config["applied_schedules"] = self.runner.applied_schedules()
        return config

    @logger_wrapper(logger)
    def update_config(self, update):
        # Asking for the links costs a netifd dump, so only when they are checked.
        link_of = self.runner.link_of() if model.touches_links(update) else {}
        result, error, message = self.uci.update(update, link_of)
        reply = {"result": result}
        if error:
            reply["error"] = error
            reply["message"] = message
        return reply

    @logger_wrapper(logger)
    def get_links(self):
        return self.runner.links()
