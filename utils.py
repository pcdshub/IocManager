######################################################################
#
# Exported API routines:
#
# getBaseName(iocName)
#     Return the basename of the iocAdmin PVs for a particular IOC.
#
# fixdir(rundir, iocName)
#     Abbreviate the running directory of an IOC by making it relative
#     to EPICS_SITE_TOP and removing the final "build" or "iocBoot"
#     portion of the path.
#
# check_status(host, port, id)
#     Check the health of an IOC, returning a dictionary with status,
#     pid, id, autorestart, autorestartmode, and rdir.
#
# killProc(host, port)
#     Kill the IOC at the given location.
#
# restartProc(host, port)`
#     Restart the IOC at the given location.
#
# startProc(hutch, entry)
#     entry is a configuration dictionary entry that should be started
#     for a particular hutch.
#
# readConfig(hutch, time=None, do_os=False)
#     Read the configuration file for a given hutch if newer than time.
#     Return None on failure or no change, otherwise a tuple: (filetime,
#     configlist, hostlist, vars).  filetime is the modification time of
#     the configuration, configlist is a list of dictionaries containing
#     an IOC configuration, hostlist is a (hint) list of hosts in this
#     hutch, and vars is an additional list of variables defined in the
#     config file.
#
#     If do_os is True, also scan the .hosts directory to build a host type
#     lookup table.
#
# writeConfig(hutch, hostlist, configlist, vars, f=None)
#     Write the configuration file for a given hutch.  Deals with the
#     existence of uncommitted changes ("new*" fields).  If f is given,
#     write to this open file instead of the real configuration file.
#     vars is a dictionary of additional values to write.
#
# installConfig(hutch, filename, fd=None)
#     Install the given filename as the configuration file for the
#     specified hutch.  If fd is None, do it directly, otherwise send
#     a request to run the installConfig utility through the given pipe.
#
# readStatusDir(hutch, readfile)
#     Read the status directory for a particular hutch, returning a list
#     of dictionaries containing updated information.  The readfile parameter
#     is a function passed a filepath and the IOC name.  This should read
#     any updated information, returning a list of lines or an empty list
#     if the file was not read.  The default readfile always reads everything.
#
# applyConfig(hutch, verify=None, ioc=None)
#     Apply the current configuration for the specified hutch. Before
#     the configuration is applied, the verify method, if any is called.
#     This routine is passed:
#         current - The actual state of things.
#         config - The desired configuration.
#         kill_list - The IOCs that should be killed.
#         start_list - The IOCs that should be started.
#         restart_list - The IOCs that should be restarted with ^X.
#     The method should return a (kill, start, restart) tuple of the
#     IOCs that should *really* be changed.  (This method could then
#     query the user to limit the changes or cancel them altogether.)
#     If an ioc is specified (by name), only that IOC will be changed,
#     otherwise the entire configuration will be applied.
#
# netconfig(host)
#     Return a dictionary with the netconfig information for this host.
#
# rebootServer(host)
#     Attempt to reboot the specified host.  Return True if successful.
#
# getHutchList()
#     Return the list of all supported hutches.
#
######################################################################


import telnetlib, string, datetime, os, time, fcntl, re, glob, subprocess, copy, sys, stat

#
# Defines
#
CAMRECORDER  = os.getenv("CAMRECORD_ROOT")
PROCSERV_EXE = os.getenv("PROCSERV_EXE")
if PROCSERV_EXE is None:
    PROCSERV_EXE = "procServ"
else:
    PROCSERV_EXE = PROCSERV_EXE.split()[0]
# Note: TMP_DIR and CONFIG_FILE should be on the same file system so os.rename works!!
TMP_DIR      = "%s/config/.status/tmp" % os.getenv("PYPS_ROOT")   
STARTUP_DIR  = "%s/config/%%s/iocmanager/" % os.getenv("PYPS_ROOT")
CONFIG_DIR  = "%s/config/" % os.getenv("PYPS_ROOT")
CONFIG_FILE = "%s/config/%%s/iocmanager.cfg" % os.getenv("PYPS_ROOT")
NOSSH_FILE = "%s/config/%%s/iocmanager.nossh" % os.getenv("PYPS_ROOT")
HIOC_STARTUP = "/reg/d/iocCommon/hioc/%s/startup.cmd"
HIOC_POWER   = "/reg/common/tools/bin/power"
HIOC_CONSOLE = "/reg/common/tools/bin/console"
AUTH_FILE    = "%s/config/%%s/iocmanager.auth" % os.getenv("PYPS_ROOT")
SPECIAL_FILE = "%s/config/%%s/iocmanager.special" % os.getenv("PYPS_ROOT")
STATUS_DIR   = "%s/config/.status/%%s" % os.getenv("PYPS_ROOT")
HOST_DIR     = "%s/config/.host" % os.getenv("PYPS_ROOT")
LOGBASE      = "%s/%%s/iocInfo/ioc.log" % os.getenv("IOC_DATA")
PVFILE       = "%s/%%s/iocInfo/IOC.pvlist" % os.getenv("IOC_DATA")
INSTALL      = __file__[:__file__.rfind('/')] + "/installConfig"
BASEPORT     = 39050
COMMITHOST   = "psbuild-rhel7"
NETCONFIG    = "/reg/common/tools/bin/netconfig"

STATUS_INIT      = "INITIALIZE WAIT"
STATUS_NOCONNECT = "NOCONNECT"
STATUS_RUNNING   = "RUNNING"
STATUS_SHUTDOWN  = "SHUTDOWN"
STATUS_DOWN      = "HOST DOWN"
STATUS_ERROR     = "ERROR"

CONFIG_NORMAL    = 0
CONFIG_ADDED     = 1
CONFIG_DELETED   = 2

# messages expected from procServ
MSG_BANNER_END = "server started at"
MSG_ISSHUTDOWN = "is SHUT DOWN"
MSG_ISSHUTTING = "is shutting down"
MSG_KILLED     = "process was killed"
MSG_RESTART = "new child"
MSG_PROMPT_OLD = "\x0d\x0a[$>] "
MSG_PROMPT = "\x0d\x0a> "
MSG_SPAWN = "procServ: spawning daemon"
MSG_AUTORESTART_MODE            = "auto restart mode"
MSG_AUTORESTART_IS_ON           = "auto restart( mode)? is ON,"
MSG_AUTORESTART_IS_ONESHOT      = "auto restart( mode)? is ONESHOT,"
MSG_AUTORESTART_CHANGE          = "auto restart to "
MSG_AUTORESTART_MODE_CHANGE     = "auto restart mode to "

EPICS_DEV_TOP	 = "/reg/g/pcds/epics-dev"
EPICS_SITE_TOP   = "/reg/g/pcds/epics/"

stpaths = ["%s/children/build/iocBoot/%s/st.cmd", "%s/build/iocBoot/%s/st.cmd", "%s/iocBoot/%s/st.cmd"]

hosttype = {}

######################################################################
#
# Name and Directory Utilities
#

#
# Given an IOC name, find the base PV name.
#
def getBaseName(ioc):
    pvInfoPath = PVFILE % ioc
    if not os.path.isfile( pvInfoPath ):
        return None
    try:
        lines = open(pvInfoPath).readlines()
        for l in lines:
            pv = l.split(",")[0]
            if pv[-10:] == ":HEARTBEAT":
                return pv[:-10]
    except:
        print "Error parsing %s for base PV name!" % (pvInfoPath)
    return None

#
# Given a full path and an IOC name, return a path relative
# to EPICS_SITE_TOP without the final "iocBoot".
#
def fixdir(dir, id):
    # Handle ".."
    l = dir.split('/')
    while ".." in l:
        idx = l.index("..")
        l = l[:idx-1]+l[idx+1:]
    dir = "/".join(l)
    if dir[0:len(EPICS_SITE_TOP)] == EPICS_SITE_TOP:
        dir = dir[len(EPICS_SITE_TOP):]
    try:
        ext = "/children/build/iocBoot/" + id
        if dir[len(dir)-len(ext):len(dir)] == ext:
            dir = dir[0:len(dir)-len(ext)]
    except:
        pass
    try:
        ext = "/build/iocBoot/" + id
        if dir[len(dir)-len(ext):len(dir)] == ext:
            dir = dir[0:len(dir)-len(ext)]
    except:
        pass
    try:
        ext = "/iocBoot/" + id
        if dir[len(dir)-len(ext):len(dir)] == ext:
            dir = dir[0:len(dir)-len(ext)]
    except:
        pass
    return dir


######################################################################
#
# Telnet/Procserv Utilities
#

#
# Read and parse the connection information from a new procServ telnet connection.
# Returns a dictionary of information.
#
def readLogPortBanner(tn):
    try:
        response = tn.read_until(MSG_BANNER_END, 1)
    except:
        response = ""
    if not response.count(MSG_BANNER_END):
        return {'status'      : STATUS_ERROR,
                'pid'         : "-",
                'rid'         : "-",
                'autorestart' : False,
                'autooneshot' : False,
                'autorestartmode' : False,
                'rdir'        : "/tmp" }
    if re.search('SHUT DOWN', response):
        tmpstatus = STATUS_SHUTDOWN
        pid = "-"
    else:
        tmpstatus = STATUS_RUNNING
        pid = re.search('@@@ Child \"(.*)\" PID: ([0-9]*)', response).group(2)
    match = re.search('@@@ Child \"(.*)\" start', response)
    getid = "-"
    if match:
        getid = match.group(1)
    match = re.search('@@@ Server startup directory: (.*)', response)
    dir = "/tmp"
    if match:
        dir = match.group(1)
        if dir[-1] == '\r':
            dir = dir[:-1]
    # Note: This means that ONESHOT counts as OFF!
    if re.search(MSG_AUTORESTART_IS_ON, response):
        arst = True
    else:
        arst = False
    if re.search(MSG_AUTORESTART_IS_ONESHOT, response):
        arst1 = True
    else:
        arst1 = False
    # procServ 2.8 changed "auto restart" to "auto restart mode"
    if re.search(MSG_AUTORESTART_MODE, response):
        arstm = True
    else:
        arstm = False

    return {'status'      : tmpstatus,
            'pid'         : pid,
            'rid'         : getid,
            'autorestart' : arst,
            'autooneshot' : arst1,
            'autorestartmode' : arstm,
            'rdir'        : fixdir(dir, getid) }

pdict = {}
#
# Returns a dictionary with status information for a given host/port.
#
def check_status(host, port, id):
    global pdict
    now = time.time()
    try:
        (last, pingrc) = pdict[host]
        havestat = now - last > 120
    except:
        havestat = False
    if not havestat:
        # Ping the host to see if it is up!
        pingrc = os.system("ping -c 1 -w 1 -W 0.002 %s >/dev/null 2>/dev/null" % host)
        pdict[host] = (now, pingrc)
    if pingrc != 0:
        return {'status'      : STATUS_DOWN,
                'rid'         : id,
                'pid'         : "-",
                'autorestart' : False,
                'rdir'        : "/tmp" }
    try:
        tn = telnetlib.Telnet(host, port, 1)
    except:
        return {'status'      : STATUS_NOCONNECT,
                'rid'         : id,
                'pid'         : "-",
                'autorestart' : False,
                'autorestartmode' : False,
                'rdir'        : "/tmp" }
    result = readLogPortBanner(tn)
    tn.close()
    return result

def openTelnet(host, port):
    connected = False
    telnetCount = 0
    while (not connected) and (telnetCount < 2):
        telnetCount += 1
        try:
            tn = telnetlib.Telnet(host, port, 1)
        except:
            time.sleep(0.25)
        else:
            connected = True
    if connected:
        return tn
    else:
        return None

def fixTelnetShell(host, port):
    tn = openTelnet(host, port)
    tn.write("\x15\x0d");
    statd = tn.expect([MSG_PROMPT_OLD], 2)
    tn.write("export PS1='> '\n");
    statd = tn.read_until(MSG_PROMPT, 2)
    tn.close()

#
# See if the procServ is in an acceptible state: on, off, or oneshot.
# If not, send ^T until it is.
#
# Return True if we're in a good state, False if there was some problem along the way.
#    
def checkTelnetMode(host, port, onOK=True, offOK=False, oneshotOK=False, verbose=False):
    while True:
        tn = openTelnet(host, port)
        if not tn:
            print 'ERROR: checkTelnetMode() telnet to %s port %s failed' % (host, port)
            return False
        try:
            statd = readLogPortBanner(tn)
        except:
            print 'ERROR: checkTelnetMode() failed to readLogPortBanner on %s port %s' % (host, port)
            tn.close()
            return False
        try:
            if verbose:
                print 'checkTelnetMode: %s port %s status is %s' % (host, port, statd['status'])
            if statd['autorestart']:
                if onOK:
                    tn.close()
                    return True
            elif statd['autooneshot']:
                if oneshotOK:
                    tn.close()
                    return True
            else:
                if offOK:
                    tn.close()
                    return True
            if verbose:
                print 'checkTelnetMode: turning off autorestart on %s port %s' % (host, port)
            # send ^T to toggle off auto restart.
            tn.write("\x14")
            # wait for toggled message
            if statd['autorestartmode']:
                r = tn.read_until(MSG_AUTORESTART_MODE_CHANGE, 1)
            else:
                r = tn.read_until(MSG_AUTORESTART_CHANGE, 1)
            time.sleep(0.25)
            tn.close()
        except:
            print 'ERROR: checkTelnetMode() failed to turn off autorestart on %s port %s' % (host, port)
            tn.close()
            return False

def killProc(host, port, verbose=False):
    print "Killing IOC on host %s, port %s..." % (host, port)
    if not checkTelnetMode(host, port, onOK=False, offOK=True, oneshotOK=False, verbose=verbose):
        return
    # Now, reconnect to actually kill it!
    tn = openTelnet(host, port)
    if tn:
        statd = readLogPortBanner(tn)
        if statd['status'] == STATUS_RUNNING:
            try:
                if verbose:
                    print 'killProc: Sending Ctrl-X to %s port %s' % (host, port)
                # send ^X to kill child process
                tn.write("\x18");
                # wait for killed message
                r = tn.read_until(MSG_KILLED, 1)
                time.sleep(0.25)
            except:
                print 'ERROR: killProc() failed to kill process on %s port %s' % (host, port)
                tn.close()
                return
        try:
            if verbose:
                print 'killProc: Sending Ctrl-Q to %s port %s' % (host, port)
            # send ^Q to kill procServ
            tn.write("\x11");
        except:
            print 'ERROR: killProc() failed to kill procServ on %s port %s' % (host, port)
            tn.close()
            return
        tn.close()
    else:
        print 'ERROR: killProc() telnet to %s port %s failed' % (host, port)

def restartProc(host, port):
    print "Restarting IOC on host %s, port %s..." % (host, port)
    # Can't deal with ONESHOT mode!
    if not checkTelnetMode(host, port, onOK=True, offOK=True, oneshotOK=False):
        return
    tn = openTelnet(host, port)
    started = False
    if tn:
        statd = readLogPortBanner(tn)
        if statd['status'] == STATUS_RUNNING:
            try:
                # send ^X to kill child process
                tn.write("\x18");

                # wait for killed message
                r = tn.read_until(MSG_KILLED, 1)
                time.sleep(0.25)
            except:
                pass # What do we do now?!?

        if not statd['autorestart']:
            # send ^R to restart child process
            tn.write("\x12");

        # wait for restart message
        r = tn.read_until(MSG_RESTART, 1)
        if not r.count(MSG_RESTART):
            print 'ERROR: no restart message... '
        else:
            started = True

        tn.close()
    else:
        print 'ERROR: restartProc() telnet to %s port %s failed' % (host, port)

    return started

def startProc(cfg, entry, local=False):
    # Hopefully, we can dispose of this soon!
    platform = '1'
    if cfg == 'xrt':
        platform = '2'
    if cfg == 'las':
        platform = '3'

    if local:
        host = "localhost"
    else:
        host  = entry['host']
    port  = entry['port']
    name  = entry['id']
    try:
        cmd = entry['cmd']
    except:
        cmd = "./st.cmd"
    try:
        if 'u' in entry['flags']:
            # The Old Regime: add u to flags to append the ID to the command.
            cmd += ' -u ' + name
    except:
        pass
        
    sr = os.getenv("SCRIPTROOT")
    if sr == None:
        sr = STARTUP_DIR % cfg
    elif sr[-1] != '/':
        sr += '/'
    cmd = "%sstartProc %s %d %s %s" % (sr, name, port, cfg, cmd)
    log = LOGBASE % name
    ctrlport = BASEPORT + 2 * (int(platform) - 1)
    print "Starting %s on port %s of host %s, platform %s..." % (name, port, host, platform)
    cmd = '%s --logfile %s --name %s --allow --coresize 0 --savelog %d %s' % \
          (PROCSERV_EXE, log, name, port, cmd)
    try:
        tn = telnetlib.Telnet(host, ctrlport, 1)
    except:
        print "ERROR: telnet to procmgr (%s port %d) failed" % (host, ctrlport)
        print ">>> Please start the procServ process on host %s!" % host
    else:
        # telnet succeeded

        # send ^U followed by carriage return to safely reach the prompt
        tn.write("\x15\x0d");

        # wait for prompt (procServ)
        statd = tn.read_until(MSG_PROMPT, 2)
        if not string.count(statd, MSG_PROMPT):
            print 'ERROR: no prompt at %s port %s' % (host, ctrlport)
            
        # send command
        tn.write('%s\n' % cmd);

        # wait for prompt
        statd = tn.read_until(MSG_PROMPT, 2)
        if not string.count(statd, MSG_PROMPT):
            print 'ERR: no prompt at %s port %s' % (host, ctrlport)

        # close telnet connection
        tn.close()

######################################################################
#
# Configuration/Status Utilities
#

#
# Reads a hutch configuration file and returns a tuple:
#     (filetime, configlist, hostlist, varlist).
#
# cfg can be a path to config file or name of a hutch
#
def readConfig(cfg, time=None, silent=False, do_os=False):
    config = {'procmgr_config': None, 'hosts': None, 'dir':'dir',
              'id':'id', 'cmd':'cmd', 'flags':'flags', 'port':'port', 'host':'host',
              'disable':'disable', 'history':'history', 'delay':'delay', 'alias':'alias', 'hard':'hard' }
    vars = set(config.keys())
    if len(cfg.split('/')) > 1: # cfg is file path
        cfgfn = cfg
    else: # cfg is name of hutch
        cfgfn = CONFIG_FILE % cfg
    try:
        f = open(cfgfn, "r")
    except Exception, msg:
        if not silent:
            print "readConfig file error: %s" % str(msg)
        return None

    try:
        mtime = os.stat(cfgfn).st_mtime
        if time != None and time == mtime:
            res = None
        else:
            execfile(cfgfn, {}, config)
            newvars = set(config.keys()).difference(vars)
            vdict = {}
            for v in newvars:
                vdict[v] = config[v]
            res = (mtime, config['procmgr_config'], config['hosts'], vdict)
    except Exception, msg:
        if not silent:
            print "readConfig error: %s" % str(msg)
        res = None
    f.close()
    if res == None:
        return None
    for l in res[1]:
        # Add defaults!
        if not 'disable' in l.keys():
            l['disable'] = False
        if not 'hard' in l.keys():
            l['hard'] = False
        if not 'history' in l.keys():
            l['history'] = []
        if not 'alias' in l.keys():
            l['alias'] = ""
        l['cfgstat'] = CONFIG_NORMAL
        if l['hard']:
            l['base'] = getBaseName(l['id'])
            l['dir'] = getHardIOCDir(l['id'], silent)
            l['host'] = l['id']
            l['port'] = -1
            l['rhost'] = l['id']
            l['rport'] = -1
            l['rdir'] = l['dir']
            l['newstyle'] = False
            l['pdir'] = ""
        else:
            l['rid'] = l['id']
            l['rdir'] = l['dir']
            l['rhost'] = l['host']
            l['rport'] = l['port']
            l['newstyle'] = False
            l['pdir'] = findParent(l['id'], l['dir'])
    if do_os:
        global hosttype
        hosttype = {}
        for fn in config['hosts']:
            try:
                hosttype[fn] = open("%s/%s" % (HOST_DIR, fn)).readlines()[0].strip()
            except:
                pass
    return res

#
# Writes a hutch configuration file, dealing with possible changes ("new*" fields).
#
def writeConfig(hutch, hostlist, cfglist, vars, f=None):
    if f == None:
        raise Exception("Must specify output file!")
    f.truncate()
    for (k, v) in vars.items():
        try:
            if not v in ["True", "False"]:
                n = int(v)
            f.write("%s = %s\n" % (k, str(v)))
        except:
            f.write('%s = "%s"\n' % (k, str(v)))
    f.write("\nhosts = [\n")
    for h in hostlist:
        f.write("   '%s',\n" % h)
    f.write("]\n\n");
    f.write("procmgr_config = [\n")
    cl = sorted(cfglist, key=lambda x: x['id'])
    for entry in cl:
        if entry['cfgstat'] == CONFIG_DELETED:
            continue
        try:
            id = entry['newid'].strip()  # Bah.  Sometimes we add a space so this becomes blue!
        except:
            id = entry['id']
        try:
            alias = entry['newalias']
        except:
            alias = entry['alias']
        if entry['hard']:
            if alias != "":
                extra = ", alias: '%s'" % alias
            else:
                extra = ""
            f.write(" {id:'%s', hard: True%s},\n" % (id, extra))
            continue
        try:
            host = entry['newhost']
        except:
            host = entry['host']
        try:
            port = entry['newport']
        except:
            port = entry['port']
        try:
            dir = entry['newdir']
        except:
            dir = entry['dir']
        extra = ""
        try:
            disable = entry['newdisable']
        except:
            disable = entry['disable']
        if disable:
            extra += ", disable: True"
        if alias != "":
            extra += ", alias: '%s'" % alias
        try:
            h = entry['history']
            if h != []:
                extra += ",\n  history: [" + ", ".join(["'"+l+"'" for l in h]) + "]"
        except:
            pass
        try:
            extra += ", delay: %d" % entry['delay']
        except:
            pass
        try:
            extra += ", cmd: '%s'" % entry['cmd']
        except:
            pass
        f.write(" {id:'%s', host: '%s', port: %s, dir: '%s'%s},\n" %
                (id, host, port, dir, extra))
    f.write("]\n");
    f.close()
    os.chmod(f.name, stat.S_IRUSR | stat.S_IRGRP | stat.S_IWUSR | stat.S_IWGRP | stat.S_IROTH)

#
# Install an existing file as the hutch configuration file.
#
# Much simpler, and this should be atomic!
#
def installConfig(hutch, file, fd=None):
    os.rename(file, CONFIG_FILE % hutch)

#
# Reads the status directory for a hutch, looking for changes.  The newer
# parameter is a routine that is called as newer(iocname, mtime) which
# returns True if the file has been modified since last read.  In this
# case, newer should also remember mtime as the last read time.
#
# Returns a list of dictionaries containing the new information.
#
def readStatusDir(cfg, readfile=lambda fn, f: open(fn).readlines()):
    files = os.listdir(STATUS_DIR % cfg)
    d = {}
    for f in files:
        fn = (STATUS_DIR % cfg) + "/" + f
        mtime = os.stat(fn).st_mtime
        l = readfile(fn, f)
        if l != []:
            stat = l[0].strip().split()                     # PID HOST PORT DIRECTORY
            if len(stat) == 4:
                try:
                    if d[(stat[1], int(stat[2]))]['mtime'] < mtime:
                        # Duplicate, but newer, so replace!
                        try:
                            print "Deleting obsolete %s in favor of %s" % (d[(stat[1], int(stat[2]))]['rid'], f)
                            os.unlink((STATUS_DIR % cfg) + "/" + d[(stat[1], int(stat[2]))]['rid'])
                        except:
                            print "Error while trying to delete file %s" % (STATUS_DIR % cfg) + "/" + d[(stat[1], int(stat[2]))]['rid'] + "!"
                        # Leave this here to make sure file is updated.
                        raise Exception( "Need to update cfg file." )
                    else:
                        # Duplicate, but older, so ignore!
                        try:
                            print "Deleting obsolete %s in favor of %s" % (f, d[(stat[1], int(stat[2]))]['rid'])
                            os.unlink(fn)
                        except:
                            print "Error while trying to delete file %s!" % fn
                except:
                    try:
                        d[(stat[1], int(stat[2]))] = {'rid' : f,
                                                  'pid': stat[0],
                                                  'rhost': stat[1],
                                                  'rport': int(stat[2]),
                                                  'rdir': stat[3],
                                                  'newstyle' : True,
                                                  'mtime': mtime,
                                                  'hard': False}
                    except:
                        print "Status dir failure!"
                        print f
                        print stat
            else:
                try:
                    os.unlink(fn)
                except:
                    print "Error while trying to delete file %s!" % fn
    return d.values()

#
# Apply the current configuration.
#
def applyConfig(cfg, verify=None, ioc=None):
  result = readConfig(cfg)
  if result == None:
      print "Cannot read configuration for %s!" % cfg
      return -1
  (mtime, cfglist, hostlist, vdict) = result

  config = {}
  for l in cfglist:
    if ioc == None or ioc == l['id']:
        config[l['id']] = l

  runninglist = readStatusDir(cfg)

  current = {}
  notrunning = {}
  for l in runninglist:
      if ioc == None or ioc == l['rid']:
          result = check_status(l['rhost'], l['rport'], l['rid'])
          rdir = l['rdir']
          l.update(result);
          if l['rdir'] == '/tmp':
              l['rdir'] = rdir
          else:
              l['newstyle'] = False
          if result['status'] == STATUS_RUNNING:
              current[l['rid']] = l
          else:
              notrunning[l['rid']] = l

  running = current.keys()
  wanted  = config.keys()

  # Double-check for old-style IOCs that don't have an indicator file!
  for l in wanted:
      if not l in running:
          result = check_status(config[l]['host'], int(config[l]['port']), config[l]['id'])
          if result['status'] == STATUS_RUNNING:
              result.update({'rhost': config[l]['host'],
                             'rport': config[l]['port'],
                             'newstyle': False})
              current[l] = result

  running = current.keys()
  neww = []
  notw = []
  for l in wanted:
      try:
          if not config[l]['hard']:
              if not config[l]['newdisable']:
                  neww.append(l)
              else:
                  notw.append(l)
      except:
          if not config[l]['hard']:
              if not config[l]['disable']:
                  neww.append(l)
              else:
                  notw.append(l)
  wanted = neww

  #
  # Note the hard IOC handling... we don't want to start them, but they 
  # don't have entries in the running directory anyway so we don't think
  # we need to!
  #

  # Camera recorders always seem to be in the wrong directory, so cheat!
  for l in cfglist:
      if l['dir'] == CAMRECORDER:
          try:
              current[l['id']]['rdir'] = CAMRECORDER
          except:
              pass

  #
  # Now, we need to make three lists: kill, restart, and start.
  #
  
  # Kill anyone who we don't want, or is running on the wrong host or port, or is oldstyle and needs
  # an upgrade.
  kill_list    = [l for l in running if not l in wanted or
                    current[l]['rhost'] != config[l]['host'] or
                    current[l]['rport'] != config[l]['port'] or
                    (	(not current[l]['newstyle']) and
                        current[l]['rdir'] != config[l]['dir']	)]

  #
  # Now there is a problem if an IOC is bad and repeatedly crashing.  The running state may
  # not be accurate, as it is oscillating between RUNNING and SHUTDOWN.  If it's enabled, not
  # much we can do but let it spin... but if it's disabled, we need to be certain to kill it.
  # 
  # We don't want to just add *everything* though... this makes the screen too verbose!  So, we
  # compromise... if the status file is *new*, then maybe it's crashing and needs to be killed
  # again.  If it's old though, let's assume that it's dead and we can leave it alone...
  #
  # If it's dead, it might not *have* a status file, hence the try.
  #
  now = time.time()
  for l in notw:
      try:
          if not l in running and now - notrunning[l]['mtime'] < 600:
              kill_list.append(l)
      except:
          pass
                  
  # Start anyone who wasn't running, or was running on the wrong host or port, or is oldstyle and needs
  # an upgrade.
  start_list   = [l for l in wanted if not l in running or current[l]['rhost'] != config[l]['host'] or
                  current[l]['rport'] != config[l]['port'] or
                  (not current[l]['newstyle'] and
                   current[l]['rdir'] != config[l]['dir'])]

  # Anyone running the wrong version, newstyle, on the right host and port just needs a restart.
  restart_list = [l for l in wanted if l in running and current[l]['rhost'] == config[l]['host'] and
                  current[l]['newstyle'] and
                  current[l]['rport'] == config[l]['port'] and
                  current[l]['rdir'] != config[l]['dir']]

  if verify != None:
      (kill_list, start_list, restart_list) = verify(current, config, kill_list, start_list, restart_list)
  
  for l in kill_list:
    try:
        killProc(current[l]['rhost'], int(current[l]['rport']))
    except:
        killProc(config[l]['host'], int(config[l]['port']))
    try:
        # This is dead, so get rid of the status file!
        os.unlink((STATUS_DIR % cfg) + "/" + l)
    except:
        print "Error while trying to delete file %s" % (STATUS_DIR % cfg) + "/" + l + "!"

  for l in start_list:
    startProc(cfg, config[l])

  for l in restart_list:
    restartProc(current[l]['rhost'], int(current[l]['rport']))

  time.sleep(1)
  return 0

######################################################################
#
# Miscellaneous utilities
#

def check_auth(user, hutch):
    lines = open(AUTH_FILE % hutch).readlines()
    lines = [l.strip() for l in lines]
    for l in lines:
        if l == user:
            return True
    return False

# checks if ioc is marked as toggleable between defined versions of IOCs
# schema will be ioc_name:permittedversion1,permittedversion2,etc
def check_special(req_ioc, req_hutch, req_version = "no_upgrade"):
    with open(SPECIAL_FILE % req_hutch) as fp:
        lines = fp.readlines()
        lines = [l.strip()for l in lines]
        for entry in lines:
            ioc_vers_list = entry.split(":")
            ioc_name = ioc_vers_list[0]

            #check that the ioc is in permissioned list before moving forward
            if (ioc_name != req_ioc):
                continue # not the ioc we are looking for
            
            if req_version == "no_upgrade": 
                return True # NOTE(josh): this does assume that the only place check_special is invoked without overloading the default argument is in the raw enable / disable case

            # if there is information after the colon, parse it
            if len(ioc_vers_list) > 1:
                perm_version = ioc_vers_list[-1].split(",")
                for vers in perm_version:
                    if vers == req_version:
                      return True # return True if the requested version is in the list
            # if the entry has no colon, assumed just ioc name

        return False

def check_ssh(user, hutch):
    try:
        lines = open(NOSSH_FILE % hutch).readlines()
    except:
        return True
    lines = [l.strip() for l in lines]
    for l in lines:
        if l == user:
            return False
    return True

eq      = re.compile("^[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*(.*?)[ \t]*$")
eqq     = re.compile('^[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*"([^"]*)"[ \t]*$')
eqqq    = re.compile("^[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*'([^']*)'[ \t]*$")
sp      = re.compile("^[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]+(.+?)[ \t]*$")
spq     = re.compile('^[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]+"([^"]*)"[ \t]*$')
spqq    = re.compile("^[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]+'([^']*)'[ \t]*$")

def readAll(fn):
    if fn[0] != '/':
        fn = EPICS_SITE_TOP + fn
    try:
        return open(fn).readlines()
    except:
        return []

def findParent(ioc, dir):
    fn = dir + "/" + ioc + ".cfg"
    lines = readAll(fn)
    if lines == []:
        fn = dir + "/children/" + ioc + ".cfg"
        lines = readAll(fn)
    if lines == []:
        return ""
    lines.reverse()
    for l in lines:
        m = eqqq.search(l)
        if m == None:
            m = eqq.search(l)
            if m == None:
                m = eq.search(l)
                if m == None:
                    m = spqq.search(l)
                    if m == None:
                        m = spq.search(l)
                        if m == None:
                            m = sp.search(l)
        if m != None:
            var = m.group(1)
            val = m.group(2)
            if var == "RELEASE":
                val = val.replace("$$PATH/", dir + "/" + ioc + ".cfg").replace("$$UP(PATH)", dir)
                return fixdir(val, ioc)
    return ""

def read_until(fd, expr):
    exp = re.compile(expr, re.S)
    data = ""
    while True:
        v = os.read(fd, 1024)
        #print "<<< %s" % v.encode("string-escape")
        data += v
        m = exp.search(data)
        if m != None:
            return m

def flush_input(fd):
    fcntl.fcntl(fd, fcntl.F_SETFL, os.O_NONBLOCK) 
    while True:
        try:
            data = os.read(fd, 1024)
        except:
            fcntl.fcntl(fd, fcntl.F_SETFL, 0) 
            return

def do_write(fd, msg):
    os.write(fd, msg)

def commit_config(hutch, comment, fd):
    config = CONFIG_FILE % hutch
    flush_input(fd)
    do_write(fd, "cat >" + config + ".comment <<EOFEOFEOF\n");
    do_write(fd, comment)
    do_write(fd, "\nEOFEOFEOF\n");
    read_until(fd, "> ")
    # Sigh.  This does nothing but read the file, which makes NFS get the latest.
    do_write(fd, "set xx=`mktemp`\n")
    read_until(fd, "> ")
    do_write(fd, "cp " + config + " $xx\n")
    read_until(fd, "> ")
    do_write(fd, "rm -f $xx\n")
    read_until(fd, "> ")
    do_write(fd, "umask 2; git commit -F " + config + ".comment " + config + "\n")
    read_until(fd, "> ")
    do_write(fd, "rm -f " + config + ".comment\n")
    read_until(fd, "> ")

# Find siocs matching input arguments
# May want to extend this to regular expressions at some point
# eg: find_iocs(host='ioc-xcs-mot1') or find_iocs(id='ioc-xcs-imb3')
# Returns list of tuples of form:
#  ['config-file', {ioc config dict}]
def find_iocs(**kwargs):
    cfgs = glob.glob(CONFIG_FILE % '*')
    configs = list()
    for cfg in cfgs:
        config = readConfig(cfg)[1]
        for ioc in config:
            for k in kwargs.items():
                if ioc.get(k[0])!=k[1]:
                    break
            else:
                configs.append([cfg,ioc])
                pass
    return configs

def netconfig(host):
    try:
        env = copy.deepcopy(os.environ)
        del env['LD_LIBRARY_PATH']
        p = subprocess.Popen([NETCONFIG, "view", host], env=env, stdout=subprocess.PIPE)
        r = [l.strip().split(": ") for l in p.communicate()[0].split('\n')]
        d = {}
        for l in r:
            if len(l) == 2:
                d[l[0].lower()] = l[1]
        return d
    except:
        return {}

def rebootServer(host):
    return os.system("/reg/common/tools/bin/psipmi %s power cycle" % host) == 0

def getHardIOCDir(host, silent=False):
    dir = "Unknown"
    try:
        lines = [l.strip() for l in open(HIOC_STARTUP % host).readlines()]
    except:
        if not silent:
            print "Error while trying to read HIOC startup file for %s!" % host
        return "Unknown"
    for l in lines:
        if l[:5] == "chdir":
            try:
                dir = "ioc/" + re.search('\"/iocs/(.*)/iocBoot', l).group(1)
            except:
                pass # Having dir show "Unknown" should suffice.
    return dir

def restartHIOC(host):
    """ Attempts to console into a HIOC and reboot it via the shell. """
    try:
        for l in netconfig(host)['console port dn'].split(','):
            if l[:7] == 'cn=port':
                port = 2000 + int(l[7:])
            if l[:7] == 'cn=digi':
                host = l[3:]
    except:
        print "Error parsing netconfig for HIOC %s console info!" % host
        return False
    try:
        tn = telnetlib.Telnet(host, port, 1)
    except:
        print "Error making telnet connection to HIOC %s!" % host
        return False
    tn.write("\x0a")
    tn.read_until("> ", 2)
    tn.write("exit\x0a")
    tn.read_until("> ", 2)
    tn.write("rtemsReboot()\x0a")
    tn.close()
    return True

def rebootHIOC(host):
    """ Attempts to power cycle a HIOC via the PDU entry in netconfig. """
    try:
        env = copy.deepcopy(os.environ)
        del env['LD_LIBRARY_PATH']
        p = subprocess.Popen([HIOC_POWER, host, 'cycle'], env=env, stdout=subprocess.PIPE)
        print p.communicate()[0]
        return True
    except:
        print "Error while trying to power cycle HIOC %s!" % host
        return False

def findPV(regexp, ioc):
    try:
        lines = [l.split(",")[0] for l in open(PVFILE % ioc).readlines()]
    except:
        return []
    return filter(regexp.search, lines)

def getHutchList():
    try:
        p = subprocess.Popen(["csh", "-c", "cd %s; echo */iocmanager.cfg" % CONFIG_DIR], stdout=subprocess.PIPE)
        return [l.split('/')[0] for l in p.communicate()[0].strip().split()]
    except:
        return []

#
# Does this configuration list look valid?  Currently, just check if there
# is a duplicate host/port combination.
#
def validateConfig(cl):
    for i in range(len(cl)):
        try:
            h = cl[i]['newhost']
        except:
            h = cl[i]['host']
        try:
            p = cl[i]['newport']
        except:
            p = cl[i]['port']
        for j in range(i+1, len(cl)):
            try:
                h2 = cl[j]['newhost']
            except:
                h2 = cl[j]['host']
            try:
                p2 = cl[j]['newport']
            except:
                p2 = cl[j]['port']
            if (h == h2 and p == p2):
                return False
    #
    # Anything else we want to check here?!?
    #
    return True

#
# Will we find an st.cmd file along this path?
#
def validateDir(dir, ioc):
    if dir[0] != '/':
        dir = EPICS_SITE_TOP + dir
    for p in stpaths:
        if os.path.exists(p % (dir, ioc)):
            return True
    if os.path.exists(dir + "/st.cmd"):
        return True
    return False

