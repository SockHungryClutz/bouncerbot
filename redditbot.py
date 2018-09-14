# WOOHOO! Makin a reddit bot and stuff!
import praw
import time
import asyncio
from snoopsnoo import SnoopSnooAPI

# Define Helper Functions
# Reads a file, giving back a list of all lines (including line endings)
def readFile(filename):
	with open(filename) as f:
		return f.readlines()

# Returns a cleaned list from a file, may or may not be subdivided per line
def parseFile(filename, split):
	r = readFile(filename)
	i = len(r) - 1
	while i >= 0:
		if split:
			r[i] = r[i][:-1].split()
		else:
			r[i] = r[i][:-1]
		i -= 1
	return r

# Writes out to a file, can take a mode as argument
def writeFile(filename, content, mode):
	with open(filename, mode) as f:
		f.write(content)

# Writes the usercache out to file
def writeUserCache(uc):
	ostr = uc[0][0] + '\n'
	for ustr in uc[1]:
		ostr += ustr + ' '
	ostr += '\n'
	for cstr in uc[2]:
		ostr += cstr + ' '
	ostr += '\n'
	for pstr in uc[3]:
		ostr += pstr + ' '
	ostr += '\n'
	writeFile("redditcache.txt", ostr, 'w')

# Writes the accepted users list out to file
def writeAcceptedUsers(au):
	ostr = ""
	for usr in au:
		ostr += usr + '\n'
	writeFile("acceptedusers.txt", ostr, 'w')

# Manages how long each task should sleep, posting a warning if a task takes too long
def checkTime(atime, btime, cr):
	sleeptime = atime - btime
	if sleeptime < 0:
		print("!Coroutine "+ cr +" went over time! " + str(sleeptime))
		sleeptime = 0
	return sleeptime

"""
Main class of the whole damn deal
"""
class RedditBot():
	def __init__(self, queueList, config):
		# Accepted users is one user per line
		# User cache has the last postID first, then a line of all tracking users,
		# then a line of number of days left to track each user
		print("Starting RedditBot...")
		self.acceptedUsers = parseFile("acceptedusers.txt", False)
		self.redditCache = parseFile("redditcache.txt", True)

		self.r = praw.Reddit(client_id=config['reddit_creds']['client_id'],
							client_secret=config['reddit_creds']['client_secret'],
							user_agent=config['reddit_creds']['user_agent'])
		self.sr = self.r.subreddit("furry_irl")
		
		self.REDDIT_REFRESH_RATE = int(config['general']['reddit_new_refresh'])
		self.TOP_REFRESH_RATE = int(config['general']['reddit_top_refresh'])
		self.SNOOPSNOO_REFRESH_RATE = int(config['general']['snoop_snoo_refresh'])
		self.EXIT_POLL_RATE = int(config['general']['reddit_exit_refresh'])
		self.QUEUE_POLL_RATE = int(config['general']['reddit_queue_poll'])
		self.CYCLES_IN_REVIEW = config['general']['review_cycles']
		self.MAX_COMMENT_KARMA = int(config['general']['max_comment_karma'])
		self.REQUIRED_KARMA_TOTAL = int(config['general']['total_karma_required'])
		
		self.acceptQueue = queueList[0]
		self.postQueue = queueList[1]
		self.manualQueue = queueList[2]
		
		self.gracefulExit = False
		
		print("Reddit initialize success!")
	
	# Whether or not a user meets the requirements
	def isQualified(self, subKarma, comKarma):
		if comKarma > self.MAX_COMMENT_KARMA:
			c = self.MAX_COMMENT_KARMA
		else:
			c = comKarma
		return (subKarma + c >= self.REQUIRED_KARMA_TOTAL)
	
	# Async - Checks whether a user meets the requirements using snoopsnoo
	async def async_isQualifiedSnoop(self, user):
		jd = await SnoopSnooAPI.async_getSubredditActivity(user, "furry_irl")
		if jd != None:
			skarma = jd["submission_karma"]
			ckarma = jd["comment_karma"]
			return self.isQualified(skarma, ckarma)
		return False
	
	# Async - gets new posts and checks users periodically
	async def async_newUsers(self):
		lastSubmission = self.redditCache[0][0]
		while not self.gracefulExit:
			# time how long a cycle takes so it always starts at the right time
			startTime = time.time()
			n = 25
			si = 0
			newPosts = self.sr.new(limit=n)
			users = []
			
			# search through the latest for the last id, expanding search if
			# latest was not found in each batch of 25
			foundLatest = False
			while not foundLatest:
				for post in newPosts:
					if post.id == self.redditCache[0][0]:
						foundLatest = True
						break
					if si == 0:
						if lastSubmission == "0":
							# don't break, 
							# this is a workaround to avoid infinite load on start
							foundLatest = True
						lastSubmission = post.id
					users.append(post.author)
					si += 1
				if not foundLatest:
					n += 25
					si = 0
					users = []
					newPosts = self.sr.new(limit=n)
			print("grabbed " + str(si) + " new posts!")
			si -= 1
			
			# iterate through all the recent posts
			while si >= 0:
				# if author is already accepted, skip it
				if users[si].name in self.acceptedUsers:
					si -= 1
					continue
				# if author is already being watched, reset their refresh counter
				if users[si].name in self.redditCache[1]:
					userIndex = self.redditCache[1].index(users[si].name)
					self.redditCache[2][userIndex] = self.CYCLES_IN_REVIEW
					si -= 1
					continue
				# check author's karma to see if they're even close
				if not self.isQualified((users[si].link_karma) * 2, (users[si].comment_karma) * 2):
					si -= 1
					continue
				# author not found elsewhere and passes sanity checks, add them to list
				self.redditCache[1].append(users[si].name)
				self.redditCache[2].append(self.CYCLES_IN_REVIEW)
				si -= 1
			# Write out the user cache
			self.redditCache[0][0] = lastSubmission
			writeUserCache(self.redditCache)
			
			# keep the pace
			endTime = time.time()
			await asyncio.sleep(checkTime(self.REDDIT_REFRESH_RATE, startTime - endTime, "async_newUsers"))
	
	# Async - checks top posts of the subreddit
	async def async_topPosts(self):
		await asyncio.sleep(self.TOP_REFRESH_RATE)
		while not self.gracefulExit:
			startTime = time.time()
			topPosts = self.sr.top('day', limit=10)
			for post in topPosts:
				if not post.id in self.redditCache[3]:
					self.redditCache[3].append(str(post.id))
					if post.over_18:
						self.postQueue.put([post.author.name, '<'+post.url+'> **NSFW**', '<'+post.shortlink+'> **NSFW**'])
					else:
						self.postQueue.put([post.author.name, post.url, post.shortlink])
					l = len(self.redditCache[3])
					if l >= 40:
						self.redditCache[3] = self.redditCache[3][l-30:]
			writeUserCache(self.redditCache)
			endTime = time.time()
			await asyncio.sleep(checkTime(self.TOP_REFRESH_RATE, startTime - endTime, "async_topPosts"))
	
	# Async - checks users against snoopsnoo
	async def async_checkUsers(self):
		await asyncio.sleep(self.SNOOPSNOO_REFRESH_RATE)
		while not self.gracefulExit:
			startTime = time.time()
			print("Time to refresh SnoopSnoo for " + str(len(self.redditCache[1])) + " users...")
			u = 0
			while u < len(self.redditCache[1]):
				usr = self.redditCache[1][u]
				self.r = await SnoopSnooAPI.async_refreshSnoop(usr)
				if self.r != "OK":
					print("Error in SS refresh for '" + usr + "': " + self.r)
					u += 1
				else:
					if await self.async_isQualifiedSnoop(usr):
						print("CONGRATULATIONS!! " + usr + " is qualified to join!")
						# Add user to queue so discord side can announce it
						self.acceptQueue.put(usr)
						self.acceptedUsers.append(usr)
						self.redditCache[1].pop(u)
						self.redditCache[2].pop(u)
					else:
						self.redditCache[2][u] = str(int(self.redditCache[2][u]) - 1)
						if self.redditCache[2][u] == "0":
							self.redditCache[1].pop(u)
							self.redditCache[2].pop(u)
						else:
							u += 1
			# Write the (hopefully changed) accepted users list
			writeAcceptedUsers(self.acceptedUsers)
			endTime = time.time()
			await asyncio.sleep(checkTime(self.SNOOPSNOO_REFRESH_RATE, startTime - endTime, "async_checkUsers"))
	
	# Async - adds users from the ignore queue
	async def async_ignore(self):
		await asyncio.sleep(self.QUEUE_POLL_RATE)
		while not self.gracefulExit:
			startTime = time.time()
			# remove from self.manualQueue until empty
			while not self.manualQueue.empty():
				newUser = self.manualQueue.get()
				self.acceptedUsers.append(newUser)
				if newUser in self.redditCache[1]:
					idx = self.redditCache[1].index(newUser)
					self.redditCache[1].pop(idx)
					self.redditCache[2].pop(idx)
			endTime = time.time()
			await asyncio.sleep(checkTime(self.QUEUE_POLL_RATE, startTime - endTime, "async_ignore"))
	
	# Async - checks for exit conditions and prepares to stop
	async def async_checkExit(self):
		await asyncio.sleep(self.EXIT_POLL_RATE)
		while not self.gracefulExit:
			ge = parseFile("closegracefully.txt", False)
			if ge[0] != "no":
				self.acceptQueue.put(None)
				self.gracefulExit = True
				self.acceptQueue.close()
				self.postQueue.close()
				break
			await asyncio.sleep(self.EXIT_POLL_RATE)
	
	# sets up the coroutines for the bot to run
	async def run(self):
		tasks = []
		# these async functions, should be gucci coexisting 
		# because its technically single threaded...
		# have to think of the consequences of changing data midway though
		tasks.append(asyncio.ensure_future(self.async_newUsers()))
		tasks.append(asyncio.ensure_future(self.async_topPosts()))
		tasks.append(asyncio.ensure_future(self.async_checkUsers()))
		tasks.append(asyncio.ensure_future(self.async_ignore()))
		tasks.append(asyncio.ensure_future(self.async_checkExit()))
		# Quit as soon as one returns (the checkExit), don't care about results
		done, notdone = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
		for t in notdone:
			t.cancel()

def initBotAndRun(queueList, config):
	rb = RedditBot(queueList, config)
	loop = asyncio.get_event_loop()
	try:
		loop.run_until_complete(rb.run())
	finally:
		loop.close()