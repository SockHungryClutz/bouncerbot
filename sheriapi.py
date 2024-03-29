# Almost drop-in replacement for snoopsnoo library
# Well, now that site is dead...
import requests
import json
import aiohttp
import asyncio

# JSON Decoder that allows escape characters
class UnStrictDecoder(json.JSONDecoder):
    def __init__(self, *args, **kwargs):
        json.JSONDecoder.__init__(self, strict=False, *args, **kwargs)

# Main API class
class SheriAPI():
    # Sync - Converts a response from a snoopsnoo API JSON string to a Python object
    @staticmethod
    def jsonStrToObj(s, escapeQuotes=True):
        copy_s = s
        if escapeQuotes:
            # try without, just cuz
            try:
                ret = json.loads(s, cls=UnStrictDecoder)
            except:
                s = s.replace('\\"','"')
                s = s.replace('\\\\','\\')
                try:
                    ret = json.loads(s, cls=UnStrictDecoder)
                except:
                    # try removing more in case of formatting issues with comments
                    s = s.replace('\\\\','\\')
                    s = s.replace('\\"','"')
                    ret = json.loads(s, cls=UnStrictDecoder)
        else:
            ret = json.loads(s, cls=UnStrictDecoder)
        return ret
    
    # Sync - Get a python object representing a user's activity in a subreddit
    @staticmethod
    def getSubredditActivity(user, subreddit, snoop):
        idx = snoop.find('"subreddit": {')
        idx = snoop.find('"name": "'+subreddit+'",', idx)
        if(idx != -1):
            begin = snoop.rfind('{',0,idx)
            end = snoop.find('}',idx)
            return SheriAPI.jsonStrToObj(snoop[begin:end+1])
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
    
    # Async - Method to use if you just want basic info, not full refresh
    @staticmethod
    async def async_getUserInfo(user):
        async with aiohttp.ClientSession() as ses:
            res = await SheriAPI.async_get(ses, "https://sherley.azurewebsites.net/api/Query?username=" + user)
            idx = res.find('"_errors":[{')
            if idx != -1:
                return ("ERROR getting user: " + user), None
            try:
                jd = SheriAPI.jsonStrToObj(res)
            except Exception as e:
                return "EXCEPTION " + str(e) + "\n>>>response content<<<\n" + res, None
            return res, jd