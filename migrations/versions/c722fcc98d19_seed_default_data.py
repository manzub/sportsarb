"""seed default data

Revision ID: c722fcc98d19
Revises: d656435773c0
Create Date: 2025-12-05 21:28:50.870169

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c722fcc98d19'
down_revision = 'd656435773c0'
branch_labels = None
depends_on = None



def upgrade():
  op.execute("""
    INSERT INTO plans (plan_name, price, stripe_price_id, duration)
    VALUES 
      ('Basic', 9.99, 'price_1SD4iYFL77NInx71sxYlHcbR', 30),
      ('Premium', 29.99, 'price_1SI9LBFL77NInx71t8YkLJYv', 30)
    ON CONFLICT (plan_name) DO NOTHING;
  """)

  op.execute("""
    INSERT INTO app_settings (setting_name, value)
    VALUES
      ('default_plan_benefit',
      '{"pre-match odds": true,
        "in-play odds": false,
        "valuebets": false,
        "middlebets": false,
        "surebets": true}'::jsonb),
      ('basic_plan_benefit',
      '{"pre-match odds": true,
        "in-play odds": true,
        "valuebets": false,
        "middlebets": true,
        "surebets": true}'::jsonb),
      ('premium_plan_benefit',
      '{"pre-match odds": true,
        "in-play odds": true,
        "valuebets": true,
        "middlebets": true,
        "surebets": true}'::jsonb),
      ('exchange_rates',
      '{"USD": 1,
        "GBP": 0.79,
        "EUR": 0.93,
        "NGN": 1600}'::jsonb),
      ('bookmaker_region','"uk"'::jsonb),
      ('finder_fetch_results','true'::jsonb),
      ('finder_use_offline','true'::jsonb),
      ('finder_save_offline','false'::jsonb),
      ('free_plan_cutoff','"1.0"'::jsonb),
      ('app_name','"SBFinder"'::jsonb)
    ON CONFLICT (setting_name) DO NOTHING;
  """)


  op.execute("""
    INSERT INTO users (email, password, is_admin, is_verified, auth_provider, active)
    VALUES ('admin@sbfinder.com', 'scrypt:32768:8:1$BZ4Xo7TuwjYxQdxG$6971cf5a78fa6721b9771ae539ce064cff0f6e035febb83a5f56a7398794a20f60523a96ae4994357acd6fdcf124b8658a1fdd018aa2fc9e5b7eb19469a906f0', TRUE, TRUE, 'local', TRUE)
    ON CONFLICT (email) DO NOTHING;
  """)


def downgrade():
  op.execute("DELETE FROM plans;")
  op.execute("DELETE FROM app_settings;")
  op.execute("DELETE FROM users WHERE email='admin@sbfinder.com';")