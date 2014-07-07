#!/usr/bin/env python
import sys
import utils

if __name__ == '__main__':
  cfg  = sys.argv[1]
  sys.exit(utils.applyConfig(cfg))
