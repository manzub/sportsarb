"""updated user.favorite_leagues dialects to jsonb

Revision ID: c6619e55ffd0
Revises: 4c7597ea3cb9
Create Date: 2025-10-27 23:17:46.422758

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'c6619e55ffd0'
down_revision = '4c7597ea3cb9'
branch_labels = None
depends_on = None



def upgrade():
  # Convert array columns to JSONB safely
  op.execute("""
    ALTER TABLE users
    ALTER COLUMN favorite_leagues
    TYPE JSONB
    USING COALESCE(to_jsonb(favorite_leagues), '[]'::jsonb);
  """)

  op.execute("""
    ALTER TABLE users
    ALTER COLUMN favorite_sports
    TYPE JSONB
    USING COALESCE(to_jsonb(favorite_sports), '[]'::jsonb);
  """)


def downgrade():
  op.execute("""
    ALTER TABLE users
    ALTER COLUMN favorite_leagues
    TYPE VARCHAR[] 
    USING ARRAY(
      SELECT jsonb_array_elements_text(favorite_leagues)
    );
  """)

  op.execute("""
    ALTER TABLE users
    ALTER COLUMN favorite_sports
    TYPE VARCHAR[]
    USING ARRAY(
      SELECT jsonb_array_elements_text(favorite_sports)
    );
  """)
