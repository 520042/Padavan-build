#!/bin/sh
/usr/bin/clnc -c /tmp/clnc_test/t_tproxy.conf -d
echo "CLNC_EXIT=$?" >> /tmp/clnc_test/tproxy.log 2>&1
