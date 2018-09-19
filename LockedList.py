# Class that holds a lock and a list, since list isn't always thread safe
from multiprocessing import Lock

class LockedList:
	def __init__(self, lst):
		self._lst = lst
		self._lock = Lock()
	
	def acquireLock(self):
		return self._lock.acquire()
	
	def releaseLock(self):
		return self._lock.release()
	
	def getList(self):
		return self._lst