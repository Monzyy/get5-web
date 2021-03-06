"""empty message

Revision ID: d0e6d96ed657
Revises: ded2e28b5186
Create Date: 2017-07-13 18:36:57.053736

"""

# revision identifiers, used by Alembic.
revision = 'd0e6d96ed657'
down_revision = 'ded2e28b5186'

from alembic import op
import sqlalchemy as sa


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('tournament_gameserver',
    sa.Column('tournament_id', sa.Integer(), nullable=True),
    sa.Column('game_server_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['game_server_id'], ['game_server.id'], ),
    sa.ForeignKeyConstraint(['tournament_id'], ['tournament.id'], )
    )
    op.add_column('tournament', sa.Column('veto_mappool', sa.String(length=160), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('tournament', 'veto_mappool')
    op.drop_table('tournament_gameserver')
    # ### end Alembic commands ###
