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

from .utils import convert_size, prompt, _download, choose, select, get_genre

import logging
#logging.basicConfig(level=logging.DEBUG)


LOG = logging.getLogger(__file__)



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

        servers = [s for s in self.__account.resources() if 'server' in s.provides]
        if owned:
            servers = [s for s in server is s.owned]

        server = choose('Select server', servers, 'name')
        n = server[0].connect()
        return n

    def browser(self, servername=None):
        # So it would be nice if we didnt have to login..
        name = servername or self._servername
        if name:
            name = servername or self._servername
            resource = self.__account.resource(name)
        else:
            servers = [s for s in self.__account.resources() if 'server' in s.provides]
            server = choose('Select server', servers, 'name')
            resource = server[0]

        url = 'https://app.plex.tv/desktop#!/server/%s?key=' % (resource.clientIdentifier)
        try:
            import webbrowser
            ctrl = webbrowser.open(url)
        except:
            pass

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
        to_delete = []
        all_dupes = []

        for section in pms.library.sections():
            # make sure we handle epds too if not
            # go this another way.
            if section.TYPE in ('movie'):
                all_dupes = section.search(duplicate=True)
            elif section.TYPE in ('show'):
                all_dupes += section.search(libtype='episode', duplicate=True)

        # Should we have a spinner to a progess bar? Since this can be slow.
        for item in all_dupes:
            # Remove this hack when https://github.com/pkkid/python-plexapi/issues/201 has been fixed
            patched_items = []
            for zomg in item.media:
                zomg._initpath = item.key
                patched_items.append(zomg)

            zipped = zip(patched_items, item.iterParts())
            parts = sorted(zipped, key=lambda i: i[1].size, reverse=True)

            LOG.debug('Keeping %s %s' %  (parts[0][1].file, convert_size(parts[0][1].size)))
            for media, part in parts[1:]:
                LOG.debug('Checking if %s  %s should be deleted' % (part.file, convert_size(part.size)))

                if lang and any([True for i in part.audioStreams() if i.langCode == lang]):
                    LOG.debug('False, because of lang code')
                    continue

                elif ignore_category and any(True for i in get_genre(item) if i.tag == ignore_category):
                    LOG.debug('False, because of ignore_category')
                    continue

                else:
                    LOG.debug('True')
                    to_delete.append((media, part))

        # Should the user be allowed to choose what should be deleted?
        click.echo('Got %s after the filers.' % len(to_delete))

        for i, (media, part) in enumerate(to_delete):
            click.echo('%s: %s' % (i, part.file))

        result = prompt('Select what files you want to delete> ', to_delete)

        delete = False
        if click.prompt('Are your sure you wish to delete %s files' % len(result)):
            delete = True

        for media, part in result:
            removed_files_size += part.size
            if delete:
                # TODO add click style.
                click.echo('Deleting %s %s' % (part.file, convert_size(part.size)))
                media.delete()

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
