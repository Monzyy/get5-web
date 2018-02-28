from flask import Blueprint, request, render_template, flash, g, redirect, jsonify, Markup, url_for

from ..utils import steamid
from .. import app, db, BadRequestError, config_setting, flash_errors, utils
from ..models import User, Team, Match



veto_blueprint = Blueprint('veto', __name__)

def parse_progress(progress):
    progress_list = []
    for step in progress:
        team_no, action, mapname = step.split(':')
        progress_list.append({
            'team': int(team_no),
            'action': action,
            'mapname': mapname
        })
    return progress_list


@veto_blueprint.route('/veto/<int:matchid>')
def veto(matchid):
    match = Match.query.get_or_404(matchid)
    team1 = Team.query.get_or_404(match.team1_id)
    team2 = Team.query.get_or_404(match.team2_id)
    if match.veto_process is None or not match.veto_process:
        flash('Veto not meant to be done here dawg', 'danger')
        return redirect(url_for('match.match', matchid=matchid))

    return render_template('veto.html', match=match, mappool=match.veto_mappool, 
                           user=g.user, process=match.veto_process, team1=team1, team2=team2,
                           progress=parse_progress(match.veto_progress))

@veto_blueprint.route('/veto/<int:matchid>/refresh')
def refresh(matchid):
    match = Match.query.get_or_404(matchid)
    resp = {}
    num = len(match.veto_progress)
    
    if request.args.get('progress_count', type=int) <= num:
        resp['progress'] = parse_progress(match.veto_progress)
        resp['progress_count'] = num  
        if len(match.veto_process) > num:
            resp['next_action'] = dict(zip(('team', 'action'), match.veto_process[num].split(':')))
    resp['done'] = (len(match.veto_progress) == len(match.veto_mappool))
    return jsonify(resp)

@veto_blueprint.route('/veto/<int:matchid>/action', methods=['POST'])
def action(matchid):
    if not g.user:
        return jsonify({'error': 'You are not allowed to participate in the vetoes!'})
    match = Match.query.get_or_404(matchid)
    step_idx = len(match.veto_progress) if match.veto_progress is not None else 0
    if step_idx == len(match.veto_process):
        return jsonify({})
    this_step = match.veto_process[step_idx]
    team_no, act = this_step.split(':')
    team_id = match.team1_id if int(team_no) is 1 else match.team2_id
    team = Team.query.get_or_404(team_id)
    if g.user.steam_id not in team.auths:
        return jsonify({'error': 'You are not allowed to choose on behalf of the another team! Hacker-boy...'})
    mapname = request.form.get('mapname')
    if mapname not in match.veto_mappool or \
       mapname in ' '.join(match.veto_progress):
        return jsonify({'error': 'Cannot veto that map! Hacker-boy...'})

    veto_map(match, team_no, act, mapname)
    if step_idx + 1 == len(match.veto_process):
        mps = ' '.join(match.veto_progress)
        for mp in match.veto_mappool:
            if mp not in mps:
                veto_map(match, 0, 'p', mp)

    db.session.commit()

    return jsonify({'team_no': team_no, 'action': act, 'mapname': mapname})


def veto_map(match, team_no, step, mapname):
    updated_progress = list(match.veto_progress if match.veto_progress is not None else [])
    updated_progress.append("{}:{}:{}".format(team_no, step, mapname))
    match.veto_progress = updated_progress
    if step == 'p':
        updated_final = list(match.final_mappool if match.final_mappool is not None else [])
        updated_final.append(mapname)
        match.final_mappool = list(updated_final)