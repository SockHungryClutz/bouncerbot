"""
BouncerBot - Python bot to assist the Furry Shitposting Guild
Many months of weird optimizations led this to be a mess of processes that
probably aren't necessary, so here's what they look like:
(lines indicate interprocess communication)

DiscordLogger                  RedditLogger
     |                               |
 DiscordBot -- SharedUserList -- RedditBot
 
The discord and reddit bots are also async, meaning everything is a
weird but efficient mess.
"""
import discord
from discord.ext import commands
import asyncio
import configparser
import time
from datetime import datetime
from multiprocessing import Process, Queue, Manager
import redditbot
from snoopsnoo import SnoopSnooAPI
from RollingLogger import RollingLogger_Async
from FileParser import FileParser

VERSION = '1.3.0'

bot = commands.Bot(command_prefix='b.', description='BouncerBot '+VERSION+' - Helper bot to automate some tasks for the Furry Shitposting Guild\n(use "b.<command>" to give one of the following commands)', case_insensitive=True)

# So apparently the rewrite should have the bot as a subclass of bot...
# TODO: the above

# Read configuration
config = configparser.ConfigParser()
config.read('botconfig.ini')
token = config['discord_creds']['token']
queuePoll = int(config['general']['discord_queue_poll'])
logname = config['logging']['discord_log_name']
filesizemax = int(config['logging']['max_file_size'])
numlogsmax = int(config['logging']['max_number_logs'])
logVerbosity = int(config['logging']['log_verbosity'])
subreddit = config['general']['subreddit']
MAX_COMMENT_KARMA = int(config['general']['max_comment_karma'])
REQUIRED_KARMA_TOTAL = int(config['general']['total_karma_required'])
realCleanShutDown = False
p = None

# Get the accepted users list
aul = FileParser.parseFile("acceptedusers.txt", False)

# Mapping of reddit usernames to discord id's
userMap = FileParser.parseFile("usermap.txt", True)

# Create the queues the processes will use to communicate
newUserQueue = Queue()
newPostQueue = Queue()
queueList = [newUserQueue, newPostQueue]

# Start the discord logger
# No wait, don't, it breaks on Windows
logger = None

# in all likelihood, this will only ever use a couple channels to talk
# let's cache them in a dict to save a few cycles
channelCache = {}

# The process to create and run the reddit bot
def makeRedditBot(configuration, queues, usrlist):
	redditbot.initBotAndRun(queues, configuration, usrlist)

# Send a message to a channel with a specific name
def findChannel(chnl):
	global channelCache
	foundChannel = None
	try:
		foundChannel = channelCache[chnl]
	except KeyError as e:
		allChannels = bot.get_all_channels()
		for channel in allChannels:
			if channel.name == chnl:
				foundChannel = channel.id
				channelCache[chnl] = channel.id
	return foundChannel

# Whether or not a user is qualified to join
def isQualified(subKarma, comKarma):
	if comKarma > MAX_COMMENT_KARMA:
		c = MAX_COMMENT_KARMA
	else:
		c = comKarma
	return (subKarma + c >= REQUIRED_KARMA_TOTAL)

# Escapes underscores in usernames to prevent weird italics
def fixUsername(name):
	return name.replace('_','\_')

# Checks post and user queues from the reddit side, messaging when any are ready
async def check_user_queue():
	logger.info("Hewwo owo")
	await bot.wait_until_ready()
	while not bot.is_closed:
		logger.info("checking new user queue...")
		while not newUserQueue.empty():
			newUsr = newUserQueue.get()
			logger.info("new user accepted: "+newUsr)
			redditurl = "https://www.reddit.com/u/" + newUsr
			snoopurl = "https://snoopsnoo.com/u/" + newUsr
			msg = fixUsername(newUsr) + " is now eligible for entry! :grinning:\n" + redditurl + "\n" + snoopurl
			sendchannel = await bot.get_channel(findChannel(config['general']['user_announce_channel']))
			await sendchannel.send(content=msg, embed=None)
		await asyncio.sleep(queuePoll)

async def check_post_queue():
	await bot.wait_until_ready()
	while not bot.is_closed:
		logger.info("checking post queue...")
		closeDiscord = False
		while not newPostQueue.empty():
			newPost = newPostQueue.get()
			if newPost == None:
				closeDiscord = True
				continue
			logger.info("added post: "+newPost[0]+' ; '+newPost[1]+' ; '+newPost[2])
			if newPost[0].lower() in userMap[0]:
				uidx = userMap[0].index(newPost[0].lower())
				duser = await bot.get_user_info(userMap[1][uidx])
				realuser = duser.mention + " (" + fixUsername(newPost[0]) + ")"
			else:
				realuser = fixUsername(newPost[0])
			msg = "user: " + realuser + "\ncontent: " + newPost[1] + "\npost: " + newPost[2]
			sendchannel = await bot.get_channel(findChannel(config['general']['post_announce_channel']))
			await sendchannel.send(content=msg, embed=None)
		if closeDiscord:
			# all other queues should be closed by the reddit side
			logger.info("Discord process is shutting down now")
			realCleanShutDown = True
			p.join()
			break
		await asyncio.sleep(queuePoll)

@bot.event
async def on_ready():
	await bot.change_presence(game=discord.Game(name='b.help for commands', type=1))
	logger.info('Discord log in success!')

# check that's pretty useful
async def is_admin(ctx):
	if ctx.author.top_role.permissions.manage_channels:
		return True
	else:
		await ctx.send("Sorry, you can't use this command! :confused:")
		return False

@bot.command()
async def checkUser(ctx, *args):
	"""Checks a reddit user's karma on furry_irl and in total"""
	if len(args) <= 0:
		 await ctx.send("You need to specify a reddit user!\neg. `b.check SimStart`")
	else:
		logger.info("check called: " + args[0])
		usrS = await SnoopSnooAPI.async_getUserJSON(args[0])
		usr = SnoopSnooAPI.jsonStrToObj(usrS, False)
		totalC = 0
		totalS = 0
		firlC = 0
		firlK = 0
		needRefresh = False
		name = args[0]
		try:
			errCode = usr['error']
			if errCode == 404:
				# there was an error, try refreshing the user
				needRefresh = True
		except KeyError as e:
			# this means that all's good, do the rest of the stuff
			pass
		# Check the time of the last refresh
		if not needRefresh:
			updTime = usr['data']['metadata']['last_updated']
			uT = datetime.strptime(updTime, "%a, %d %b %Y %X %Z")
			nT = datetime.utcnow()
			dT = (nT - uT).total_seconds()
			if dT >= 14400:
				needRefresh = True
		if needRefresh:
			logger.info("user needed refresh...")
			await ctx.send("Give me a minute while I refresh " + fixUsername(args[0]) + "'s profile...")
			ref = await SnoopSnooAPI.async_refreshSnoop(args[0])
			if ref == "OK":
				# all is good, get the new user info
				usrS = await SnoopSnooAPI.async_getUserJSON(args[0])
				usr = SnoopSnooAPI.jsonStrToObj(usrS, False)
			elif ref.find("EXCEPTION") == 0:
				# some server side exception, tell user not to panic
				logger.warning("snoopsnoo error: " + ref)
				return await ctx.send("Oopsie Woopsie! SnoopSnoo made a little fucky wucky!\n(try again in a minute)")
			else:
				# something went wrong, say something and return
				logger.warning("refresh error: " + ref)
				return await ctx.send("Error getting info on " + fixUsername(args[0]) + ", are you sure the user exists?")
		try:
			updTime = usr['data']['metadata']['last_updated']
			name = usr['data']['username']
			totalC = usr['data']['summary']['comments']['all_time_karma']
			totalS = usr['data']['summary']['submissions']['all_time_karma']
			# async doesn't matter when string is provided
			firl = SnoopSnooAPI.getSubredditActivity(args[0], subreddit, usrS)
			if firl != None:
				firlC = firl["comment_karma"]
				firlK = firl["submission_karma"]
		except KeyError as e:
			# probably couldn't find the subreddit, all's good, just pass
			pass
		# Build the response embed
		embd = discord.Embed(title="Overview for " + fixUsername(name), description="https://snoopsnoo.com/u/" + name + "\n https://www.reddit.com/u/" + name, color=0xa78c2c)
		embd.add_field(name="Total Karma", value="Submission: " + str(totalS) + " | Comment: " + str(totalC), inline=False)
		embd.add_field(name=subreddit+" Karma", value="Submission: " + str(firlK) + " | Comment: " + str(firlC), inline=False)
		embd.add_field(name="Last Refreshed: ", value=updTime, inline=True)
		await ctx.send(embed=embd)
		
		# Check if the user is able to join now, and add to queue if they are
		if(isQualified(firlK, firlC) and not (name.lower() in acceptedusers)):
			acceptedusers.append(name.lower())
			newUserQueue.put(name)

@bot.command()
@commands.check(is_admin)
async def ignore(ctx, *args):
	"""Manually specify a reddit user for this bot to ignore (mods only)"""
	if len(args) <= 0:
		await ctx.send("You need to specify a reddit user!\neg. `b.ignore SimStart`")
	else:
		logger.info("b.ignore called: "+args[0])
		acceptedusers.append(args[0].lower())
		await ctx.send(args[0] + " will be ignored by this bot :thumbsup:")

@bot.group()
async def ping(ctx):
	"""Set up username pings for #top-posts-of-day"""
	if ctx.invoked_subcommand is None:
		await ctx.send("Invalid command! use `b.ping user <@discord> <redditname>` or `b.ping me <redditname>`")

@ping.command()
@commands.check(is_admin)
async def user(ctx, member: discord.Member=None, redditname: str=None):
	"""Associate a discord user to a reddit username (mods only)"""
	if member is None or redditname is None:
		await ctx.send("You need to specify both a Discord user and a reddit username,\neg. `b.ping user @SimStart SimStart`")
	else:
		logger.info("b.ping user called: "+str(member.id)+" ; "+redditname)
		if not redditname.lower() in acceptedusers:
			await ctx.send("Couldn't find '"+redditname+"' in accepted users, are you sure their name is spelled correctly?")
		else:
			userMap[0].append(redditname.lower())
			userMap[1].append(str(member.id))
			FileParser.writeNestedList("usermap.txt", userMap, 'w')
			await ctx.send("Added "+fixUsername(redditname)+" to the ping list :thumbsup:")

@ping.command()
async def me(ctx, redditname: str=None):
	"""Associate a reddit username to your discord name"""
	if redditname is None:
		await ctx.send("You need to specify a reddit username,\neg. `b.ping me SimStart`")
	else:
		logger.info("b.ping me called: "+str(ctx.author.id)+" ; "+redditname)
		if not redditname.lower() in acceptedusers:
			await ctx.send("Couldn't find '"+redditname+"' in accepted users, are you sure their name is spelled correctly?")
		else:
			userMap[0].append(redditname.lower())
			userMap[1].append(str(ctx.author.id))
			FileParser.writeNestedList("usermap.txt", userMap, 'w')
			await ctx.send("Added "+fixUsername(redditname)+" to the ping list :thumbsup:")

@ping.command()
@commands.check(is_admin)
async def remove(ctx, redditname: str=None):
	"""Remove all associations used for a reddit user (mods only)"""
	if redditname is None:
		await ctx.send("You need to specify a reddit username,\neg. `b.ping remove SimStart`")
	else:
		logger.info("b.ping remove called: "+redditname)
		num = 0
		while redditname.lower() in userMap[0]:
			idx = userMap[0].index(redditname.lower())
			userMap[0].pop(idx)
			userMap[1].pop(idx)
			num += 1
		FileParser.writeNestedList("usermap.txt", userMap, 'w')
		await ctx.send("Removed "+str(num)+" instances of "+fixUsername(redditname)+" from the ping list :thumbsup:")

if __name__ == '__main__':
	print("BouncerBot : " + VERSION + "\nCreated by SockHungryClutz for the Furry Shitposting Guild\n(All further non-error messages will be output to logs)")
	# Start the logger
	logger = RollingLogger_Async(logname, filesizemax, numlogsmax, logVerbosity)
	
	# Create the shared list between the processes
	man = Manager()
	acceptedusers = man.list(aul)
	
	# Create the reddit bot and spin it off to a subprocess before starting discord
	p = Process(target=makeRedditBot, args=(config, queueList, acceptedusers,))
	p.start()
	
	# Finally, run the discord bot
	theLoop = bot.loop
	theLoop.create_task(check_user_queue())
	theLoop.create_task(check_post_queue())
	# Work around discord heartbeat timeouts on lesser hardware (raspberry pi)
	isFirstLoop = True
	while not realCleanShutDown:
		# Hack, thanks Hornwitser
		if bot.is_closed and not isFirstLoop:
			logger.warning("Bot closed, attempting reconnect...")
			bot._closed.clear()
			bot.http.recreate()
		try:
			isFirstLoop = False
			theLoop.run_until_complete(bot.start(token))
		except BaseException as e:
			logger.warning("Discord connection reset:\n" + str(e))
		finally:
			time.sleep(60)
	theLoop.run_until_complete(bot.logout())
	logger.closeLog()
	theLoop.close()
