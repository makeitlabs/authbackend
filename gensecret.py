#!/usr/bin/python3
import os
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.fernet import Fernet
import getpass
import sys
import base64

# 1. Define your password and the secret you want to hide
password  = getpass.getpass("Password: ").encode("utf-8")
password2 = getpass.getpass("Reenter : ").encode("utf-8")
if (password != password2):
    print ("Mismatch")
    sys.exit(1)
secret_message = input("Secret: ").encode('utf-8')

# 2. Generate a random 16-byte salt
salt = os.urandom(16)

# 3. Set up PBKDF2
kdf = PBKDF2HMAC(
    algorithm=hashes.SHA256(),
    length=32,
    salt=salt,
    iterations=480_000, # High iteration count makes guessing harder
)

# 4. Derive the key and encrypt
key = base64.urlsafe_b64encode(kdf.derive(password))
f = Fernet(key)
encrypted_secret = f.encrypt(secret_message)

# 5. Print the values you need to copy into your final script
print(f"HEX_SALT='{salt.hex()}'")
print(f"ENCRYPTED_SECRET=b'{encrypted_secret.decode()}'")
