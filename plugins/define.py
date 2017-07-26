import wikipedia
import urbandict
from classes.plugin import Plugin

from decorators import *
from util import *

log = logging.getLogger('pedantbot')


class Define(Plugin):
    plugin_name = "lookup words online"

    def __init__(self, *args, **kwargs):
        Plugin.__init__(self, *args, **kwargs)

    @command(pattern="^!(?:wikipedia|wp) (.+)$",
             description="lookup a term on wikipedia",
             usage="!wikipedia <term>")
    async def wikipedia_lookup(self, message: discord.Message, args: tuple):
        channel = message.channel  # type: discord.Channel
        user = message.author  # type: discord.Member

        term = args[0]

        await self.client.send_typing(channel)
        results = wikipedia.search(term, 5)
        if len(results) == 0:
            await self.client.send_message(
                channel,
                "No results found for '{}'".format(
                    clean_string(term)
                )
            )
            return

        elif len(results) == 1:
            page = self.get_wikipedia_page(term)
        else:
            summaries = []
            for result in results:
                try:
                    summary = wikipedia.summary(result, chars=50)
                except wikipedia.exceptions.DisambiguationError as de:
                    summary = wikipedia.summary(de.options[0], chars=50)
                except wikipedia.exceptions.PageError:
                    continue

                summaries.append((
                    result,
                    summary
                ))

            res = await confirm_dialog(
                self.client,
                channel,
                user,
                "Multiple results for '{}'".format(clean_string(term)),
                "Please select one of the following: \n\n{}```".format(
                    '\n'.join('**{}.** `{}`: {}'.format(n, item[0], item[1]) for n, item in enumerate(summaries))
                ) + '\n**c**  cancel',
                options=tuple([*[str(x) for x in range(len(results))], 'c']),
                colour=discord.Colour.orange()
            )

            if not res:
                return

            if res.content.lower() == 'c':
                return
            else:
                await self.client.send_typing(channel)
                page = self.get_wikipedia_page(results[int(res.content)])

        summary = markdown_links(
            self.wikipedia_links(
                page,
                "summary"
            )
        )

        embed = discord.Embed(
            title=page.title,
            color=discord.Color.light_grey(),
            description=truncate(summary, 600),
            url=page.url,
        )
        embed.set_footer(
            text="Wikipedia: {}".format(page.pageid),
            icon_url="https://www.wikipedia.org/portal/wikipedia.org/assets/img/Wikipedia-logo-v2.png"
        )

        try:
            embed.set_thumbnail(url=page.images[0])
        except KeyError:
            pass
        except IndexError:
            pass

        await self.client.send_message(
            channel,
            embed=embed
        )

    @staticmethod
    def get_wikipedia_page(title: str = ""):
        try:
            page = wikipedia.page(title)
        except wikipedia.exceptions.DisambiguationError as de:
            page = wikipedia.page(de.options[0])
        return page

    @staticmethod
    def wikipedia_links(page: wikipedia.WikipediaPage, section: str = "summary"):
        if not isinstance(page, wikipedia.WikipediaPage):
            raise TypeError("'page' must be a 'wikipedia.WikipediaPage'.")

        subject = getattr(page, section)
        if not isinstance(subject, str):
            raise TypeError("'page.{section}' is not of type 'str'".format(section=section))

        for n, link in enumerate(page.links):
            subject = subject.replace(
                link,
                '<a href="https://wikipedia.org/wiki/{page}">{label}</a>'.format(
                    n=n,
                    label=link,
                    page=link.replace(" ", "_")
                ),
                1
            )

        return subject

    # TODO: !define from wordsapi.com

    # TODO: !thesaurus, API unknown

    @command(pattern="^!(?:urbandict|urban|ud) (.+)$",
             description="lookup definitions for a word on urbandictionary",
             usage="!urbandict <term>")
    async def urbandict_lookup(self, message: discord.Message, args: tuple):
        channel = message.channel
        user = message.author

        definition = None

        await self.client.send_typing(channel)
        definitions = urbandict.define(args[0])

        body = ""
        if len(definitions) > 1:
            for i in range(min(5, len(definitions))):
                _def = definitions[i]
                body += "`[{}]` **{}**\n".format(i, _def.get('word', 'none').title().replace('\n', ''))
                body += '```{:.200}```\n'.format(_def.get('def', 'no definition found'))

            res = await confirm_dialog(
                self.client,
                channel,
                user,
                title="Multiple definitions for '{}'".format(args[0]),
                description=body,
                options=tuple(str(x) for x in range(len(definitions))),
                colour=discord.Colour.orange()
            )

            if not res or res.content == '0':
                definition = definitions[0]
            else:
                definition = definitions[int(res.content)]

        if not definition:
            definition = definitions[0]

        await self.client.send_typing(channel)

        for i in definition:
            definition[i] = re.sub(r'/\n+/', r'\n', definition[i])

        embed = discord.Embed(
            title=definition.get('word', 'No title'),
            colour=discord.Colour.gold(),
            url='http://www.urbandictionary.com/define.php?term=' + re.sub(' ', '%20', definition['word']),
            description=definition.get('def', 'no definition found')
        )

        embed.set_footer(
            text='Urban Dictionary',
            icon_url='http://d2gatte9o95jao.cloudfront.net/assets/apple-touch-icon-2f29e978facd8324960a335075aa9aa3.png'
        )

        if re.sub(r'\n', r'', definition['example']) != '':
            embed.add_field(
                name='Example',
                value=definition.get('example', 'No example found')
            )

        await self.client.send_message(
            channel,
            embed=embed
        )
