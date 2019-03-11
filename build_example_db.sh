#!/bin/sh
rm makeit.db 
sqlite3 makeit.db < makeit_db.example 
