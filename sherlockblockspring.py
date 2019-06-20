# RIP SnoopSnoo
# This calls directly to the blockspring behind it, likely throttled without api_key
# not exactly a drop-in replacement for SnoopSnooAPI but it'll do
# Also not using the premade blockspring python thing since it can't do async
# Thanks to blockspring for keeping it accessible tho
import requests
import json
import aiohttp
import asyncio

# JSON Decoder that allows escape characters
class UnStrictDecoder(json.JSONDecoder):
    def __init__(self, *args, **kwargs):
        json.JSONDecoder.__init__(self, strict=False, *args, **kwargs)

# Main API class
class BlockSpringAPI():
    # Sync - Converts a response from a snoopsnoo API JSON string to a Python object *****REQUIRED*****
    @staticmethod
    def jsonStrToObj(s, escapeQuotes=True):
        if escapeQuotes:
            s = s.replace('\\"','"')
            s = s.replace('\\\\','\\')
        return json.loads(s, cls=UnStrictDecoder)
    
    # Sync - Get a python object representing a user's activity in a subreddit
    @staticmethod
    def getSubredditActivity(user, subreddit, snoop):
        idx = snoop.find('"subreddit": {')
        idx = snoop.find('"name": "'+subreddit+'",', idx)
        if(idx != -1):
            begin = snoop.rfind('{',0,idx)
            end = snoop.find('}',idx)
            return SnoopSnooAPI.jsonStrToObj(snoop[begin:end+1])
        return None
    
    # Async - http get, but async
    @staticmethod
    async def async_get(ses, url):
        try:
            async with ses.get(url) as resp:
                return await resp.text()
        except:
            return '{"_errors":[{"1":"aiohttp fail - get"}]}'
    
    # Async - http post, also async
    @staticmethod
    async def async_post(ses, url, data):
        try:
            async with ses.post(url, data=data) as resp:
                return await resp.text()
        except:
            return '{"_errors":[{"1":"aiohttp fail - post"}]}'
    
    # Async - json http post, also async
    @staticmethod
    async def async_post_json(ses, url, json):
        try:
            async with ses.post(url, json=json) as resp:
                return await resp.text()
        except:
            return '{"_errors":[{"1":"aiohttp fail - post_json"}]}'
    
    # Async - This is the one that takes forever to respond *****REQUIRED*****
    @staticmethod
    async def async_refreshUser(user):
        async with aiohttp.ClientSession() as ses:
            res = await SnoopSnooAPI.async_post(ses, "https://sender.blockspring.com/api_v2/blocks/d03751d846a6a0ff9a6dfd36b9c1c641?api_key=", data={"username" : user, "json_data" : ""})
            idx = res.find('"_errors":[{')
            if idx != -1:
                return ("ERROR getting user: " + user), None
            idx = res.find('"results":')
            upd = res[idx+11:-2]
            try:
                jd = SnoopSnooAPI.jsonStrToObj(upd)
            except Exception as e:
                return "EXCEPTION " + str(e) + "\n>>>response content<<<\n" + res, None
            return res, jd
