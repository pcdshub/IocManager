#!/usr/bin/env python
import sys, getopt, socket, tempfile, stat, pwd, os
import utils
from psp.caput import caput

def match_hutch(h, hlist):
    h = h.split('-')
    if h[0] in hlist:
        return h[0]
    if h[1] in hlist:
        return h[1]
    return None

def get_hutch(ioc, results):
    hlist = utils.getHutchList()
    for (a, v) in results:
        if a == '--hutch':
            if not v in hlist:
                raise Exception("Nonexistent hutch %s" % v)
            return v
    v = match_hutch(socket.gethostname(), hlist)
    if v is None:
        v = match_hutch(ioc, hlist)
    return v

def usage():
    print "Usage: imgr IOCNAME [--hutch HUTCH] --reboot soft"
    print "       imgr IOCNAME [--hutch HUTCH] --reboot hard"
    print "       imgr IOCNAME [--hutch HUTCH] --enable"
    print "       imgr IOCNAME [--hutch HUTCH] --disable"
    print "       imgr IOCNAME [--hutch HUTCH] --upgrade RELEASE_DIR"
    print "       imgr IOCNAME [--hutch HUTCH] --move HOST"
    print "       imgr IOCNAME [--hutch HUTCH] --move HOST:PORT"
    sys.exit(1)

def soft_reboot(hutch, ioc):
    base = utils.getBaseName(ioc)
    if base is None:
        print "IOC %s not found!" % ioc
        sys.exit(1)
    caput(base + ":SYSRESET", 1)
    sys.exit(0)

def hard_reboot(hutch, ioc):
    (ft, cl, hl, vs) = utils.readConfig(hutch)
    for c in cl:
        if c['id'] == ioc:
            utils.restartProc(c['host'], c['port'])
            sys.exit(0)
    print "IOC %s not found in hutch %s!" % (ioc, hutch)
    sys.exit(1)

def do_commit(hutch, cl, hl, vs):
    file = tempfile.NamedTemporaryFile(dir=utils.TMP_DIR, delete=False)
    utils.writeConfig(hutch, hl, cl, vs, file)
    file.close()
    os.chmod(file.name, stat.S_IRUSR | stat.S_IRGRP |stat.S_IROTH)
    os.system("ssh %s %s %s %s" % (utils.COMMITHOST, utils.INSTALL, hutch, file.name))
    try:
        os.unlink(file.name)
    except:
        print "Error removing temporary file %s!" % file.name

def set_state(hutch, ioc, enable):
    if not utils.check_auth(pwd.getpwuid(os.getuid())[0], hutch):
        print "Not authorized!"
        sys.exit(1)
    (ft, cl, hl, vs) = utils.readConfig(hutch)
    try:
        utils.COMMITHOST = vs["COMMITHOST"]
    except:
        pass
    for c in cl:
        if c['id'] == ioc:
            c['newdisable'] = not enable
            do_commit(hutch, cl, hl, vs)
            utils.applyConfig(hutch, None, ioc)
            sys.exit(0)
    print "IOC %s not found in hutch %s!" % (ioc, hutch)
    sys.exit(1)

def upgrade(hutch, ioc, version):
    if not utils.check_auth(pwd.getpwuid(os.getuid())[0], hutch):
        print "Not authorized!"
        sys.exit(1)
    if not utils.validateDir(version, ioc):
        print "%s does not have an st.cmd for %s!" % (version, ioc)
        sys.exit(1)
    (ft, cl, hl, vs) = utils.readConfig(hutch)
    try:
        utils.COMMITHOST = vs["COMMITHOST"]
    except:
        pass
    for c in cl:
        if c['id'] == ioc:
            c['newdir'] = version
            do_commit(hutch, cl, hl, vs)
            utils.applyConfig(hutch, None, ioc)
            sys.exit(0)
    print "IOC %s not found in hutch %s!" % (ioc, hutch)
    sys.exit(1)

def move(hutch, ioc, hostport):
    if not utils.check_auth(pwd.getpwuid(os.getuid())[0], hutch):
        print "Not authorized!"
        sys.exit(1)
    (ft, cl, hl, vs) = utils.readConfig(hutch)
    try:
        utils.COMMITHOST = vs["COMMITHOST"]
    except:
        pass
    for c in cl:
        if c['id'] == ioc:
            hp = hostport.split(":")
            c['newhost'] = hp[0]
            if len(hp) > 1:
                c['newport'] = int(hp[1])
            if not utils.validateConfig(cl):
                print "Port conflict when moving %s to %s, not moved!" % (ioc, hostport)
                sys.exit(1)
            do_commit(hutch, cl, hl, vs)
            utils.applyConfig(hutch, None, ioc)
            sys.exit(0)
    print "IOC %s not found in hutch %s!" % (ioc, hutch)
    sys.exit(1)

if __name__ == "__main__":
    try:
        ioc = sys.argv[1]
        results = getopt.getopt(sys.argv[2:], '', ['reboot=', 'disable', 'enable', 'upgrade=', 'move=', 'hutch='])
    except:
        usage()
    hutch = get_hutch(ioc, results[0])
    if hutch is None:
        usage()
    for (a, v) in results[0]:
        if a == '--hutch':
            pass
        elif a == '--reboot':
            if v == 'hard':
                hard_reboot(hutch, ioc)
            elif v == 'soft':
                soft_reboot(hutch, ioc)
            else:
                usage()
        elif a == '--disable' or a == '--enable':
            set_state(hutch, ioc, a == '--enable')
        elif a == '--upgrade':
            upgrade(hutch, ioc, v)
        elif a == '--move':
            move(hutch, ioc, v)
        else:
            usage()
    sys.exit(0)
