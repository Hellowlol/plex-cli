# -*- coding: utf-8 -*-

"""Console script for plexcli."""

import os
import logging
from functools import partial

import click
import fire
from tqdm import tqdm

from plexapi import CONFIG
from plexapi.myplex import MyPlexAccount
from plexapi.server import PlexServer
from plexapi.video import Episode, Movie, Show

from .utils import choose, convert_size, get_genre, prompt, select, _download


LOG = logging.getLogger(__file__)


# Just patch this to keep it dry
click.prompt = partial(click.prompt, prompt_suffix='> ')


class CLI():
    """Simple cli for plex. --dry_run=True to test commands."""
    def __init__(self, username=None, password=None, servername=None, debug=False, dry_run=False):
        self._username = username or CONFIG.get('auth.myplex_username')
        self._password = password or CONFIG.get('auth.myplex_password')
        self._servername = servername or CONFIG.get('default.servername')
        self._dry_run = dry_run

        if not self._username or not self._password:
            self._username = click.prompt('Enter username')
            self._password = click.prompt('Enter password')

        if debug:
            logging.basicConfig(level=logging.DEBUG)

        self.__account = MyPlexAccount(self._username, self._password)

    def _get_server(self, servername=None, owned=False, msg='Select server'):
        """Helper for servers."""
        if servername:
            return self.__account.resource(servername).connect()

        servers = [s for s in self.__account.resources() if 'server' in s.provides]
        if owned:
            servers = [s for s in server is s.owned]

        server = choose(msg, servers, 'name')
        n = server[0].connect()
        return n

    def browser(self, servername=None):
        """Open the plex web interface in your default browser.

           Args:
                servername (str): the server your want to use.

        """
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
        return click.launch(url)

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

    def account(self):
        """Access to the account."""
        return self.__account

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
                if not self._dry_run:
                    result = select(result)
                    _download(result, save_path)
                else:
                    click.echo('Skipping download bacause of dry_run')

            else:
                for item in result:
                    do = getattr(item, cmd)
                    if callable(do):
                        if self._dry_run is False:
                            # Make sure we protect the user from doing stupid stuff.
                            if cmd == 'delete':
                                title = item.title or item.name
                                if click.confirm('Are you sure you wish to delete %s?' % title):
                                    do()

                            else:
                                do()
                        else:
                            click.echo('Skipping %s on %s becaue of dry_run' % (do, item.title))

        return result

    def kick(self, user, reason=''):
        """Stop a playback on your server."""
        pms = self._get_server()
        for mediaitem in pms.sessions():
            un = ''.join(mediaitem.usernames).lower()
            if un == user.lower():
                click.echo('Stopped playback on %s %s' % (un, reason))
                mediaitem.stop(reason)

    def watching(self):
        """Who's streaming from your server."""
        pms = self._get_server()
        sessions = pms.sessions()
        c = choose('Select a user',
                   sessions,
                   lambda k: '%s %s' % (''.join(k.usernames), k.title))

        return sessions

    def share(self, user, sections=None, servername=None):
        """Share library(s) with a user.
           WARNING: BY default this will add EVERY sections!

           Args:
                user (str): the user you want to share with.
                sections (str): sections
                servername (str): the server you want to share.

           Returns: None

        """
        pms = self._get_server(servername)

        if sections is None:
            sections = pms.sections()
        else:
            sections = sections.split(',')
            sections = [s for s in pms.section if s.title in sections]

        if self._dry_run is False:
            self.__account.inviteFriend(user, pms, sections)
            click.echo('Shared %s on %s with %s' % (','.join(i.title for i in pms.sections()), pms.friendlyName, user))

    def unshare(self, user):
        self.__account.removeFriend(user)
        click.echo('Unshared %s' % user)

    def remove_dupes(self, lang='nor', ignore_category='Family'):
        """Remove any duplicates from your movie library.

           Args:
                lang (str): ex nor, eng etc.
                ingnore_ignore_category (str): Usefull for kids movies where i have duplicates because of language

           Returns:
                None

        """
        pms = self._get_server()

        ignore_category = ignore_category.split()
        removed_files_size = 0
        to_delete = []
        all_dupes = []

        for section in pms.library.sections():
            if section.TYPE in ('movie'):
                all_dupes = section.search(duplicate=True)
            elif section.TYPE in ('show'):
                all_dupes += section.search(libtype='episode', duplicate=True)

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
                    LOG.debug('Skipping, because of lang code')
                    continue

                elif ignore_category and any(True for i in get_genre(item) if i.tag == ignore_category):
                    LOG.debug('Skipping, because of ignore_category')
                    continue

                else:
                    LOG.debug('Added to delete list.')
                    to_delete.append((media, part))


        for i, (media, part) in enumerate(to_delete):
            click.echo('%s: %s' % (i, part.file))

        result = prompt('Select what files you want to delete', to_delete)

        delete = False
        if click.confirm('Are your sure you wish to delete %s files' % len(result)):
            delete = True

        # This has to require a double confirm as there is no turning back.
        if delete is True:
            delete = False
            if click.confirm('Are your really sure you want to delete the files? There is NO turning back'):
                delete = True

        for media, part in result:
            removed_files_size += part.size
            if delete:
                if self._dry_run is False:
                    click.secho('Deleting %s %s' % (part.file, convert_size(part.size)), fg='red')
                    media.delete()
                else:
                    click.echo('Didnt deleting %s %s because of dry_run' % (part.file, convert_size(part.size)))


        click.secho('Deleted %s files freeing up %s' % (len(result),
                   convert_size(removed_files_size)), fg='red')



    def diff(self, my_servername, your_servername, section_type=None):
        """E-PEEN check"""
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

        #missing = []
        #for your_item in your_result:
        #    if your_item not in my_result:
        #        missing.append(your_item)

        #for miss in missing:
        #    click.echo(miss.title)

    def sync(self, frm=None, too=None, section_type=None, two_way=False):
        """ Sync between servers.

            Args:
                frm (str): the server you want to sync from
                too (str): the server you want to sync too
                section_type(str): The sections types you want synced.
                two_way (bool): Sync two ways

        """
        my_result = []
        your_result = []

        your = self._get_server(frm, msg='Select the server you want to sync from')
        mine = self._get_server(too, msg='Select the server you want to sync too')

        if section_type is None:
            # Lets try to set some sane defaults
            section_type = ('show', 'movie')
        else:
            section_type.split(',')

        for section in your.library.sections():
            # Let's lean on pms for this one as plexapi does not support this atm
            # using plexapi for this takes more 40 sec in my library.
            if section.TYPE == 'show':
                key = '/library/sections/%s/all?type=4&viewCount>=0' % section.key
                your_result += section.fetchItems(key)

            elif section.TYPE == 'movie':
                key = '/library/sections/%s/all?viewCount>=0' % section.key
                your_result += section.fetchItems(key)

        # remove this when it cached in plexapi
        check_sections = [section for section in your.library.sections() if section.TYPE in section_type]
        with tqdm(your_result) as yr:
            for item in yr:
                for section in check_sections:
                    # Accessing a guid requires a reload..
                    # But i dont't know a better way to make sure
                    # we checking the same items.
                    result = section.search(guid=item.guid)
                    if result:
                        mf = result[0]
                        tqdm.write('Setting %s as WATCHED on %s' % (mf._prettyfilename(), mine.friendlyName))
                        mf.markAsWatched()

        if two_way:
            click.echo('Started too sync the other way')
            sync(mine.friendlyName, your.friendlyName, section_type=','.join(section_type))
















def main():
    fire.Fire(CLI)



if __name__ == '__main__':
    main()
