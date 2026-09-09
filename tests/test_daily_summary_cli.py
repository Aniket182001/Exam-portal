from unittest.mock import patch
from datetime import date, datetime, timedelta, timezone
import pytest

from app.services.daily_summary_service import DailyExamSummaryReport, to_exam_local_datetime
from app.services.daily_summary_email_delivery_service import DailySummaryDeliveryResult

def get_dummy_report(d: date) -> DailyExamSummaryReport:
    return DailyExamSummaryReport(
        report_date=d,
        total_submissions=5,
        total_passed=3,
        total_failed=2,
        total_unevaluated=0,
        total_companies=1,
        named_companies_count=1,
        company_groups=[]
    )

def test_daily_summary_cli_explicit_date_success(app):
    runner = app.test_cli_runner()
    
    target = date(2026, 9, 1)
    mock_report = get_dummy_report(target)
    mock_result = DailySummaryDeliveryResult(
        success=True,
        status="sent",
        message="Sent",
        report_date=target,
        recipient_count=1,
        recipients=["test@example.com"]
    )

    with patch('app.services.daily_summary_service.generate_daily_exam_summary', return_value=mock_report) as mock_gen:
        with patch('app.services.daily_summary_email_delivery_service.send_daily_exam_summary_email', return_value=mock_result) as mock_send:
            result = runner.invoke(args=['daily-summary', '--date', '2026-09-01'])
            
            assert result.exit_code == 0
            assert "Generating Daily Examination Summary for: 2026-09-01" in result.output
            assert "Success: Daily summary sent." in result.output
            mock_gen.assert_called_once_with(target)
            mock_send.assert_called_once_with(mock_report, skip_if_empty=True)

def test_daily_summary_cli_invalid_date(app):
    runner = app.test_cli_runner()
    result = runner.invoke(args=['daily-summary', '--date', 'not-a-date'])
    
    assert result.exit_code == 1
    assert "Invalid date format" in result.output

def test_daily_summary_cli_previous_day_calculation(app):
    runner = app.test_cli_runner()
    
    now_utc = datetime.now(timezone.utc)
    now_local = to_exam_local_datetime(now_utc, None)
    expected_target = (now_local - timedelta(days=1)).date()
    
    mock_report = get_dummy_report(expected_target)
    mock_result = DailySummaryDeliveryResult(
        success=True,
        status="sent",
        message="Sent",
        report_date=expected_target,
        recipient_count=1,
        recipients=["test@example.com"]
    )

    with patch('app.services.daily_summary_service.generate_daily_exam_summary', return_value=mock_report) as mock_gen:
        with patch('app.services.daily_summary_email_delivery_service.send_daily_exam_summary_email', return_value=mock_result) as mock_send:
            result = runner.invoke(args=['daily-summary'])
            
            assert result.exit_code == 0
            assert f"Generating Daily Examination Summary for: {expected_target.isoformat()}" in result.output
            mock_gen.assert_called_once_with(expected_target)

def test_daily_summary_cli_empty_report_skipped(app):
    runner = app.test_cli_runner()
    
    target = date(2026, 9, 1)
    mock_report = DailyExamSummaryReport(
        report_date=target,
        total_submissions=0,
        total_passed=0,
        total_failed=0,
        total_unevaluated=0,
        total_companies=0,
        named_companies_count=0,
        company_groups=[]
    )
    mock_result = DailySummaryDeliveryResult(
        success=True,
        status="skipped_empty",
        message="Skipped empty",
        report_date=target,
        recipient_count=1,
        recipients=["test@example.com"]
    )

    with patch('app.services.daily_summary_service.generate_daily_exam_summary', return_value=mock_report):
        with patch('app.services.daily_summary_email_delivery_service.send_daily_exam_summary_email', return_value=mock_result):
            result = runner.invoke(args=['daily-summary', '--date', '2026-09-01'])
            
            assert result.exit_code == 0
            assert "Success: Skipped sending due to empty report." in result.output

def test_daily_summary_cli_delivery_failure(app):
    runner = app.test_cli_runner()
    
    target = date(2026, 9, 1)
    mock_report = get_dummy_report(target)
    mock_result = DailySummaryDeliveryResult(
        success=False,
        status="failed",
        message="SMTP Error",
        report_date=target,
        recipient_count=1,
        recipients=["test@example.com"]
    )

    with patch('app.services.daily_summary_service.generate_daily_exam_summary', return_value=mock_report):
        with patch('app.services.daily_summary_email_delivery_service.send_daily_exam_summary_email', return_value=mock_result):
            result = runner.invoke(args=['daily-summary', '--date', '2026-09-01'])
            
            assert result.exit_code == 1
            # Wait, in the CLI command I used result.error_message. Let me check the command.
            # In Phase 4, the property is result.message, not error_message. I need to fix the CLI.
            assert "Delivery failed: SMTP Error" in result.output

def test_daily_summary_cli_no_recipients(app):
    runner = app.test_cli_runner()
    
    target = date(2026, 9, 1)
    mock_report = get_dummy_report(target)
    mock_result = DailySummaryDeliveryResult(
        success=False,
        status="no_recipients",
        message="No recipients configured",
        report_date=target,
        recipient_count=0,
        recipients=[]
    )

    with patch('app.services.daily_summary_service.generate_daily_exam_summary', return_value=mock_report):
        with patch('app.services.daily_summary_email_delivery_service.send_daily_exam_summary_email', return_value=mock_result):
            result = runner.invoke(args=['daily-summary', '--date', '2026-09-01'])
            
            assert result.exit_code == 1
            assert "Delivery failed: No recipients configured." in result.output

def test_daily_summary_cli_generation_failure(app):
    runner = app.test_cli_runner()
    
    with patch('app.services.daily_summary_service.generate_daily_exam_summary', side_effect=Exception("Database connection error")):
        result = runner.invoke(args=['daily-summary', '--date', '2026-09-01'])
        
        assert result.exit_code == 1
        assert "Unexpected error: Database connection error" in result.output
