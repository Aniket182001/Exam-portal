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


@click.command('test-admin-notification')
@click.option('--recipient', default=None, help='Override recipient email for this test')
@with_appcontext
def test_admin_notification_command(recipient):
    """Test Brevo SMTP configuration and send a sample exam submission notification."""
    from app.services.email_service import (
        get_mail_config,
        parse_recipients,
        build_submission_notification_content,
        send_smtp_email
    )
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    click.secho("\n=== AIQM Brevo SMTP Admin Notification Test ===", fg="cyan", bold=True)
    cfg = get_mail_config()

    click.echo(f"  • SMTP Server : {cfg['server']}:{cfg['port']}")
    click.echo(f"  • TLS / SSL   : TLS={cfg['use_tls']}, SSL={cfg['use_ssl']}")
    click.echo(f"  • Default From: {cfg['sender']}")
    click.echo(f"  • Username    : {cfg['username'] or '<Not Set>'}")
    
    pwd = cfg['password']
    if pwd:
        masked = pwd[:3] + "..." + pwd[-3:] if len(pwd) > 6 else "****"
        click.echo(f"  • SMTP Key    : {masked} (Set)")
    else:
        click.echo("  • SMTP Key    : <Not Set>")

    if recipient:
        recipients = parse_recipients(recipient)
        click.echo(f"  • Target Recip: {recipients} (Overridden via --recipient)")
    else:
        recipients = parse_recipients(cfg['recipients_raw'])
        click.echo(f"  • Target Recip: {recipients} (From EXAM_SUBMISSION_NOTIFICATION_RECIPIENTS)")

    if not cfg['username'] or not cfg['password']:
        click.secho(
            "\n[Error] Missing Brevo SMTP credentials: MAIL_USERNAME and/or MAIL_PASSWORD (SMTP Key).",
            fg="red",
            bold=True
        )
        click.echo("Please set MAIL_USERNAME and MAIL_PASSWORD in your environment / .env file.")
        return

    if not recipients:
        click.secho(
            "\n[Error] No recipient email specified.",
            fg="red",
            bold=True
        )
        click.echo("Please configure EXAM_SUBMISSION_NOTIFICATION_RECIPIENTS or pass --recipient your-email@domain.com")
        return

    sample_time = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Kolkata")).strftime("%d-%b-%Y %I:%M %p %Z")
    sample_data = {
        "attempt_id": 9999,
        "candidate_name": "Jane Doe (Test Candidate)",
        "candidate_email": "jane.doe.test@example.com",
        "exam_title": "AIQM Certified Professional (Test Run)",
        "exam_code": "TEST-CODE-001",
        "submission_time": sample_time,
        "attempt_number": 1,
        "submission_type": "Test Verification Run",
        "score": 82.0,
        "max_marks": 100.0,
        "percentage": 82.0,
        "result_status": "Pass",
        "evaluation_status": "not_required",
    }

    subject, text_body, html_body = build_submission_notification_content(sample_data)

    click.echo("\nAttempting SMTP transmission via Brevo...")
    success = send_smtp_email(
        to_addresses=recipients,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        sender=cfg['sender'],
        config=cfg,
    )

    if success:
        click.secho("\n[Success] Test admin notification email sent successfully!", fg="green", bold=True)
        click.echo(f"Check the inbox for: {', '.join(recipients)}")
    else:
        click.secho("\n[Failure] Could not send test notification. See log messages above for details.", fg="red", bold=True)
