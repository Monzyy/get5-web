#!/usr/bin/env python3.6

import argparse
import sys

import get5

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Testing web server for get5.')
    parser.add_argument('--host', default='127.0.0.1',
                        help='ip for the server to listen on')
    parser.add_argument('--port', '-p', type=int, default=5000,
                        help='port for the server to listen on')
    args = parser.parse_args()

    get5.register_blueprints()
    sys.stderr.write(' * Starting get5 testing server. This is for testing only, do not run in production\n')
    get5.app.run(host=args.host, port=args.port)
