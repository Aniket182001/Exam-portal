import sys
import os
import subprocess

def verify_backup(backup_file):
    """
    Verifies the integrity of a PostgreSQL custom-format backup file.
    """
    if not os.path.exists(backup_file):
        print(f"ERROR: Backup file {backup_file} does not exist.")
        return 1
        
    size_bytes = os.path.getsize(backup_file)
    if size_bytes < 10240:
        print(f"ERROR: Backup file {backup_file} is too small ({size_bytes} bytes). Expected > 10KB.")
        return 1
        
    try:
        # Run pg_restore --list to check the archive format
        result = subprocess.run(['pg_restore', '--list', backup_file], 
                              capture_output=True, text=True, check=True)
        print(f"Backup file {backup_file} verified successfully.")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"ERROR: pg_restore --list failed on {backup_file}.")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        return 1
    except FileNotFoundError:
        print("ERROR: pg_restore command not found.")
        return 1

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python verify_backup.py <backup_file_path>")
        sys.exit(1)
    sys.exit(verify_backup(sys.argv[1]))
