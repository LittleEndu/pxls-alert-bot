import asyncio
import datetime
import json
import os
import struct
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
        self.color_tuple = list()
        self.boarddata = bytearray()
        self.unprocessed_pixels = list()
        self.log_entries_cache = dict()
        if not os.path.isdir("backups"):
            os.makedirs("backups")
        self.templates = self.find_backup("templates")
        self.log_channels = self.find_backup("log-channels")
        self.thresholds = self.find_backup("thresholds")

        self.bot.loop.create_task(self.task_pxls_spectator())
        self.bot.loop.create_task(self.task_pixels_processor())
        self.bot.loop.create_task(self.task_backup_maker())

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
                        (0, 131, 199, 255), (0, 0, 234, 255), (207, 110, 228, 255), (130, 0, 128, 255)]
        color_names = ["white", "light gray", "dark gray", "black", "pink", "red", "orange", "brown", "yellow",
                       "light green", "dark green", "cyan/teal", "sky blue", "dark blue", "purpleishpink",
                       "dark purple"]
        return color_names[self.get_nearest_pixel_index(color_tuple, named_colors)]

    async def initpxls(self):
        async with aiohttp.ClientSession() as session:
            async with session.get("https://pxls.space/info", headers={'Cookie': 'pxls-agegate=1'}) as response:
                info = literal_eval(str(await response.read())[2:-1])
                self.width = info["width"]
                self.height = info["height"]
                self.color_tuples = [struct.unpack('BBBB', bytes.fromhex(i[1:] + "FF")) for i in info["palette"]]
            async with session.get("https://pxls.space/boarddata", headers={'Cookie': 'pxls-agegate=1'}) as response:
                self.boarddata = bytearray(await response.read())

    async def task_backup_maker(self):
        while True:
            await asyncio.sleep(3600)
            self.make_backup()

    def make_backup(self):
        self.backup_info(self.templates, "templates")
        self.backup_info(self.log_channels, "log-channels")
        self.backup_info(self.thresholds, "thresholds")

    def backup_info(self, info, name):
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

    async def task_pxls_spectator(self):
        await self.initpxls()
        while True:
            try:
                async with websockets.connect("ws://pxls.space/ws", extra_headers={"Cookie": "pxls-agegate=1"}) as ws:
                    while True:
                        info = literal_eval(await ws.recv())
                        if info["type"] == "pixel":
                            for px in info["pixels"]:
                                self.boarddata[px['x'] * self.width + px['y']] = px['color']
                                self.unprocessed_pixels.append({"x": px['x'], "y": px['y'], "color": px['color']})
            except websockets.ConnectionClosed:
                await asyncio.sleep(60)

    def pixel_into_embed(self, pixel, is_helpful, is_harmful, is_questionable, on_templates, should_be, to_add=None):
        title = ""
        color = 0x000000
        if is_helpful:
            title = "\U0001f44d Helpful"
            color = 0x55FF00
        if is_harmful:
            if not title:
                title = "\u274c Harmful"
                color = 0xFF0000
            else:
                title = "(There's a conflicting pixel. Please check templates)\nConflicting"
        if is_questionable:
            if not title:
                title = "\u2049 Questionable"
                color = 0xFFFF00
            else:
                title = "(There's a conflicting pixel. Please check templates)\nConflicting"

        try:
            if pixel['debug']:
                title += " AND FAKE DEBUG "
        except:
            pass

        em = discord.Embed(color=color)
        name = "{} pixel placed at x={}, y={}".format(title, pixel["x"], pixel["y"])

        if to_add:
            name += ". " + to_add.strip()
        elif is_harmful or is_questionable:
            name += ". Is {} but should be {}!".format(self.get_color_name(self.color_tuples[pixel['color']]),
                                                       self.get_color_name(self.color_tuples[should_be[0]]))
        template = on_templates[0]
        value = "https://pxls.space/#template={}&ox={}&oy={}&x={}&y={}&scale=50&oo=0.5".format(template["template"],
                                                                                               template['ox'],
                                                                                               template['oy'],
                                                                                               pixel["x"], pixel["y"])
        em.add_field(name=name, value=value)
        return em

    async def task_pixels_processor(self):
        while True:
            await asyncio.sleep(5)
            for pixel in self.unprocessed_pixels[:]:
                # Log pixels
                for server_id in self.log_channels:
                    if server_id in self.templates:
                        is_harmful = False
                        is_helpful = False
                        is_questionable = False
                        on_templates = list()
                        should_be = list()
                        for template in self.templates[server_id]:
                            assert isinstance(pixel, dict)
                            xx = pixel["x"] - template["ox"]
                            yy = pixel["y"] - template["oy"]
                            # if pixel is on template
                            if xx >= 0 and yy >= 0 and xx < template["w"] and yy < template["h"] and template["data"][
                                                yy * template["w"] + xx] != -1:

                                on_templates.append(template)
                                should_be.append(template["data"][yy * template["w"] + xx])
                                # if the colors match
                                if pixel["color"] == template["data"][yy * template["w"] + xx]:
                                    is_helpful = True
                                    template["score"] = template["score"] * 0.5 + 1
                                else:
                                    keep_going = True
                                    for ix in range(-1, 3, 1):
                                        if keep_going:
                                            if ix == 2:
                                                is_harmful = True
                                                template["score"] = template["score"] * 0.9 - 1
                                                break
                                            for iy in range(-1, 2, 1):
                                                try:
                                                    # look for pixels around the placed one
                                                    if pixel["color"] == template["data"][
                                                                                (yy + iy) * template["w"] + xx + ix]:
                                                        is_questionable = True
                                                        template["score"] = template["score"] * 0.9 - 0.5
                                                        keep_going = False
                                                        break
                                                except:
                                                    continue
                        if on_templates:
                            embed = self.pixel_into_embed(pixel, is_helpful, is_harmful, is_questionable, on_templates,
                                                          should_be)
                            for channel_id in set(self.log_channels[server_id]):
                                entry_id = "x".join([channel_id, str(pixel['x']), str(pixel['y'])])
                                if entry_id in self.log_entries_cache:
                                    await self.bot.delete_message(self.log_entries_cache[entry_id])
                                    del self.log_entries_cache[entry_id]
                                if is_harmful or is_questionable:
                                    self.log_entries_cache[entry_id] = await self.bot.send_message(
                                        self.bot.get_channel(channel_id), embed=embed)
                                else:
                                    await self.bot.send_message(self.bot.get_channel(channel_id), embed=embed)

                self.unprocessed_pixels.remove(pixel)

    ### Actual commands

    @commands.command(pass_context=True)
    @commands.has_permissions(administrator=True)
    async def makebackup(self, ctx):
        if ctx.message.author.id == self.config["owner_id"]:
            self.make_backup()
            await self.bot.say("Successfully made backup")
        else:
            await self.bot.say("Only bot owner can force backups. They are done automatically every hour.")

    @commands.command(pass_context=True)
    @commands.has_permissions(administrator=True)
    async def debugfakepixel(self, ctx, x: int, y: int, color_index: int):
        if ctx.message.author.id == self.config["owner_id"]:
            self.unprocessed_pixels.append({'x': x, 'y': y, 'color': color_index, 'debug': True})
            await self.bot.say("Succesfully faked pixel. Should appear in logs soon.")
        else:
            await self.bot.say("Only bot owner can use debug.")

    @commands.command(pass_context=True)
    @commands.has_permissions(administrator=True)
    async def startlogs(self, ctx):
        """
        Starts logs in this channel
        """
        self.log_channels.setdefault(ctx.message.server.id, []).append(ctx.message.channel.id)
        await self.bot.say("Will show logs to this channel")

    @commands.command(pass_context=True)
    @commands.has_permissions(administrator=True)
    async def stoplogs(self, ctx):
        """
        Stop logs in this channel
        """
        try:
            self.log_channels[ctx.message.server.id].remove(ctx.message.channel.id)
            await self.bot.say("Successfully removed channel from logs list")
        except:
            await self.bot.say("That channel isn't in the logs list")

    @commands.command(pass_context=True)
    @commands.has_permissions(administrator=True)
    async def addtemplate(self, ctx, url: str, *, name: str):
        """
        Adds template from url
        """
        try:
            parameters = {i.split("=")[0]: i.split("=")[1] for i in url[url.find("#") + 1:].split("&")}
            async with aiohttp.ClientSession() as session:
                async with session.get(urllib.parse.unquote(parameters["template"])) as response:
                    im = Image.open(BytesIO(await response.read()))
            if "tw" in parameters:
                if not parameters["tw"] == str(im.size[0]):
                    await self.bot.say("Can't use scaled images.")
                    return
            info = dict()
            info["template"] = parameters["template"]
            info["ox"] = int(parameters["ox"])
            info["oy"] = int(parameters["oy"])
            info["data"] = [self.get_nearest_pixel_index(i, self.color_tuples) for i in im.getdata()]
            print(im.size)
            info["w"], info["h"] = im.size
            info["name"] = name
            info["score"] = 0
            self.templates.setdefault(ctx.message.server.id, []).append(info)
            await self.bot.say("Successfully added the template.")
        except Exception as error:
            await self.bot.say("Error while adding template.")
            print(traceback.format_exception(type(error), error, error.__traceback__))

    @commands.command(pass_context=True)
    @commands.has_permissions(administrator=True)
    async def listtemplates(self, ctx):
        """
        List all templates
        """
        try:
            fmt = ", ".join([template['name'] for template in self.templates[ctx.message.server.id]])
            if not fmt:
                await self.bot.say("No templates were found!")
            while fmt:
                await self.bot.say(fmt[:1500])
                fmt = fmt[1500:]
        except:
            await self.bot.say("No templates have been added")

    @commands.command(pass_context=True)
    @commands.has_permissions(administrator=True)
    async def removetemplate(self, ctx, *, name: str):
        """
        Removes template using name
        """
        try:
            removed = 0
            for template in self.templates[ctx.message.server.id]:
                if template["name"] == name:
                    self.templates[ctx.message.server.id].remove(template)
                    removed += 1
            if removed:
                await self.bot.say("Successfully removed {} template{}.".format(removed, "" if removed == 1 else "s"))
            else:
                await self.bot.say("Didn't find such template.")
        except Exception as error:
            await self.bot.say("Error while removing template.")
            print(traceback.format_exception(type(error), error, error.__traceback__))


def setup(bot):
    bot.add_cog(Pxls(bot))
