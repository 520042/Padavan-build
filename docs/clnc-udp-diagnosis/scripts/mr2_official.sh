#!/bin/sh
/usr/bin/clnc -c /tmp/clnc_test/t_official.conf -d
echo "CLNC_EXIT=$?" >> /tmp/clnc_test/official.log 2>&1
