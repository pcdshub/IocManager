import pyca
import threading
import sys
import copy

class Pv(pyca.capv):
  def __init__(self, name, simulated=None):
    pyca.capv.__init__(self, name)
    self.__connection_sem = threading.Event()
    self.connect_cb = self.connection_handler
    self.simulated = simulated
    if simulated != None:
      self.data["status"] = 0L
      self.data["secs"] = 0L
      self.data["nsec"] = 0L
      self.data["value"] = 0L
      self.data["severity"] = 0L
    self.ismonitored = False

  # Channel access callbacks
  def connection_handler(self, isconnected):
    if isconnected:
      self.__connection_sem.set()

  # Calls to channel access methods
  def connect(self, timeout=-1.0):
    if self.simulated != None:
      return
    tmo = float(timeout)
    self.create_channel()
    if tmo > 0:
      self.__connection_sem.wait(tmo)
      if not self.__connection_sem.isSet():
        raise pyca.pyexc, "connection timedout for PV %s" %(self.name)

  def disconnect(self):
    if self.simulated != None:
      return
    self.clear_channel()

  def monitor(self, mask, ctrl=False, count=None):
    self.subscribe_channel(mask, ctrl, count)
    self.ismonitored = True

  def unsubscribe(self):
    self.unsubscribe_channel()
    self.ismonitored = False

  def get(self, ctrl=False, timeout=-1.0, count=None):
    tmo = float(timeout)
    self.get_data(ctrl, tmo, count)

  def put(self, value, timeout=-1.0):
    tmo = float(timeout)
    self.put_data(value, tmo)
    
  # Used to obtain a copy of the data which won't be overwritten by ca callbacks
  def getcopy(self):
    interval = sys.getcheckinterval()
    try:
      #sys.setcheckinterval(sys.maxint)
      sys.setcheckinterval(100)
      datacopy = copy.deepcopy(self.data)
    finally:
      sys.setcheckinterval(interval)
    return datacopy

  # Re-define getattr method to allow direct access to 'data' dictionary members
  def __getattr__(self, name):
    if self.data.has_key(name):
      return self.data[name]
    else:
      raise AttributeError

  def setvalue(self, value):
    self.data["value"] = value
    
