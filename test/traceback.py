#!/usr/bin/bash

FN=/root/trackback_`date --iso-8601`.log
grep Traceback -b10 -a200 /var/log/apache2/authbackend-error.log > $FN

# Use redirection (<) so wc -c outputs only the raw number without the filename
S=$(wc -c < $FN)

# Compare numerically using -eq (or check if S is zero)
if (( S == 0 )); then
  rm $FN
fi
