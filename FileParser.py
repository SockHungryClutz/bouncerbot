# Handler for parsing caches and other such files
# Reads a file, giving back a list of all lines (including line endings)
class FileParser():
	@staticmethod
	def readFile(filename):
		with open(filename) as f:
			return f.readlines()
	
	@staticmethod
	# Returns a cleaned list from a file, may or may not be subdivided per line
	def parseFile(filename, split):
		r = FileParser.readFile(filename)
		i = len(r) - 1
		while i >= 0:
			if split:
				r[i] = r[i][:-1].split()
			else:
				r[i] = r[i][:-1]
			i -= 1
		return r
	
	@staticmethod
	# Writes out to a file, can take a mode as argument
	def writeFile(filename, content, mode):
		with open(filename, mode) as f:
			f.write(content)
