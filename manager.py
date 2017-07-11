#!/usr/bin/env python3.6

import get5
from get5 import db
import get5.models

import flask_script
import flask_migrate

manager = flask_script.Manager(get5.app)

# Database migrations
migrate = flask_migrate.Migrate(get5.app, get5.db)
manager.add_command('db', flask_migrate.MigrateCommand)


if __name__ == '__main__':
    manager.run()
