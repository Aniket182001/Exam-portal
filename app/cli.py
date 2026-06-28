import click
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash
from app.extensions import db
from app.models.user import User

@click.command('create-admin')
@with_appcontext
def create_admin_command():
    """Interactively creates a new admin user."""
    click.secho("=== AIQM Exam Portal Admin Setup ===", fg="cyan", bold=True)
    
    username = click.prompt("Username", type=str).strip()
    if User.query.filter_by(username=username).first():
        click.secho(f"Error: Username '{username}' already exists.", fg="red", err=True)
        return

    email = click.prompt("Email", type=str).strip()
    if User.query.filter_by(email=email).first():
        click.secho(f"Error: Email '{email}' already exists.", fg="red", err=True)
        return

    password = click.prompt("Password", hide_input=True, confirmation_prompt="Confirm Password")
    
    hashed_password = generate_password_hash(password)
    
    new_admin = User(
        username=username,
        email=email,
        password_hash=hashed_password,
        role="admin",
        is_active=True
    )
    
    db.session.add(new_admin)
    
    try:
        db.session.commit()
        click.secho(f"\nSuccess! Admin user '{username}' has been created successfully.", fg="green", bold=True)
    except Exception as e:
        db.session.rollback()
        click.secho(f"\nError: Failed to create user. {str(e)}", fg="red", err=True)
