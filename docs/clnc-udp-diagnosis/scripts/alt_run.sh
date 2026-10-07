#!/bin/sh
rm -f /tmp/clnc_test/out.txt
"$1" -c /tmp/clnc_test/tf.conf -d > /tmp/clnc_test/out.txt 2>&1
echo "RC=$?" >> /tmp/clnc_test/out.txt
