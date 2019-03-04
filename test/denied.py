#!/usr/bin/python

import os, sys, subprocess, re
for x in open("../doorbot-cmp.txt").readlines():
        sp = x.strip().split()
        if sp and sp[0] == "[MEMBER]":
            name = sp[1]
            fl=name.split(".",2)
            if (len(fl)==2):
                (f,l)=fl
            else:
                f=""
                l=fl[0]
            print f,l,sp[3:]
            f=subprocess.Popen(["grep","-i",l,"../stripedebug.txt"],stdout=subprocess.PIPE)
            for x in  f.stdout.readlines(): print x.strip()
            f.wait()
            f=subprocess.Popen(["grep","-i",l,"../memberpaysync_debug.txt"],stdout=subprocess.PIPE)
            for x in  f.stdout.readlines(): print x.strip()
            f.wait()
            f=subprocess.Popen(["grep","-i",l,"../doorbot-v0-api.acl"],stdout=subprocess.PIPE)
            for x in  f.stdout.readlines(): print x.strip()
            f.wait()

            print 
