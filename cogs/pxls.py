import asyncio
import datetime
import json
import math
import os
import random
import struct
import time
import traceback
import urllib.parse
from ast import literal_eval
from io import BytesIO

import aiohttp
import discord
import websockets
from PIL import Image
from discord.ext import commands
from discord.ext.commands import Bot


class Pxls(object):
    """
    For pxls stuff
    """

    def __init__(self, bot: Bot):
        self.bot = bot
        with open("config.json") as file_in:
            self.config = json.load(file_in)

        self.width = 0
        self.height = 0
        self.color_tuples = list()
        self.boarddata = bytearray()
        self.unprocessed_pixels = list()
        self.unsent_pixels = dict()
        self.preview_radius = self.config.setdefault("preview_radius", 20)

        if not os.path.isdir("backups"):
            os.makedirs("backups")
        self.templates = self.find_backup("templates")
        self.alert_channels = self.find_backup("alert-channels")
        self.numbers = self.find_backup("numbers")
        self.mentions = self.find_backup("mentions")
        self.statistics = self.find_backup("statistics")
        # statistics are server_id:(harmful users, helpful users, harmful pixels, helpful pixels)

        self.spectator = self.bot.loop.create_task(self.task_pxls_spectator())
        self.time_based = self.bot.loop.create_task(self.task_5seconds())
        self.backer = self.bot.loop.create_task(self.task_backup_maker())
        self.pixel_processor = self.bot.loop.create_task(self.task_pixel_processor())

        self.cleanup()

    def find_backup(self, name):
        for file in os.listdir("backups"):
            if file.startswith(name):
                with open("backups/{}".format(file)) as file_in:
                    return json.load(file_in)
        return dict()

    def get_nearest_pixel_index(self, tuple_in, color_tuples):
        try:
            return color_tuples.index(tuple_in)
        except:
            pass
        differences = []
        for color in color_tuples:
            differences.append(sum([abs(color[i] - tuple_in[i]) for i in range(3)]))
        minimum = 0
        for i in range(len(differences)):
            if differences[i] < differences[minimum]:
                minimum = i
        try:
            tdif = sum([abs(tuple_in[i] - (0, 0, 0, 0)[i]) for i in range(4)])
            if tdif < differences[minimum]:
                return -1
            if tuple_in[3] < 100:
                return -1
        except:
            pass
        return minimum

    def get_color_name(self, color_tuple):
        named_colors = [(255, 255, 255, 255), (228, 228, 228, 255), (136, 136, 136, 255), (34, 34, 34, 255),
                        (255, 167, 209, 255), (229, 0, 0, 255), (229, 149, 0, 255), (160, 106, 66, 255),
                        (229, 217, 0, 255), (148, 224, 68, 255), (2, 190, 1, 255), (0, 211, 221, 255),
                        (0, 131, 199, 255), (0, 0, 234, 255), (207, 110, 228, 255), (130, 0, 128, 255),
                        (255, 0, 255, 255), (245, 245, 220, 255), (0, 0, 0, 255), (128, 0, 0, 255)]
        color_names = ["white", "light gray", "dark gray", "black", "pink", "red", "orange", "brown", "yellow",
                       "light green", "dark green", "cyan/teal", "sky blue", "dark blue", "purpleishpink",
                       "dark purple", "magenta", "beige", "true black", "maroon"]
        return color_names[self.get_nearest_pixel_index(color_tuple, named_colors)]

    async def init_pxls(self):
        async with aiohttp.ClientSession() as session:
            async with session.get("{}/info".format(self.config['pxls_default']),
                                   headers={'Cookie': 'pxls-agegate=1'}) as response:
                info = literal_eval(str(await response.read())[2:-1])
                self.width = info["width"]
                self.height = info["height"]
                self.color_tuples = [struct.unpack('BBBB', bytes.fromhex(i[1:] + "FF")) for i in info["palette"]]
            async with session.get("{}/boarddata".format(self.config['pxls_default']),
                                   headers={'Cookie': 'pxls-agegate=1'}) as response:
                self.boarddata = bytearray(await response.read())

    def make_backup(self):
        self.cleanup()
        self.backup_info(self.templates, "templates")
        self.backup_info(self.alert_channels, "alert-channels")
        self.backup_info(self.mentions, "mentions")
        self.backup_info(self.numbers, "numbers")

    def cleanup(self):
        for server in self.bot.servers:
            self.numbers.setdefault(server.id, dict())
        for server_id in self.alert_channels:
            self.alert_channels[server_id] = list(set(self.alert_channels[server_id]))
        for server_id in self.mentions:
            self.mentions[server_id] = list(set(self.mentions[server_id]))

    def backup_info(self, info, name):
        servers = [i.id for i in self.bot.servers]
        for server_id in list(info.keys()):
            if server_id not in servers:
                try:
                    del info[server_id]
                except:
                    pass
        if not os.path.isdir("backups"):
            os.makedirs("backups")
        date = str(datetime.datetime.now())
        for i in "- :.":
            date = date.replace(i, "")
        with open("backups/{}{}.json".format(name, date), "w") as file_out:
            json.dump(info, file_out)
        for file in os.listdir("backups"):
            if file.startswith(name):
                if file != "{}{}.json".format(name, date):
                    os.remove("backups/{}".format(file))

    async def task_backup_maker(self):
        while True:
            await asyncio.sleep(3600)
            self.make_backup()
            await self.init_pxls()

    async def task_pxls_spectator(self):
        while True:
            try:
                async with websockets.connect(self.config['pxls_ws'], extra_headers={"Cookie": "pxls-agegate=1"}) as ws:
                    await self.init_pxls()
                    while True:
                        await asyncio.sleep(1)
                        info = literal_eval(await ws.recv())
                        if info["type"] == "pixel":
                            for px in info["pixels"]:
                                self.boarddata[px['x'] + px['y'] * self.width] = px['color']
                                self.unprocessed_pixels.append({"x": px['x'], "y": px['y'], "color": px['color']})
            except:
                await asyncio.sleep(60)

    async def task_5seconds(self):
        while True:
            await asyncio.sleep(5)
            for server_id in self.statistics:
                stats = self.statistics[server_id]
                stats = [max(stats[0] - 5/60, 0), max(stats[1] - 5/60, 0), stats[2], stats[3]]
                if stats[0] < stats[2]:
                    stats[0] += 1
                    stats[2] = 0
                if stats[1] < stats[3]:
                    stats[1] += 1
                    stats[3] = 0
                self.statistics[server_id] = stats
            for server_id in self.templates:
                for template in self.templates[server_id]:
                    if template.setdefault('score', 0) > -0.5:
                        template['score'] *= 0.99

    async def task_pixel_processor(self):
        while True:
            await asyncio.sleep(1)
            for pixel in self.unprocessed_pixels[:]:
                for server_id in [i.id for i in self.bot.servers]:
                    if server_id in self.templates:
                        is_harmful = False
                        is_helpful = False
                        for template in self.templates[server_id]:
                            assert isinstance(template, dict)
                            assert isinstance(pixel, dict)
                            xx = pixel["x"] - template["ox"]
                            yy = pixel["y"] - template["oy"]
                            # if pixel is on template
                            if xx >= 0 and yy >= 0 and xx < template["w"] and yy < template["h"] and template["data"][
                                        xx + yy * template["w"]] != -1:
                                # if the colors match
                                if pixel["color"] == template["data"][xx + yy * template["w"]]:
                                    is_helpful = True
                                    template['score'] = template.setdefault('score', 0) + 1
                                else:
                                    is_harmful = True
                                    template['score'] = template.setdefault('score', 0) - 1
                            try:
                                last_alert = self.numbers[server_id]['last_alert'] + self.numbers[server_id]['silence']
                                threshold = self.numbers[server_id].setdefault('threshold', 5)
                                if last_alert < time.time() and template['score'] < threshold * -1:
                                    self.numbers[server_id]['last_alert'] = time.time()
                                    template['score'] = -1
                                    msg = ""
                                    if server_id in self.mentions:
                                        msg = "".join([str(i) for i in set(self.mentions[server_id])])
                                        if [i for i in self.bot.get_server(server_id).roles if
                                            i.name == "@everyone"][
                                            0].mention in self.mentions[server_id]:
                                            msg = "@everyone " + msg
                                    msg = "{}\nScreenshot taken around {}, {}".format(msg, pixel['x'], pixel['y'])
                                    r = self.preview_radius
                                    preview = Image.new("RGBA", (r * 2, r * 2))
                                    data = []
                                    from_x = min(max(pixel['x'] - r, 0), self.width - r * 2)
                                    to_x = max(min(pixel['x'] + r, self.width), r * 2)
                                    from_y = min(max(pixel['y'] - r, 0), self.height - r * 2)
                                    to_y = max(min(pixel['y'] + r, self.height), r * 2)
                                    for j in range(from_y, to_y):
                                        for i in range(from_x, to_x):
                                            data.append(self.color_tuples[self.boarddata[i + j * self.width]])
                                    preview.putdata(data)
                                    preview = preview.resize((300, 300))
                                    buffer = BytesIO()
                                    preview.save(buffer, "jpeg")
                                    buffer.seek(0)

                                    for channel_id in set(self.alert_channels[server_id]):
                                        try:
                                            await self.bot.send_file(self.bot.get_channel(channel_id), buffer,
                                                                     filename="Preview.jpeg", content=msg)
                                        except:
                                            try:
                                                await self.bot.send_message(self.bot.get_channel(channel_id),
                                                                            "Allow me to send files")
                                            except:
                                                pass
                            except:
                                pass

                        self.numbers.setdefault(server_id, dict())
                        if is_harmful:
                            stats = self.statistics.setdefault(server_id, [0, 0, 0, 0])
                            stats[2] += 1.1
                            self.statistics[server_id] = stats
                        if is_helpful:
                            stats = self.statistics.setdefault(server_id, [0, 0, 0, 0])
                            stats[3] += 1.1
                            self.statistics[server_id] = stats

                self.unprocessed_pixels.remove(pixel)

    # Actual commands

    @commands.command(pass_context=True, hidden=True)
    async def assure(self, ctx):
        """
        Assures that all tasks are running
        """
        if self.spectator.done():
            self.spectator = self.bot.loop.create_task(self.task_pxls_spectator())
            await self.bot.say("Restarting task_pxls_spectator")
        else:
            await self.bot.say("task_pxls_spectator is running")
        if self.time_based.done():
            self.time_based = self.bot.loop.create_task(self.task_5seconds())
            await self.bot.say("Restarting task_5seconds")
        else:
            await self.bot.say("task_5seconds is running")
        if self.backer.done():
            self.backer = self.bot.loop.create_task(self.task_backup_maker())
            await self.bot.say("Restarting task_backup_maker")
        else:
            await self.bot.say("task_backup_maker is running")
        if self.pixel_processor.done():
            self.pixel_processor = self.bot.loop.create_task(self.task_pixel_processor())
            await self.bot.say("Restarting task_pixel_processor")
        else:
            await self.bot.say("task_pixel_processor is running")

    @commands.command(pass_context=True, hidden=True)
    async def makebackup(self, ctx):
        if ctx.message.author.id == self.config["owner_id"]:
            await self.bot.send_typing(ctx.message.channel)
            self.make_backup()
            await self.bot.say("Successfully made backup")
        else:
            await self.bot.say("Only bot owner can force backups. They are done automatically every hour.")

    @commands.command(pass_context=True, hidden=True)
    async def debugfakepixel(self, ctx, x: int, y: int, color_index: int):
        if ctx.message.author.id == self.config["owner_id"]:
            self.unprocessed_pixels.append({'x': x, 'y': y, 'color': color_index, 'debug': True})
            await self.bot.say("Succesfully faked pixel.")
        else:
            await self.bot.say("Only bot owner can use debug.")

    @commands.command(pass_context=True)
    @commands.has_permissions(administrator=True)
    async def startalerts(self, ctx):
        """
        Starts alerts in this channel

        Alerts happen when 1) Currently there's damage over threshold 2) enough time as passed from last alert
        The time is controlled with setsilence
        The threshold is controller with setthreshold
        """
        self.alert_channels.setdefault(ctx.message.server.id, []).append(ctx.message.channel.id)
        self.numbers.setdefault(ctx.message.server.id, dict())
        self.numbers[ctx.message.server.id].setdefault('thresholds', 5)
        self.numbers[ctx.message.server.id].setdefault('silence', 15 * 60)
        self.numbers[ctx.message.server.id].setdefault('last_alert', 0)
        await self.bot.say("Will alert this channel")

    @commands.command(pass_context=True)
    @commands.has_permissions(administrator=True)
    async def stopalerts(self, ctx):
        """
        Stops alerts in this channel
        """
        try:
            self.alert_channels[ctx.message.server.id].remove(ctx.message.channel.id)
            await self.bot.say("Successfully removed channel from alerts list")
        except:
            await self.bot.say("That channel isn't in the alerts list")
        # lazy code
        try:
            while True:
                self.alert_channels[ctx.message.server.id].remove(ctx.message.channel.id)
        except:
            pass

    @commands.command(pass_context=True, aliases=['addm'])
    @commands.has_permissions(administrator=True)
    async def addmention(self, ctx, role: discord.Role):
        """
        Adds a role what to mention in alerts

        The role needs to be mentionable for it to work. Everyone is a valid role, Here isn't.
        """
        self.mentions.setdefault(ctx.message.server.id, []).append(role.mention)
        await self.bot.say("Successfully added the role to mentions list")

    @commands.command(pass_context=True)
    @commands.has_permissions(administrator=True)
    async def removemention(self, ctx, role: discord.Role):
        """
        Removes a role from what to mention in alerts
        """
        try:
            self.mentions[ctx.message.server.id].remove(role.mention)
            await self.bot.say("Successfully removed tole from mentions list")
        except:
            await self.bot.say("That role isn't in the mentions list")
        try:
            while True:
                self.mentions[ctx.message.server.id].remove(role.mention)
        except:
            pass

    @commands.command(pass_context=True)
    @commands.has_permissions(administrator=True)
    async def setthreshold(self, ctx, value: float):
        """
        Set the threshold value used for alerts
        """
        try:
            if value < 0:
                await self.bot.say("Threshold must be positive")
                return
            self.numbers.setdefault(ctx.message.server.id, dict())["threshold"] = value
            await self.bot.say("Successfully set the threshold")
        except Exception as error:
            await self.bot.say("Error while setting threshold value.")
            traceback.print_exception(type(error), error, error.__traceback__)

    @commands.command(pass_context=True)
    @commands.has_permissions(administrator=True)
    async def setsilence(self, ctx, minutes: float):
        """
        Set the silence time for alerts
        """
        try:
            if minutes < 0:
                await self.bot.say("Minutes must be positive")
                return
            self.numbers.setdefault(ctx.message.server.id, dict())['silence'] = minutes * 60
            await self.bot.say("Successfully set the silence")
        except Exception as error:
            await self.bot.say("Error while setting silence.")
            traceback.print_exception(type(error), error, error.__traceback__)

    @commands.command(pass_context=True)
    async def showsettings(self, ctx):
        """
        Shows current settings
        """
        try:
            await self.bot.say(
                "silence time: {} minutes\nthreshold: {} pixels".format(
                    self.numbers.setdefault(ctx.message.server.id, dict()).setdefault('silence', 900) / 60,
                    self.numbers.setdefault(ctx.message.server.id, dict()).setdefault('threshold', 5)))
        except:
            pass
        if ctx.message.server.id in self.alert_channels:
            if self.alert_channels[ctx.message.server.id]:
                await self.bot.say("Showing alerts in channel{}: {}".format(
                    "" if len(self.alert_channels[ctx.message.server.id]) == 1 else "s", ", ".join(
                        [self.bot.get_channel(i).mention for i in set(self.alert_channels[ctx.message.server.id])])))
        if ctx.message.server.id in self.mentions:
            if self.mentions[ctx.message.server.id]:
                ll = len(self.mentions[ctx.message.server.id])
                roles = [i.name for i in ctx.message.server.roles if i.mention in self.mentions[ctx.message.server.id]]
                if "@everyone" in roles:
                    roles.remove("@everyone")
                    roles.append("everyone")
                await self.bot.say(
                    "Mentioning {} role{}: {}".format("this" if ll == 1 else "these", "" if ll == 1 else "s",
                                                      ", ".join(roles)))

    @commands.command(pass_context=True)
    @commands.has_permissions(administrator=True)
    async def testalert(self, ctx):
        """
        Does a test alert.
        """
        if not ctx.message.server.id in self.alert_channels:
            await self.bot.say("You don't seem to have any alert channels")
            return
        try:
            for channel in set(self.alert_channels[ctx.message.server.id]):
                msg = "\nTEST ALERT"
                if ctx.message.server.id in self.mentions:
                    msg = "".join([str(i) for i in self.mentions[ctx.message.server.id]]) + msg
                    if [i for i in self.bot.get_server(ctx.message.server.id).roles if i.name == "@everyone"][
                        0].mention in self.mentions[ctx.message.server.id]:
                        msg = "@everyone " + msg
                await self.bot.send_message(self.bot.get_channel(channel), msg)
        except Exception as error:
            await self.bot.say("Error while making test alert!")
            traceback.print_exception(type(error), error, error.__traceback__)

    @commands.command(pass_context=True, aliases=['addt'])
    @commands.has_permissions(administrator=True)
    async def addtemplate(self, ctx, url: str, *, name: str):
        """
        Adds template from url
        """
        await self.bot.send_typing(ctx.message.channel)
        im = None
        if "#" not in url:
            await self.bot.say("You need the url that has # in it")
        try:
            parameters = {i.split("=")[0]: i.split("=")[1] for i in url[url.find("#") + 1:].split("&")}
            async with aiohttp.ClientSession() as session:
                async with session.get(urllib.parse.unquote(parameters["template"])) as response:
                    im = Image.open(BytesIO(await response.read()))
            if "tw" in parameters:
                if not parameters["tw"] == str(im.size[0]):
                    await self.bot.say("Can't use scaled images.")
                    return
            if im.size[0] * im.size[1] > 40000:
                await self.bot.say("This imgae is too large! Please use images 200x200 in size or less.")
                return
            int(parameters.setdefault('ox', 0))
            int(parameters.setdefault('oy', 0))
            if int(parameters["ox"]) < 0 or int(parameters["ox"]) + im.size[0] > self.width or int(
                    parameters["oy"]) < 0 or int(parameters["oy"]) + im.size[1] > self.height:
                await self.bot.say("This imgae is outside the canvas!")
                return
            if im.mode != "RGBA":
                im = im.convert("RGBA")
            info = dict()
            info["template"] = parameters["template"]
            info["ox"] = int(parameters["ox"])
            info["oy"] = int(parameters["oy"])
            info["data"] = [self.get_nearest_pixel_index(i, self.color_tuples) for i in im.getdata()]
            info["w"], info["h"] = im.size
            info["name"] = name
            info["score"] = 0
            self.templates.setdefault(ctx.message.server.id, []).append(info)
            await self.bot.say("Successfully added the template.")
        except Exception as error:
            await self.bot.say("Error while adding template.")
            traceback.print_exception(type(error), error, error.__traceback__)
            if im:
                image_data = [i for i in im.getdata()]
                with open("debug.txt", "w") as file_out:
                    file_out.write(str(image_data))

    @commands.command(pass_context=True)
    @commands.has_permissions(administrator=True)
    async def removetemplate(self, ctx, *, name: str):
        """
        Removes template using name
        """
        try:
            removed = 0
            for template in self.templates[ctx.message.server.id][:]:
                if template["name"] == name:
                    self.templates[ctx.message.server.id].remove(template)
                    removed += 1
            if removed:
                await self.bot.say("Successfully removed {} template{}.".format(removed, "" if removed == 1 else "s"))
            else:
                await self.bot.say("Didn't find such template.")
        except Exception as error:
            await self.bot.say("Error while removing template.")
            traceback.print_exception(type(error), error, error.__traceback__)

    @commands.command(pass_context=True)
    @commands.has_permissions(administrator=True)
    async def setuphelp(self, ctx):
        """
        Shows info on how to get the bot running
        """
        msg = """
1. Get templates. Template images need to be 1:1 and less that 40k pixels (about 200x200)
2. Upload the image. You can just use discord for that :smile:
3. Go to https://pxls.space/ In there press ``T`` to open Templates. Then copy the link to the URL box.
4. Move the template to desired location using ``ctrl + click&drag``. The template starts at ``0, 0``
5. pxls.space has generated the correct link into address bar. Just copy it from there.
6. Now use addtemplate. You need to name the template.
7. Say startalerts in a channel you want to alert.
8. Add roles to mention with addmention.
9. You are setup.

If anything else is confusing you can always use the help command. Or try and find me in pxls discord
"""
        await self.bot.say(msg)

    @commands.command(pass_context=True, aliases=['listtemplates', 'statistics', 'stats', 'templates'])
    async def status(self, ctx):
        """
        Shows status on templates
        """
        emb = discord.Embed()
        count = 0
        try:
            for template in self.templates[ctx.message.server.id]:
                total = 0
                done = 0
                ox = template['ox']
                oy = template['oy']
                for xx in range(template['w']):
                    for yy in range(template['h']):
                        if template['data'][xx + yy * template['w']] != -1:
                            total += 1
                            if template['data'][xx + yy * template['w']] == self.boarddata[
                                                xx + ox + (yy + oy) * self.width]:
                                done += 1
                if done == total:
                    template['score'] = 0
                icon = "\u23f9"
                if template['score'] > 0.5:
                    icon = "\u23eb"
                if template['score'] < -0.5:
                    icon = "\u23ec"
                emb.add_field(name=template['name'], value="{}% done {}".format(str(done / total * 100)[:5], icon))
                count += 1
                if count == 15:
                    try:
                        await self.bot.send_message(ctx.message.channel, embed=emb)
                    except discord.Forbidden:
                        await self.bot.say("Allow me to embed links")
        except:
            emb.add_field(name="Error!", value="No templates found")
        try:
            await self.bot.send_message(ctx.message.channel, embed=emb)
        except discord.Forbidden:
            await self.bot.say("Allow me to embed links")
        stats = self.statistics.setdefault(ctx.message.server.id, [0, 0, 0, 0])
        helpful = math.ceil(stats[1])
        harmful = math.ceil(stats[0])
        msg = "About {} helpful pixel{} per minute".format(helpful, "" if helpful == 1 else "s")
        msg += "\nAbout {} harmful pixel{} pre minute".format(harmful, "" if harmful == 1 else "s")
        await self.bot.say(msg)

    @commands.command(pass_context=True)
    async def directions(self, ctx, how_much=5, *, name=None):
        """
        Gives directions on what to place
        """
        await self.bot.send_typing(ctx.message.channel)
        if how_much < 6:
            how_much = 6
        if how_much > 32:
            await self.bot.say("I won't give out more than 32 directions")
            how_much = 32
        if how_much % 2 == 1:
            how_much += 1
        directions = list()
        if not ctx.message.server.id in self.templates:
            await self.bot.say("No templates found... Can't give directions :'(")
            return
        for template in self.templates[ctx.message.server.id]:
            if name is not None:
                if template["name"] != name:
                    continue
            total = 0
            xx = template['ox']
            yy = template['oy']
            for pixel in template['data']:
                if pixel == -1:
                    xx += 1
                    if xx == template['ox'] + template['w']:
                        xx = template['ox']
                        yy += 1
                    continue
                if not self.boarddata[xx + yy * self.width] == pixel:
                    url = "{}/#template={}&ox={}&oy={}&x={}&y={}&scale=50&oo=0.5".format(
                        self.config['pxls_default'], template["template"], template['ox'], template['oy'], xx, yy)
                    pixel_is = self.get_color_name(self.boarddata[xx + yy * self.width])
                    should_be = self.get_color_name(self.color_tuples[pixel])
                    directions.append(["Pixel at x={}, y={} is {} but should be {}".format(xx, yy, pixel_is, should_be),
                                       "[Link to {}]({})".format(template['name'], url)])
                    total += 1
                    if total >= how_much:
                        break
                xx += 1
                if xx == template['ox'] + template['w']:
                    xx = template['ox']
                    yy += 1

        if directions:
            try:
                embed = discord.Embed()
                random.shuffle(directions)
                current = 0
                for direct in directions[:how_much]:
                    if current < 16:
                        embed.add_field(name=direct[0], value=direct[1])
                        current += 1
                    else:
                        await self.bot.send_message(ctx.message.channel, embed=embed)
                        embed = discord.Embed()
                        current = 0
                        embed.add_field(name=direct[0], value=direct[1])
                await self.bot.send_message(ctx.message.channel, embed=embed)
            except discord.Forbidden:
                await self.bot.say("Allow me to embed links")
        else:
            await self.bot.say("Didn't find anything to do.\n"
                               "Maybe everything is already done :thinking:\n"
                               "Or there's no such template :shrug:")

    @commands.command(pass_context=True)
    async def link(self, ctx, x: int, y: int, name=None):
        """
        Generates link with cordinates
        """
        msg = "Here you go.\n"
        tt = ""
        if name:
            if ctx.message.server.id in self.templates:
                for template in self.templates[ctx.message.server.id]:
                    if template['name'] == name:
                        tt = "&template={}&ox={}&oy={}".format(template['template'], template['ox'], template['oy'])
        url = "{}/#x={}&y={}{}".format(self.config['pxls_default'], x, y, tt)
        await self.bot.say(msg + url)


def setup(bot):
    bot.add_cog(Pxls(bot))
