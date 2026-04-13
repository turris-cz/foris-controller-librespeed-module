#
# foris-controller-librespeed-module
# Copyright (C) 2022 CZ.NIC, z.s.p.o. (http://www.nic.cz/)
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

import argparse
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path
from subprocess import PIPE, Popen

from . import __version__


def main():

    # Parse the command line options
    parser = argparse.ArgumentParser(prog="turris-librespeed")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--data-dir", default="/tmp/librespeed-data/", type=Path, required=False
    )
    parser.add_argument("--server", type=int, required=False)
    parser.add_argument("--bin", default="librespeed-cli", required=False)

    options = parser.parse_args()

    args = [options.bin, "--json"]
    if options.server:
        args.extend(("--server", str(options.server)))

    try:
        options.data_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(e)
        sys.exit(1)

    args.append("--insecure")

    proc = Popen(
        args,
        text=True,
        stdout=PIPE,
    )
    (out, err) = proc.communicate()
    if proc.returncode != 0:
        print(err)
        sys.exit(proc.returncode)

    try:
        parsed = json.loads(out)
    except json.JSONDecodeError as e:
        print(e)
        sys.exit(1)

    try:
        date = datetime.date.fromisoformat(parsed[0]["timestamp"][:10])
    except (KeyError, ValueError) as e:
        print(e)
        sys.exit(1)

    target_dir = options.data_dir / f"{date.year:04}-{date.month:02}"
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(e)
        sys.exit(1)

    # Store to .tmp file first
    with tempfile.NamedTemporaryFile(
        "w", suffix="tmp", dir=target_dir, delete=False
    ) as f:
        f.write(json.dumps(parsed))
        f.flush()

        # move file to proper locaction
        os.replace(f.name, target_dir / f"{parsed[0]['timestamp']}.json")


if __name__ == "__main__":
    main()
