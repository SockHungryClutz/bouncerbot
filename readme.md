# BouncerBot

Helper bot for the Furry Shitposting Guild

-----

## Requirements

* [Python](https://www.python.org/downloads/release/python-366/) 3.4-3.6 (3.7+ **MIGHT** work)  
* Use [pip](https://pypi.org/project/pip/) to install the following: (or use `pip install -r requirements.txt`)
  * [requests](https://pypi.org/project/requests/)  
  * [discord.py](https://pypi.org/project/discord.py/) (V 1.1 or greater)  
  * [praw](https://pypi.org/project/praw/) (V6.1.0 or greater for spoiler support!)  
* Everything else should be installed with the other packages

**NOTE**: As of discord.py 1.0.0 or so, use the discord.py repository and not discord-rewrite!

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

To run this headless, use the following command in a bash terminal:
`nohup python3 bouncerbot.py & disown`

The bot will print a startup message, and all future messages will be logged as long as it's a non-fatal error.

-----

## Other

* To stop, edit `closegracefully.txt` to say anything other than `no` with a new line (the new line MUST be included)  
* To clear the reddit cache (only works between runs), edit `redditcache.txt` to have 5 blank lines, and put `0` on the first line  
* Clearing the usermap can be done similarly, edit `usermap.txt` to have 3 blank lines
* For all other support questions and concerns, please don't bother me

-----

## About User Privacy

I created the anonymous modmail feature with the intentions that users can step forward with information that they would not be comfortable disclosing when the information is attached to their username. However, there is potential for abuse on both ends of the message; users can spread misinformation and spam to mods, and the mods can ask the owner (me) to unmask who certain anonymous users are, violating the trust provided by anonymous modmail. Moderators must exercise caution, and be skeptical of whatever anonymous mail comes in. As the saying goes, "trust, but verify." In the same vein, moderators must trust in the anonymous modmail, and understand that unmasking anonymous users leads to distrust in the system, and negates the purpose of anonymous modmail. That being said, unmasking users is only possible by the owner (me). Why is it possible at all? Bouncerbot must be able to decipher the Discord ID's of users that send anonymous modmail to ensure continuity between conversations and that replies are sent to the proper user. As such, the user IDs are stored on disk, and if they were obfuscated, then it must always be possible to unobfuscate, this is essential to how Bouncerbot operates.

As for my view on unmasking users: it is not an option to be taken lightly. I firmly believe that unmasking users creates more problems than it could ever solve. The system of trust built around having anonymous modmail would be entirely ruined after the first unmasking, leading to the nullification of its purpose, and sowing immense distrust in the mods. This is the last thing that I want to happen. I believe that there will always be better ways to solve issues with anonymous users, and nothing is worth the dire consequence of unmasking any user. It is with this philosophy that I will petition against any movement to unmask anonymous users in mod mail, if only to be devil's advocate and make all stop and consider the ramifications of doing so.