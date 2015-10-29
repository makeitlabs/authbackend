#!/usr/bin/env python
# Utilities for MakeIt Labs

import hashlib
    
def hash_rfid(rfid):
    "Given an integer RFID, create a hashed value for storage"
    if rfid == 'None':
        return ''
    else:
        m = hashlib.sha224()
        rfidStr = "%.10d"%(int(rfid))
        m.update(str(rfidStr).encode())
        return m.hexdigest()

