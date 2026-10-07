#!/bin/sh
/usr/bin/clnc -c /tmp/clnc_test/test.conf -d
echo "CLNC_EXIT=$?" >> /tmp/clnc_test/clnc.log 2>&1
