import sys
import os
import argparse
import subprocess
import datetime
import time

def run_cmd(cmd, check=True, cwd=None):
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False, cwd=cwd, text=True, capture_output=True)
    if check and result.returncode != 0:
        print(f"COMMAND FAILED: {' '.join(cmd)}")
        print(f"STDOUT:\n{result.stdout}")
        print(f"STDERR:\n{result.stderr}")
        sys.exit(1)
    return result

def get_ist_time():
    # Convert UTC to IST (+5:30)
    utc = datetime.datetime.now(datetime.timezone.utc)
    ist = utc + datetime.timedelta(hours=5, minutes=30)
    return ist

def stage_1_precheck(args, db_url):
    print("--- STAGE 1: PRECHECK ---")
    ist = get_ist_time()
    print(f"Current IST Time: {ist.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Check deployment window
    hour = ist.hour
    if not (hour >= 22 or hour < 6):
        if args.emergency_override:
            print(f"WARNING: Deploying outside maintenance window. Override reason: {args.override_reason}")
        else:
            print("ERROR: Deploying outside of maintenance window (22:00 - 06:00 IST).")
            print("Use --emergency-override and --override-reason to bypass.")
            sys.exit(2)
            
    # Check working tree
    result = run_cmd(['git', 'status', '--porcelain'])
    if result.stdout.strip():
        # Let's ignore untracked files for safety but block on modified tracked files
        tracked_changes = [line for line in result.stdout.split('\n') if line and not line.startswith('??')]
        if tracked_changes:
            print("ERROR: Git working tree is not clean (tracked files modified).")
            print(result.stdout)
            sys.exit(1)
    
    import shutil
    required_tools = ['git', 'alembic']
    if db_url:
        required_tools.append('pg_dump')
        
    for tool in required_tools:
        if not shutil.which(tool):
            if tool == 'alembic':
                # Might be installed in venv and callable via python -m alembic or flask db
                pass
            else:
                print(f"ERROR: Required tool '{tool}' not found.")
                sys.exit(1)

def stage_2_backup(args, db_url):
    print("--- STAGE 2: BACKUP ---")
    if not db_url:
        print("No DATABASE_URL found. Skipping pg_dump (assuming SQLite).")
        return None
        
    os.makedirs(args.backup_dir, exist_ok=True)
    timestamp = get_ist_time().strftime('%Y%m%d_%H%M%S')
    backup_file = os.path.join(args.backup_dir, f"exam-portal-backup-{timestamp}.dump")
    
    # Run pg_dump (Assuming db_url can be used by pg_dump, or credentials are in pgpass)
    # Since this is a python script, we'll just pass the URL
    run_cmd(['pg_dump', '-Fc', '-f', backup_file, db_url])
    print(f"Backup created at {backup_file}")
    return backup_file

def stage_3_verify_backup(backup_file):
    print("--- STAGE 3: VERIFY BACKUP ---")
    if not backup_file:
        print("Skipping verification (no backup file).")
        return
        
    script_dir = os.path.dirname(os.path.abspath(__file__))
    verify_script = os.path.join(script_dir, 'verify_backup.py')
    run_cmd([sys.executable, verify_script, backup_file])

def stage_4_verify_code(commit):
    print("--- STAGE 4: VERIFY CODE ---")
    run_cmd(['git', 'fetch', 'origin', '--tags'])
    
    # Check if commit is reachable from origin/main
    result = subprocess.run(['git', 'merge-base', '--is-ancestor', commit, 'origin/main'])
    if result.returncode != 0:
        print(f"ERROR: Commit {commit} is not reachable from origin/main.")
        sys.exit(1)
        
    run_cmd(['git', 'checkout', commit])
    
    # Verify HEAD matches
    result = run_cmd(['git', 'rev-parse', 'HEAD'])
    head_sha = result.stdout.strip()
    
    result2 = run_cmd(['git', 'rev-parse', commit])
    target_sha = result2.stdout.strip()
    
    if head_sha != target_sha:
        print(f"ERROR: Failed to checkout exact commit {commit}. HEAD is {head_sha}")
        sys.exit(1)

def stage_5_verify_migration(script_dir):
    print("--- STAGE 5: VERIFY MIGRATION ---")
    check_script = os.path.join(script_dir, 'check_migration_sync.py')
    result = run_cmd([sys.executable, check_script], check=False)
    
    if result.returncode == 0:
        print("No migration required. Proceeding.")
        return False
    elif result.returncode == 10:
        print("Migration required. Path is valid.")
        return True
    else:
        print("ERROR: Migration synchronization check failed.")
        print(result.stdout)
        sys.exit(1)

def stage_6_apply_migration():
    print("--- STAGE 6: APPLY MIGRATION ---")
    run_cmd(['flask', 'db', 'upgrade'])

def stage_7_verify_migration(script_dir):
    print("--- STAGE 7: VERIFY MIGRATION (POST) ---")
    check_script = os.path.join(script_dir, 'check_migration_sync.py')
    result = run_cmd([sys.executable, check_script], check=False)
    
    if result.returncode != 0:
        print("ERROR: Post-migration sync check failed. Migration did not complete properly.")
        print("HALTING DEPLOYMENT. DO NOT RESTART SERVICE. DO NOT AUTO-ROLLBACK.")
        sys.exit(1)

def stage_8_restart():
    print("--- STAGE 8: RESTART ---")
    try:
        run_cmd(['sudo', 'systemctl', 'restart', 'exam-portal.service'])
    except Exception as e:
        print("systemctl failed. If you are not using systemd, please restart your service manually.")
        pass

def stage_9_10_health_smoke(script_dir):
    print("--- STAGE 9 & 10: HEALTH & SMOKE CHECK ---")
    health_script = os.path.join(script_dir, 'health_check.py')
    
    # Wait a few seconds for the service to bind
    time.sleep(3)
    
    result = run_cmd([sys.executable, health_script], check=False)
    if result.returncode != 0:
        print("ERROR: Health or smoke check failed after restart.")
        print("HALTING DEPLOYMENT. Database migration is intact. Investigate application logs.")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Exam Portal Deployment Orchestrator")
    parser.add_argument('--commit', required=True, help="Target commit SHA or Tag")
    parser.add_argument('--check-only', action='store_true', help="Run up to stage 5 only")
    parser.add_argument('--emergency-override', action='store_true', help="Bypass time window")
    parser.add_argument('--override-reason', type=str, help="Reason for emergency override")
    parser.add_argument('--backup-dir', default='/var/backups/exam-portal', help="Directory for DB backups")
    
    args = parser.parse_args()
    
    if args.emergency_override and not args.override_reason:
        print("ERROR: --override-reason is required when using --emergency-override")
        sys.exit(1)
        
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Extract DB URL directly from .env if possible (just for pg_dump)
    db_url = None
    try:
        from dotenv import load_dotenv
        load_dotenv()
        db_url = os.environ.get("DATABASE_URL")
    except ImportError:
        pass
        
    stage_1_precheck(args, db_url)
    backup_file = stage_2_backup(args, db_url)
    stage_3_verify_backup(backup_file)
    stage_4_verify_code(args.commit)
    
    migration_required = stage_5_verify_migration(script_dir)
    
    if args.check_only:
        print("--- CHECK ONLY COMPLETED ---")
        sys.exit(0)
        
    if migration_required:
        stage_6_apply_migration()
        stage_7_verify_migration(script_dir)
        
    stage_8_restart()
    stage_9_10_health_smoke(script_dir)
    
    print("\n==============================================")
    print("DEPLOYMENT COMPLETED SUCCESSFULLY")
    print(f"Commit: {args.commit}")
    print("==============================================")

if __name__ == "__main__":
    main()
