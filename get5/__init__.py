# =============================================================================
# Get5-web
# Copyright (C) 2016. Sean Lewis.  All rights reserved.
# =============================================================================
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import re
import sys
import logging
import logging.handlers

from . import logos
from . import steamid
from . import util
from . import config

from flask import (Flask, render_template, flash, jsonify,
                   request, g, session, redirect)

import flask_cache
import flask_sqlalchemy
import flask_openid
import flask_limiter

# Import the Flask Framework
app = Flask(__name__, instance_relative_config=True)
app.config.from_pyfile('prod_config.py')

def config_setting(key):
    if key in app.config:
        return app.config[key]
    else:
        if key in config.defaults:
            return config.defaults[key]
        else:
            app.logger.error(
                'Tried to lookup missing config setting: %s' % key)
            return None

# Setup caching
cache = flask_cache.Cache(app, config={
    'CACHE_TYPE': 'filesystem',
    'CACHE_DIR': '/tmp',
    'CACHE_THRESHOLD': 25000,
    'CACHE_DEFAULT_TIMEOUT': 60,
})

# Setup openid
oid = flask_openid.OpenID(app)

# Setup database connection
db = flask_sqlalchemy.SQLAlchemy(app)
from .models import User, Team, GameServer, Match, Tournament, MapStats, PlayerStats  # noqa: E402

# Setup rate limiting
limiter = flask_limiter.Limiter(
    app,
    key_func=flask_limiter.util.get_remote_address,
    default_limits=['250 per minute'],
)

# Setup logging
formatter = logging.Formatter(
    '[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s')
if 'LOG_PATH' in app.config:
    file_handler = logging.handlers.TimedRotatingFileHandler(
        app.config['LOG_PATH'], when='midnight')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    app.logger.addHandler(file_handler)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.INFO)
stream_handler.setFormatter(formatter)
app.logger.addHandler(stream_handler)
app.logger.setLevel(logging.INFO)

# Find version info
app.jinja_env.globals.update(VERSION=util.get_version())
app.jinja_env.globals.update(BRAND=config_setting('BRAND'))

# Setup any data structures needed
logos.initialize_logos()
_steam_id_re = re.compile('steamcommunity.com/openid/id/(.*?)$')


def register_blueprints():
    from .api import api_blueprint
    app.register_blueprint(api_blueprint)

    from .tournament import tournament_blueprint
    app.register_blueprint(tournament_blueprint)

    from .match import match_blueprint
    app.register_blueprint(match_blueprint)

    from .team import team_blueprint
    app.register_blueprint(team_blueprint)

    from .server import server_blueprint
    app.register_blueprint(server_blueprint)


@app.route('/login')
@oid.loginhandler
def login():
    if g.user is not None:
        return redirect(oid.get_next_url())
    return oid.try_login('http://steamcommunity.com/openid')


@oid.after_login
def create_or_login(resp):
    match = _steam_id_re.search(resp.identity_url)
    steam_id = match.group(1)
    is_in_whitelist = (steam_id in config_setting('WHITELISTED_IDS'))
    if (not steam_id) or (config_setting('WHITELISTED_IDS') and not is_in_whitelist):
        return 'Sorry, you don\'t have access to this webpanel'

    g.user = User.get_or_create(steam_id)
    steamdata = steamid.get_steam_userinfo(
        g.user.steam_id, app.config['STEAM_API_KEY'])
    g.user.name = steamdata['personaname']
    db.session.commit()
    session['user_id'] = g.user.id
    return redirect(oid.get_next_url())


class BadRequestError(ValueError):
    pass


@app.errorhandler(BadRequestError)
def bad_request_handler(error):
    return bad_request(error.args)


def bad_request(message):
    response = jsonify({'message': message})
    response.status_code = 400
    return response


@app.errorhandler(404)
def page_not_found(e):
    """Return a custom 404 error."""
    return 'Sorry, Nothing at this URL.', 404


@app.errorhandler(500)
def application_error(e):
    """Return a custom 500 error."""
    app.logger.error(e)
    return 'Sorry, unexpected error: {}'.format(e), 500


@app.before_request
def before_request():
    g.user = None
    if 'user_id' in session:
        g.user = User.query.get(session['user_id'])


@app.before_request
def log_entry():
    context = {
        'url': request.path,
        'method': request.method,
        'ip': request.environ.get('REMOTE_ADDR')
    }
    app.logger.debug(
        'Handling %(method)s request from %(ip)s for %(url)s', context)


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(oid.get_next_url())


@app.route('/')
def home():
    return redirect(config_setting('DEFAULT_PAGE'))


def flash_errors(form):
    for field, errors in list(form.errors.items()):
        for error in errors:
            flash('Error in the %s field - %s' % (
                getattr(form, field).label.text,
                error))


@app.route('/user/<int:userid>', methods=['GET'])
def user(userid):
    user = User.query.get_or_404(userid)
    return render_template('user.html', user=g.user, displaying_user=user)


@app.route('/metrics', methods=['GET'])
def metrics():
    return render_template('metrics.html', user=g.user, values=get_metrics())


@cache.cached(timeout=300)
def get_metrics():
    values = []

    def add_val(name, value):
        values.append((name, value))

    add_val('Registered users', User.query.count())
    add_val('Tournaments created', Tournament.query.count())
    add_val('Saved teams', Team.query.count())
    add_val('Matches created', Match.query.count())
    add_val('Servers added', GameServer.query.count())
    add_val('Maps with stats saved', MapStats.query.count())
    add_val('Unique players', PlayerStats.query.distinct().count())
    add_val('Top 10 killers', {player.name: player.kills for player in PlayerStats.query.order_by('kills').limit(10).all()})

    return values

register_blueprints()
