# -*- coding: utf-8 -*-

"""Console script for plexcli."""

import os

from tqdm import tqdm
import click
import fire

from plexapi import CONFIG
from plexapi.myplex import MyPlexAccount
from plexapi.server import PlexServer
from plexapi.utils import download as utils_download
from plexapi.video import Episode, Movie, Show



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
    result = choose('Choose result', results, lambda x: '(%s) %s' % (x.type.title(), x.title[0:60]))
    for r in result:
        if isinstance(r, Show):
            display = lambda i: '%s %s %s' % (r.grandparentTitle, r.seasonEpisode, r.title)
            final += choose('Choose episode', r.episodes(), display)
        else:
            final.append(r)

    return final



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
            self.__server = self.__account.resource(servername).connect()
            return self._server

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
                            if click.confirm('Are you sure you wish to delete'):
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

    def diff(self, mine, yours, section_type=None):
        raise NotImplementedError
        mine = self._get_server(mine)
        your = self._get_server(yours)


