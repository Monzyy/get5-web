import datetime
from flask import Blueprint, request, render_template, flash, g, redirect, jsonify, Markup, url_for

from . import steamid
import get5
from get5 import app, db, BadRequestError, config_setting
from .models import User, Team, Tournament, Match, GameServer
from . import util

from wtforms import (
    Form, widgets, validators,
    StringField, RadioField,
    SelectField, ValidationError, SelectMultipleField)
from wtforms.ext.sqlalchemy.fields import QuerySelectField

match_blueprint = Blueprint('match', __name__)


class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


def different_teams_validator(form, field):
    if form.team1.data == form.team2.data:
        raise ValidationError('Teams cannot be equal')


def mappool_validator(form, field):
    if 'preset' in form.series_type.data and len(form.veto_mappool.data) != 1:
        raise ValidationError(
            'You must have exactly 1 map selected to do a bo1 with a preset map')

    max_maps = 1
    try:
        max_maps = int(form.series_type.data[2])
    except ValueError:
        max_maps = 1

    if len(form.veto_mappool.data) < max_maps:
        raise ValidationError(
            'You must have at least {} maps selected to do a Bo{}'.format(max_maps, max_maps))

def server_query_factory():
    return GameServer.query.filter((GameServer.public_server == True) | (GameServer.user_id == g.user.id))

def team_query_factory():
    return Team.query.filter((Team.public_team == True) | (Team.user_id == g.user.id))

class MatchForm(Form):
    server = QuerySelectField('Server', validators=[validators.required()],
                              query_factory=server_query_factory)

    match_title = StringField('Match title text',
                              default='Map {MAPNUMBER} of {MAXMAPS}',
                              validators=[validators.Length(min=-1, max=Match.title.type.length)])

    series_type = RadioField('Series type',
                             validators=[validators.required()],
                             default='bo1',
                             choices=[
                                 ('bo1-preset', 'Bo1 with preset map'),
                                 ('bo1', 'Bo1 with map vetoes'),
                                 ('bo2', 'Bo2 with map vetoes'),
                                 ('bo3', 'Bo3 with map vetoes'),
                                 ('bo5', 'Bo5 with map vetoes'),
                                 ('bo7', 'Bo7 with map vetoes'),
                             ])

    team1 = QuerySelectField('Team 1', get_label='name', validators=[validators.required()],
                             query_factory=team_query_factory)

    team1_string = StringField('Team 1 title text',
                               default='',
                               validators=[validators.Length(min=-1,
                                                             max=Match.team1_string.type.length)])

    team2 = QuerySelectField('Team 2', get_label='name', query_factory=team_query_factory,
                             validators=[validators.required(), different_teams_validator])

    team2_string = StringField('Team 2 title text',
                               default='',
                               validators=[validators.Length(min=-1,
                                                             max=Match.team2_string.type.length)])

    mapchoices = config_setting('MAPLIST')
    default_mapchoices = config_setting('DEFAULT_MAPLIST')
    veto_mappool = MultiCheckboxField('Map pool',
                                      choices=[(
                                          name, util.format_mapname(name)) for name in mapchoices],
                                      default=default_mapchoices,
                                      validators=[mappool_validator],
                                      )


@match_blueprint.route('/match/create', methods=['GET', 'POST'])
def match_create():
    if not g.user:
        return redirect('/login')

    form = MatchForm(request.form)

    if request.method == 'POST':
        num_matches = g.user.matches.count()
        max_matches = config_setting('USER_MAX_MATCHES')

        if max_matches >= 0 and num_matches >= max_matches and not g.user.admin:
            flash('You already have the maximum number of matches ({}) created'.format(
                num_matches), 'danger')

        if form.validate():
            mock = config_setting('TESTING')
            
            server = form.server.data
            import q; q(server)

            match_on_server = g.user.matches.filter_by(
                server_id=server.id, end_time=None, cancelled=False).first()

            server_avaliable = False
            json_reply = None

            if g.user.id != server.user_id:
                server_avaliable = False
                message = 'This is not your server!'
            elif match_on_server is not None:
                server_avaliable = False
                message = 'Match {} is already using this server'.format(
                    match_on_server.id)
            elif mock:
                server_avaliable = True
                message = 'Success'
            else:
                json_reply, message = util.check_server_avaliability(
                    server)
                server_avaliable = (json_reply is not None)

            if server_avaliable:
                skip_veto = 'preset' in form.data['series_type']
                try:
                    max_maps = int(form.data['series_type'][2])
                except ValueError:
                    max_maps = 1

                match = Match.create(
                    g.user, form.team1.data.id, form.team2.data.id,
                    form.data['team1_string'], form.data['team2_string'],
                    max_maps, skip_veto, form.data['match_title'],
                    form.data['veto_mappool'], server_id=server.id)

                # Save plugin version data if we have it
                if json_reply and 'plugin_version' in json_reply:
                    match.plugin_version = json_reply['plugin_version']
                else:
                    match.plugin_version = 'unknown'

                server.in_use = True

                db.session.commit()
                app.logger.info('User {} created match {}, assigned to server {}'
                                .format(g.user.id, match.id, server.id))

                if mock or match.send_to_server():
                    return redirect('/mymatches')
                else:
                    flash('Failed to load match configs on server', 'danger')
            else:
                flash(message, 'warning')

        else:
            get5.flash_errors(form)

    return render_template('match_create.html', form=form, user=g.user, teams=g.user.teams,
                           match_text_option=config_setting('CREATE_MATCH_TITLE_TEXT'))


@match_blueprint.route('/match/<int:matchid>')
def match(matchid):
    match = Match.query.get_or_404(matchid)
    team1 = Team.query.get_or_404(match.team1_id)
    team2 = Team.query.get_or_404(match.team2_id)
    map_stat_list = match.map_stats.all()

    is_owner = False
    has_admin_access = False

    if g.user:
        is_owner = (g.user.id == match.user_id)
        has_admin_access = is_owner or (config_setting(
            'ADMINS_ACCESS_ALL_MATCHES') and g.user.admin)

    return render_template('match.html', user=g.user, admin_access=has_admin_access,
                           match=match, team1=team1, team2=team2,
                           map_stat_list=map_stat_list)


@match_blueprint.route('/match/<int:matchid>/edit', methods=['GET', 'POST'])
def match_edit(matchid):
    match = Match.query.get_or_404(matchid)
    admintools_check(g.user, match)

    form = MatchForm(
        request.form,
        server=GameServer.query.get(match.server_id),
        series_type="bo{}".format(match.max_maps),
        team1=Team.query.get(match.team1_id),
        team2=Team.query.get(match.team2_id),)

    if request.method == 'GET':
        return render_template('match_create.html', user=g.user, form=form,
                               edit=True, is_admin=g.user.admin)

    elif request.method == 'POST':
        if request.method == 'POST':
            if form.validate() or True: # TODO form validation on edit
                skip_veto = 'preset' in form.data['series_type']
                try:
                    max_maps = int(form.data['series_type'][2])
                except ValueError:
                    max_maps = 1
                data = form.data
                update_dict = {
                    'team1_id': form.team1.data.id,
                    'team2_id': form.team2.data.id,
                    'max_maps': max_maps,
                    'server_id': form.server.data.id,
                }
                Match.query.filter_by(id=matchid).update(update_dict)
                db.session.commit()
                return redirect(url_for('match.match', matchid=matchid))
            else:
                get5.flash_errors(form)

    return render_template('match_create.html', user=g.user, form=form, edit=True,
                           is_admin=g.user.admin)



@match_blueprint.route('/match/<int:matchid>/config')
def match_config(matchid):
    match = Match.query.get_or_404(matchid)
    dict = match.build_match_dict()
    return jsonify(dict)


def admintools_check(user, match):
    if user is None:
        raise BadRequestError('You do not have access to this page')

    grant_admin_access = user.admin and get5.config_setting(
        'ADMINS_ACCESS_ALL_MATCHES')
    if user.id != match.user_id and not grant_admin_access:
        raise BadRequestError('You do not have access to this page')

    if match.finished():
        raise BadRequestError('Match already finished')

    if match.cancelled:
        raise BadRequestError('Match is cancelled')


@match_blueprint.route('/match/<int:matchid>/start')
def match_start(matchid):
    match = Match.query.get_or_404(matchid)
    admintools_check(g.user, match)

    if match.server_id is None:
        tournament = Tournament.query.get_or_404(match.tournament_id)
        server = tournament.get_available_server()
        if server:
            match.server_id = server.id
            server.in_use = True
        else:
            flash('No server currently available in tournament server pool!', 'danger')
            return redirect(url_for('match.match', matchid=matchid))
    else:
        server = GameServer.query.get(match.server_id)
    json_reply, message = util.check_server_avaliability(server)
    server_avaliable = (json_reply is not None)
    if server_avaliable:
        if 'plugin_version' in json_reply.keys():
            match.plugin_version = json_reply['plugin_version']
        else:
            match.plugin_version = 'unknown'
        match.start_time = datetime.datetime.utcnow()
        if match.send_to_server():
            db.session.commit()
            return redirect('/mymatches')

    flash("Failed to start match... " + message, 'warning')
    return redirect(url_for('match.match', matchid=matchid))

@match_blueprint.route('/match/<int:matchid>/cancel')
def match_cancel(matchid):
    match = Match.query.get_or_404(matchid)
    admintools_check(g.user, match)

    match.cancelled = True
    server = None
    if match.server_id:
        server = GameServer.query.get(match.server_id)
        if server:
            server.in_use = False
   
    db.session.commit()

    try:
        server.send_rcon_command('get5_endmatch', raise_errors=True)
    except (AttributeError, util.RconError) as e:
        flash('Failed to cancel match on server: ' + str(e), 'danger')

    return redirect('/mymatches')


@match_blueprint.route('/match/<int:matchid>/rcon')
def match_rcon(matchid):
    match = Match.query.get_or_404(matchid)
    admintools_check(g.user, match)

    command = request.values.get('command')
    server = GameServer.query.get_or_404(match.server_id)

    if command:
        try:
            rcon_response = server.send_rcon_command(
                command, raise_errors=True)
            if rcon_response:
                rcon_response = Markup(rcon_response.replace('\n', '<br>'))
            else:
                rcon_response = 'No output'
            flash(rcon_response)
        except util.RconError as e:
            print(e)
            flash('Failed to send command: ' + str(e), 'danger')

    return redirect('/match/{}'.format(matchid))


@match_blueprint.route('/match/<int:matchid>/pause')
def match_pause(matchid):
    match = Match.query.get_or_404(matchid)
    admintools_check(g.user, match)
    server = GameServer.query.get_or_404(match.server_id)

    try:
        server.send_rcon_command('sm_pause', raise_errors=True)
        flash('Paused match')
    except util.RconError as e:
        flash('Failed to send pause command: ' + str(e), 'danger')

    return redirect('/match/{}'.format(matchid))


@match_blueprint.route('/match/<int:matchid>/unpause')
def match_unpause(matchid):
    match = Match.query.get_or_404(matchid)
    admintools_check(g.user, match)
    server = GameServer.query.get_or_404(match.server_id)

    try:
        server.send_rcon_command('sm_unpause', raise_errors=True)
        flash('Unpaused match')
    except util.RconError as e:
        flash('Failed to send unpause command: ' + str(e), 'danger')

    return redirect('/match/{}'.format(matchid))


@match_blueprint.route('/match/<int:matchid>/adduser')
def match_adduser(matchid):
    match = Match.query.get_or_404(matchid)
    admintools_check(g.user, match)
    server = GameServer.query.get_or_404(match.server_id)
    team = request.values.get('team')
    if not team:
        raise BadRequestError('No team specified')

    auth = request.values.get('auth')
    suc, new_auth = steamid.auth_to_steam64(auth)
    if suc:
        try:
            command = 'get5_addplayer {} {}'.format(new_auth, team)
            response = server.send_rcon_command(command, raise_errors=True)
            flash(response)
        except util.RconError as e:
            flash('Failed to send command: ' + str(e))

    else:
        flash('Invalid steamid: {}'.format(auth), 'warning')

    return redirect('/match/{}'.format(matchid))


@match_blueprint.route('/match/<int:matchid>/backup', methods=['GET'])
def match_backup(matchid):
    match = Match.query.get_or_404(matchid)
    admintools_check(g.user, match)
    server = GameServer.query.get_or_404(match.server_id)
    file = request.values.get('file')

    if not file:
        # List backup files
        backup_response = server.send_rcon_command(
            'get5_listbackups ' + str(matchid))
        if backup_response:
            backup_files = sorted(backup_response.split('\n'))
        else:
            backup_files = []

        return render_template('match_backup.html', user=g.user,
                               match=match, backup_files=backup_files)

    else:
        # Restore the backup file
        command = 'get5_loadbackup {}'.format(file)
        response = server.send_rcon_command(command)
        if response:
            flash('Restored backup file {}'.format(file), 'success')
        else:
            flash('Failed to restore backup file {}'.format(file), 'danger')
            return redirect('match/{}/backup'.format(matchid))

        return redirect('match/{}'.format(matchid))


@match_blueprint.route("/matches")
def matches():
    page = util.as_int(request.values.get('page'), on_fail=1)
    matches = Match.query.order_by(-Match.id).filter_by(
        cancelled=False).paginate(page, 20)
    return render_template('matches.html', user=g.user, matches=matches,
                           my_matches=False, all_matches=True, page=page)


@match_blueprint.route("/matches/<int:userid>")
def matches_user(userid):
    user = User.query.get_or_404(userid)
    page = util.as_int(request.values.get('page'), on_fail=1)
    matches = user.matches.order_by(-Match.id).paginate(page, 20)
    is_owner = (g.user is not None) and (userid == g.user.id)
    return render_template('matches.html', user=g.user, matches=matches,
                           my_matches=is_owner, all_matches=False, match_owner=user, page=page)


@match_blueprint.route("/mymatches")
def mymatches():
    if not g.user:
        return redirect('/login')

    return redirect('/matches/' + str(g.user.id))
