import datetime
from .. import db
from . import Match


class MapStats(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('match.id'))
    map_number = db.Column(db.Integer)
    map_name = db.Column(db.String(64))
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    winner = db.Column(db.Integer, db.ForeignKey('team.id'))
    team1_score = db.Column(db.Integer, default=0)
    team2_score = db.Column(db.Integer, default=0)
    player_stats = db.relationship(
        'PlayerStats', backref='mapstats', lazy='dynamic')

    @staticmethod
    def get_or_create(match_id, map_number, map_name=''):
        match = Match.query.get(match_id)
        if match is None or map_number >= match.max_maps:
            return None

        rv = MapStats.query.filter_by(
            match_id=match_id, map_number=map_number).first()
        if rv is None:
            rv = MapStats()
            rv.match_id = match_id
            rv.map_number = map_number
            rv.map_name = map_name
            rv.start_time = datetime.datetime.utcnow()
            rv.team1_score = 0
            rv.team2_score = 0
            db.session.add(rv)
        return rv

    def __repr__(self):
        return 'MapStats(' + str(self.id) + ',' + str(self.map_name) + ')'



class PlayerStats(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('match.id'))
    map_id = db.Column(db.Integer, db.ForeignKey('map_stats.id'))
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'))
    steam_id = db.Column(db.String(40))
    name = db.Column(db.String(40))
    kills = db.Column(db.Integer, default=0)
    deaths = db.Column(db.Integer, default=0)
    roundsplayed = db.Column(db.Integer, default=0)
    assists = db.Column(db.Integer, default=0)
    flashbang_assists = db.Column(db.Integer, default=0)
    teamkills = db.Column(db.Integer, default=0)
    suicides = db.Column(db.Integer, default=0)
    headshot_kills = db.Column(db.Integer, default=0)
    damage = db.Column(db.Integer, default=0)
    bomb_plants = db.Column(db.Integer, default=0)
    bomb_defuses = db.Column(db.Integer, default=0)
    v1 = db.Column(db.Integer, default=0)
    v2 = db.Column(db.Integer, default=0)
    v3 = db.Column(db.Integer, default=0)
    v4 = db.Column(db.Integer, default=0)
    v5 = db.Column(db.Integer, default=0)
    k1 = db.Column(db.Integer, default=0)
    k2 = db.Column(db.Integer, default=0)
    k3 = db.Column(db.Integer, default=0)
    k4 = db.Column(db.Integer, default=0)
    k5 = db.Column(db.Integer, default=0)
    firstkill_t = db.Column(db.Integer, default=0)
    firstkill_ct = db.Column(db.Integer, default=0)
    firstdeath_t = db.Column(db.Integer, default=0)
    firstdeath_Ct = db.Column(db.Integer, default=0)

    def get_steam_url(self):
        return 'http://steamcommunity.com/profiles/{}'.format(self.steam_id)

    def get_rating(self):
        AverageKPR = 0.679
        AverageSPR = 0.317
        AverageRMK = 1.277
        KillRating = float(self.kills) / float(self.roundsplayed) / AverageKPR
        SurvivalRating = float(self.roundsplayed -
                               self.deaths) / self.roundsplayed / AverageSPR
        killcount = float(self.k1 + 4 * self.k2 + 9 *
                          self.k3 + 16 * self.k4 + 25 * self.k5)
        RoundsWithMultipleKillsRating = killcount / self.roundsplayed / AverageRMK
        rating = (KillRating + 0.7 * SurvivalRating +
                  RoundsWithMultipleKillsRating) / 2.7
        return rating

    def get_kdr(self):
        if self.deaths == 0:
            return float(self.kills)
        else:
            return float(self.kills) / self.deaths

    def get_hsp(self):
        if self.kills == 0:
            return 0.0
        else:
            return float(self.headshot_kills) / self.kills

    def get_adr(self):
        if self.roundsplayed == 0:
            return 0.0
        else:
            return float(self.damage) / self.roundsplayed

    def get_fpr(self):
        if self.roundsplayed == 0:
            return 0.0
        else:
            return float(self.kills) / self.roundsplayed

    @staticmethod
    def get_or_create(matchid, mapnumber, steam_id):
        mapstats = MapStats.get_or_create(matchid, mapnumber)
        if len(mapstats.player_stats.all()) >= 40:  # Cap on players per map
            return None

        rv = mapstats.player_stats.filter_by(steam_id=steam_id).first()

        if rv is None:
            rv = PlayerStats()
            rv.match_id = matchid
            rv.map_number = mapstats.id
            rv.steam_id = steam_id
            rv.map_id = mapstats.id
            db.session.add(rv)

        return rv



