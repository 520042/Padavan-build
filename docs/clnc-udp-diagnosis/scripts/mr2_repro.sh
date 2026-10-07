#!/bin/sh
/usr/bin/clnc -c /tmp/clnc_test/t_repro.conf -d
echo "CLNC_EXIT=$?" >> /tmp/clnc_test/repro.log 2>&1
