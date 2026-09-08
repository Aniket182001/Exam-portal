import sys
import os

# Add parent dir to path so we can import app and extensions
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))

from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.migration import MigrationContext
from app import create_app
from app.extensions import db

def check_migration_sync():
    """
    Checks if the database is in sync with the codebase's alembic migrations.
    Returns:
        0: Synced
        10: Migration required, valid path
        1: Divergent / Corrupted / Fatal error
    """
    try:
        app = create_app()
        cfg = Config("migrations/alembic.ini")
        cfg.set_main_option("script_location", "migrations")
        script = ScriptDirectory.from_config(cfg)
        
        heads = script.get_heads()
        if len(heads) == 0:
            print("No migrations found in codebase.")
            return 0
        if len(heads) > 1:
            print(f"FATAL: Multiple migration heads found in codebase: {heads}")
            return 1
            
        expected_head = heads[0]
        print(f"Codebase expected migration head: {expected_head}")
        
        with app.app_context():
            with db.engine.connect() as conn:
                ctx = MigrationContext.configure(conn)
                current_rev = ctx.get_current_revision()
                
        print(f"Database current revision: {current_rev}")
        
        if current_rev == expected_head:
            print("Database is completely synced with codebase.")
            return 0
            
        # Check if there's a valid path
        try:
            rev_steps = list(script.iterate_revisions(expected_head, current_rev))
            if not rev_steps:
                # Should not happen unless current_rev is somehow an ancestor but iterate_revisions returned empty
                print("FATAL: Cannot resolve upgrade path.")
                return 1
            print(f"Valid migration path found from {current_rev} to {expected_head}.")
            return 10
        except Exception as e:
            print(f"FATAL: Divergent or missing migration path: {e}")
            return 1
            
    except Exception as e:
        print(f"FATAL error checking migration sync: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(check_migration_sync())
