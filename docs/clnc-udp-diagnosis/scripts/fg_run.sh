#!/bin/sh
rm -f /tmp/clnc_test/out.txt
/usr/bin/clnc -c /tmp/clnc_test/tf.conf -d > /tmp/clnc_test/out.txt 2>&1
echo "CLNC_RC=$?" >> /tmp/clnc_test/out.txt
