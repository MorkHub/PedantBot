import logging

import wikipedia
from classes.plugin import Plugin

from decorators import *
from util import *

log = logging.getLogger('pedantbot')


class Define(Plugin):
    plugin_name = "lookup words online"

    def __init__(self, *args, **kwargs):
        Plugin.__init__(self, *args, **kwargs)

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

    @command(pattern="^!wikipedia (.+)$",
             description="lookup a term on wikipedia",
             usage="!wikipedia <term>")
    async def wikipedia_lookup(self, message: discord.Message, args: tuple):
        server = message.server  # type: discord.Server
        channel = message.channel  # type: discord.Channel
        user = message.author  # type: discord.Member

        term = args[0]

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
                options = tuple([*[str(x) for x in range(len(results))], 'c']),
                colour=discord.Colour.orange()
            )

            if not res:
                return

            if res.content.lower() == 'c':
                return
            else:
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
                    page=link.replace(" ","_")
                ),
                1
            )

        return subject

    # TODO: !define from wordsapi.com

    # TODO: !urban from urbandict.com

    # TODO: !thesaurus, API unknown