"""
BouncerBot - Python bot to assist the Furry Shitposting Guild
I wanted this to be 2-in-1 reddit and discord bot, and also have separate
processes for both, but the discord bot doesn't lend itself well to being
put inside a class and have dependencies like queues to talk to other 
processes. As a compromise that I don't like, discord bot has the main
process while reddit takes a separate process.
"""
import discord
from discord.ext import commands
import asyncio
import configparser
import time
from datetime import datetime
from multiprocessing import Process, Queue
import redditbot
from snoopsnoo import SnoopSnooAPI
from RollingLogger import RollingLogger
from FileParser import FileParser
from LockedList import LockedList

VERSION = '1.1.2'

bot = commands.Bot(command_prefix='b.', description='BouncerBot '+VERSION+' - Helper bot to automate some tasks for the Furry Shitposting Guild\n(use "b.<command>" to give one of the following commands)')

# Read configuration
config = configparser.ConfigParser()
config.read('botconfig.ini')
token = config['discord_creds']['token']
queuePoll = int(config['general']['discord_queue_poll'])
logname = config['logging']['discord_log_name']
filesizemax = int(config['logging']['max_file_size'])
numlogsmax = int(config['logging']['max_number_logs'])
subreddit = config['general']['subreddit']
MAX_COMMENT_KARMA = int(config['general']['max_comment_karma'])
REQUIRED_KARMA_TOTAL = int(config['general']['total_karma_required'])
realCleanShutDown = False
p = None

# Init a locked list to use later
acceptedusers = LockedList(FileParser.parseFile("acceptedusers.txt", False))

# Create the queues the processes will use to communicate
newUserQueue = Queue()
newPostQueue = Queue()
queueList = [newUserQueue, newPostQueue]

# Start the discord logger
logger = RollingLogger(logname, filesizemax, numlogsmax)

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

# Checks post and user queues from the reddit side, messaging when any are ready
async def check_queues():
	await bot.wait_until_ready()
	await bot.change_presence(game=discord.Game(name='b.help for commands', type=1))
	while not bot.is_closed:
		closeDiscord = False
		while not newUserQueue.empty():
			newUsr = newUserQueue.get()
			logger.info("new user accepted: "+newUsr)
			redditurl = "https://www.reddit.com/u/" + newUsr
			snoopurl = "https://snoopsnoo.com/u/" + newUsr
			msg = newUsr + " is now eligible for entry! :grinning:\n" + redditurl + "\n" + snoopurl
			await bot.send_message(bot.get_channel(findChannel(config['general']['user_announce_channel'])), content=msg, embed=None)
		while not newPostQueue.empty():
			newPost = newPostQueue.get()
			if newPost == None:
				closeDiscord = True
				continue
			logger.info("added post: "+newPost[0]+' ; '+newPost[1]+' ; '+newPost[2])
			msg = "user: " + newPost[0] + "\ncontent: " + newPost[1] + "\npost: " + newPost[2]
			await bot.send_message(bot.get_channel(findChannel(config['general']['post_announce_channel'])), content=msg, embed=None)
		if closeDiscord:
			# all other queues should be closed by the reddit side
			logger.info("Discord process is shutting down now")
			realCleanShutDown = True
			p.join()
			break
		await asyncio.sleep(queuePoll)
	await bot.logout()

@bot.event
async def on_ready():
	logger.info('Discord log in success!')

@bot.command()
async def check(*args):
	"""Checks a reddit user's karma on furry_irl and in total"""
	if len(args) <= 0:
		 await bot.say("You need to specify a reddit user!\neg. `b.check SimStart`")
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
			await bot.say("Give me a minute while I refresh " + args[0] + "'s profile...")
			ref = await SnoopSnooAPI.async_refreshSnoop(args[0])
			if ref == "OK":
				# all is good, get the new user info
				usrS = await SnoopSnooAPI.async_getUserJSON(args[0])
				usr = SnoopSnooAPI.jsonStrToObj(usrS, False)
			elif ref.find("EXCEPTION") == 0:
				# some server side exception, tell user not to panic
				logger.warning("snoopsnoo error: " + ref)
				return await bot.say("Oopsie Woopsie! SnoopSnoo made a little fucky wucky!\n(try again in a minute)")
			else:
				# something went wrong, say something and return
				logger.warning("refresh error: " + ref)
				return await bot.say("Error getting info on " + args[0] + ", are you sure the user exists?")
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
		embd = discord.Embed(title="Overview for " + name, description="https://snoopsnoo.com/u/" + name + "\n https://www.reddit.com/u/" + name, color=0xa78c2c)
		embd.add_field(name="Total Karma", value="Submission: " + str(totalS) + " | Comment: " + str(totalC), inline=False)
		embd.add_field(name=subreddit+" Karma", value="Submission: " + str(firlK) + " | Comment: " + str(firlC), inline=False)
		embd.add_field(name="Last Refreshed: ", value=updTime, inline=True)
		await bot.say(embed=embd)
		
		# Check if the user is able to join now, and add to queue if they are
		acceptedusers.acquireLock()
		if(isQualified(firlK, firlC) and not (name.lower() in acceptedusers.getList())):
			acceptedusers.getList().append(name.lower())
			newUserQueue.put(name)
		acceptedusers.releaseLock()

@bot.command(pass_context=True)
async def ignore(ctx, *args):
	"""Manually specify a reddit user for this bot to ignore (mods only)"""
	if len(args) <= 0:
		await bot.say("You need to specify a reddit user!\neg. `b.ignore SimStart`")
	else:
		logger.info("b.ignore called: "+args[0])
		if ctx.message.author.top_role.permissions.manage_channels:
			#manualAddQueue.put(args[0])
			acceptedusers.acquireLock()
			acceptedusers.getList().append(args[0].lower())
			acceptedusers.releaseLock()
			await bot.say(args[0] + " will be ignored by this bot :thumbsup:")
		else:
			await bot.say("Sorry, you can't use this command! :confused:")

if __name__ == '__main__':
	print("BouncerBot : " + VERSION + "\nCreated by SockHungryClutz for the Furry Shitposting Guild\n(All further non-error messages will be output to logs)")
	# Create the reddit bot and spin it off to a subprocess before starting discord
	p = Process(target=makeRedditBot, args=(config, queueList, acceptedusers,))
	p.start()
	
	# Finally, run the discord bot
	bot.loop.create_task(check_queues())
	# Work around discord heartbeat timeouts on lesser hardware (raspberry pi)
	while not realCleanShutDown:
		try:
			bot.run(token)
		except BaseException:
			time.sleep(5)