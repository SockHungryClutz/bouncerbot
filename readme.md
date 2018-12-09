# BouncerBot

Helper bot for the Furry Shitposting Guild

-----

## Requirements

* [Python](https://www.python.org/downloads/release/python-366/) 3.4-3.6 (3.7+ **MIGHT** work)  
* Use [pip](https://pypi.org/project/pip/) to install the following:  
  * [requests](https://pypi.org/project/requests/)  
  * [discord-rewrite](https://pypi.org/project/discord-rewrite/) (**NOT** discord.py)  
  * [praw](https://pypi.org/project/praw/)  
* Everything else should be installed with the other packages

**NOTE**: you will have to use `pip install git+https://github.com/Rapptz/discord.py@rewrite` to install discord-rewrite, the version on pypi has issues

-----

## Setup

Setup a reddit app by following the first part of [these](https://github.com/reddit-archive/reddit/wiki/OAuth2) instructions. Also follow [these steps](https://github.com/reactiflux/discord-irc/wiki/Creating-a-discord-bot-&-getting-a-token) to get a discord bot too. Save all those secret special tokens and strings under the respective fields in `botconfig.ini`.

While you're in `botconfig.ini`, set the channels to the names of the channels where you want the bot to send each of the types of comments. You can also adjust how long between each asynchronous check for many different conditions (each of those values is in seconds). The karma requirements dictate the total amount of karma needed to have the bot send a message for review, as well as how much comment karma counts for.

Log file names as well as max log file size and max number of log files can be adjusted in the logging section of the config, default is 5 logs each for both reddit and discord bots, and each log is at most 16MB

Be sure to invite the bot using the app id from discord and permissions that allow reading and sending messages and using embed.

-----

## Running

Navigate to the directory that contains this project in a command, powershell, or terminal window, and run:  
`python bouncerbot.py`

The bot will print a startup message, and all future messages will be logged as long as it's a non-fatal error.

-----

## Other

* To stop, edit `closegracefully.txt` to say anything other than `no` with a new line (the new line MUST be included)  
* To clear the reddit cache (only works between runs), edit `redditcache.txt` to have 5 blank lines, and put `0` on the first line  
* Clearing the usermap can be done similarly, edit `usermap.txt` to have 3 blank lines
* For all other support questions and concerns, please don't bother me