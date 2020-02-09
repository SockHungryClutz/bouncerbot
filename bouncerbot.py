"""
BouncerBot - Python bot to assist the Furry Shitposting Guild
Many months of weird optimizations led this to be a mess of processes that
probably aren't necessary, so here's what they look like:
(lines indicate interprocess communication)

 DiscordBot -- SharedUserList -- RedditBot

The discord and reddit bots are also async, meaning everything is a
weird but efficient mess. DiscordBot process can also make processes
to handle checking large numbers of users
"""
import os
import discord
from discord.ext import commands
import asyncio
import configparser
import time
from datetime import datetime
from multiprocessing import Process, Queue, Manager
import redditbot
from sheriapi import SheriAPI
from RollingLogger import RollingLogger_Sync
from FileParser import FileParser

VERSION = '2.3.0a'

bot = commands.Bot(command_prefix='b.', description='BouncerBot '+VERSION+' - Helper bot to automate some tasks for the Furry Shitposting Guild\n(use "b.<command>" to give one of the following commands)', case_insensitive=True)

# Read configuration, default global values
config = configparser.ConfigParser()
token = ''
queuePoll = 60
logname = ''
filesizemax = 8000
numlogsmax = 5
logVerbosity = 4
subreddit = ''
MAX_COMMENT_KARMA = 0
REQUIRED_KARMA_TOTAL = 10000
# keys in here are int, else they're assumed to be str
config_int_map = ['max_comment_karma', 'total_karma_required']
def reloadConfig():
    global config, token, queuePoll, logname, filesizemax, numlogsmax, logVerbosity, subreddit, MAX_COMMENT_KARMA, REQUIRED_KARMA_TOTAL
    config.read('botconfig.ini')
    token = config['discord_creds']['token']
    queuePoll = int(config['timing']['discord_queue_poll'])
    logname = config['logging']['discord_log_name']
    filesizemax = int(config['logging']['max_file_size'])
    numlogsmax = int(config['logging']['max_number_logs'])
    logVerbosity = int(config['logging']['log_verbosity'])
    subreddit = config['general']['subreddit']
    MAX_COMMENT_KARMA = int(config['general']['max_comment_karma'])
    REQUIRED_KARMA_TOTAL = int(config['general']['total_karma_required'])
reloadConfig()

lastMessageFrom = ""
messageComboBreak = True
realCleanShutDown = False
p = None

# Get the accepted users list
aul = FileParser.parseFile("acceptedusers.txt", False)

# Mapping of reddit usernames to discord id's and DM channels
userMap = FileParser.parseFile("usermap.txt", True)

# Create the queues the processes will use to communicate
newUserQueue = Queue()
newPostQueue = Queue()
configQueue = Queue()
queueList = [newUserQueue, newPostQueue, configQueue]
# Extra stuff for the check file process
filesAwaited = 0
fileQueue = Queue()
fileprocs = []

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

# Does processing for files of users to check
def file_check(oldfn, newfn, channel, resultq):
    users = FileParser.parseFile(newfn, False);
    # delete file after loading
    os.remove(newfn)
    fileloop = asyncio.new_event_loop()
    filetasks = []
    results = []
    #for usr in users:
    #    filetasks.append(fileloop.create_task(process_user(usr)))
    try:
        #done,notdone = fileloop.run_until_complete(asyncio.wait(filetasks, return_when=asyncio.ALL_COMPLETED))
        for usr in users:
            done = fileloop.run_until_complete(process_user(usr))
            results.append(done)
        results = sorted(results, key=lambda s: s.lower())
        results.insert(0, '"Username", "Total Karma", "Submission Karma", "Comment Karma", "Notes"')
        FileParser.writeList(oldfn+'_results.txt',results,'w')
        resultq.put([oldfn, channel])
    except BaseException as e:
        print("Exception in file_check: " + str(e))
    fileloop.close()

# Async routine that checks one user for the above function
async def process_user(usr):
    maxServRetry = 2
    maxUsrRetry = 1
    result = -1
    while result < 0 and maxServRetry >= 0 and maxUsrRetry >= 0:
        result,totalC,totalS,firlC,firlK,updTime = await check_user(usr, None)
        # All these users should have > 0 subreddit karma, treat this as a server error
        if result == -1 or firlK < 1:
            maxServRetry -= 1
        elif result == -2:
            maxUsrRetry -= 1
    if result == -1:
        return usr+', 0, 0, 0, "Server side SnoopSnoo Error occurred"'
    elif result == -2:
        return usr+', 0, 0, 0, "User not found, do they exist?"'
    else:
        return usr+", "+str(firlC+firlK)+", "+str(firlK)+", "+str(firlC)+", OK"

# Checks post and user queues from the reddit side, messaging when any are ready
async def check_user_queue():
    global realCleanShutDown
    await bot.wait_until_ready()
    while not bot.is_closed() and not realCleanShutDown:
        while not newUserQueue.empty():
            newUsr = newUserQueue.get()
            logger.info("new user accepted: "+newUsr)
            redditurl = "https://www.reddit.com/u/" + newUsr
            snoopurl = "https://snoopsnoo.com/u/" + newUsr
            msg = fixUsername(newUsr) + " is now eligible for entry! :grinning:\n" + redditurl + "\n" + snoopurl
            try:
                await bot.get_channel(findChannel(config['general']['user_announce_channel'])).send(content=msg, embed=None)
            except BaseException as e:
                logger.error("Failed to send user message!\n" + str(e))
        await asyncio.sleep(queuePoll)

async def check_post_queue():
    global realCleanShutDown
    await bot.wait_until_ready()
    while not bot.is_closed() and not realCleanShutDown:
        closeDiscord = False
        while not newPostQueue.empty():
            newPost = newPostQueue.get()
            if newPost == None:
                closeDiscord = True
                continue
            isSpoiler = False
            # don't log post title, emojis can break shit
            logger.info("added post: "+newPost[1]+' ; '+newPost[2]+' ; '+newPost[3])
            if newPost[1].lower() in userMap[0]:
                uidx = userMap[0].index(newPost[1].lower())
                duser = await bot.fetch_user(int(userMap[1][uidx]))
                realuser = duser.mention + " (" + fixUsername(newPost[1]) + ")"
            else:
                realuser = fixUsername(newPost[1])
            # trailing '?' denotes spoiler, not a valid url since params come after it
            if newPost[-1][0] == '?':
                isSpoiler = True
                newPost = newPost[:-1]
            realtitle = fixUsername(newPost[0])
            if isSpoiler:
                msg = realtitle+"\nuser: "+realuser+"\ncontent: ||"+newPost[2]+"||\npost: ||"+newPost[3]+"||"
            else:
                msg = realtitle+"\nuser: "+realuser+"\ncontent: "+newPost[2]+"\npost: "+newPost[3]
            try:
                # trailing '!' denotes NSFW post now, can't happen otherwise since it'd make an invalid url
                if newPost[-1][0] == '!':
                    await bot.get_channel(findChannel(config['general']['nsfw_post_channel'])).send(content=msg, embed=None)
                else:
                    await bot.get_channel(findChannel(config['general']['post_announce_channel'])).send(content=msg, embed=None)
            except BaseException as e:
                logger.error("Failed to send post message!\n" + str(e))
        if closeDiscord:
            # all other queues should be closed by the reddit side
            configQueue.close()
            logger.info("Discord process is shutting down now")
            realCleanShutDown = True
            p.join()
            break
        await asyncio.sleep(queuePoll)
    await bot.logout()

# another check for file queue
async def check_file_queue():
    global filesAwaited, realCleanShutDown
    await bot.wait_until_ready()
    while not bot.is_closed() and not realCleanShutDown:
        if filesAwaited == 0:
            await asyncio.sleep(30)
        else:
            while not fileQueue.empty():
                l = fileQueue.get()
                fn = l[0]
                ch = l[1]
                # join in order they were made I guess
                fileprocs[0].join()
                del fileprocs[0]
                list_files = [
                    discord.File(fn+'_results.txt', fn+'_Results.csv'),
                ]
                await bot.get_channel(findChannel(ch)).send(fn + " Done!", files=list_files)
                os.remove(fn+'_results.txt')
                filesAwaited -= 1
            await asyncio.sleep(5)

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game(name='b.help for commands', type=1))
    logger.info('Discord log in success!')

# overwrite the on_message handler to accept DM's
@bot.event
async def on_message(message):
    global lastMessageFrom, messageComboBreak
    # ignore other bots I guess
    if not message.author.bot:
        # isinstance is poor form, but what're you going to do?
        if isinstance(message.channel, discord.DMChannel):
            if message.content[:4].lower() == "anon":
                # Keep users anonymous
                logger.info("Received message from Anonymous User ; " + str(message.id))
                # Can't do much here since the bot needs their discord ID to persist between restarts
                # and any obfuscation could eventually be cracked
                key = str(message.author.id) + "anon"
                auth = "Anonymous User"
                msg = message.content[4:]
            else:
                logger.info("Received message from " + str(message.author.id) + " ; " + str(message.id))
                key = str(message.author.id)
                auth = message.author.name+" ("+message.author.mention+")"
                msg = message.content
            if not (key in userMap[3]):
                if key in userMap[2]:
                    idx = userMap[2].index(key)
                else:
                    idx = len(userMap[2])
                    userMap[2].append(key)
                    FileParser.writeNestedList("usermap.txt", userMap, 'w')
                # skip header if no other messages were posted to the channel since last message
                # and the author of the previous message is the same
                skipheader = (key == lastMessageFrom) and (messageComboBreak == False)
                if skipheader:
                    mail = msg
                else:
                    mail = "From: "+auth+"\n(reply with `b.reply "+str(idx)+" \"message here\"`, mute with `b.mute "+str(idx)+"`)\n\n"+msg
                lastMessageFrom = key
                # Get attachments, put in the URLs, don't save anything unknown to the bot
                try:
                    for item in message.attachments:
                        mail += "\n" + item.url
                except:
                    logger.warning("Could not get URL for all attachments")
                mailchannel = bot.get_channel(findChannel(config['general']['dm_channel']))
                messageComboBreak = False
                await mailchannel.send(mail)
            else:
                await message.channel.send("You are currently muted, DM the mods directly to appeal your mute")
        else:
            mailchannel = bot.get_channel(findChannel(config['general']['dm_channel']))
            if (message.channel.id == mailchannel.id) and (message.author.id != bot.user.id):
                messageComboBreak = True
            await bot.process_commands(message)

# check that's pretty useful
async def is_admin(ctx):
    if ctx.author.top_role.permissions.manage_channels:
        return True
    else:
        await ctx.send("Sorry, you can't use this command! :confused:")
        return False

# check that's very restrictive, only for the owner of the app
async def is_owner(ctx):
    appinfo = await ctx.bot.application_info()
    if ctx.author.id == appinfo.owner.id:
        return True
    else:
        await ctx.send("This super-secret command only works for my owner!")
        return False

# async function to slide into them DM's
async def get_dm_channel(auth):
    dm_chan = auth.dm_channel
    if dm_chan == None:
        await auth.create_dm()
        dm_chan = auth.dm_channel
    return dm_chan

# Async function check a single reddit user, returns a code for success/failure
async def check_user(username, ctx):
    ref = ""
    usr = None
    totalC = 0
    totalS = 0
    firlC = 0
    firlK = 0
    updTime = ""
    # some default value to prevent errors
    if ctx != None:
        logger.info("user needed refresh...")
        await ctx.send("Give me a minute while I refresh " + fixUsername(username) + "'s profile...")
    ref,usr = await SheriAPI.async_getUserInfo(username)
    if ref.find("EXCEPTION") == 0:
        # some server side exception, tell user not to panic
        if ctx != None:
            logger.warning("snoopsnoo error: " + ref)
        return -1,totalC,totalS,firlC,firlK,updTime
    elif ref.find("ERROR") == 0:
        # something went wrong, say something and return
        if ctx != None:
            logger.warning("refresh error: " + ref)
        return -2,totalC,totalS,firlC,firlK,updTime
    try:
        name = usr['username']
        totalC = usr['summary']['comments']['all_time_karma']
        totalS = usr['summary']['submissions']['all_time_karma']
        firl = SheriAPI.getSubredditActivity(username, subreddit, ref)
        if firl != None:
            firlC = firl["comment_karma"]
            firlK = firl["submission_karma"]
    except KeyError as e:
        # probably couldn't find the subreddit, all's good, just pass
        pass
    # return OK and the results
    return 0,totalC,totalS,firlC,firlK,updTime

@bot.command()
async def check(ctx, *args):
    """Checks reddit user or users' karma on furry_irl and in total"""
    global filesAwaited
    global fileprocs
    files = ctx.message.attachments
    if len(args) <= 0 and len(files) <= 0:
         await ctx.send("You need to specify a reddit user!\neg. `b.check SimStart`\nOr, attach a file of usernames to your message!")
    else:
        if len(files) > 0:
            # Prevent abuse by users
            if ctx.author.top_role.permissions.manage_channels:
                logger.info("check called with " + str(len(files)) + " files")
                # process files one at a time, but do all at once for each file
                for f in files:
                    tempfn = "temp"+str(filesAwaited)+".txt"
                    try:
                        await f.save(tempfn)
                    except BaseException as e:
                        logger.warning("Save file failed: " + e)
                        return await ctx.send("Error! Could not open file! :dizzy_face:")
                    await ctx.send("Checking users in " + f.filename + ", hang tight, this could take awhile...")
                    fileprocs.append(Process(target=file_check, args=(f.filename,tempfn,ctx.channel.name,fileQueue,)))
                    fileprocs[filesAwaited].start()
                    filesAwaited += 1
            else:
                await ctx.send("Sorry! Only mods can check files!")
        else:
            name = args[0]
            logger.info("check called: " + args[0])
            result,totalC,totalS,firlC,firlK,updTime = await check_user(args[0], ctx)
            if result == -1:
                return await ctx.send("Oopsie Woopsie! Sheri must have messed up!\n(try again in a minute)")
            elif result == -2:
                return await ctx.send("Error getting info on " + fixUsername(args[0]) + ", are you sure the user exists?")
            else:
                # Build the response embed
                if updTime == "":
                    updTime = "Now"
                embd = discord.Embed(title="Overview for " + fixUsername(name), description="https://www.reddit.com/u/" + name + "\nhttps://snoopsnoo.com/u/" + name, color=0xa78c2c)
                embd.add_field(name="Total Karma", value="Submission: " + str(totalS) + " | Comment: " + str(totalC), inline=False)
                embd.add_field(name=subreddit+" Karma", value="Submission: " + str(firlK) + " | Comment: " + str(firlC), inline=False)
                embd.add_field(name="Last Refreshed: ", value=updTime, inline=True)
                await ctx.send(embed=embd)
                
                # Check if the user is able to join now, and add to queue if they are
                if(isQualified(firlK, firlC) and not (name.lower() in acceptedusers)):
                    acceptedusers.append(name.lower())
                    newUserQueue.put(name)

@bot.command()
async def refresh(ctx, *args):
    """Manually refresh a user profile on SnoopSnoo"""
    if len(args) <= 0:
        await ctx.send("You need to specify a reddit user!\neg. `b.refresh SimStart`")
    else:
        logger.info("b.refresh called: "+args[0])
        await ctx.send("Give me a minute while I refresh" + args[0] + "'s profile...")
        ref,usr = await SheriAPI.async_refreshSnoop(args[0])
        if ref.find("EXCEPTION") == 0:
            # some server side exception, tell user not to panic
            logger.warning("snoopsnoo error: " + ref)
            return await ctx.send("Oopsie Woopsie! SnoopSnoo made a little fucky wucky!\n(try again in a minute)")
        elif ref.find("ERROR") == 0:
            # something went wrong, say something and return
            logger.warning("refresh error: " + ref)
            return await ctx.send("Error getting info on " + fixUsername(args[0]) + ", are you sure the user exists?")
        else:
            return await ctx.send("Updated SnoopSnoo Profile now available!\nhttps://snoopsnoo.com/u/" + args[0])

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
        await ctx.send("Invalid command! use `b.ping user <@discord> <redditname>` or `b.ping member <discordname> <redditname>` or `b.ping me <redditname>`")

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

@ping.command()
@commands.check(is_admin)
async def cleanup(ctx):
    """Cleanup unused pings and print new users (mods only)"""
    logger.info("b.ping cleanup called")
    FileParser.writeNestedList("usermap_backup.txt", userMap, 'w')
    guilds = await bot.fetch_guilds().flatten()
    activeIdList = []
    for guild in guilds:
        if guild.large:
            await bot.request_offline_members(guild.id)
        for member in guild.members:
            if member.id != bot.user.id:
                activeIdList.append(member.id)
    # if user in pinglist isn't a member, remove them
    removedPings = []
    itr = len(userMap[1]) - 1
    while itr >= 0:
        if int(userMap[1][itr]) not in activeIdList:
            removedPings.append(userMap[0][itr])
        itr -= 1
    # if member isn't in ping list, notify mods
    notifyList = []
    itr = len(activeIdList) - 1
    while itr >= 0:
        if str(activeIdList[itr]) not in userMap[1]:
            newUser = await bot.fetch_user(activeIdList[itr])
            notifyList.append(newUser.name)
        itr -= 1
    # call out any duplicates
    duperedd = []
    dupedisc = []
    seenr = []
    seend = []
    itr = len(userMap[0]) - 1
    while itr >= 0:
        if (userMap[0][itr] in seenr) and (userMap[0][itr] not in duperedd):
            duperedd.append(userMap[0][itr])
        else:
            seenr.append(userMap[0][itr])
        if (userMap[1][itr] in seend) and (userMap[1][itr] not in dupedisc):
            dupedisc.append(userMap[1][itr])
        else:
            seend.append(userMap[1][itr])
        itr -= 1
    # send results
    if len(removedPings) > 0:
        result = "Registered reddit users who aren't members: (use `b.ping remove` to remove)\n"
        for rmember in removedPings:
            result += rmember + ", "
    else:
        result = "No erraneous ping entries found"
    if len(notifyList) > 0:
        result += "\n\nUsers who need ping setup:\n"
        for nmember in notifyList:
            result += nmember + ", "
    else:
        result += "\n\nNo users need ping setup"
    if len(duperedd) > 0:
        result += "\n\nReddit usernames that map to multiple discord users: (fix by using `b.ping remove` then readding only the correct ping)"
        for rname in duperedd:
            tempidx = 0
            result += "\n" + rname + " - Maps to: "
            while rname in userMap[0][tempidx:]:
                usr = await bot.fetch_user(userMap[1][userMap[0][tempidx:].index(rname)+tempidx])
                result += usr.name + ', '
                tempidx = userMap[0][tempidx:].index(rname)+tempidx+1
    else:
        result += "\n\nNo duplicate reddit user entries"
    if len(dupedisc) > 0:
        result += "\n\nDiscord users with multiple reddit users: (fix by using `b.ping remove` on incorrect reddit users)"
        for discid in dupedisc:
            tempidx = 0
            usr = await bot.fetch_user(int(discid))
            result += "\n" + usr.name + " - Maps to: "
            while discid in userMap[1][tempidx:]:
                result += userMap[0][userMap[1][tempidx:].index(discid)+tempidx] + ', '
                tempidx = userMap[1][tempidx:].index(discid)+tempidx+1
    else:
        result += "\n\nNo duplicate Discord ID entries"
    await ctx.send(result)

# mod only command to show mod commands, viewable from b.help
@bot.command()
@commands.check(is_admin)
async def modhelp(ctx):
    """Shows moderator commands (mods only)"""
    logger.info("b.modhelp called")
    await ctx.send("""```
Super-Special mod-only commands
(use "b.<command>" to give one of the following commands)

sendlists   Send the lists of accepted and pingable users
sendmessage Send a DM on behalf of the moderators
announce    Make an announcement on behalf of the moderators
reply       Reply to a received modmail DM
mute        Mute all modmail DMs from a user
unmute      Undo a mute
configure   Set a config value for this bot
    ```""")

# secret command to send the current user lists
@bot.command(hidden=True)
@commands.check(is_admin)
async def sendlists(ctx):
    """Sends the lists of accepted and pingable users (mods only)"""
    logger.info("b.sendLists called")
    list_files = [
        discord.File('acceptedusers.txt', 'AcceptedUsers.txt'),
        discord.File('usermap.txt', 'PingList.txt'),
    ]
    await ctx.send(files=list_files)

# admin command to message a user on behalf of the admins
@bot.command(hidden=True)
@commands.check(is_admin)
async def sendmessage(ctx, *args):
    """Message a user on behalf of the mods (mods only)"""
    if len(args) <= 1:
        await ctx.send("You need to specify a discord user and message!\neg. `b.sendmessage SimStart \"good bot\"`")
    elif len(args) > 2:
        await ctx.send("Be sure to wrap your message in double quotes!\neg. `b.sendmessage SimStart \"good bot\"`")
    else:
        logger.info("b.sendmessage called by: " + str(ctx.author.id) + " ; " + args[0] + " ; " + args[1])
        usr = ctx.guild.get_member_named(args[0])
        if usr != None:
            dm_chan = await get_dm_channel(usr)
            if dm_chan != None:
                success = True
                msg = args[1]
                try:
                    for item in ctx.message.attachments:
                        msg += "\n" + item.url
                except:
                    logger.warning("Could not get URL for all attachments")
                try:
                    await dm_chan.send(msg)
                except BaseException as e:
                    success = False
                if success:
                    await ctx.send("Message sent! :e_mail:")
                else:
                    await ctx.send("Could not send message, user not in server or is blocking me!")
            else:
                await ctx.send("Failed to open DM channel! Try again!")
                logger.warning("sendmessage failed: could not slide into DM's!")
        else:
            await ctx.send("Could not find the user, either use their display name or their discord identifier (username#1234)")

# reply to a modmail DM
@bot.command(hidden=True)
@commands.check(is_admin)
async def reply(ctx, *args):
    """Reply to a modmail DM (mods only)"""
    if len(args) <= 1:
        await ctx.send("You need to specify an ID and message!\neg. `b.reply 0 \"hello\"`")
    elif len(args) > 2:
        await ctx.send("Be sure to wrap your message in double quotes!\neg. `b.reply 0 \"hello\"`")
    else:
        logger.info("b.reply called by " + str(ctx.author.id) + " ; " + args[0])
        try:
            idx = int(args[0])
        except:
            await ctx.send(args[0] + " is not a valid index! try again")
            return
        if len(userMap[2]) <= idx:
            await ctx.send(args[0] + " is not a valid index! try again")
        else:
            id = userMap[2][idx]
            if id[-4:] == "anon":
                id = id[:-4]
            try:
                dm_chan = await get_dm_channel(bot.get_user(int(id)))
                if dm_chan != None:
                    msg = args[1]
                    try:
                        for item in ctx.message.attachments:
                            msg += "\n" + item.url
                    except:
                        logger.warning("Could not get URL for all attachments")
                    await dm_chan.send(msg)
                    await ctx.send("Message sent! :e_mail:")
                else:
                    await ctx.send("Failed to open DM channel! Try again!")
            except:
                await ctx.send("Could not send message, user not in server or is blocking me!")

# mute DMs from a user
@bot.command(hidden=True)
@commands.check(is_admin)
async def mute(ctx, *args):
    """Mute all modmail DMs from a user (mods only)"""
    if len(args) < 1:
        await ctx.send("You need to specify an ID!\neg. `b.mute 0`")
    else:
        logger.info("b.mute called by " + str(ctx.author.id) + " ; " + args[0])
        try:
            idx = int(args[0])
        except:
            await ctx.send(args[0] + " is not a valid index! try again")
            return
        if len(userMap[2]) <= idx:
            await ctx.send(args[0] + " is not a valid index! try again")
        else:
            id = userMap[2][idx]
            userMap[3].append(id)
            FileParser.writeNestedList("usermap.txt", userMap, 'w')
            await ctx.send("Ignoring DMs from User ID " + str(idx) + ":thumbsup:")

# unmute DMs from a user
@bot.command(hidden=True)
@commands.check(is_admin)
async def unmute(ctx, *args):
    """Undo a mute (mods only)"""
    if len(args) < 1:
        await ctx.send("You need to specify an ID!\neg. `b.unmute 0`")
    else:
        logger.info("b.unmute called by " + str(ctx.author.id) + " ; " + args[0])
        try:
            idx = int(args[0])
        except:
            await ctx.send(args[0] + " is not a valid index! try again")
            return
        if len(userMap[2]) <= idx:
            await ctx.send(args[0] + " is not a valid index! try again")
        else:
            id = userMap[2][idx]
            if id in userMap[3]:
                midx = userMap[3].index(id)
                userMap[3].pop(midx)
                FileParser.writeNestedList("usermap.txt", userMap, 'w')
                await ctx.send("Unmuting DMs from User ID " + str(idx) + ":thumbsup:")
            else:
                await ctx.send("User ID " + str(idx) + " is not currently muted")

# admin command to post an announcement
@bot.command(hidden=True)
@commands.check(is_admin)
async def announce(ctx, *args):
    """Make an announcement (mods only)"""
    if len(args) <= 0:
        await ctx.send("You need to write a message!\neg. `b.sendannouncement \"Don't Panic! this is just a test!\"`")
    elif len(args) > 1:
        await ctx.send("Be sure to wrap your message in double quotes!\neg. `b.sendannouncement \"Don't Panic! this is just a test!\"`")
    else:
        logger.info("b.announce called by: " + str(ctx.author.id))
        await bot.get_channel(findChannel(config['general']['mod_announce_channel'])).send(content=args[0], embed=None)
        await ctx.send("Announcement posted! :loudspeaker:")

# set a configuration value from a command
@bot.command(hidden=True)
@commands.check(is_admin)
async def configure(ctx, *args):
    global config
    if len(args) <= 1:
        await ctx.send("You need to specify a key and value!\neg. `b.configure total_karma_required 15000`")
    elif len(args) > 2:
        await ctx.send("Too many arguments! You only need a key and value!\neg. `b.configure total_karma_required 15000`")
    else:
        logger.info("b.configure called by " + str(ctx.author.id) + " ; " + args[0])
        if args[0] in config['general'] and not args[0] == "subreddit":
            if args[0] in config_int_map:
                try:
                    int(args[1])
                except:
                    await ctx.send(args[1]+" is not an integer as expected!")
                    return
            config['general'][args[0]] = args[1]
            configQueue.put([args[0], args[1]])
            with open('botconfig.ini', 'w') as ini:
                config.write(ini)
            reloadConfig()
            await ctx.send("Config updated, "+args[0]+" = "+args[1])
        else:
            await ctx.send("Not a valid config key, see https://github.com/SockHungryClutz/bouncerbot/blob/master/botconfig.ini")

# super-secret command to DM the current cache and settings for the bot
# THIS WILL SEND THE API KEY INFORMATION TOO, SO IT IS ONLY FOR THE OWNER
@bot.command(hidden=True)
@commands.check(is_owner)
async def sendCache(ctx):
    """Sends ALL importnat background info about this bot"""
    logger.info("b.sendCache called")
    cache_files = [
        discord.File('redditcache.txt', 'redditcache.txt'),
        discord.File('botconfig.ini', 'botconfig.ini'),
    ]
    dm_chan = await get_dm_channel(ctx.author)
    if dm_chan != None:
        await dm_chan.send(files=cache_files)
    else:
        logger.warning("sendcache failed: could not slide into DM's!")

# super-secret command that sends the logs via DM
# less dangerous than above, but still owner-only
@bot.command(hidden=True)
@commands.check(is_owner)
async def sendLogs(ctx):
    """Sends bouncerbot's logs for analysis"""
    logger.info("b.sendLogs called")
    log_files = [
        discord.File('RedditLog.log', 'RedditLog.txt'),
        discord.File('DiscordLog.log', 'DiscordLog.txt'),
    ]
    dm_chan = await get_dm_channel(ctx.author)
    if dm_chan != None:
        await dm_chan.send(files=log_files)
    else:
        logger.warning("sendlogs failed: could not slide into DM's!")

if __name__ == '__main__':
    print("BouncerBot : " + VERSION + "\nCreated by SockHungryClutz for the Furry Shitposting Guild\n(All further non-error messages will be output to logs)")
    # Start the logger
    logger = RollingLogger_Sync(logname, filesizemax, numlogsmax, logVerbosity)
    
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
    theLoop.create_task(check_file_queue())
    # Work around discord heartbeat timeouts on lesser hardware (raspberry pi)
    while not realCleanShutDown:
        # Hopefully don't need to use a hack for this...
        if bot.is_closed():
            logger.warning("Bot closed, attempting reconnect...")
            bot.clear()
        try:
            theLoop.run_until_complete(bot.start(token))
        except BaseException as e:
            logger.warning("Discord connection reset:\n" + str(e))
        finally:
            time.sleep(60)
    logger.closeLog()
    theLoop.close()
