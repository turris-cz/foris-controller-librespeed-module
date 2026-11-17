Foris Controller LibreSpeed module
==================================

A foris-controller module for LibreSpeed internet speed measurements. It is a
thin layer over librespeed-common from the OpenWrt packages feed, which owns
the measurements, the schedules and the history: the UCI config
``librespeed``, the ubus object ``librespeed`` and
``/usr/libexec/librespeed-run``. luci-app-librespeed works on the same data, so
both front ends always show the same state.

Requirements
============

* python3
* foris-controller
* librespeed-common 1.0.0-r6 or later (measurements per interface)

Installation
============

	``pip install .``

API
===

All actions belong to the module ``librespeed``. Every action and field is
described in ``foris_controller_modules/librespeed/schema/librespeed.json``.
Units are in the field names (``_mbps``, ``_ms``, ``_seconds``,
``_percent``, ``_days``); other times are Unix seconds.

On a Turris router foris-controller listens on MQTT, port 11883, with its
credentials in ``/etc/fosquitto/credentials.plain``. The examples use::

	FC="mqtt --port 11883 --passwd-file /etc/fosquitto/credentials.plain"

Measuring
---------

``get_status``
	The state of record. Measurements also start from cron and from LuCI, so
	poll it about every 2 s while ``running`` is true and about every 30 s
	otherwise. While running it names the ``phase`` (``ping``, ``download``,
	``upload``), ``speed_mbps`` and, with clients that report it,
	``phase_progress_percent``. Afterwards ``last_error`` is empty after a
	success, ``stopped`` after a stop, and the failure otherwise; ``failures``
	keeps each interface's last failure until its link succeeds::

		foris-client -m librespeed -a get_status $FC

``start``
	Starts a measurement of ``interface``, or of the default interface, in the
	background. The reply comes once the measurement runs, once it has already
	ended (a quick failure), or after 5 s at most; ``get_status`` then tells
	which. A refusal has ``started`` false and an ``error`` code (see
	`Errors`_)::

		foris-client -m librespeed -a start -I '{"interface": "wan"}' $FC

``stop``
	Stops the running measurement, however it was started. ``stopped`` says
	whether one was running::

		foris-client -m librespeed -a stop $FC

``get_result``
	The last completed measurement, or ``null`` before the first one::

		foris-client -m librespeed -a get_result $FC

``get_history``
	Recorded results from ``from`` to ``to`` (both optional), at most the newest
	``limit``, oldest first. A range within the raw retention is answered from
	the raw history with ``resolution`` ``raw``. When a daily archive is kept,
	a range reaching further back, and also a request without ``from``, is
	answered from the archive with ``resolution`` ``1d``: one entry per
	completed day and interface, holding the day's mean and its ``_min``,
	``_max`` and ``samples``. The two never mix in one reply, so pass ``from``
	to get raw results::

		foris-client -m librespeed -a get_history -I '{"from": 1794000000, "limit": 100}' $FC

Settings
--------

``get_config``
	The default ``interface``, the ``server`` (``auto`` or an id),
	``scheme``, ``server_list``, the original ``schedule`` (``null`` when it
	was removed), the further ``interface_schedules``, the
	``applied_schedules`` cron runs now (with their ``next_runs``) and the
	``history`` settings. Values are reported as stored, even ones librespeed
	cannot use, except where librespeed falls back to a default, which is then
	reported instead. After a change ``applied_schedules`` catches up within
	seconds::

		foris-client -m librespeed -a get_config $FC

``update_config``
	Changes what it names and leaves the rest. ``schedule`` replaces the
	original schedule, which measures the default interface when its
	``interface`` is null; ``null`` removes it. ``interface_schedules``
	replaces all further schedules, each naming its interface. Only one
	enabled schedule may measure a link (``wan`` and ``wan6`` are one link).
	Values equal to the stored ones are not written again, so a daily
	measurement keeps its drawn time::

		foris-client -m librespeed -a update_config -I '{"schedule": {"enabled": true, "interface": null, "interval": "1d", "days": [], "hours": {"from": 2, "to": 5}}}' $FC

``get_links``
	The interfaces a measurement can be bound to: ``links`` to offer, the link
	each interface is recorded as (``wan6`` as ``wan``), and those whose link
	is ``down``::

		foris-client -m librespeed -a get_links $FC

Errors
------

``start`` refuses with one of these ``error`` codes, plus librespeed's own
words in ``message``:

=============================  ==============================================
``already_running``            another measurement runs; wait for it
``not_installed``              librespeed-run is missing
``unknown_interface``          no such interface in ``/etc/config/network``
``interface_not_configured``   netifd does not know it, e.g. it is disabled
``interface_down``             its link is down
``netifd_unavailable``         netifd did not answer
``backend_unavailable``        the ``librespeed`` ubus object did not answer
=============================  ==============================================

``update_config`` changes nothing and answers ``result`` false with
``duplicate_link`` (two enabled schedules would measure one link) or
``invalid_hours`` (a window ends before it starts). Malformed requests, such
as an interval cron cannot run, are rejected by the schema before they reach
the module. When the ``librespeed`` ubus object does not answer, other actions
answer with foris-controller's error reply, except ``get_config``, which then
reports no ``applied_schedules`` so the settings can still be shown, and
``update_config``, which then tells links apart by interface name only, as the
init script does.

Development
===========

The tests start foris-controller with both backends, ``openwrt`` against
``tests/uci_configs`` and the scripts under ``tests/test_root``, and ``mock``.
They need what the Turris CI image ``registry.nic.cz/turris/foris-ci/python3``
provides (uci, ubus, mosquitto) and run with::

	tox -- --backend openwrt --backend mock

The module must be installed as a wheel, as tox does: an editable install
cannot merge into foris-controller's ``foris_controller_backends`` package.

The ``openwrt`` backend talks to ``tests/test_root/bin/ubus``, which replays
the replies in ``tests/ubus_replies``. They were captured from rpcd and
librespeed-common on OpenWrt 25.12 with ``capture.sh`` beside them, so a new
librespeed-common is followed by capturing them again.
