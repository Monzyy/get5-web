from flask import url_for
from .. import app, db



class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    steam_id = db.Column(db.String(40), unique=True)
    name = db.Column(db.String(40))
    admin = db.Column(db.Boolean, default=False)
    servers = db.relationship('GameServer', backref='user', lazy='dynamic')
    teams = db.relationship('Team', backref='user', lazy='dynamic')
    matches = db.relationship('Match', backref='user', lazy='dynamic')
    tournaments = db.relationship('Tournament', backref='user', lazy='dynamic')

    @staticmethod
    def get_or_create(steam_id):
        rv = User.query.filter_by(steam_id=steam_id).one_or_none()
        if rv is None:
            rv = User()
            rv.steam_id = steam_id
            db.session.add(rv)
            app.logger.info('Creating user for {}'.format(steam_id))
            rv.admin = ('ADMIN_IDS' in app.config) and (
                steam_id in app.config['ADMIN_IDS'])
        return rv

    def get_url(self):
        return url_for('user', userid=self.id)

    def get_steam_url(self):
        return 'http://steamcommunity.com/profiles/{}'.format(self.steam_id)

    def get_recent_matches(self, limit=10):
        return self.matches.filter_by(cancelled=False).limit(limit)

    def __repr__(self):
        return 'User(id={}, steam_id={}, name={}, admin={})'.format(
            self.id, self.steam_id, self.name, self.admin)