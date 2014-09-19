#!/usr/bin/env python
import utils
import sys
from options import Options

if __name__ == "__main__":
    options = Options(['name'], [], [])
    try:
        options.parse()
    except Exception, msg:
        options.usage(str(msg))
        sys.exit(1)
    iocs = utils.find_iocs(id=options.name)
    for ioc in iocs:
        print "\tCONFIG:\t\t%s\n\tHOST:\t\t%s\n\tPORT:\t\t%s\n\tENABLED:\t%s" % \
              (ioc[0], ioc[1].get('host'), ioc[1].get('port'), not ioc[1].get('disable'))
    sys.exit(0)
