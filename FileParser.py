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
        l = len(r) - 1
        i = l
        lastChar = r[l][-1]
        while i >= 0:
            if split:
                r[i] = r[i][:-1].split()
            else:
                r[i] = r[i][:-1]
            i -= 1
        if not lastChar.isspace():
            if split:
                r[l][len(r[l])-1] = r[l][len(r[l])-1] + lastChar
            else:
                r[l] = r[l] + lastChar
        return r
    
    @staticmethod
    # Writes out to a file, can take a mode as argument
    def writeFile(filename, content, mode):
        with open(filename, mode) as f:
            f.write(content)
    
    @staticmethod
    # Writes an entire list to a file
    def writeList(filename, lst, mode):
        ostr = ""
        for n in lst:
            ostr += n + '\n'
        FileParser.writeFile(filename, ostr, mode)
    
    @staticmethod
    # Writes a nested list to file
    def writeNestedList(filename, lst, mode):
        ostr = ""
        for n in lst:
            for o in n:
                ostr += o + ' '
            ostr += '\n'
        FileParser.writeFile(filename, ostr, mode)
