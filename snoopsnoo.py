# Library of SnoopSnoo functions to call into
import requests
import json
import aiohttp
import asyncio

# JSON Decoder that allows escape characters
class UnStrictDecoder(json.JSONDecoder):
	def __init__(self, *args, **kwargs):
		json.JSONDecoder.__init__(self, strict=False, *args, **kwargs)

# Main API class
class SnoopSnooAPI():
	# Sync - Converts a response from a snoopsnoo API JSON string to a Python object
	@staticmethod
	def jsonStrToObj(s, escapeQuotes=True):
		if escapeQuotes:
			s = s.replace('\\"','"')
			s = s.replace('\\\\','\\')
		
		return json.loads(s, cls=UnStrictDecoder)
	
	# Sync - Get cached info of user in JSON formatted string
	@staticmethod
	def getUserJSON(user):
		return requests.get("https://snoopsnoo.com/api/u/" + user).text
	
	# Sync - Same as above but returns a python object
	@staticmethod
	def getUserObj(user):
		js = requests.get("https://snoopsnoo.com/api/u/" + user).text
		return SnoopSnooAPI.jsonStrToObj(js)
	
	# Sync - Get a python object representing a user's activity in a subreddit
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
	
	# Sync - Refreshes snoopsnoo's cache of a user
	@staticmethod
	def refreshSnoop(user):
		req = requests.post("https://sender.blockspring.com/api_v2/blocks/d03751d846a6a0ff9a6dfd36b9c1c641?api_key=d1b2e14d5b005465cfe3c83976a9240a", data={"username" : user, "json_data" : ""})
		upd = req.text
		idx = upd.find('"_errors":[{')
		if idx != -1:
			return ("error getting user: " + user)
		idx = upd.find('"results":')
		upd = upd[idx+11:-2]
		print(upd)
		jd = SnoopSnooAPI.jsonStrToObj(upd)
		r2 = requests.post("https://snoopsnoo.com/update",json=jd)
		return r2.text
	
	# Async - http get, but async
	@staticmethod
	async def async_get(ses, url):
		async with ses.get(url) as resp:
			return await resp.text()
	
	# Async - http post, also async
	@staticmethod
	async def async_post(ses, url, data):
		async with ses.post(url, data=data) as resp:
			return await resp.text()
	
	# Async - async version of getUserJSON
	@staticmethod
	async def async_getUserJSON(user):
		async with aiohttp.ClientSession() as ses:
			return await SnoopSnooAPI.async_get(ses, "https://snoopsnoo.com/api/u/" + user)
	
	# Async - async version of getUserObj
	@staticmethod
	async def async_getUserObj(user):
		js = await SnoopSnooAPI.async_getUserJSON(user)
		return SnoopSnooAPI.jsonStrToObj(js)
	
	# Async - async version of getSubredditActivity
	@staticmethod
	async def async_getSubredditActivity(user, subreddit):
		snoop = await SnoopSnooAPI.async_getUserJSON(user)
		idx = snoop.find('"subreddit": {')
		idx = snoop.find('"name": "'+subreddit+'",', idx)
		if(idx != -1):
			begin = snoop.rfind('{',0,idx)
			end = snoop.find('}',idx)
			return SnoopSnooAPI.jsonStrToObj(snoop[begin:end+1])
		return None
	
	# Async - This is the one that takes forever to respond
	@staticmethod
	async def async_refreshSnoop(user):
		async with aiohttp.ClientSession() as ses:
			res = await SnoopSnooAPI.async_post(ses, "https://sender.blockspring.com/api_v2/blocks/d03751d846a6a0ff9a6dfd36b9c1c641?api_key=d1b2e14d5b005465cfe3c83976a9240a", data={"username" : user, "json_data" : ""})
			idx = res.find('"_errors":[{')
			if idx != -1:
				return ("error getting user: " + user)
			idx = res.find('"results":')
			upd = res[idx+11:-2]
			try:
				jd = SnoopSnooAPI.jsonStrToObj(upd)
			except Exception as e:
				return "EXCEPTION " + str(e) + "\n>>>response content<<<\n" + res
			# this must be done synchronously since the old version of aiohttp used by the
			# the old version of discord.py doesn't support json POST
			r2 = requests.post("https://snoopsnoo.com/update",json=jd)
			return r2.text