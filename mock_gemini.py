#!/usr/bin/env python3
import time
import sys
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("-m")
parser.add_argument("-y", action="store_true")
parser.add_argument("--output-format")
parser.add_argument("-p")
args = parser.parse_args()

if "sleep" in args.p:
    time.sleep(10)
    print("Slept 10 seconds")
elif "inactivity" in args.p:
    print("Starting...")
    sys.stdout.flush()
    time.sleep(10)
    print("Done after inactivity")
else:
    print("OK")
