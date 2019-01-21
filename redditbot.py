# Reddit bot that handles the reddit side of things
import praw
import time
import asyncio
from snoopsnoo import SnoopSnooAPI
from RollingLogger import RollingLogger_Async
from FileParser import FileParser

"""
Main class for the reddit side
"""
class RedditBot():
	def __init__(self, queueList, config, usrlist):
		# Accepted users is one user per line
		# User cache has the last postID first, then a line of all tracking users,
		# then a line of number of days left to track each user
		self.acceptedUsers = usrlist
		self.redditCache = FileParser.parseFile("redditcache.txt", True)
		
		self.r = praw.Reddit(client_id=config['reddit_creds']['client_id'],
							client_secret=config['reddit_creds']['client_secret'],
							user_agent=config['reddit_creds']['user_agent'])
		self.sr = self.r.subreddit(config['general']['subreddit'])
		
		self.REDDIT_REFRESH_RATE = int(config['general']['reddit_new_refresh'])
		self.TOP_REFRESH_RATE = int(config['general']['reddit_top_refresh'])
		self.SNOOPSNOO_REFRESH_RATE = int(config['general']['snoop_snoo_refresh'])
		self.EXIT_POLL_RATE = int(config['general']['reddit_exit_refresh'])
		self.CYCLES_IN_REVIEW = config['general']['review_cycles']
		self.MAX_COMMENT_KARMA = int(config['general']['max_comment_karma'])
		self.REQUIRED_KARMA_TOTAL = int(config['general']['total_karma_required'])
		
		self.acceptQueue = queueList[0]
		self.postQueue = queueList[1]
		
		# Start the logger
		self.logger = RollingLogger_Async(config['logging']['reddit_log_name'], int(config['logging']['max_file_size']), int(config['logging']['max_number_logs']), int(config['logging']['log_verbosity']))
		
		self.gracefulExit = False
		
		self.logger.info("Reddit initialize success!")
	
	# Manages how long each task should sleep, posting a warning if a task takes too long
	def checkTime(self, atime, btime, cr):
		sleeptime = atime - btime
		if sleeptime < 0:
			self.logger.warning("!Coroutine "+ cr +" went over time! " + str(sleeptime))
			sleeptime = 0
		return sleeptime
	
	# Whether or not a user meets the requirements
	def isQualified(self, subKarma, comKarma):
		if comKarma > self.MAX_COMMENT_KARMA:
			c = self.MAX_COMMENT_KARMA
		else:
			c = comKarma
		return (subKarma + c >= self.REQUIRED_KARMA_TOTAL)
	
	# Async - Checks whether a user meets the requirements using snoopsnoo
	async def async_isQualifiedSnoop(self, user):
		jd = await SnoopSnooAPI.async_getSubredditActivity(user, self.sr.display_name)
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
			wasChanged = False
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
					# don't keep going if the post is older than 1H 5M
					# prevent long loads and getting stuck on removed posts
					if startTime - int(post.created_utc) >= 3900:
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
			self.logger.info("grabbed " + str(si) + " new posts!")
			si -= 1
			
			# iterate through all the recent posts
			while si >= 0:
				# if author is already accepted, skip it
				if users[si].name.lower() in self.acceptedUsers:
					si -= 1
					continue
				# if author is already being watched, reset their refresh counter
				if users[si].name in self.redditCache[1]:
					wasChanged = True
					userIndex = self.redditCache[1].index(users[si].name)
					self.redditCache[2][userIndex] = self.CYCLES_IN_REVIEW
					si -= 1
					continue
				# check author's karma to see if they're even close
				if not self.isQualified((users[si].link_karma) * 2, (users[si].comment_karma) * 2):
					si -= 1
					continue
				# author not found elsewhere and passes sanity checks, add them to list
				wasChanged = True
				self.redditCache[1].append(users[si].name)
				self.redditCache[2].append(self.CYCLES_IN_REVIEW)
				si -= 1
			# Write out the user cache
			wasChanged = wasChanged or (self.redditCache[0][0] != lastSubmission)
			self.redditCache[0][0] = lastSubmission
			if wasChanged:
				FileParser.writeNestedList("redditcache.txt", self.redditCache, 'w')
			
			# keep the pace
			endTime = time.time()
			await asyncio.sleep(self.checkTime(self.REDDIT_REFRESH_RATE, startTime - endTime, "async_newUsers"))
	
	# Async - checks top posts of the subreddit
	async def async_topPosts(self):
		await asyncio.sleep(self.TOP_REFRESH_RATE)
		while not self.gracefulExit:
			startTime = time.time()
			wasChanged = False
			self.logger.info("Refreshing top 10 posts...")
			topPosts = self.sr.top('day', limit=10)
			for post in topPosts:
				if not post.id in self.redditCache[3]:
					wasChanged = True
					self.redditCache[3].append(str(post.id))
					if post.over_18:
						self.postQueue.put([post.title, post.author.name, '<'+post.url+'> **NSFW**', '<'+post.shortlink+'> **NSFW**'])
					else:
						self.postQueue.put([post.title, post.author.name, post.url, post.shortlink])
					l = len(self.redditCache[3])
					if l >= 40:
						self.redditCache[3] = self.redditCache[3][l-30:]
			if wasChanged:
				FileParser.writeNestedList("redditcache.txt", self.redditCache, 'w')
			endTime = time.time()
			await asyncio.sleep(self.checkTime(self.TOP_REFRESH_RATE, startTime - endTime, "async_topPosts"))
	
	# Async - checks users against snoopsnoo
	async def async_checkUsers(self):
		await asyncio.sleep(self.SNOOPSNOO_REFRESH_RATE)
		while not self.gracefulExit:
			startTime = time.time()
			wasChanged = False
			self.logger.info("Time to refresh SnoopSnoo for " + str(len(self.redditCache[1])) + " users...")
			u = 0
			while u < len(self.redditCache[1]):
				usr = self.redditCache[1][u]
				res = await SnoopSnooAPI.async_refreshSnoop(usr)
				if res != "OK":
					# See if the user exists, may be deleted or banned
					ru = self.r.redditor(usr)
					try:
						if ru.id:
							self.logger.warning("Error in SS refresh for '" + usr + "': " + res)
							u += 1
					except:
							self.logger.warning("User likely deleted or suspended - '" + usr + "': " + res)
							self.redditCache[1].pop(u)
							self.redditCache[2].pop(u)
				else:
					if await self.async_isQualifiedSnoop(usr):
						wasChanged = True
						self.logger.info("CONGRATULATIONS!! " + usr + " is qualified to join!")
						# Add user to queue so discord side can announce it
						self.acceptQueue.put(usr)
						self.acceptedUsers.append(usr.lower())
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
			if wasChanged:
				FileParser.writeList("acceptedusers.txt", self.acceptedUsers, 'w')
			FileParser.writeNestedList("redditcache.txt", self.redditCache, 'w')
			endTime = time.time()
			await asyncio.sleep(self.checkTime(self.SNOOPSNOO_REFRESH_RATE, startTime - endTime, "async_checkUsers"))
	
	# Async - checks for exit conditions and prepares to stop
	async def async_checkExit(self):
		await asyncio.sleep(self.EXIT_POLL_RATE)
		while not self.gracefulExit:
			ge = FileParser.parseFile("closegracefully.txt", False)
			if ge[0] != "no":
				self.logger.info("Reddit process is shutting down now")
				self.postQueue.put(None)
				self.gracefulExit = True
				self.postQueue.close()
				self.logger.closeLog()
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
		tasks.append(asyncio.ensure_future(self.async_checkExit()))
		# Quit as soon as one returns (the checkExit), don't care about results
		done, notdone = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
		# Log if a coroutine returned early because of an exception
		for t in done:
			exp = t.exception()
			if exp:
				self.logger.error("REDDIT BOT EXCEPTION: " + str(exp))
		for t in notdone:
			t.cancel()

def initBotAndRun(queueList, config, usrlist):
	rb = RedditBot(queueList, config, usrlist)
	loop = asyncio.get_event_loop()
	# Restart coroutines if we didn't mean to shutdown
	while not rb.gracefulExit:
		try:
			loop.run_until_complete(rb.run())
		except BaseException as e:
			print("Exception in InitAndRun: " + str(e))
		time.sleep(60)
	loop.close()
