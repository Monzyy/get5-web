from flask import url_for, Markup
from .. import db, utils
from . import User, Match



class Team(db.Model):
    MAXPLAYERS = 7

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    name = db.Column(db.String(40))
    tag = db.Column(db.String(40), default='')
    flag = db.Column(db.String(4), default='')
    logo = db.Column(db.String(10), default='')
    auths = db.Column(db.PickleType)
    challonge_id = db.Column(db.Integer, index=True, nullable=True)
    public_team = db.Column(db.Boolean, index=True)
    open_join = db.Column(db.Boolean, index=True)

    @staticmethod
    def create(user, name, tag, flag, logo, auths, challonge_id=None, public_team=False, open_join=False):
        rv = Team()
        rv.user_id = user.id
        rv.set_data(name, tag, flag, logo, auths, challonge_id, public_team and user.admin, open_join)
        db.session.add(rv)
        return rv

    def set_data(self, name, tag, flag, logo, auths, challonge_id, public_team, open_join):
        self.name = name
        self.tag = tag
        self.flag = flag.lower() if flag else ''
        self.logo = logo
        if auths is None:
            auths = ['' for _ in range(Team.MAXPLAYERS)]
        self.auths = auths
        self.challonge_id = challonge_id
        self.public_team = public_team
        self.open_join = open_join

    def can_edit(self, user):
        if not user:
            return False
        if self.user_id == user.id:
            return True
        return False

    def get_players(self):
        results = []
        for steam64 in self.auths:
            if steam64:
                name = utils.get_steam_name(steam64)
                if not name:
                    name = ''

                results.append((steam64, name))
        return results

    def can_delete(self, user):
        if not self.can_edit(user):
            return False
        return self.get_recent_matches().count() == 0

    def get_recent_matches(self, limit=10):
        if self.public_team:
            matches = Match.query.order_by(-Match.id).limit(100).from_self()
        else:
            owner = User.query.get_or_404(self.user_id)
            matches = owner.matches

        recent_matches = matches.filter(
            ((Match.team1_id == self.id) | (Match.team2_id == self.id)) & (
                Match.cancelled == False) & (Match.start_time != None)  # noqa: E712
        ).order_by(-Match.id).limit(5)

        if recent_matches is None:
            return []
        else:
            return recent_matches

    def get_vs_match_result(self, match_id):
        other_team = None
        my_score = 0
        other_team_score = 0

        match = Match.query.get(match_id)
        if match.team1_id == self.id:
            my_score = match.team1_score
            other_team_score = match.team2_score
            other_team = Team.query.get(match.team2_id)
        else:
            my_score = match.team2_score
            other_team_score = match.team1_score
            other_team = Team.query.get(match.team1_id)

        # for a bo1 replace series score with the map score
        if match.max_maps == 1:
            mapstat = match.map_stats.first()
            if mapstat:
                if match.team1_id == self.id:
                    my_score = mapstat.team1_score
                    other_team_score = mapstat.team2_score
                else:
                    my_score = mapstat.team2_score
                    other_team_score = mapstat.team1_score

        if match.live():
            return 'Live, {}:{} vs {}'.format(my_score, other_team_score, other_team.name)
        if my_score < other_team_score:
            return 'Lost {}:{} vs {}'.format(my_score, other_team_score, other_team.name)
        elif my_score > other_team_score:
            return 'Won {}:{} vs {}'.format(my_score, other_team_score, other_team.name)
        else:
            return 'Tied {}:{} vs {}'.format(other_team_score, my_score, other_team.name)

    def get_flag_html(self, scale=1.0):
        # flags are expected to be 32x21
        width = int(round(32.0 * scale))
        height = int(round(21.0 * scale))

        html = '<img src="{}"  width="{}" height="{}">'
        output = html.format(
            utils.countries.get_flag_img_path(self.flag), width, height)
        return Markup(output)

    def get_logo_html(self, scale=1.0):
        if utils.logos.has_logo(self.logo):
            width = int(round(32.0 * scale))
            height = int(round(32.0 * scale))
            html = ('<img src="{}"  width="{}" height="{}">')
            return Markup(html.format(utils.logos.get_logo_img(self.logo), width, height))
        else:
            return ''

    def get_url(self):
        return url_for('team.team', teamid=self.id)

    def get_name_url_html(self):
        return Markup('<a href="{}">{}</a>'.format(self.get_url(), self.name))

    def get_logo_or_flag_html(self, scale=1.0, other_team=None):
        if utils.logos.has_logo(self.logo) and (other_team is None or utils.logos.has_logo(other_team.logo)):
            return self.get_logo_html(scale)
        else:
            return self.get_flag_html(scale)

    def __repr__(self):
        return 'Team(id={}, user_id={}, name={}, flag={}, logo={}, public={})'.format(
            self.id, self.user_id, self.name, self.flag, self.logo, self.public_team)
