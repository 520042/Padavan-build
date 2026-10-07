#!/bin/sh
/usr/bin/clnc -c /tmp/clnc_test/t_noheader.conf -d
echo "CLNC_EXIT=$?" >> /tmp/clnc_test/noheader.log 2>&1
