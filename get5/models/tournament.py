from .. import db
from . import User

TournamentTeam = db.Table('tournament_team', db.Model.metadata,
                          db.Column('tournament_id', db.Integer,
                                    db.ForeignKey('tournament.id')),
                          db.Column('team_id', db.Integer,
                                    db.ForeignKey('team.id'))
                          )

TournamentGameServer = db.Table('tournament_gameserver', db.Model.metadata,
                                db.Column('tournament_id', db.Integer,
                                          db.ForeignKey('tournament.id')),
                                db.Column('game_server_id', db.Integer,
                                          db.ForeignKey('game_server.id'))
                                )


class Tournament(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    winner = db.Column(db.Integer, db.ForeignKey('team.id'))
    cancelled = db.Column(db.Boolean, default=False)
    finished = db.Column(db.Boolean, default=False)
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    name = db.Column(db.String(60))
    url = db.Column(db.String(60))
    challonge_id = db.Column(db.Integer)
    challonge_data = db.Column(db.PickleType)
    participants = db.relationship(
        'Team', secondary=TournamentTeam, backref='tournaments', lazy='dynamic')
    matches = db.relationship('Match', backref='tournament', lazy='dynamic')
    serverpool = db.relationship(
        'GameServer', secondary=TournamentGameServer, backref='tournaments', lazy='dynamic')
    veto_mappool = db.Column(db.String(160))

    @staticmethod
    def create(user, name, url, veto_mappool, serverpool=None, challonge_id=None, challonge_data=None):
        rv = Tournament()
        rv.user_id = user.id
        rv.url = url
        rv.name = name
        rv.veto_mappool = ' '.join(veto_mappool)
        if serverpool:
            rv.serverpool.extend(serverpool)
        rv.challonge_id = challonge_id
        rv.challonge_data = challonge_data
        db.session.add(rv)
        return rv

    def finalized(self):
        return self.cancelled or self.finished()

    def pending(self):
        return self.start_time is None and not self.cancelled

    def finished(self):
        return self.end_time is not None and not self.cancelled

    def live(self):
        return self.start_time is not None and self.end_time is None and not self.cancelled

    def get_user(self):
        return User.query.get(self.user_id)

    def get_available_server(self):
        for server in self.serverpool.all():
            if not server.in_use:
                return server
        return None

    def __repr__(self):
        return 'Tournament(id={})'.format(self.id)
