import telnetlib, string, datetime, os, time, fcntl
from re import search

CAMRECORDER = "/reg/g/pcds/controls/camrecord"
STARTUP_DIR = "/reg/g/pcds/controls/ioc/"
CONFIG_DIR  = STARTUP_DIR + "CONFIG/"
STATUS_DIR  = STARTUP_DIR + "STATUS/"
LOGBASE     = "/reg/d/iocData/%s/iocInfo/ioc.log*"
LOGFILE     = "/reg/d/iocData/%s/iocInfo/ioc.log_" + datetime.datetime.today().strftime("%m%d%Y_%H%M%S")
PVFILE      = "/reg/d/iocData/%s/iocInfo/IOC.pvlist"
BASEPORT    = 29000

STATUS_NOCONNECT = "NOCONNECT"
STATUS_RUNNING = "RUNNING"
STATUS_SHUTDOWN = "SHUTDOWN"
STATUS_ERROR = "ERROR"

# messages expected from procServ
MSG_BANNER_END = "server started at"
MSG_ISSHUTDOWN = "is SHUT DOWN"
MSG_ISSHUTTING = "is shutting down"
MSG_KILLED     = "process was killed"
MSG_RESTART = "new child"
MSG_PROMPT = "\x0d\x0a> "
MSG_SPAWN = "procServ: spawning daemon"
MSG_AUTORESTART_IS_ON = "auto restart is ON"
MSG_AUTORESTART_TO_ON = "auto restart to ON"
MSG_AUTORESTART_TO_OFF = "auto restart to OFF"

EPICS_TOP      = "/reg/g/pcds/package/epics/"
EPICS_SITE_TOP = "/reg/g/pcds/package/epics/3.14/"

def fixdir(dir, id):
    if dir[0:len(EPICS_SITE_TOP)] == EPICS_SITE_TOP:
        dir = dir[len(EPICS_SITE_TOP):]
    if dir[0:len(EPICS_TOP)] == EPICS_TOP:
        dir = "../" + dir[len(EPICS_TOP):]
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

def readLogPortBanner(tn):
    response = tn.read_until(MSG_BANNER_END, 1)
    if not string.count(response, MSG_BANNER_END):
        return (STATUS_ERROR, "-", "-", "-", False)
    if search('SHUT DOWN', response):
        tmpstatus = STATUS_SHUTDOWN
        pid = "-"
    else:
        tmpstatus = STATUS_RUNNING
        pid = search('@@@ Child \"(.*)\" PID: ([0-9]*)', response).group(2)
    getid = search('@@@ Child \"(.*)\" start', response).group(1)
    ppid  = search('@@@ procServ server PID: ([0-9]*)', response).group(1)
    dir   = search('@@@ Server startup directory: (.*)', response).group(1)
    if dir[-1] == '\r':
        dir = dir[:-1]
    if search(MSG_AUTORESTART_IS_ON, response):
        arst = True
    else:
        arst = False
    return (tmpstatus, pid, ppid, getid, arst, fixdir(dir, getid))

#
# Returns (status, PID, SERVER_PID, ID, dir).
#
def check_status(host, port):
    try:
        tn = telnetlib.Telnet(host, port, 1)
    except:
        return (STATUS_NOCONNECT, "-", "-", "-", False, "/tmp")
    result = readLogPortBanner(tn)
    tn.close()
    return result

def readConfig(cfg):
    platform = '1'
    if cfg == 'fee':
        platform = '2'
    if cfg == 'las':
        platform = '3'
    config = {'platform': platform, 'procmgr_config': None, 'hosts': None, 'dir':'dir',
              'id':'id', 'cmd':'cmd', 'flags':'flags', 'port':'port', 'host':'host',
              'rtprio':'rtprio', 'env':'env', 'procmgr_macro': {}, 'disable':'disable',
              'history':'history' }
    f = open(CONFIG_DIR + cfg, "r")
    fcntl.lockf(f, fcntl.LOCK_SH)    # Wait for the lock!!!!
    try:
        execfile(CONFIG_DIR + cfg, {}, config)
        # Then config['platform'] and config['procmgr_config'] are set to something reasonable!
        res = (config['platform'], config['procmgr_config'], config['hosts'])
    except:
        res = None
    fcntl.lockf(f, fcntl.LOCK_UN)
    f.close()
    return res

def killProc(host, port):
    print "Killing IOC on host %s, port %s..." % (host, port)
    # open a connection to the procServ control port
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
        response = readLogPortBanner(tn)

        if response[0] == STATUS_RUNNING:
            try:
                if response[4]:
                    # send ^T to toggle off auto restart.
                    tn.write("\x14")
                    # wait for toggled message
                    response = tn.read_until(MSG_AUTORESTART_TO_OFF, 1)
                    time.sleep(0.25)
                    
                # send ^X to kill child process
                tn.write("\x18");
                # wait for killed message
                response = tn.read_until(MSG_KILLED, 1)
                time.sleep(0.25)
                
                # send ^Q to kill procServ
                tn.write("\x11");
            except:
                pass # What to do???

        # close telnet connection
        tn.close()
    else:
        print 'ERROR: killProc() telnet to %s port %s failed' % (host, port)

def restartProc(host, port):
    print "Restarting IOC on host %s, port %s..." % (host, port)
    # open a connection to the procServ control port
    started = False
    connected = False
    telnetCount = 0
    while (not connected) and (telnetCount < 2):
        telnetCount += 1
        try:
            tn = telnetlib.Telnet(host, port, 1)
        except:
            time.sleep(.25)
        else:
            connected = True

    if connected:
        response = readLogPortBanner(tn)
        arst = response[4]
        if response[0] == STATUS_RUNNING:
            try:
                # send ^X to kill child process
                tn.write("\x18");

                # wait for killed message
                response = tn.read_until(MSG_KILLED, 1)
                time.sleep(0.25)
            except:
                pass # What do we do now?!?

        if not arst:
            # send ^R to restart child process
            tn.write("\x12");

        # wait for restart message
        response = tn.read_until(MSG_RESTART, 1)
        if not string.count(response, MSG_RESTART):
            print 'ERROR: no restart message... '
        else:
            started = True

        # close telnet connection
        tn.close()
    else:
        print 'ERROR: restartProc() telnet to %s port %s failed' % (host, port)

    return started

def startProc(platform, cfg, entry):
    host  = entry['host']
    port  = entry['port']
    name  = entry['id']
    try:
        cmd = entry['cmd']
    except:
        # The New Regime: no cmd --> invoke startProc.
        cmd = STARTUP_DIR + "startProc " + name + " " + port + " " + cfg
    try:
        if 'u' in entry['flags']:
            # The Old Regime: supply a command, and flag it with 'u' to append the ID to the command.
            cmd += ' -u ' + name
    except:
        pass
    log = LOGFILE % name
    ctrlport = BASEPORT + 100 * int(platform)
    print "Starting %s on port %s of host %s, platform %s..." % (name, port, host, platform)
    cmd = '/reg/g/pcds/package/procServ-2.5.1/procServ --logfile %s --name %s --allow --coresize 0 %s %s' % \
          (log, name, port, cmd)
    try:
        tn = telnetlib.Telnet(host, BASEPORT + 100 * int(platform), 1)
    except:
        print "ERROR: telnet to procmgr (%s port %d) failed" % (host, ctrlport)
        print ">>> Please start the procServ process on host %s!" % host
    else:
        # telnet succeeded

        # send ^U followed by carriage return to safely reach the prompt
        tn.write("\x15\x0d");

        # wait for prompt (procServ)
        response = tn.read_until(MSG_PROMPT, 2)
        if not string.count(response, MSG_PROMPT):
            print 'ERROR: no prompt at %s port %s' % (host, ctrlport)
            
        # send command
        tn.write('%s\n' % cmd);

        # wait for prompt
        response = tn.read_until(MSG_PROMPT, 2)
        if not string.count(response, MSG_PROMPT):
            print 'ERR: no prompt at %s port %s' % (host, ctrlport)

        # close telnet connection
        tn.close()

def readStatus(cfg):
    files = os.listdir(STATUS_DIR + cfg)
    d = {}
    for f in files:
        try:
            l = open(STATUS_DIR + cfg + "/" + f).readlines()
        except:
            continue
        stat = l[0].strip().split()                     # PID HOST PORT DIRECTORY
        result = check_status(stat[1], int(stat[2]))    # STATUS PID SERVERPID ID
        # What if PID or ID don't match?!?
        if result[0] == STATUS_NOCONNECT or result[0] == STATUS_ERROR:
            os.unlink(STATUS_DIR + cfg + "/" + f)
        else:
            d[f] = {'pid': stat[0], 'host': stat[1], 'port': stat[2],
                    'dir': stat[3], 'status': result[0],
                    'ppid': result[2], 'newstyle': True}
    return d

def getState(cfg):
  result = readConfig(cfg)
  if result == None:
      print "Cannot read configuration for %s!" % cfg
      return -1
  (platform, cfglist, hostlist) = result

  config = {}
  for l in cfglist:
    # Make sure that disable is defined!
    try:
        v = l['disable']
    except:
        l['disable'] = False
    config[l['id']] = l

  current = readStatus(cfg)
  running = current.keys()
  wanted  = config.keys()

  # Double-check for old-style IOCs that don't have an indicator file!
  for l in wanted:
      if not l in running:
          result = check_status(config[l]['host'], int(config[l]['port']))
          if result[0] == STATUS_RUNNING:
              current[l] = {'pid': result[1], 'host': config[l]['host'],
                            'port': config[l]['port'], 'dir': result[5],
                            'status': result[0], 'ppid': result[2],
                            'newstyle': False}

  # Camera recorders always seem to be in the wrong directory, so cheat!
  for l in cfglist:
      if l['dir'] == CAMRECORDER:
          try:
              current[l['id']]['dir'] = CAMRECORDER
          except:
              pass
  running = current.keys()

  # If an IOC is disabled, we don't really want it!
  wanted = [l for l in wanted if not config[l]['disable']]
  
  return (config, current, running, wanted, hostlist, platform)

def getAllStatus(cfg):
  (config, current, running, wanted, hostlist, platform) = getState(cfg)

  # OK.  Let's make this into a list of tuples: (id, config, current).
  slist = []
  klist = set(current.keys())
  klist = klist.union(set(wanted))
  for key in klist:
      try:
          cfgentry = config[key]
      except:
          cfgentry = None
      try:
          curentry = current[key]
      except:
          curentry = None
      slist.append((key, cfgentry, curentry))
  if hostlist == None:
      hostlist = []
      for (key, cfgentry, curentry) in slist:
          if cfgentry != None:
              hostlist.append(cfgentry['host'])
          else:
              hostlist.append(curentry['host'])
      hostlist = list(set(hostlist))
      hostlist.sort()
  return (slist, hostlist)

def applyConfig(cfg):
  (config, current, running, wanted, hostlist, platform) = getState(cfg)

  #
  # Now, we need to make three lists: kill, restart, and start.
  #
  
  # Kill anyone who we don't want, or is running on the wrong host or port, or is oldstyle and needs
  # an upgrade.
  kill_list    = [l for l in running if not l in wanted or current[l]['host'] != config[l]['host'] or
                  current[l]['port'] != config[l]['port'] or
                  (not current[l]['newstyle'] and current[l]['dir'] != config[l]['dir'])]
                  
  # Start anyone who wasn't running, or was running on the wrong host or port, or is oldstyle and needs
  # an upgrade.
  start_list   = [l for l in wanted if not l in running or current[l]['host'] != config[l]['host'] or
                  current[l]['port'] != config[l]['port'] or
                  (not current[l]['newstyle'] and current[l]['dir'] != config[l]['dir'])]

  # Anyone running the wrong version, newstyle, on the right host and port just needs a restart.
  restart_list = [l for l in wanted if l in running and current[l]['host'] == config[l]['host'] and
                  current[l]['newstyle'] and current[l]['port'] == config[l]['port'] and
                  current[l]['dir'] != config[l]['dir']]
  
  for l in kill_list:
    killProc(current[l]['host'], int(current[l]['port']))
    try:
        # This is dead, so get rid of the status file!
        os.unlink(STATUS_DIR + cfg + "/" + l)
    except:
        pass


  for l in start_list:
    startProc(platform, cfg, config[l])

  for l in restart_list:
    restartProc(current[l]['host'], int(current[l]['port']))

  time.sleep(1)
  return 0

def getCurrentStatus(host, port):
    result = check_status(host, port)
    if result[0] == STATUS_RUNNING:
        return {'pid': result[1], 'host': host,
               'port': port, 'dir': result[5],
               'status': result[0], 'ppid': result[2],
               'newstyle': False}
    else:
        return None

def getBaseName(ioc):
    try:
        lines = open(PVFILE % ioc).readlines()
        for l in lines:
            pv = l.split(",")[0]
            if pv[-10:] == ":HEARTBEAT":
                return pv[:-10]
    except:
        pass
    return None
