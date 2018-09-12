# Library of SnoopSnoo functions to call into
import requests
import json

# JSON Decoder that allows escape characters
class UnStrictDecoder(json.JSONDecoder):
	def __init__(self, *args, **kwargs):
		json.JSONDecoder.__init__(self, strict=False, *args, **kwargs)

# Main API class
class SnoopSnooAPI():
	# Converts a response from a snoopsnoo API JSON string to a Python object
	@staticmethod
	def jsonStrToObj(s, escapeQuotes=True):
		if escapeQuotes:
			s = s.replace('\\"','"')
			s = s.replace('\\\\','\\')
		
		return json.loads(s, cls=UnStrictDecoder)
	
	# Get cached info of user in JSON formatted string
	@staticmethod
	def getUserJSON(user):
		return requests.get("https://snoopsnoo.com/api/u/" + user).text
	
	# Same as above but returns a python object
	@staticmethod
	def getUserObj(user):
		js = requests.get("https://snoopsnoo.com/api/u/" + user).text
		return SnoopSnooAPI.jsonStrToObj(js)
	
	# Get a python object representing a user's activity in a subreddit
	@staticmethod
	def getSubredditActivity(user, subreddit, str=None):
		if str == None:
			snoop = SnoopSnooAPI.getUserJSON(user)
		else:
			snoop = str
		idx = snoop.find('"subreddit": {')
		idx = snoop.find('"name": "'+subreddit+'",', idx)
		if(idx != -1):
			begin = snoop.rfind('{',0,idx)
			end = snoop.find('}',idx)
			return SnoopSnooAPI.jsonStrToObj(snoop[begin:end+1])
		return None
	
	# Refreshes snoopsnoo's cache of a user
	@staticmethod
	def refreshSnoop(user):
		req = requests.post("https://sender.blockspring.com/api_v2/blocks/d03751d846a6a0ff9a6dfd36b9c1c641?api_key=d1b2e14d5b005465cfe3c83976a9240a", data={"username" : user, "json_data" : ""})
		upd = req.text
		idx = upd.find('"_errors":[{')
		if idx != -1:
			return ("error getting user: " + user)
		idx = upd.find('"results":')
		upd = upd[idx+11:-2]
		jd = SnoopSnooAPI.jsonStrToObj(upd)
		r2 = requests.post("https://snoopsnoo.com/update",json=jd)
		return r2.text