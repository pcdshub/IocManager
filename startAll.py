#!/usr/bin/env python
import sys
import utils

if __name__ == '__main__':
  cfg  = sys.argv[1]
  host = sys.argv[2]
  result = utils.readConfig(cfg)
  if result == None:
      print "Cannot read configuration for %s!" % cfg
      sys.exit(-1)
  (platform, config) = result
  for l in config:
      if l['host'] == host:
          utils.startProc(platform, cfg, l)
