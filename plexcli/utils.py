# -*- coding: utf-8 -*-

import math

import click
from plexapi.video import Episode, Movie, Show
from plexapi.utils import download as utils_download


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
                result = [items[z] for z in ips]
                break

            else:
                result = items[int(inp)]
                break

        except(ValueError, IndexError):
            pass

    if not isinstance(result, list):
        result = [result]

    return result


def _download(items, path=None):
    locs = []
    for item in items:
        parts = [i for i in item.iterParts() if i]
        for part in parts:
            filename = '%s.%s' % (item._prettyfilename(), part.container)
            url = item._server.url('%s?download=1' % part.key)
            filepath = utils_download(url, filename=filename, savepath=path,
                                      session=item._server._session, showstatus=True)
            locs.append(filepath)

    return locs


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
                result = [items[z] for z in ips]
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
    result = choose('Choose result', results, lambda x: '(%s) %s %s' %
                    (x.type.title(), x.title[0:60], x._server.friendlyName))
    for r in result:
        if isinstance(r, Show):
            display = lambda i: '%s %s %s' % (r.grandparentTitle, r.seasonEpisode, r.title)
            final += choose('Choose episode', r.episodes(), display)
        else:
            final.append(r)

    return final


def convert_size(size_bytes):
    # stole from stackoverflow
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return "%s %s" % (s, size_name[i])



def get_genre(item):
    if item.TYPE == 'episode':
        return item.show().genres
    return item.genres
