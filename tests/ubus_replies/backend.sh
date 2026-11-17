#!/bin/sh
# A minimal LibreSpeed backend: uhttpd with CGI endpoints on eth0, port 8080,
# serving server lists that point at itself (up) and at a closed port (down).
mkdir -p /var/run /www/cgi-bin /www/lists
apk update >/dev/null 2>&1
apk add uhttpd >/dev/null 2>&1 || exit 1
ip=$BACKEND_IP
cat > /www/cgi-bin/empty.php <<'EOF'
#!/bin/sh
cat > /dev/null
printf 'Status: 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 0\r\n\r\n'
EOF
cat > /www/cgi-bin/garbage.php <<'EOF'
#!/bin/sh
ck=$(echo "$QUERY_STRING" | sed -n 's/.*ckSize=\([0-9]*\).*/\1/p')
printf 'Status: 200 OK\r\nContent-Type: application/octet-stream\r\n\r\n'
head -c $((${ck:-4} * 1048576)) /dev/zero
EOF
cat > /www/cgi-bin/getIP.php <<'EOF'
#!/bin/sh
printf 'Status: 200 OK\r\nContent-Type: application/json\r\n\r\n{"processedString":"192.0.2.10 - Example Networks","rawIspInfo":{"ip":"192.0.2.10","org":"Example Networks"}}'
EOF
chmod 0755 /www/cgi-bin/*
echo "[{\"id\":2,\"name\":\"Local\",\"server\":\"http://$ip:8080/cgi-bin/\",\"dlURL\":\"garbage.php\",\"ulURL\":\"empty.php\",\"pingURL\":\"empty.php\",\"getIpURL\":\"getIP.php\"}]" > /www/lists/up.json
echo "[{\"id\":1,\"name\":\"Down\",\"server\":\"http://$ip:9/\",\"dlURL\":\"garbage.php\",\"ulURL\":\"empty.php\",\"pingURL\":\"empty.php\",\"getIpURL\":\"getIP.php\"}]" > /www/lists/down.json
echo "backend on $ip"
exec uhttpd -f -p 0.0.0.0:8080 -h /www -x /cgi-bin -t 60 -T 30
