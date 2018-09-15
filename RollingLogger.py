# Class for logging stuff
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

class RollingLogger:
	def __init__(self, name, fileSize, numFile):
		self.logger = logging.getLogger(name)
		self.logger.setLevel(logging.INFO)
		self.handler = RotatingFileHandler(name+".log", maxBytes=fileSize, backupCount=numFile)
		self.logger.addHandler(self.handler)
		self.logger.info(">Logger " + name + " initialized - " + str(datetime.now()) + "<")
	
	def debug(self, msg):
		self.logger.debug("[" + str(datetime.now()) + "] *  " +msg)
	
	def info(self, msg):
		self.logger.info("[" + str(datetime.now()) + "]    " +msg)
	
	def warning(self, msg):
		self.logger.warning("[" + str(datetime.now()) + "] !  " +msg)
	
	def error(self, msg):
		self.logger.error("[" + str(datetime.now()) + "] !! " +msg)
	
	def critical(self, msg):
		self.logger.critical("[" + str(datetime.now()) + "] !!!" +msg)