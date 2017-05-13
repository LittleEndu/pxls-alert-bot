import inspect
import json
import logging
import os
import sys
import traceback
from datetime import datetime

import discord
import logbook
from discord.ext import commands

if not os.path.isfile("config.json"):
    import shutil

    shutil.copyfile("example-config.json", "config.json")

with open("config.json") as file_in:
    config = json.load(file_in)

bot = commands.Bot(command_prefix=config["prefix"], description='''pxls-alert-bot by LittleEndu''')

if not os.path.isdir("logs"):
    os.makedirs("logs")
bot.logger = logbook.Logger("Pxls")
bot.logger.handlers.append(
    logbook.FileHandler("logs/" + str(datetime.now().date()) + ".log", level="INFO", bubble=True))
bot.logger.handlers.append(logbook.StreamHandler(sys.stderr, level='INFO', bubble=True))
logging.root.setLevel(logging.INFO)


@bot.event
async def on_ready():
    bot.logger.info('Logged in as')
    bot.logger.info(bot.user.name)
    bot.logger.info(bot.user.id)
    bot.logger.info('------')
    try:
        if config['status']:
            game = discord.Game(name=config['status'])
            await bot.change_presence(game=game)
    except:
        pass


@bot.event
async def on_message(message):
    await bot.process_commands(message)


@bot.event
async def on_command_error(e, ctx):
    # Check the type of the error.
    if isinstance(e, (commands.errors.BadArgument, commands.errors.MissingRequiredArgument)):
        await bot.send_message(ctx.message.channel, ":x: Bad argument: {}".format(' '.join(e.args)))
        return
    elif isinstance(e, commands.errors.CheckFailure):
        await bot.send_message(ctx.message.channel, ":x: Check failed. You probably don't have permission to do this.")
        return
    elif isinstance(e, commands.errors.CommandNotFound):
        await bot.send_message(ctx.message.channel, ":question:")
        return
    else:
        await bot.send_message(ctx.message.channel,
                               ":x: Error occurred while handling the command. This has been logged")
        bot.logger.error("".join(traceback.format_exception(type(e), e.__cause__, e.__cause__.__traceback__)))


@bot.command(pass_context=True, hidden=True)
async def reload(ctx):
    """
    Reloads all modules.
    """
    if ctx.message.author.id == config["owner_id"]:
        utils = []
        for i in bot.extensions:
            utils.append(i)
        fail = False
        for i in utils:
            bot.unload_extension(i)
            try:
                bot.load_extension(i)
            except:
                await bot.say('Failed to reload extension ``%s``' % i)
                fail = True
        if fail:
            await bot.say('Reloaded remaining extensions.')
        else:
            await bot.say('Reloaded all extensions.')
    else:
        await bot.say(":x: Only the bot owner can reload extensions")


@bot.command(pass_context=True)
async def bug(ctx):
    """
    Link github
    """
    try:
        em = discord.Embed()
        em.add_field(name="You can report bugs here.", value="https://github.com/LittleEndu/pxls-alert-bot/issues")
        await bot.send_message(ctx.message.channel, embed=em)
    except discord.Forbidden:
        await bot.say("You can report bugs here.\nhttps://github.com/LittleEndu/pxls-alert-bot/issues")


@bot.command(pass_context=True, hidden=True)
async def load(ctx, *, extension: str):
    """
    Load an extension.
    """
    if ctx.message.author.id == config["owner_id"]:
        try:
            bot.load_extension("cogs.{}".format(extension))
        except Exception as e:
            traceback.print_exc()
            await bot.say("Could not load `{}` -> `{}`".format(extension, e))
        else:
            await bot.say("Loaded cog `{}`.".format(extension))
    else:
        await bot.say(":x: Only the bot owner can load extensions")


@bot.command(pass_context=True, hidden=True)
async def unload(ctx, *, extension: str):
    """
    Unload an extension.
    """
    if ctx.message.author.id == config["owner_id"]:
        try:
            bot.unload_extension("{}".format(extension))
        except Exception as e:
            traceback.print_exc()
            await bot.say("Could not unload `{}` -> `{}`".format(extension, e))
        else:
            await bot.say("Unloaded `{}`.".format(extension))
    else:
        await bot.say(":x: Only the bot owner can unload extensions")


@bot.command(pass_context=True, hidden=True)
async def debug(ctx, *, command: str):
    """
    Run a debug command.
    """
    if ctx.message.author.id == config["owner_id"]:
        try:
            result = eval(command)
            if inspect.isawaitable(result):
                result = await result
        except Exception as e:
            result = repr(e)
        if config["token"] in str(result):
            fmt = "Doing this would reveal my token!!!"
        else:
            fmt = "```xl\nInput: {}\nOutput: {}\nOutput class: {}```".format(command, result, result.__class__.__name__)
        await bot.say(fmt)
    else:
        await bot.say(":x: Only the bot owner can run debug commands")


@bot.command(pass_context=True, hidden=True)
async def announce(ctx, *, announcement: str):
    """
    Announce stuff
    """
    announcement = "(Sorry if this isn't the right channel for these) Announcement from bot maker:\n\n" + announcement
    if ctx.message.author.id == config["owner_id"]:
        sent = False
        error = None
        for server in bot.servers:
            try:
                await bot.send_message(destination=server.default_channel, content=announcement)
                sent = True
                break
            except:
                pass
            for channel in server.channels:
                if channel.type == discord.ChannelType.text:
                    try:
                        await bot.send_message(destination=channel, content=announcement)
                        sent = True
                        break
                    except Exception as e:
                        error = e
        if not sent:
            await bot.say("Failed to send message...\n" + repr(e))
    else:
        await bot.say("Only the bot owner can announce stuff")


if __name__ == '__main__':
    if config["token"]:
        for extension in config['auto_load']:
            try:
                bot.load_extension(extension)
                bot.logger.info("Successfully loaded {}".format(extension))
            except Exception as e:
                bot.logger.info('Failed to load extension {}\n{}: {}'.format(extension, type(e).__name__, e))
        bot.run(config['token'])
    else:
        bot.logger.info("Please add the bot's token to the config file!")
