#!/bin/sh
# Captures the replies in this directory: the librespeed ubus object as rpcd
# and librespeed-common's ucode plugin answer on OpenWrt 25.12, with netifd
# replaced by a dump (wan and wan6 on eth0, lte down, lan without a gateway)
# and a LibreSpeed backend from backend.sh in a second container:
#
#   docker network create --subnet 172.30.0.0/16 lsnet
#   docker run -d --rm --name ls-backend --network lsnet --ip 172.30.0.2 \
#       -e BACKEND_IP=172.30.0.2 -v "$PWD:/rt:ro" \
#       openwrt/rootfs:aarch64_generic-openwrt-25.12 sh /rt/backend.sh
#   docker run --rm --network lsnet --ip 172.30.0.3 -e BACKEND_IP=172.30.0.2 \
#       -v <packages>/utils/librespeed-common:/pkg:ro -v "$PWD:/rt:ro" \
#       -v "$PWD/out:/out" openwrt/rootfs:aarch64_generic-openwrt-25.12 sh /rt/capture.sh
#
# /rt also holds librespeed-cli, a Go client with --json-stream. The replies
# were then committed with the backend's address replaced by 192.0.2.2.
set -u
OUT=/out
mkdir -p /var/lock /var/run/ubus /tmp /www/cgi-bin /www/lists
apk update >/dev/null 2>&1
apk add librespeed-cli librespeed-common uhttpd >/tmp/apk.log 2>&1 || { tail /tmp/apk.log; exit 1; }
cp /pkg/files/librespeed-run /pkg/files/librespeed-aggregate /usr/libexec/
chmod 0755 /usr/libexec/librespeed-run /usr/libexec/librespeed-aggregate
sed -i "s/%%VERSION%%/1.0.0-6/g" /usr/libexec/librespeed-run /usr/libexec/librespeed-aggregate
cp /pkg/files/librespeed.uc /usr/share/rpcd/ucode/librespeed.uc
cp /pkg/files/librespeed.init /etc/init.d/librespeed
chmod 0755 /etc/init.d/librespeed
cp /pkg/files/librespeed.config /etc/config/librespeed
cp /rt/librespeed-cli /usr/bin/librespeed-cli
chmod 0755 /usr/bin/librespeed-cli

# netifd: wan (IPv4 default route) and wan6 share eth0, lte is down, lan has no gateway.
cat > /tmp/dump.json <<'EOF'
{"interface":[
 {"interface":"lan","up":true,"pending":false,"available":true,"dynamic":false,"proto":"static","device":"br-lan","l3_device":"br-lan","ipv4-address":[{"address":"192.168.1.1","mask":24}],"route":[]},
 {"interface":"loopback","up":true,"pending":false,"available":true,"dynamic":false,"proto":"static","device":"lo","l3_device":"lo","ipv4-address":[{"address":"127.0.0.1","mask":8}],"route":[]},
 {"interface":"wan","up":true,"pending":false,"available":true,"dynamic":false,"proto":"static","device":"eth0","l3_device":"eth0","ipv4-address":[{"address":"172.30.0.3","mask":16}],"route":[{"target":"0.0.0.0","mask":0,"nexthop":"172.30.0.1"}]},
 {"interface":"wan6","up":true,"pending":false,"available":true,"dynamic":false,"proto":"dhcpv6","device":"eth0","l3_device":"eth0","ipv6-address":[{"address":"2001:db8::2","mask":64}],"route":[]},
 {"interface":"lte","up":false,"pending":false,"available":true,"dynamic":false,"proto":"dhcp","device":"wwan0","route":[]}
]}
EOF
mkdir -p /tmp/stub
cat > /tmp/stub/ubus <<'EOF'
#!/bin/sh
case "$*" in
*"network.interface dump"*) [ -e /tmp/no-netifd ] && exit 4; cat /tmp/dump.json ;;
*) exec /bin/ubus "$@" ;;
esac
EOF
chmod 0755 /tmp/stub/ubus
export PATH=/tmp/stub:$PATH
touch /etc/config/network
for i in lan wan wan6 lte disabledif; do uci set "network.$i=interface"; done
uci set network.wan6.proto=dhcpv6
uci commit network

/sbin/ubusd >/dev/null 2>&1 &
sleep 1
/sbin/rpcd >/dev/null 2>&1 &
sleep 2
/bin/ubus list librespeed >/dev/null || { echo "librespeed object missing"; exit 1; }

B="http://$BACKEND_IP:8080"

cap() {
	name=$1
	shift
	/bin/ubus call librespeed "$@" > "$OUT/$name.json" 2> "$OUT/$name.err"
	echo "$name rc=$?: $(tr -d '\n\t' < "$OUT/$name.json" | cut -c1-150)"
}
wait_idle() {
	for i in $(seq 1 90); do
		/bin/ubus call librespeed status | grep -q '"running": false' && return 0
		sleep 1
	done
	return 1
}

uci set librespeed.main.server_list=$B/lists/up.json
uci commit librespeed

cap idle-status status
cap idle-result result
cap idle-history history
cap idle-config config
cap links links
cap start-refused-down start '{"interface":"lte"}'
cap start-refused-unknown start '{"interface":"nope"}'
cap start-refused-notconfigured start '{"interface":"disabledif"}'
touch /tmp/no-netifd
cap start-refused-netifd start '{"interface":"wan"}'
cap links-netifd links
rm /tmp/no-netifd
mv /usr/libexec/librespeed-run /usr/libexec/librespeed-run.off
cap start-refused-notinstalled start
mv /usr/libexec/librespeed-run.off /usr/libexec/librespeed-run

cap start-ok start '{"interface":"wan"}'
sleep 2
cap start-already-running start
seen=""
for i in $(seq 1 60); do
	/bin/ubus call librespeed status > /tmp/st.json
	grep -q '"running": false' /tmp/st.json && break
	ph=$(jsonfilter -i /tmp/st.json -e '@.phase')
	case " $seen " in *" ${ph:-none} "*) ;; *)
		cp /tmp/st.json "$OUT/running-${ph:-connecting}-status.json"
		echo "running-${ph:-connecting}-status: $(tr -d '\n\t' < /tmp/st.json | cut -c1-200)"
		seen="$seen ${ph:-none}"
	esac
	sleep 1
done
wait_idle
cap finished-status status
cap finished-result result
cap finished-history history

cap start-wan6 start '{"interface":"wan6"}'
wait_idle
cap finished-wan6-result result

cap start-to-stop start '{"interface":"wan"}'
sleep 8
cap stop stop
sleep 3
cap stopped-status status
cap stop-idle stop

uci set librespeed.main.server_list=$B/lists/down.json
uci set librespeed.main.server=1
uci commit librespeed
cap start-to-fail start '{"interface":"wan"}'
wait_idle
cap failed-status status
uci set librespeed.main.server_list=$B/lists/up.json
uci set librespeed.main.server=auto
uci commit librespeed

uci set librespeed.schedule.enabled=1
sid=$(uci add librespeed schedule)
uci set "librespeed.$sid.interface=lte"
uci set "librespeed.$sid.enabled=1"
uci set "librespeed.$sid.interval=7d"
uci set "librespeed.$sid.days=1,3"
uci set "librespeed.$sid.hours=2-5"
sid=$(uci add librespeed schedule)
uci set "librespeed.$sid.interface=wan6"
uci set "librespeed.$sid.enabled=0"
uci set "librespeed.$sid.interval=90m"
uci commit librespeed
( set +u; . /lib/functions.sh; . /etc/init.d/librespeed; sync_cron ) 2>&1 | head -5
echo "crontab: $(grep librespeed-run /etc/crontabs/root | tr '\n' '|')"
cap scheduled-config config
uci export librespeed > "$OUT/scheduled-uci.txt"

hist=/tmp/librespeed/history.jsonl
old=$(( $(date +%s) - 2 * 86400 ))
for k in 0 1 2; do
	printf '{ "timestamp": "%s", "epoch": %d, "interface": "wan", "server": { "id": 2, "name": "Local", "url": "http:\\/\\/127.0.0.1:8080\\/cgi-bin\\/" }, "proto": "http", "download_mbps": %d.5, "upload_mbps": 40%d.25, "ping_ms": 1.%d, "jitter_ms": 0.%d }\n' \
		"$(date -u -d "@$((old + k * 600))" +%Y-%m-%dT%H:%M:%SZ)" $((old + k * 600)) $((900 + k)) $k $k $k >> "$hist"
done
uci set librespeed.history.archive_path=/tmp/archive/daily.jsonl
uci commit librespeed
mkdir -p /tmp/archive
/usr/libexec/librespeed-aggregate
cap history-archive history
cap history-from history "{\"from\": $(( $(date +%s) - 3600 ))}"
cap history-limit history "{\"from\": $(( $(date +%s) - 3 * 86400 )), \"limit\": 2}"
ls "$OUT"
