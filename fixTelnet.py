#!/usr/bin/env python
import sys
import utils

if __name__ == '__main__':
# port = sys.argv[1]
# utils.fixTelnetShell('localhost', port)
  host = sys.argv[1]
  port = sys.argv[2]
  utils.fixTelnetShell(host, port)
