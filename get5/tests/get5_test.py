import unittest
import logging

from .. import db, app, register_blueprints
from ..models import User, Team, GameServer, Match


# All tests will use this base test framework, including the test date defined
# in create_test_data. This data will already be in the database on test start.
class Get5Test(unittest.TestCase):

    def setUp(self):
        app.config.from_pyfile('test_config.py')
        app.logger.setLevel(logging.ERROR)
        self.app = app.test_client()
        register_blueprints()
        db.create_all()
        self.create_test_data()

    def tearDown(self):
        db.session.remove()
        db.drop_all()

    def create_test_data(self):
        user = User.get_or_create('123')
        user.admin = True
        User.get_or_create('12345')
        db.session.commit()

        team1 = Team.create(user, 'EnvyUs', 'EnvyUs', 'fr',
                            'nv', ['76561198053858673'])
        team2 = Team.create(user, 'Fnatic', 'Fnatic', 'se', 'fntc',
                            ['76561198053858673'])
        server = GameServer.create(
            user, 'myserver1', '127.0.0.1', '27015', 'password', False)
        server.in_use = True

        GameServer.create(user, 'myserver2', '127.0.0.1', '27016', 'password', True)
        db.session.commit()

        Match.create(user=user, team1_id=team1.id, team2_id=team2.id,
                     team1_string='', team2_string='', max_maps=1, skip_veto=False,
                     title='Map {MAPNUMBER}', veto_mappool=['de_dust2', 'de_cache', 'de_mirage'], 
                     challonge_id=None, server_id=server.id)
        db.session.commit()
