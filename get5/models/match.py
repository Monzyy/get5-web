import random
import string
from flask import url_for, Markup
from .. import db
from . import User, GameServer


class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    server_id = db.Column(db.Integer, db.ForeignKey('game_server.id'), index=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'))
    challonge_id = db.Column(db.Integer, index=True, nullable=True)
    team1_id = db.Column(db.Integer, db.ForeignKey('team.id'))
    team2_id = db.Column(db.Integer, db.ForeignKey('team.id'))
    team1_string = db.Column(db.String(32), default='')
    team2_string = db.Column(db.String(32), default='')
    winner = db.Column(db.Integer, db.ForeignKey('team.id'))
    plugin_version = db.Column(db.String(32), default='unknown')

    forfeit = db.Column(db.Boolean, default=False)
    cancelled = db.Column(db.Boolean, default=False)
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    max_maps = db.Column(db.Integer)
    title = db.Column(db.String(60), default='')
    skip_veto = db.Column(db.Boolean)
    api_key = db.Column(db.String(32))

    veto_process = db.Column(db.PickleType)
    veto_progress = db.Column(db.PickleType)
    veto_mappool = db.Column(db.PickleType)
    final_mappool = db.Column(db.PickleType)
    map_stats = db.relationship('MapStats', backref='match', lazy='dynamic')

    team1_score = db.Column(db.Integer, default=0)
    team2_score = db.Column(db.Integer, default=0)

    @staticmethod
    def create(user, team1_id, team2_id, team1_string, team2_string,
               max_maps, skip_veto, title, veto_mappool, veto_process=None, challonge_id=None, server_id=None):
        rv = Match()
        rv.user_id = user.id
        rv.set_data(team1_id, team2_id, team1_string, team2_string,
                    max_maps, skip_veto, title, veto_mappool, veto_process, challonge_id, server_id)
        rv.api_key = ''.join(random.SystemRandom().choice(
            string.ascii_uppercase + string.digits) for _ in range(24))
        db.session.add(rv)
        return rv

    def set_data(self, team1_id, team2_id, team1_string, team2_string,
                 max_maps, skip_veto, title, veto_mappool, veto_process, challonge_id, server_id):
        self.team1_id = team1_id
        self.team2_id = team2_id
        self.skip_veto = skip_veto
        self.title = title
        self.veto_mappool = veto_mappool if veto_mappool is not None else []
        self.veto_process = veto_process if veto_process is not None else []
        self.veto_progress = []
        self.server_id = server_id
        self.challonge_id = challonge_id
        self.max_maps = max_maps

    def get_status_string(self, show_winner=True):
        if self.pending():
            return 'Pending'
        elif self.live():
            team1_score, team2_score = self.get_current_score()
            return 'Live, {}:{}'.format(team1_score, team2_score)
        elif self.finished():
            t1score, t2score = self.get_current_score()
            min_score = min(t1score, t2score)
            max_score = max(t1score, t2score)
            score_string = '{}:{}'.format(max_score, min_score)

            if not show_winner:
                return 'Finished'
            elif self.winner == self.team1_id:
                return 'Won {} by {}'.format(score_string, self.get_team1().name)
            elif self.winner == self.team2_id:
                return 'Won {} by {}'.format(score_string, self.get_team2().name)
            else:
                return 'Tied {}'.format(score_string)

        else:
            return 'Cancelled'

    def get_vs_string(self):
        team1 = self.get_team1()
        team2 = self.get_team2()
        scores = self.get_current_score()

        str = '{} vs {} ({}:{})'.format(
            team1.get_name_url_html(), team2.get_name_url_html(), scores[0], scores[1])

        return Markup(str)

    def finalized(self):
        return self.cancelled or self.finished()

    def pending(self):
        return self.start_time is None and not self.cancelled

    def finished(self):
        return self.end_time is not None and not self.cancelled

    def live(self):
        return self.start_time is not None and self.end_time is None and not self.cancelled

    def get_server(self):
        return GameServer.query.filter_by(id=self.server_id).first()

    def get_current_score(self):
        if self.max_maps == 1:
            mapstat = self.map_stats.first()
            if not mapstat:
                return (0, 0)
            else:
                return (mapstat.team1_score, mapstat.team2_score)

        else:
            return (self.team1_score, self.team2_score)

    def get_scores(self):
        scores = list()
        for mapstat in self.map_stats.all():
            scores.append((mapstat.team1_score, mapstat.team2_score))
        return scores

    def get_format(self):
        return "Bo{}".format(self.max_maps)

    def send_to_server(self):
        server = GameServer.query.get(self.server_id)
        if not server:
            return False

        url = url_for('match.match_config', matchid=self.id,
                      _external=True, _scheme='http')
        # Remove http protocal since the get5 plugin can't parse args with the
        # : in them.
        url = url.replace("http://", "")
        url = url.replace("https://", "")

        loadmatch_response = server.send_rcon_command(
            'get5_loadmatch_url ' + url)

        server.send_rcon_command(
            'get5_web_api_key ' + self.api_key)

        if loadmatch_response:  # There should be no response
            return False

        return True

    def get_team(self, team_id):
        from . import Team
        return Team.query.get(team_id)

    def get_team1(self):
        return self.get_team(self.team1_id)

    def get_team2(self):
        return self.get_team(self.team2_id)

    def get_user(self):
        return User.query.get(self.user_id)

    def get_winner(self):
        if self.team1_score > self.team2_score:
            return self.get_team1()
        elif self.team2_score > self.team1_score:
            return self.get_team2()
        else:
            return None

    def get_loser(self):
        if self.team1_score > self.team2_score:
            return self.get_team2()
        elif self.team2_score > self.team1_score:
            return self.get_team1()
        else:
            return None

    def build_match_dict(self):
        d = {}
        d['matchid'] = str(self.id)
        d['match_title'] = self.title

        d['skip_veto'] = self.skip_veto
        if self.max_maps == 2:
            d['bo2_series'] = True
        else:
            d['maps_to_win'] = self.max_maps / 2 + 1

        def add_team_data(teamkey, teamid, matchtext):
            from . import Team
            team = Team.query.get(teamid)
            if not team:
                return
            d[teamkey] = {}

            # Add entries if they have values.
            def add_if(key, value):
                if value:
                    d[teamkey][key] = value
            add_if('name', team.name)
            add_if('name', team.name)
            add_if('tag', team.tag)
            add_if('flag', team.flag.upper())
            add_if('logo', team.logo)
            add_if('matchtext', matchtext)
            d[teamkey]['players'] = [x for x in team.auths if x != '']

        add_team_data('team1', self.team1_id, self.team1_string)
        add_team_data('team2', self.team2_id, self.team2_string)

        d['cvars'] = {}

        d['cvars']['get5_web_api_url'] = url_for(
            'home', _external=True, _scheme='http')

        if self.veto_mappool and not self.skip_veto:
            d['maplist'] = self.veto_mappool
        else:
            d['maplist'] = self.final_mappool

        return d

    def __repr__(self):
        return 'Match(id={})'.format(self.id)