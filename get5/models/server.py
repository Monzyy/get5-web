from .. import app, db, cache, utils


class GameServer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    display_name = db.Column(db.String(32), default='')
    ip_string = db.Column(db.String(32))
    port = db.Column(db.Integer)
    rcon_password = db.Column(db.String(32))
    in_use = db.Column(db.Boolean, default=False)
    public_server = db.Column(db.Boolean, default=False, index=True)

    @staticmethod
    def create(user, display_name, ip_string, port, rcon_password, public_server):
        rv = GameServer()
        rv.user_id = user.id
        rv.display_name = display_name
        rv.ip_string = ip_string
        rv.port = port
        rv.rcon_password = rcon_password
        rv.public_server = public_server
        db.session.add(rv)
        return rv

    def send_rcon_command(self, command, raise_errors=False, num_retries=3, timeout=3.0):
        return utils.send_rcon_command(self.ip_string, self.port, self.rcon_password,
                                       command, raise_errors, num_retries, timeout)

    def get_hostport(self):
        return '{}:{}'.format(self.ip_string, self.port)

    def get_display(self):
        if self.display_name:
            return '{} ({})'.format(self.display_name, self.get_hostport())
        else:
            return self.get_hostport()

    def __repr__(self):
        return self.get_display()