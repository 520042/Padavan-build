#!/bin/sh
/usr/bin/clnc -c /tmp/clnc_test/t_noudp.conf -d
echo "CLNC_EXIT=$?" >> /tmp/clnc_test/noudp.log 2>&1
