#!/usr/bin/env python3
"""Minimal location probe placeholder for food-scout workflows."""
import json

if __name__ == '__main__':
    print(json.dumps({
        'status': 'unconfigured',
        'message': 'Location service is not configured on this host.'
    }, ensure_ascii=False))
