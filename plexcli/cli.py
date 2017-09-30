# -*- coding: utf-8 -*-

"""Console script for plexcli."""

import os

from tqdm import tqdm
import click
import fire

from plexapi import CONFIG
from plexapi.myplex import MyPlexAccount
from plexapi.server import PlexServer
#from plexapi.utils import download as utils_download
from plexapi.video import Episode, Movie, Show

from .utils import convert_size, prompt, _download, choose, select

"""
def prompt(msg, items):
    result = []
    while True:
        try:
            inp = click.prompt('%s' % msg)
            if any(s in inp for s in (':', '::', '-')):
                idx = slice(*map(lambda x: int(x.strip()) if x.strip() else None, inp.split(':')))
                result =  items[idx]
                break
            elif ',' in inp:
                ips = [int(i.strip()) for i in inp.split()]
                result = [item[z] for z in items]
                break

            else:
                result = items[int(inp)]
                break

        except(ValueError, IndexError):
            pass

    return result




def _download(items, path=None):
    for item in items:
        parts = [i for i in item.iterParts() if i]
        for part in parts:
            filename = '%s.%s' % (item._prettyfilename(), part.container)
            url = item._server.url('%s?download=1' % part.key)
            filepath = utils_download(url, filename=filename, savepath=path,
                                      session=item._server._session, showstatus=True)
            print('  %s' % filepath)


def choose(msg, items, attr):
    result = []

    if not len(items):
        return result

    click.echo('')
    for i, item in enumerate(items):
        name = attr(item) if callable(attr) else getattr(item, attr)
        click.echo('%s %s' % (i, name))

    click.echo('')

    while True:
        try:
            inp = click.prompt('%s' % msg)
            if any(s in inp for s in (':', '::', '-')):
                idx = slice(*map(lambda x: int(x.strip()) if x.strip() else None, inp.split(':')))
                result =  items[idx]
                break
            elif ',' in inp:
                ips = [int(i.strip()) for i in inp.split()]
                result = [item[z] for z in items]
                break

            else:
                result = items[int(inp)]
                break

        except(ValueError, IndexError):
            pass

    if not isinstance(result, list):
        result = [result]

    return result


def select(results):
    final = []
    result = choose('Choose result', results, lambda x: '(%s) %s %s' % (x.type.title(), x.title[0:60], x._server.friendlyName))
    for r in result:
        if isinstance(r, Show):
            display = lambda i: '%s %s %s' % (r.grandparentTitle, r.seasonEpisode, r.title)
            final += choose('Choose episode', r.episodes(), display)
        else:
            final.append(r)

    return final
"""


class CLI():
    """Main class for the cli mostly used for storage."""
    def __init__(self, username=None, password=None, servername=None, debug=False):
        self._username = username or CONFIG.get('auth.myplex_username')
        self._password = password or CONFIG.get('auth.myplex_password')
        self._servername = servername or CONFIG.get('default.servername')
        self.__server = None

        if not self._username or not self._password:
            self._username = click.prompt('Enter username')
            self._password = click.prompt('Enter password')

        if debug:
            pass

        self.__account = MyPlexAccount(self._username, self._password)

    def _get_server(self, servername=None, owned=False):
        """Helper for servers."""
        if servername:
            return self.__account.resource(servername).connect()
            #return self.__server

        servers = [s for s in self.__account.resources() if 'server' in s.provides]
        if owned:
            servers = [s for s in server is s.owned]

        server = choose('Select server', servers, 'name')
        n = server[0].connect()
        return n

    def server(self, name=None):
        """Command for PlexServer.

           Args:
                name(str): Default None. We will use this one,
                           if not we will check in the config then propt your for one

           Returns:
                PlexServer

           Example:
                plex-cli server S-PC library section TV-Shows update
        """

        n = name or self._servername
        if not n:
            return self._get_server()

        return self.__account.resource(n).connect()

    def search(self, query, cmd=None, save_path=None, all_servers=False):
        """Search plex using hub search on your own or on all servers.
           If you pass a cmd it will be called in the items you select

           Args:
                query(str): What to search for.
                cmd(str): What command to execute, default None.
                save_path(str): default None, Where to save downloads.
                all_servers(bool): Should we search all the servers you have access to.

           Returns
                list: of selected items.
        """

        result = []
        if all_servers:
            for server in [s for s in self.__account.resources() if 'server' in s.provides]:
                result += server.connect().search(query)
        else:
            pms = self._get_server()
            result += pms.search(query)

        if result and cmd:

            if cmd == 'download':
                result = select(result)
                _download(result, save_path)

            else:
                for item in result:
                    do = getattr(item, cmd)
                    if callable(do):
                        # Make sure protect the user from stupid stuff
                        if cmd == 'delete':
                            title = item.title or item.name
                            if click.confirm('Are you sure you wish to delete %s?' % title):
                                do()
                        else:
                            do()

        return result

    def kick(self, user, reason=''):
        pms = self._get_server()
        for mediaitem in pms.sessions():
            un = ''.join(mediaitem.usernames).lower()
            if un == user.lower():
                click.echo('Stopped playback on %s %s' % (un, reason))
                mediaitem.stop(reason)

    def watching(self):
        pms = self._get_server()
        c = choose('Select a user',
                   pms.sessions(),
                   lambda k: '%s %s' % (''.join(k.usernames), k.title))

        return

    def share(self, user, sections=None, servername=None):
        # THIS TOOL WILL ADD EVERY section by default!
        pms = self._get_server(servername)
        self.__account.inviteFriend(user, pms, pms.sections())
        click.echo('Shared %s on %s with %s' % (','.join(i.title for i in pms.sections()), pms.friendlyName, user))

    def unshare(self, user):
        self.__account.removeFriend(user)
        click.echo('Unshared %s' % user)

    def remove_dupes(self, lang='nor', ignore_category='Family'):
        """Remove any duplicates from your movie library.

           Args:
                lang (str): ex nor, eng etc.
                ingnore_ignore_category (str): Usefull for kids movies where i duplicates because of language

           Returns:
                None

        """
        pms = self._get_server()

        ignore_category = ignore_category.split()
        removed_files_size = 0
        deleted = []
        to_delete = []

        for section in pms.library.sections():
            # make sure we handle epds too if not
            # go this another way.
            if section.TYPE in ('movie'):
                sec_dupes = section.search(duplicate=True)
                for item in sec_dupes:
                    zipped = zip(item.media, item.iterParts())
                    parts = sorted(zipped, key=lambda i: i[1].size, reverse=True)
                    for media, part in parts[1:]:

                        if lang and any([True for i in part.audioStreams() if i.langCode == lang]):
                            continue
                        elif ignore_category and any(True for i in item.genres if i.tag == ignore_category):
                            continue
                        else:
                            to_delete.append((media, part))


        # Should the user be allowed to choose what should be deleted?
        click.echo('Got %s after the filers.' % len(to_delete))

        for i, (media, part) in enumerate(to_delete):
            click.echo('%s: %s' % (i, part.file))

        result = prompt('Select what files you want to delete> ', to_delete)
        #if not isinstance(result, list):
        #    result = [result]

        if click.prompt('Are your sure you wish to delete %s files' % len(result)):
            for media, part in result:
                removed_files_size += part.size
                pass# media.delete()

        click.echo('Deleted %s files freeing up %s' % (len(result),
                   convert_size(removed_files_size)))



    def diff(self, my_servername, your_servername, section_type=None):
        #raise NotImplementedError
        my_result = []
        your_result = []

        mine = self._get_server(my_servername)
        your = self._get_server(your_servername)
        if section_type is None:
            # Lets try to set some sane defaults
            section_type = ('show', 'movie')

        for section in mine.library.sections():
            if section.TYPE in section_type:
                my_result += section.all()

        for section in your.library.sections():
            if section.TYPE in section_type:
                your_result += section.all()

        # Everything below is just silly.
        click.echo('%s got %s' % (mine.friendlyName, len(my_result)))
        click.echo('%s got %s' % (your.friendlyName, len(your_result)))

        if len(my_result) > len(your_result):
            click.echo('You won the epeen contest')
        else:
            click.echo("You lost :'(")

        missing = []
        # fix missing we need to check the guid.
        for your_item in your_result:
            if your_item not in my_result:
                missing.append(your_item)

        print(len(missing))
        #for miss in missing:
        #    click.echo(miss.title)











def main():
    fire.Fire(CLI)



if __name__ == '__main__':
    main()
