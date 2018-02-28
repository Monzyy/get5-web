from flask import Blueprint, request, render_template, flash, g, redirect, jsonify, url_for
from wtforms import (
    Form, validators,
    StringField, BooleanField,
    SelectField, ValidationError)

from .. import app, db, flash_errors, config_setting, utils
from ..models import User, Team
from ..utils import countries, logos, steamid


team_blueprint = Blueprint('team', __name__)


def valid_auth(form, field):
    # Ignore empty data fields
    if field.data is None or field.data == '':
        return

    # Otherwise validate and coerce to steam64
    suc, newauth = steamid.auth_to_steam64(field.data)
    if suc:
        field.data = newauth
    else:
        raise ValidationError('Invalid Steam ID')


class TeamForm(Form):
    name = StringField('Team Name', validators=[
        validators.required(),
        validators.Length(min=-1, max=Team.name.type.length)])

    tag = StringField('Team Tag', validators=[
        validators.required(), validators.Length(min=-1, max=Team.tag.type.length)])

    flag_choices = [('', 'None')] + countries.country_choices
    country_flag = SelectField(
        'Country Flag', choices=flag_choices, default='')

    logo_choices = logos.get_logo_choices()
    logo = SelectField('Logo Name', choices=logo_choices, default='')

    auth1 = StringField('Player 1', validators=[valid_auth])
    auth2 = StringField('Player 2', validators=[valid_auth])
    auth3 = StringField('Player 3', validators=[valid_auth])
    auth4 = StringField('Player 4', validators=[valid_auth])
    auth5 = StringField('Player 5', validators=[valid_auth])
    auth6 = StringField('Player 6', validators=[valid_auth])
    auth7 = StringField('Player 7', validators=[valid_auth])
    open_join = BooleanField('Allow users to join team')
    public_team = BooleanField('Public Team')

    def get_auth_list(self):
        auths = []
        for i in range(1, 8):
            key = 'auth{}'.format(i)
            auths.append(self.data[key])

        return auths


@team_blueprint.route('/team/create', methods=['GET', 'POST'])
def team_create():
    if not g.user:
        return redirect('/login')

    form = TeamForm(request.form)

    if request.method == 'POST':
        num_teams = g.user.teams.count()
        max_teams = config_setting('USER_MAX_TEAMS')
        if max_teams >= 0 and num_teams >= max_teams and not g.user.admin:
            flash(
                'You already have the maximum number of teams ({}) stored'.format(num_teams))

        elif form.validate():
            data = form.data
            auths = form.get_auth_list()

            team = Team.create(user=g.user, name=data['name'], tag=data['tag'],
                               flag=data['country_flag'], logo=data['logo'],
                               auths=auths, challonge_id=None, public_team=data['public_team'] and g.user.admin,
                               open_join=data['open_join'])

            db.session.commit()
            app.logger.info(
                'User {} created team {}'.format(g.user.id, team.id))

            return redirect('/teams/{}'.format(team.user_id))

        else:
            flash_errors(form)

    return render_template('team_create.html', user=g.user, form=form,
                           edit=False, is_admin=g.user.admin)


@team_blueprint.route('/team/<int:teamid>', methods=['GET'])
def team(teamid):
    team = Team.query.get_or_404(teamid)
    tournament_list = team.tournaments
    return render_template('team.html', user=g.user, team=team, tournament_list=tournament_list)


@team_blueprint.route('/team/<int:teamid>/join', methods=['GET'])
def team_join(teamid):
    if not g.user:
        return redirect('/login')
    team = Team.query.get_or_404(teamid)
    if not team.open_join:
        flash('Team does not allow joining!', 'danger')
    elif '' not in team.auths:
        flash('Team is full!', 'danger')
    elif g.user.steam_id not in team.auths:
        auths = list(team.auths)
        auths[auths.index('')] = g.user.steam_id
        team.auths = auths
        db.session.commit()
    else:
        flash('You are already a part of this team', 'warning')
    return redirect(url_for('team.team', teamid=teamid))


@team_blueprint.route('/team/<int:teamid>/edit', methods=['GET', 'POST'])
def team_edit(teamid):
    team = Team.query.get_or_404(teamid)
    if not team.can_edit(g.user):
        return 'Not your team', 400

    form = TeamForm(
        request.form,
        name=team.name,
        tag=team.tag,
        country_flag=team.flag,
        logo=team.logo,
        auth1=team.auths[0],
        auth2=team.auths[1],
        auth3=team.auths[2],
        auth4=team.auths[3],
        auth5=team.auths[4],
        auth6=team.auths[5],
        auth7=team.auths[6],
        public_team=team.public_team,
        open_join=team.open_join)

    if request.method == 'GET':
        return render_template('team_create.html', user=g.user, form=form,
                               edit=True, is_admin=g.user.admin)

    elif request.method == 'POST':
        if request.method == 'POST':
            if form.validate():
                data = form.data
                team.set_data(data['name'], data['tag'], data['country_flag'],
                              data['logo'], form.get_auth_list(),
                              team.challonge_id,
                              data['public_team'] and g.user.admin,
                              data['open_join'])
                db.session.commit()
                return redirect(url_for('team.team', teamid=teamid))
            else:
                flash_errors(form)

    return render_template('team_create.html', user=g.user, form=form, edit=True,
                           is_admin=g.user.admin)


@team_blueprint.route('/team/<int:teamid>/delete')
def team_delete(teamid):
    team = Team.query.get_or_404(teamid)
    if not team.can_delete(g.user):
        return 'Cannot delete this team', 400
    team.tournaments.clear()
    if Team.query.filter_by(id=teamid).delete():
        db.session.commit()

    return redirect(url_for('team.teams', userid=g.user.id))


@team_blueprint.route('/teams/<int:userid>', methods=['GET'])
def teams_user(userid):
    user = User.query.get_or_404(userid)
    page = utils.as_int(request.values.get('page'), on_fail=1)
    json_data = utils.as_int(request.values.get('json'), on_fail=0)

    if json_data:
        teams_dict = {}
        for team in user.teams:
            team_dict = {}
            team_dict['name'] = team.name
            team_dict['tag'] = team.tag
            team_dict['flag'] = team.flag
            team_dict['logo'] = team.logo
            team_dict['players'] = [x for x in team.auths if bool(x)]
            teams_dict[team.id] = team_dict
        return jsonify(teams_dict)

    else:
        # Render teams page
        my_teams = (g.user is not None and userid == g.user.id)
        teams = user.teams.paginate(page, 20)
        return render_template('teams.html', user=g.user, teams=teams, my_teams=my_teams,
                               page=page, owner=user)


@team_blueprint.route('/teams', methods=['GET'])
def teams():
    page = utils.as_int(request.values.get('page'), on_fail=1)
    teams = Team.query.order_by(-Team.id).paginate(page, 20)
    return render_template('teams.html', user=g.user, teams=teams, page=page)
