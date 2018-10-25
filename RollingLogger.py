# Class for logging stuff
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

class RollingLogger:
	def __init__(self, name, fileSize, numFile, level):
		if level == 0:
			self.nologs = True
		else:
			self.logger = logging.getLogger(name)
			if level == 1:
				self.logger.setLevel(logging.CRITICAL)
			elif level == 2:
				self.logger.setLevel(logging.ERROR)
			elif level == 3:
				self.logger.setLevel(logging.WARNING)
			elif level == 4:
				self.logger.setLevel(logging.INFO)
			else:
				self.logger.setLevel(logging.DEBUG)
			self.nologs = False
			self.handler = RotatingFileHandler(name+".log", maxBytes=fileSize, backupCount=numFile)
			self.logger.addHandler(self.handler)
			self.logger.info(">Logger " + name + " initialized - " + str(datetime.now()) + "<")
	
	def debug(self, msg):
		if not self.nologs:
			self.logger.debug("[" + str(datetime.now()) + "] *   " +msg)
	
	def info(self, msg):
		if not self.nologs:
			self.logger.info("[" + str(datetime.now()) + "]     " +msg)
	
	def warning(self, msg):
		if not self.nologs:
			self.logger.warning("[" + str(datetime.now()) + "] !   " +msg)
	
	def error(self, msg):
		if not self.nologs:
			self.logger.error("[" + str(datetime.now()) + "] !!  " +msg)
	
	def critical(self, msg):
		if not self.nologs:
			self.logger.critical("[" + str(datetime.now()) + "] !!! " +msg)