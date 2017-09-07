import logging
import os
import hashlib
import numpy
from random import randint, choice
from PIL import Image, ImageDraw, ImageFont
from PIL import GifImagePlugin as gif
import PIL.ImageOps
import requests
from util import  *

from classes.plugin import Plugin
from decorators import *

log = logging.getLogger('pedantbot')
cls = gif.GifImageFile


class Fun(Plugin):
    plugin_name = "fun or silly commands"

    def __init__(self, *args, **kwargs):
        Plugin.__init__(self, *args, **kwargs)

    @staticmethod
    def animated(img: Image.Image) -> bool:
        if isinstance(img, gif.GifImageFile):
            if hasattr(img, 'n_frames'):
                if img.n_frames > 1:
                    return True
        return False

    @command(pattern="^!spoderman (.*)$",
             description="MAke TEXt Like THOse sPODErMaN MEmEs",
             usage="!spoderman <text>")
    async def spoderman_text(self, message: discord.Message, args: tuple):
        channel = message.channel
        user = message.author

        if not args:
            return

        string = ''.join(c.upper() if randint(0, 1) else c.lower() for c in args[0])

        await self.client.send_message(
            channel,
            "{user.mention}: {string}".format(
                user=user,
                string=string
            )
        )

    @command(pattern="^!(?:bigger|bigly) (.*)$",
             description="view a larger version of a custom emoji",
             usage="!bigger <emoji>")
    async def bigger_emoji(self, message: discord.Message, args: tuple):
        channel = message.channel  # type: discord.Channel

        emoji = re.findall(r'<:([^:]+):([^:>]+)>', args[0])
        if not emoji:
            await self.client.send_message(
                channel,
                "No valid emoji found."
            )
            return

        if not emoji:
            return
        name, e_id = emoji[0]

        url = "https://cdn.discordapp.com/emojis/{}.png".format(e_id)
        if not requests.get(url).status_code == 200:
            await self.client.send_message(
                channel,
                "Emoji not found."
            )
            return

        embed = discord.Embed(
            title=name,
            color=discord.Color.magenta()
        )
        embed.set_image(url=url)
        embed.set_footer(text="ID: {}".format(e_id))

        await self.client.send_message(
            channel,
            embed=embed
        )

    @command(pattern="^!(?:biggerer|biglyer) (.*)$",
             description="view an even larger version of a custom emoji",
             usage="!biggerer <emoji>",
             cooldown=3)
    async def even_bigger_emoji(self, message: discord.Message, args: tuple):
        channel = message.channel  # type: discord.Channel

        emoji = re.findall(r'<:([^:]+):([^:>]+)>', args[0])
        if not emoji:
            await self.client.send_message(
                channel,
                "No valid emoji found."
            )
            return

        bg = Image.new("RGBA", (128 * len(emoji), 128), color=(0, 0, 0, 0))
        for i, (name, e_id) in enumerate(emoji):
            url = "https://cdn.discordapp.com/emojis/{}.png".format(e_id)
            fg = Image.open(get(url))  # type: Image.Image
            w, h = fg.size

            ratio = 128 / max(h, w)
            w2 = int(ratio * w)
            h2 = int(ratio * h)

            x_offset = int((128 - w2) / 2)
            y_offset = int((128 - h2) / 2)

            fg = fg.resize((w2, h2), Image.LINEAR)
            bg.paste(fg, (128 * i - x_offset, y_offset))

        bg.save("{}.PNG".format(message.id), "PNG")

        await self.client.send_file(
            channel,
            "{}.PNG".format(message.id),
            filename="biggerer.png"
        )

        os.remove("{}.PNG".format(message.id))

    @command(pattern="^!(?:exec|eval) .*$",
             description="execute python code",
             usage="!eval <code>",
             cooldown=1)
    async def exec_python(self, message: discord.Message, *_):
        await self.client.send_message(
            message.channel,
            "{} go suck a dick".format(message.author.mention)
        )

    @command(pattern="^!(?:needsmorejpe?g|jpe?g)(?: (.*))?$",
             description="give an image more jpeg",
             usage="!needsmorejpeg",
             global_cooldown=3)
    async def needs_more_jpeg(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        responses = [
            "This image needed more JPEG",
            "Did somebody ask for more JPEG?",
            "Much better.",
            "FTFY",
            "How about this?"
        ]

        await self.client.send_typing(channel)

        try:
            img = await self.get_image(message, args)
        except Exception as e:
            await self.client.send_message(
                channel,
                "Could not load image: ```\n{}```".format(e)
            )
            return

        if not img:
            await self.client.send_message(
                channel,
                'No images found in current channel.'
            )
            return

        fn = None
        if self.animated(img):
            img = img  # type: gif.GifImageFile
            from io import BytesIO
            frames = []

            for i in range(img.n_frames):
                log.info(i)
                img.seek(i)
                buffer = BytesIO()
                img.convert("RGB").save(buffer, "JPEG", quality=1)
                frames.append(Image.open(buffer))

            fn = self.getfile("gif")
            frames[0].save(fn, "GIF", save_all=True, append_images=frames[1:], loop=img.info.get('loop'), duration=img.info.get('duration'))
            out = "needsmorejpeg.gif"
        else:
            fn = self.getfile()
            img = img.convert('RGB')
            img.save(fn, "JPEG", quality=1)
            out = "needsmore.jpeg"

        if fn is not None:
            await self.client.send_file(
                channel,
                fn,
                filename=out,
                content=choice(responses)
            )

        if os.path.exists(fn):
            os.remove(fn)

    @staticmethod
    def scale(w=200, h=200, limit=200, up=False):
        rev = False
        if h > w:
            w, h = h, w
            rev = True
        if up is True:
            W, H = round(max(limit, w)), round(max(limit, w) * (h / w))
        else:
            W, H = round(min(limit, w)), round(min(limit, w) * (h / w))
        if rev:
            W, H = H, W

        return W, H

    async def get_image(self, message: discord.Message, args: tuple, arg=0, server=False) -> Image.Image:
        server = message.server
        channel = message.channel
        user = message.author

        types = [discord.Member]
        if server is True:
            types.append(discord.Server)

        img = None
        url = None
        if args[arg]:
            target = await get_object(
                self.client,
                args[arg],
                message,
                types=tuple(types)
            )

            if target is None:
                emoji = re.findall(r'<:([^:]+):([^:>]+)>', (args[arg].split() or "a")[0])
                if emoji:
                    url = "https://cdn.discordapp.com/emojis/{}.png".format(emoji[0][1])
                    temp = get(url)
                    content_type = temp.headers.get_content_type()
                    if 'image' in content_type:
                        img = temp

                if img is None:
                    url = args[arg]
            else:
                url = "https://cdn.discordapp.com/avatars/{}/{}.{}?size=512".format(target.id, target.avatar, "gif" if target.avatar.startswith("a_") else "png")

        fg = None
        if fg is None and img is not None:
            fg = Image.open(img)
        elif fg is None:
            if url is None:
                fg = await get_last_image(channel, self.client)
            else:
                try:
                    fg = Image.open(get(url))
                except ValueError:
                    fg = None

        if img is None and fg is None:
            return None

        return fg

    @staticmethod
    def isolate_channel(image, channel=(0,)):
        a = numpy.array(image)
        all = {0, 1, 2}

        for c in all:
            try:
                if c in all.difference(channel):
                    a[:, :, c] *= 0
            except:
                pass

        return Image.fromarray(a)

    @command(pattern="!image bren(?: (.*))?",
             description="make a man think about an image/user/emoji",
             usage="!image bren [url|username|emoji]",
             global_cooldown=5)
    async def bren_thinking(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        responses = [
            'Hmmmm... :thinking:',
            "I wonder if I...",
            "Ooh!",
            "What is this?",
            "... That's it!"
        ]

        await self.client.send_typing(channel)

        fg = await self.get_image(message, args, arg=0, server=True)
        if fg is None:
            await self.client.send_message(
                channel,
                "No image found for '{}'.".format(args[0]) if args[0] else "No image found."
            )
            return

        bren = Image.open("images/bren.png")
        out = []
        n = fg.n_frames if hasattr(fg, 'n_frames') else 1
        for i in range(n):
            fg.seek(i)
            bg = bren.copy()

            w, h = fg.size
            MAX = 180
            w2, h2 = Fun.scale(w, h)

            fg2 = fg.resize((min(w2, MAX), min(MAX, h2)))
            bg.alpha_composite(
                fg2.convert("RGBA"),
                (120 + round((MAX - w2) / 2), 110 + round((MAX - h2) / 2))
            )
            out.append(bg)

        fn = None
        ext = "png"
        if len(out) == 1:
            fn = self.getfile()
            out[0].save(fn, "PNG")
        elif len(out) > 1:
            fn = self.getfile("gif")
            out[0].save(fn, "GIF", save_all=True, append_images=out[1:], loop=fg.info.get('loop', 0), duration=fg.info.get('duration', 20))
            ext = "gif"

        if fn is not None:
            await self.client.send_file(
                channel,
                fn,
                filename="bren_thinking.{}".format(ext),
                content=choice(responses)
            )

        if os.path.exists(fn):
            os.remove(fn)

    @command(pattern="!image collage(?: (.*))?",
             description="create an RGB collage from a single image",
             usage="!image collage [url|username|emoji]",
             global_cooldown=5)
    async def collage_image(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        await self.client.send_typing(channel)

        fg = await self.get_image(message, args)
        w, h = fg.size

        fg = fg.resize((int(w/2), int(h/2)))

        bg = Image.new('RGBA', (w, h), (0, 0, 0, 255))
        bg.paste(fg, (0, 0))
        bg.paste(self.isolate_channel(fg, 0), (int(w / 2), 0))
        bg.paste(self.isolate_channel(fg, 1), (0, int(h / 2)))
        bg.paste(self.isolate_channel(fg, 2), (int(w / 2), int(h / 2)))

        fn = 'images/{}.png'.format(hashlib.sha1(os.urandom(8)).hexdigest())
        bg.save(fn, "PNG")

        await self.client.send_file(
            channel,
            fn,
            filename="collage.png"
        )

        if os.path.exists(fn):
            os.remove(fn)

    @command(pattern="!image rotat[eo] ([0-9]+)(?:deg)?(?: (.*))?",
             description="create an RGB collage from a single image",
             usage="!image rotate <degrees> [url|username|emoji]",
             global_cooldown=3)
    async def rotate_image(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        responses = [
            "Swoosh!",
            "Around it goes :arrows_counterclockwise:",
            "Looks much better this way around."
        ]

        await self.client.send_typing(channel)

        if args[0] and args[0].isnumeric:
            rotation = int(args[0][:3] or 180)
        else:
            rotation = 180

        fg = await self.get_image(message, args, arg=1)

        if fg is None:
            await self.client.send_message(
                channel,
                "No image found."
            )
            return

        fg = fg.rotate(-rotation, Image.LINEAR)
        fn = self.getfile()
        fg.save(fn, "PNG")

        await self.client.send_file(
            channel,
            fn,
            filename="rotato.png",
            content=choice(responses)
        )

        if os.path.exists(fn):
            os.remove(fn)

    @staticmethod
    def getfile(ext="png"):
        return 'images/{}.{}'.format(hashlib.sha1(os.urandom(8)).hexdigest(), ext)

    @command(pattern="^!image colou?r ([^ ]*)(?: (.*))?$",
             description="make images different colours",
             usage="!image colour <colour> [user|url|emoji]",
             global_cooldown=3)
    async def image_colour(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        channels = {
            'red'    : [0],
            'yellow' : [0, 1],
            'green'  : [1],
            'blue'   : [2],
            'purple' : [0, 2]
        }

        await self.client.send_typing(channel)
        img = await self.get_image(message, args, arg=1)

        if img is None:
            await self.client.send_message(
                channel,
                "No image found."
            )
            return

        xy = img.size
        if args[0].lower() in ["gey", "gay", "rainbow", "pride"]:
            colours = [
                (212, 6, 6),
                (238, 156, 0),
                (227, 255, 0),
                (6, 191, 0),
                (0, 26, 152)
            ]

            w, h = xy
            i = h / len(colours)

            fg = Image.new("RGBA", xy, (0, 0, 0, 0))
            draw = ImageDraw.Draw(fg)
            for n, colour in enumerate(colours):
                draw.rectangle(
                    (
                        (0, int(i * n)),
                        (w, int(i * (n+1)))
                    ),
                    fill=(*colour, 127)
                )

            img = img.convert("RGBA")
            img.alpha_composite(fg.convert("RGBA"))

        else:
            mask = Image.new("L", xy, 160)
            try:
                fg = Image.new("RGB", xy, args[0])
            except ValueError:
                await self.client.send_message(
                    channel,
                    "Colour '{}' not recognised.".format(args[0])
                )
                return

            fg.putalpha(mask)

            img = img.convert("RGBA")
            img.alpha_composite(fg)

        fn = self.getfile()
        img.save(fn, "PNG")

        await self.client.send_file(
            channel,
            fp=fn,
            filename="{}.png".format(args[0]),
            content=args[0]
        )

        if os.path.exists(fn):
            os.remove(fn)

    @command(pattern="^!image invert(?: (.*))?$",
             description="invert colour on an image",
             usage="!image invert [user|url|emoji]",
             global_cooldown=3)
    async def image_invert(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        await self.client.send_typing(channel)
        img = await self.get_image(message, args, arg=0)

        if img is None:
            await self.client.send_message(
                channel,
                "No image found."
            )
            return

        fn = self.getfile()

        img = img.convert("RGBA")
        r, g, b, a = img.split()
        rgb_img = Image.merge('RGB', (r, g, b))
        rgb_invert = PIL.ImageOps.invert(rgb_img)

        r2, g2, b2 = rgb_invert.split()
        rgba_invert = Image.merge('RGBA', (r2, g2, b2, a))
        rgba_invert.save(fn)

        await self.client.send_file(
            channel,
            fn,
            filename="inverted.png"
        )

        if os.path.isfile(fn):
            os.remove(fn)

    @staticmethod
    def border_text(text, img, xy=(0, 0), y=None, font=None, fill="BLACK", outline="WHITE", draw=None):
        if y is None:
            x, y = xy
        else:
            x, y = xy, y

        if draw is None:
            draw = ImageDraw.Draw(img)

        if font is None:
            font = ImageFont.truetype("impact.ttf", 20)

        draw.text((x - 1, y), text, font=font, fill=outline)
        draw.text((x + 1, y), text, font=font, fill=outline)
        draw.text((x, y - 1), text, font=font, fill=outline)
        draw.text((x, y + 1), text, font=font, fill=outline)

        draw.text((x - 1, y - 1), text, font=font, fill=outline)
        draw.text((x + 1, y - 1), text, font=font, fill=outline)
        draw.text((x - 1, y + 1), text, font=font, fill=outline)
        draw.text((x + 1, y + 1), text, font=font, fill=outline)

        draw.text((x, y), text, font=font, fill=fill)

    @staticmethod
    def wrap_text(img, text="", font=None):
        if text == "" or text is None:
            return []

        w, h = img.size

        lines = text.split("\n")
        draw = ImageDraw.Draw(img)

        for i, _ in enumerate(lines):
            if lines[i].strip() == "":
                lines.pop(i)
                continue
            if len(lines) <= i + 1:
                lines.append("")

            width, _ = draw.textsize(lines[i], font=font)
            while width > w:
                b, a = lines[i][::-1].split(" ", maxsplit=1)
                lines[i] = a[::-1].strip()
                lines[i + 1] = (b[::-1] + ' ' + lines[i + 1]).strip()
                width, _ = draw.textsize(lines[i], font=font)
        return lines

    @command(pattern="^!meme ?([^\n]*?)\n([^\n]*)?(?:\n([^\n]*))?(?:\n.*)?$",
             description="make a meme from an image",
             usage=r"!meme [user|emoji|url] [NEWLINE <top text>] [NEWLINE <bottom_text>]",
             cooldown=3)
    async def make_meme(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        await self.client.send_typing(channel)

        im = await self.get_image(message, args, server=True)

        if im is None:
            await self.client.send_message(
                channel,
                "No image found."
            )
            return
        else:
            im = im.convert("RGBA")

        w, h = im.size

        if w < 300 or h < 300:
            w2, h2 = self.scale(w, h, 500, True)
            im = im.resize((w2, h2), Image.BILINEAR)
            w, h = im.size

        pointsize = int(min(w, h) / 7)

        draw = ImageDraw.Draw(im)
        font = ImageFont.truetype("impact.ttf", pointsize)

        top = []
        bottom = []
        if args[1] != "..NONE..":
            top = self.wrap_text(im, args[1], font=font)
        if args[2] != "..NONE..":
            bottom = self.wrap_text(im, args[2], font=font)

        for n, line in enumerate(top):
            if line == "":
                n -= 1
                continue
            tw, th = draw.textsize(line, font=font)
            x, y = int(w / 2 - tw / 2), int(th * n)
            self.border_text(line, im, xy=(x, y), font=font)
        for n, line in enumerate(bottom):
            if line == "":
                n -= 1
                continue
            tw, th = draw.textsize(line, font=font)
            x, y = int(w / 2 - tw / 2), int(h - pointsize / 4 - th * (len(bottom) - n))
            self.border_text(line, im, xy=(x, y), font=font)

        fn = self.getfile()
        im.save(fn, "PNG")

        await self.client.send_file(
            channel,
            fn,
            filename="meme.png",
        )

        if os.path.isfile(fn):
            os.remove(fn)

    @command(pattern="^!image triggered(?: (.*))?$",
             description="make someone triggered",
             usage="!image triggered [user|emoji|url]",
             global_cooldown=5)
    async def triggered_gif(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        def rand():
            return int(((randint(0, 15)))) / 100

        await self.client.send_typing(channel)

        fg = await self.get_image(message, args, server=True)
        if fg is None:
            await self.client.send_message(
                channel,
                "No image found"
            )
            return

        frames = []
        w, h = fg.size
        if min(w, h) < 300:
            fg = fg.resize(self.scale(w, h, 500, True), resample=Image.BILINEAR)
        w, h = fg.size

        for i in range(1, 20):
            im = Image.new("RGBA", (int(w*0.8), int(h*0.8)))
            im.paste(fg, (int(-w*1.1 * rand()), int(-h*1.1 * rand())))

            frames.append(im)

        fn = self.getfile("gif")
        im.save(fn, "GIF", save_all=True, append_images=frames, loop=0, duration=25)

        await self.client.send_file(
            channel,
            fn,
            filename="triggered.gif",
        )

        if os.path.isfile(fn):
            os.remove(fn)
