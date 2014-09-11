#!/usr/bin/env python
import sys
import utils

if __name__ == '__main__':
  ioc = sys.argv[1]
  cfg  = sys.argv[2]
  result = utils.readConfig(cfg)
  if result == None:
      print "NO_DIRECTORY"
      sys.exit(-1)
  (mtime, config, hosts) = result
  for l in config:
      if l['id'] == ioc:
          print l['dir']
          sys.exit(0)
  print "NO_DIRECTORY"
  sys.exit(-1)
