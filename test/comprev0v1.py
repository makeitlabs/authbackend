#!/usr/bin/python

import json,os,sys

if __name__ == "__main__":
	v1 = json.load(open("/tmp/v1.txt"))
	v0 = open("/tmp/v0.txt").readlines()[1:]

	for i in range(0,max(len(v0),len(v1))):
		vv = v0[i].split(",")
		print v1[i]['member'],vv[0]
