import os
import socket
import subprocess
import requests

from .. import app, cache


def as_int(val, on_fail=0):
    if val is None:
        return on_fail
    try:
        return int(val)
    except ValueError:
        return on_fail


def format_mapname(mapname):
    formatted_names = {
        'de_cbble': 'Cobblestone',
        'de_dust2': 'Dust II',
    }
    if mapname in formatted_names:
        return formatted_names[mapname]
    else:
        de_map = mapname.startswith('de_')
        if de_map:
            return mapname[3:].title()
        else:
            return mapname


def check_server_connection(server):
    response = send_rcon_command(
        server.ip_string, server.port, server.rcon_password, 'status')
    return response is not None


def check_server_avaliability(server):
    import json

    if not server:
        return None, 'Server not found'

    response = send_rcon_command(
        server.ip_string, server.port, server.rcon_password, 'get5_web_avaliable')

    if response:
        json_error = False
        already_live = False
        try:
            json_reply = json.loads(response)
            already_live = json_reply['gamestate'] != 0
        except (ValueError, KeyError):
            json_error = True

    if response is None:
        return None, 'Failed to connect to server'

    elif 'Unknown command' in str(response):
        return None, 'Either get5 or get5_apistats plugin missing'

    elif already_live:
        return None, 'Server already has a get5 match setup'

    elif json_error:
        return None, 'Error reading get5_web_avaliable response'

    else:
        return json_reply, ''


class RconError(ValueError):
    pass


def send_rcon_command(host, port, rcon_password, command,
                      raise_errors=False, num_retries=3, timeout=3.0):
    from valve.rcon import (RCON, RCONMessageError,
                            RCONAuthenticationError, RCONTimeoutError)

    try:
        port = int(port)
    except ValueError:
        return None

    attempts = 0
    while attempts < num_retries:
        attempts += 1
        try:
            with RCON((host, port), rcon_password, timeout=timeout) as rcon:
                response = rcon(command)
                return strip_rcon_logline(response)
        except (socket.error, socket.timeout,
                RCONMessageError, RCONAuthenticationError, RCONTimeoutError) as e:
            if attempts >= num_retries:
                if raise_errors:
                    raise RconError(str(e))
                else:
                    return None


def strip_rcon_logline(response):
    lines = response.splitlines()
    if len(lines) >= 1:
        last_line = lines[len(lines) - 1]
        if 'rcon from' in last_line:
            return '\n'.join(lines[:len(lines) - 1])

    return response


def get_version():
    try:
        root_dir = os.path.realpath(os.path.join(
            os.getcwd(), os.path.dirname(__file__), '..'))
        cmd = ['git', 'describe', '--tags', '--always']
        return subprocess.check_output(cmd, cwd=root_dir).strip().decode('utf8')
    except (OSError, subprocess.CalledProcessError):
        return None


@cache.memoize(timeout=60 * 60 * 12)  # 0.5 day timeout
def get_steam_name(steam64):
    url = 'http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={}&steamids={}'
    url = url.format(app.config['STEAM_API_KEY'], steam64)
    response = requests.get(url)
    if response.status_code == 200:
        try:
            player_list = response.json()['response']['players']
            return player_list[0]['personaname']
        except (KeyError, IndexError):
            return None

    return None
