import discord
import json
import datetime

def Embed(embed_json: str = ""):
    if not embed_json:
        raise ValueError("No JSON provided")

    parsed = None
    err = None
    try:
        raw = embed_json.replace('\n','').replace('\t','')
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        size = 30
        start = int(max(0, e.colno - (size / 2)))
        end = int(e.colno + (size / 2))
        out = embed_json[start:end]

        pointer = len(out) - (size / 2) - 1
        if pointer < 0:
            pointer = pointer * -1
        pointer = int(pointer)

        hint = "{}\n{}^".format(
            out,
            ' ' * pointer
        )

        raise ValueError(
            "You have an error in your JSON.\n"
            "```{hint}\n{error}: line {line}, column {col}```".format(
                hint=hint,
                error=e.msg,
                line=e.lineno,
                col=e.colno
            )
        )

    embed = discord.Embed()
    embed.title = data.get('title', discord.Embed.Empty)
    embed.description = data.get('description', discord.Embed.Empty)
    embed.url = data.get('url', discord.Embed.Empty)
    if 'timestamp' in data:
        try:
            embed.timestamp = datetime.datetime.fromtimestamp(float(data.get('timestamp')))
        except Exception as e:
            raise ValueError("Invalid timestamp")
    if 'colour' in data or 'color' in data:
        try:
            colour = discord.Colour(int(data.get('colour', data.get('color')).replace('#',''), 16))
            colour.to_tuple()
            embed.colour = colour
        except Exception as e:
            raise ValueError("Invalid colour")
    footer = data.get('footer',{})
    if isinstance(footer, dict):
        embed.set_footer(
            text=footer.get('text', discord.Embed.Empty),
            icon_url=footer.get('icon_url', discord.Embed.Empty)
        )

    image = data.get('image', {})
    if isinstance(image, dict):
        embed.set_image(
            url=image.get('url', "")
        )

    thumbnail = data.get('thumbnail')
    if isinstance(thumbnail, dict):
        embed.set_thumbnail(
            url=thumbnail.get('thumbnail', "")
        )

    author = data.get('author')
    if isinstance(author, dict):
        embed.set_author(
            name=author.get('name',''),
            url=author.get('url',''),
            icon_url=author.get('icon_url','')
        )

    return embed
