import datetime
from hashlib import md5
import time
from flask import Blueprint, request, render_template, flash, g, redirect, jsonify, Markup, url_for

from . import steamid
import get5
from get5 import app, db, BadRequestError, config_setting
from .models import User, Team, Match, GameServer, Tournament
from . import util
from . import challonge

from wtforms import (
    Form, widgets, validators,
    StringField, RadioField,
    SelectField, ValidationError, SelectMultipleField)
from wtforms.ext.sqlalchemy.fields import QuerySelectMultipleField

tournament_blueprint = Blueprint('tournament', __name__)

chall = challonge.ChallongeClient()

class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()

def server_query_factory():
    return GameServer.query.filter((GameServer.public_server == True) | (GameServer.user_id == g.user.id))

class AddServers(Form):
    serverpool = QuerySelectMultipleField('Server pool', query_factory=server_query_factory,
                                          option_widget=widgets.CheckboxInput())

class TournamentForm(Form):
    tournament_name = StringField('Tournament name',
                                  default=config_setting('BRAND') + ' tournament',
                                  validators=[validators.Length(min=-1, max=Tournament.name.type.length)])

    tournament_url = StringField('Tournament url',
                                 default=md5(str(time.time()).encode('ascii')).hexdigest(),
                                 validators=[validators.Length(min=-1,
                                                               max=Tournament.url.type.length)])

    tournament_type = RadioField('Tournament type',
                             validators=[validators.required()],
                             default='bo1',
                             choices=[
                                 ('single elimination', 'single elimination'.title()),
                                 ('double elimination', 'double elimination'.title()),
                                 ('round robin', 'round robin'.title()),
                             ])

    serverpool = QuerySelectMultipleField('Server pool', query_factory=server_query_factory,
                                          option_widget=widgets.CheckboxInput())

    mapchoices = config_setting('MAPLIST')
    default_mapchoices = config_setting('DEFAULT_MAPLIST')
    veto_mappool = MultiCheckboxField('Map pool',
                                      choices=[(name, util.format_mapname(name)) for name in mapchoices],
                                      default=default_mapchoices,
                                      validators=[validators.required()])

@tournament_blueprint.route('/tournament/create', methods=['GET', 'POST'])
def tournament_create():
    if not g.user:
        return redirect('/login')

    form = TournamentForm(request.form)

    if request.method == 'POST':
        num_tournaments = g.user.tournaments.count()
        max_tournaments = config_setting('USER_MAX_TOURNAMENTS')

        if max_tournaments >= 0 and num_tournaments >= max_tournaments and not g.user.admin:
            flash('You already have the maximum number of tournaments ({}) created'.format(
                num_tournaments))

        if form.validate():
            mock = config_setting('TESTING')

            reply = {}
            if mock:
                reply['id'] = 1234
                reply['name'] = "Testy McTestTournament"
                reply['full_challonge_url'] = "http://www.test.mctest/test"
                message = 'Success'
            else:
                try:
                    reply = chall.create_tournament(name=form.data['tournament_name'],
                                                    url=form.data['tournament_url'])
                    reply = reply['tournament']
                except challonge.ChallongeException as e:
                    flash(str(e))


            if reply['id']:
                t = Tournament.create(g.user, reply['name'], reply['full_challonge_url'],
                                      challonge_id=reply['id'], challonge_data=reply,
                                      veto_mappool=form.data['veto_mappool'],
                                      serverpool=form.serverpool.data)

                db.session.commit()
                app.logger.info('User {} created tournament {} - {} url {}'
                                .format(g.user.id, t.id, t.name, t.url))

                return redirect(url_for('tournament.tournament', tournamentid=t.id))
        else:
            get5.flash_errors(form)

    return render_template('tournament_create.html', form=form, user=g.user)


@tournament_blueprint.route('/tournament/<int:tournamentid>')
def tournament(tournamentid):
    tournament = Tournament.query.get_or_404(tournamentid)
    participants = tournament.participants.all()
    matches = tournament.matches.all()
    pending_matches = [match for match in matches if match.pending()]
    live_matches = [match for match in matches if match.live()]
    finished_matches = [match for match in matches if match.finished()]
    serverpool = tournament.serverpool.all()

    is_owner = False
    has_admin_access = False

    if g.user:
        is_owner = (g.user.id == tournament.user_id)
        has_admin_access = is_owner or (config_setting(
            'ADMINS_ACCESS_ALL_TOURNAMENTS') and g.user.admin)

    return render_template('tournament.html', user=g.user, admin_access=has_admin_access,
                           tournament=tournament, participants=participants,
                           live_matches=live_matches, finished_matches=finished_matches,
                           pending_matches=pending_matches, serverpool=serverpool)


@tournament_blueprint.route('/tournament/<int:tournamentid>/sync')
def tournament_sync(tournamentid):
    tournament = Tournament.query.get_or_404(tournamentid)
    admintools_check(g.user, tournament)
    try:
        reply = chall.tournament(tournament.challonge_id, include_participants=True, include_matches=True)
        reply = reply['tournament']
    except challonge.ChallongeException as e:
        flash(str(e), 'danger')
    else:
        tournament.name = reply['name']
        tournament.url = reply['full_challonge_url']
        tournament.challonge_data = reply
        db.session.commit()
        if 'participants' in reply.keys() and reply['participants']:
            sync_participants(tournament, [p['participant'] for p in reply['participants']])
        if 'matches' in reply.keys() and reply['matches']:
            sync_matches(tournament, [m['match'] for m in reply['matches']])
    return redirect(url_for('tournament.tournament', tournamentid=tournamentid))


def sync_participants(tournament, participants):
    t_participant_ids = {p.id for p in tournament.participants.all()}
    c_participant_ids = {int(p['misc']) for p in participants if p['misc'] is not None}
    for team_id in t_participant_ids.difference(c_participant_ids):
        team = Team.query.get(team_id)
        tournament.participants.remove(team)
        db.session.commit()

    for participant in participants:
        if participant['misc'] is None:
            _create_and_add_participant(tournament, participant)
        elif int(participant['misc']) not in t_participant_ids:
            team = Team.query.get(int(participant['misc']))
            if team:
                tournament.participants.append(team)
                db.session.commit()
            else:
                _create_and_add_participant(tournament, participant)


def _create_and_add_participant(tournament, participant):
    team = Team.create(g.user, name=participant['name'],
                       tag=participant['display_name'],
                       challonge_id=participant['id'],
                       flag=None, logo=None, auths=None, open_join=True)
    db.session.commit()
    try:
        chall.update_participant_misc(tournament.challonge_id, participant['id'], team.id)
    except challonge.ChallongeException as e:
         flash(e)
    else:
        tournament.participants.append(team)
        db.session.commit()


def sync_matches(tournament, challonge_matches):
    t_match_ids = {m.challonge_id for m in tournament.matches.all()}
    c_match_ids = {m['id'] for m in challonge_matches}
    for match_challonge_id in t_match_ids.difference(c_match_ids):
        match = Match.query.filter_by(challonge_id=match_challonge_id).first()
        tournament.matches.remove(match)
        db.session.commit()

    for match_dict in challonge_matches:
        if match_dict['id'] not in t_match_ids:
            _create_and_add_match(tournament, match_dict)


def _create_and_add_match(tournament, match_dict):
    if match_dict['player1_id'] is not None and match_dict['player2_id'] is not None:
        team1 = Team.query.filter_by(challonge_id=match_dict['player1_id']).first()
        team2 = Team.query.filter_by(challonge_id=match_dict['player2_id']).first()
    else:
        return

    match = Match.create(user=g.user, team1_id=team1.id, team2_id=team2.id,
                         team1_string=None, team2_string=None,
                         max_maps=1, skip_veto=False,
                         title='{} - Round {}'.format(ord(match_dict['identifier'].lower()) - 96, match_dict['round']),
                         veto_mappool=tournament.veto_mappool.split(' '),
                         challonge_id=match_dict['id'])
    tournament.matches.append(match)
    db.session.commit()

def admintools_check(user, tournament):
    if user is None:
        raise BadRequestError('You do not have access to this page')

    grant_admin_access = user.admin and get5.config_setting(
        'ADMINS_ACCESS_ALL_TOURNAMENTS')
    if user.id != tournament.user_id and not grant_admin_access:
        raise BadRequestError('You do not have access to this page')

    if tournament.cancelled:
        raise BadRequestError('tournament is cancelled')

@tournament_blueprint.route('/tournament/<int:tournamentid>/start')
def tournament_start(tournamentid):
    tournament = Tournament.query.get_or_404(tournamentid)
    admintools_check(g.user, tournament)

    try:
        data = chall.start_tournament(tournament.challonge_id)
    except challonge.ChallongeException as e:
        flash(e.message)
    else:
        tournament.start_time = datetime.datetime.utcnow()
        tournament.challonge_data = data['tournament']
        db.session.commit()
        sync_matches(tournament, [d['match'] for d in data['tournament']['matches']])

    return redirect(url_for('tournament.tournament', tournamentid=tournamentid))

@tournament_blueprint.route('/tournament/<int:tournamentid>/reset')
def tournament_reset(tournamentid):
    tournament = Tournament.query.get_or_404(tournamentid)
    admintools_check(g.user, tournament)

    try:
        data = chall.reset_tournament(tournament.challonge_id)
    except challonge.ChallongeException as e:
        flash(e.message)
    else:
        tournament.start_time = None
        tournament.challonge_data = data['tournament']
        db.session.commit()

    # TODO handle pending matches

    return redirect(url_for('tournament.tournament', tournamentid=tournamentid))

@tournament_blueprint.route('/tournament/<int:tournamentid>/cancel')
def tournament_cancel(tournamentid):
    tournament = Tournament.query.get_or_404(tournamentid)
    admintools_check(g.user, tournament)

    tournament.cancelled = True

    db.session.commit()

    # TODO cancel all matches!

    return redirect('/mytournaments')

@tournament_blueprint.route("/tournaments")
def tournaments():
    page = util.as_int(request.values.get('page'), on_fail=1)
    tournaments = Tournament.query.order_by(-Tournament.id).filter_by(
        cancelled=False).paginate(page, 20)
    return render_template('tournaments.html', user=g.user, tournaments=tournaments,
                           my_tournaments=False, all_tournaments=True, page=page)


@tournament_blueprint.route("/tournaments/<int:userid>")
def tournaments_user(userid):
    user = User.query.get_or_404(userid)
    page = util.as_int(request.values.get('page'), on_fail=1)
    tournaments = user.tournaments.order_by(-Tournament.id).paginate(page, 20)
    is_owner = (g.user is not None) and (userid == g.user.id)
    return render_template('tournaments.html', user=g.user, tournaments=tournaments,
                           my_tournaments=is_owner, all_tournaments=False, tournament_owner=user, page=page)


@tournament_blueprint.route("/mytournaments")
def mytournaments():
    if not g.user:
        return redirect('/login')

    return redirect('/tournaments/' + str(g.user.id))


@tournament_blueprint.route('/tournament/<int:tournamentid>/add_servers', methods=['GET', 'POST'])
def tournament_add_servers(tournamentid):
    tournament = Tournament.query.get_or_404(tournamentid)
    admintools_check(g.user, tournament)

    form = AddServers(request.form)

    if request.method == 'POST':
        if form.validate():
            tournament.serverpool = form.serverpool.data

            db.session.commit()

            return redirect(url_for('tournament.tournament', tournamentid=tournament.id))
        else:
            get5.flash_errors(form)

    return render_template('tournament_add_servers.html', form=form, user=g.user)

