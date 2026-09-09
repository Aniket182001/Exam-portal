"""
Tests for Phase 1: Company Normalization and Grouping.

Covers:
1. Conservative normalization:
   - Whitespace trimming and collapsing
   - Case normalization
   - Safe period stripping (e.g. 'Pvt. Ltd.' -> 'pvt ltd')
   - No semantic or fuzzy merging
2. Exact canonical company name resolution.
3. Explicitly configured alias resolves to canonical company.
4. Case/whitespace/punctuation variations of canonical & aliases resolve accurately.
5. Unknown / unmapped companies safely remain independent/separate groups.
6. Similar-but-different company names are NOT incorrectly merged.
7. Attempt grouping (group_attempts_by_company) produces clean, grouped buckets.
8. Historical StudentAttempt.company_name values in database remain completely intact.
9. Admin CRUD operations for CompanyGroup and CompanyAlias.
"""
import pytest
from app.extensions import db
from app.models import Exam, StudentAttempt
from app.models.company_group import CompanyGroup, CompanyAlias
from app.services.company_service import (
    normalize_company_key,
    clean_company_display_name,
    resolve_canonical_company,
    group_attempts_by_company,
    create_company_group,
    update_company_group,
    delete_company_group,
    add_alias_to_group,
    delete_alias,
    NO_COMPANY_LABEL,
)


# ---------------------------------------------------------------------------
# 1. Conservative Normalization Unit Tests
# ---------------------------------------------------------------------------

def test_normalize_company_key_conservative():
    """Verify normalize_company_key is conservative and deterministic."""
    # Blank / None
    assert normalize_company_key(None) == ""
    assert normalize_company_key("") == ""
    assert normalize_company_key("   ") == ""

    # Whitespace trimming and internal collapsing
    assert normalize_company_key("   Acme   Corp   ") == "acme corp"

    # Case normalization
    assert normalize_company_key("ACME CORP") == "acme corp"
    assert normalize_company_key("aCmE cOrP") == "acme corp"

    # Safe punctuation (periods in abbreviations)
    assert normalize_company_key("ABC Pvt. Ltd.") == "abc pvt ltd"
    assert normalize_company_key("ABC PVT. LTD.") == "abc pvt ltd"
    assert normalize_company_key("ABC Pvt Ltd") == "abc pvt ltd"

    # Does NOT merge similar-but-different names
    assert normalize_company_key("ABC Technologies") != normalize_company_key("ABC Pvt Ltd")
    assert normalize_company_key("Acme Global") != normalize_company_key("Acme India")
    assert normalize_company_key("ABC Private Limited") != normalize_company_key("ABC Pvt Ltd")


def test_clean_company_display_name():
    """Verify clean_company_display_name preserves casing but cleans whitespace."""
    assert clean_company_display_name(None) is None
    assert clean_company_display_name("   ") is None
    assert clean_company_display_name("  ABC   Pvt  Ltd  ") == "ABC Pvt Ltd"
    assert clean_company_display_name("Tata   Motors") == "Tata Motors"


# ---------------------------------------------------------------------------
# 2. Resolution Tests (Canonical, Aliases, Variations, Unmapped)
# ---------------------------------------------------------------------------

@pytest.fixture
def setup_companies(app):
    """Sets up standard canonical groups and aliases for testing."""
    with app.app_context():
        # Clear existing test company groups
        CompanyAlias.query.delete()
        CompanyGroup.query.delete()
        db.session.commit()

        # Group 1: ABC Pvt Ltd with aliases
        g1 = CompanyGroup(
            canonical_name="ABC Pvt Ltd",
            normalized_name=normalize_company_key("ABC Pvt Ltd")
        )
        db.session.add(g1)
        db.session.flush()

        a1 = CompanyAlias(
            company_group_id=g1.id,
            alias_name="ABC Private Limited",
            normalized_alias=normalize_company_key("ABC Private Limited")
        )
        a2 = CompanyAlias(
            company_group_id=g1.id,
            alias_name="ABC India",
            normalized_alias=normalize_company_key("ABC India")
        )
        db.session.add_all([a1, a2])

        # Group 2: ABC Technologies (similar name, but separate organization!)
        g2 = CompanyGroup(
            canonical_name="ABC Technologies",
            normalized_name=normalize_company_key("ABC Technologies")
        )
        db.session.add(g2)

        # Group 3: Acme Global
        g3 = CompanyGroup(
            canonical_name="Acme Global",
            normalized_name=normalize_company_key("Acme Global")
        )
        db.session.add(g3)

        db.session.commit()


def test_exact_canonical_resolution(app, setup_companies):
    """Exact canonical company name resolves to itself."""
    with app.app_context():
        assert resolve_canonical_company("ABC Pvt Ltd") == "ABC Pvt Ltd"
        assert resolve_canonical_company("ABC Technologies") == "ABC Technologies"
        assert resolve_canonical_company("Acme Global") == "Acme Global"


def test_known_alias_resolution(app, setup_companies):
    """Explicitly configured alias resolves to the canonical company."""
    with app.app_context():
        assert resolve_canonical_company("ABC Private Limited") == "ABC Pvt Ltd"
        assert resolve_canonical_company("ABC India") == "ABC Pvt Ltd"


def test_case_whitespace_punctuation_variations(app, setup_companies):
    """Case, whitespace, and period variations of both canonical and aliases resolve accurately."""
    with app.app_context():
        # Variations of canonical "ABC Pvt Ltd"
        assert resolve_canonical_company("abc pvt ltd") == "ABC Pvt Ltd"
        assert resolve_canonical_company("ABC PVT. LTD.") == "ABC Pvt Ltd"
        assert resolve_canonical_company("  ABC   Pvt.   Ltd.  ") == "ABC Pvt Ltd"
        assert resolve_canonical_company("Abc Pvt. Ltd") == "ABC Pvt Ltd"

        # Variations of alias "ABC Private Limited"
        assert resolve_canonical_company("abc private limited") == "ABC Pvt Ltd"
        assert resolve_canonical_company("ABC PRIVATE LIMITED") == "ABC Pvt Ltd"
        assert resolve_canonical_company("  ABC   PRIVATE   LIMITED.  ") == "ABC Pvt Ltd"


def test_unknown_company_remains_independent(app, setup_companies):
    """Unmapped/unknown company safely remains as its own independent group."""
    with app.app_context():
        # Unmapped company returns its own cleaned display string
        assert resolve_canonical_company("Stark Industries") == "Stark Industries"
        assert resolve_canonical_company("  Wayne   Enterprises  ") == "Wayne Enterprises"
        assert resolve_canonical_company(None) is None
        assert resolve_canonical_company("   ") is None


def test_similar_different_companies_not_merged(app, setup_companies):
    """Similar-looking but distinct company names are NEVER merged."""
    with app.app_context():
        # ABC Technologies must NOT be merged with ABC Pvt Ltd
        assert resolve_canonical_company("ABC Technologies") == "ABC Technologies"
        assert resolve_canonical_company("ABC Pvt Ltd") == "ABC Pvt Ltd"

        # Acme India is not an alias of Acme Global, so it stays Acme India
        assert resolve_canonical_company("Acme Global") == "Acme Global"
        assert resolve_canonical_company("Acme India") == "Acme India"


# ---------------------------------------------------------------------------
# 3. Attempt Grouping & Data Integrity Tests
# ---------------------------------------------------------------------------

def test_group_attempts_by_company(app, setup_companies):
    """Multiple attempts with different aliases are grouped under the single canonical company."""
    with app.app_context():
        exam = Exam(
            title="Grouping Exam",
            exam_code="GRPTEST01",
            duration_minutes=30,
            passing_type="percentage",
            passing_value=50.0,
        )
        db.session.add(exam)
        db.session.flush()

        import uuid
        attempts_data = [
            ("Alice", "alice@example.com", "ABC Pvt Ltd"),
            ("Bob", "bob@example.com", "ABC PVT. LTD."),
            ("Charlie", "charlie@example.com", "ABC Private Limited"),
            ("Diana", "diana@example.com", "  abc   pvt   ltd  "),
            ("Evan", "evan@example.com", "ABC Technologies"),
            ("Fiona", "fiona@example.com", "Stark Industries"),
            ("George", "george@example.com", None),
            ("Hannah", "hannah@example.com", "   "),
        ]

        attempt_objs = []
        for name, email, co in attempts_data:
            att = StudentAttempt(
                exam_id=exam.id,
                student_name=name,
                student_email=email,
                company_name=co,
                attempt_token=str(uuid.uuid4()),
                status="submitted",
            )
            db.session.add(att)
            attempt_objs.append(att)

        db.session.commit()

        # Run grouping service
        grouped = group_attempts_by_company(attempt_objs)

        # Expected buckets:
        # "ABC Pvt Ltd": Alice, Bob, Charlie, Diana (4 attempts)
        # "ABC Technologies": Evan (1 attempt)
        # "Stark Industries": Fiona (1 attempt)
        # "Independent / No Company": George, Hannah (2 attempts)

        assert "ABC Pvt Ltd" in grouped
        assert len(grouped["ABC Pvt Ltd"]) == 4
        abc_emails = {a.student_email for a in grouped["ABC Pvt Ltd"]}
        assert abc_emails == {"alice@example.com", "bob@example.com", "charlie@example.com", "diana@example.com"}

        assert "ABC Technologies" in grouped
        assert len(grouped["ABC Technologies"]) == 1
        assert grouped["ABC Technologies"][0].student_email == "evan@example.com"

        assert "Stark Industries" in grouped
        assert len(grouped["Stark Industries"]) == 1
        assert grouped["Stark Industries"][0].student_email == "fiona@example.com"

        assert NO_COMPANY_LABEL in grouped
        assert len(grouped[NO_COMPANY_LABEL]) == 2
        no_co_emails = {a.student_email for a in grouped[NO_COMPANY_LABEL]}
        assert no_co_emails == {"george@example.com", "hannah@example.com"}


def test_historical_attempt_data_remains_intact(app, setup_companies):
    """Existing StudentAttempt.company_name values in database are never changed by resolution/grouping."""
    with app.app_context():
        exam = Exam(
            title="Integrity Exam",
            exam_code="INTTEST01",
            duration_minutes=30,
            passing_type="percentage",
            passing_value=50.0,
        )
        db.session.add(exam)
        db.session.flush()

        import uuid
        original_raw = "  ABC   PVT.   LTD.  "
        attempt = StudentAttempt(
            exam_id=exam.id,
            student_name="Ian",
            student_email="ian@example.com",
            company_name=original_raw,
            attempt_token=str(uuid.uuid4()),
            status="submitted",
        )
        db.session.add(attempt)
        db.session.commit()
        att_id = attempt.id

        # Perform resolution and grouping
        canonical = resolve_canonical_company(attempt.company_name)
        assert canonical == "ABC Pvt Ltd"

        group_attempts_by_company([attempt])

        # Verify DB value is unchanged
        fresh_attempt = db.session.get(StudentAttempt, att_id)
        assert fresh_attempt.company_name == original_raw


# ---------------------------------------------------------------------------
# 4. Admin CRUD Operations Tests
# ---------------------------------------------------------------------------

def test_company_group_crud(app):
    """Test creating, updating, adding aliases, and deleting CompanyGroups."""
    with app.app_context():
        CompanyAlias.query.delete()
        CompanyGroup.query.delete()
        db.session.commit()

        # 1. Create group with aliases
        group, err = create_company_group(
            canonical_name="Tata Consultancy Services",
            aliases=["TCS", "Tata CS", "Tata Consultancy"]
        )
        assert err is None
        assert group is not None
        assert group.canonical_name == "Tata Consultancy Services"
        assert group.normalized_name == "tata consultancy services"
        assert len(group.aliases) == 3

        group_id = group.id

        # 2. Prevent duplicate canonical name
        dup, dup_err = create_company_group("tata consultancy services")
        assert dup is None
        assert "already exists" in dup_err

        # 3. Add alias to group
        alias, a_err = add_alias_to_group(group_id, "TCS India")
        assert a_err is None
        assert alias.alias_name == "TCS India"
        assert alias.normalized_alias == "tcs india"

        # 4. Prevent duplicate alias (both exact and punctuation variation)
        dup_alias, da_err = add_alias_to_group(group_id, "TCS")
        assert dup_alias is None
        assert "already registered" in da_err

        dup_alias_punc, dap_err = add_alias_to_group(group_id, "T.C.S.")
        assert dup_alias_punc is None
        assert "already registered" in dap_err

        # 5. Update canonical name
        updated, u_err = update_company_group(group_id, "TCS Limited")
        assert u_err is None
        assert updated.canonical_name == "TCS Limited"
        assert updated.normalized_name == "tcs limited"

        # 6. Delete alias
        alias_to_del = CompanyAlias.query.filter_by(normalized_alias="tcs india").first()
        del_success = delete_alias(alias_to_del.id)
        assert del_success is True
        assert CompanyAlias.query.filter_by(normalized_alias="tcs india").first() is None

        # 7. Delete group cascades aliases
        del_grp_success = delete_company_group(group_id)
        assert del_grp_success is True
        assert db.session.get(CompanyGroup, group_id) is None
        assert CompanyAlias.query.filter_by(company_group_id=group_id).count() == 0


def test_admin_companies_web_endpoints(client, app, logged_in_client):
    """Verify the /admin/companies web views and actions."""
    with app.app_context():
        CompanyAlias.query.delete()
        CompanyGroup.query.delete()
        db.session.commit()

    # GET /admin/companies
    resp = logged_in_client.get("/admin/companies")
    assert resp.status_code == 200
    assert "Company Groups & Aliases" in resp.data.decode("utf-8")

    # POST /admin/companies (Create)
    post_resp = logged_in_client.post(
        "/admin/companies",
        data={
            "canonical_name": "Infosys Limited",
            "aliases": "Infosys, Infy, Infosys Technologies",
        },
        follow_redirects=True
    )
    assert post_resp.status_code == 200
    html = post_resp.data.decode("utf-8")
    assert "Infosys Limited" in html
    assert "Infy" in html

    # Add alias via POST
    with app.app_context():
        group = CompanyGroup.query.filter_by(canonical_name="Infosys Limited").first()
        group_id = group.id

    add_alias_resp = logged_in_client.post(
        f"/admin/companies/{group_id}/aliases",
        data={"alias_name": "Infosys BPM"},
        follow_redirects=True
    )
    assert add_alias_resp.status_code == 200
    assert "Infosys BPM" in add_alias_resp.data.decode("utf-8")

    # Edit company via POST
    edit_resp = logged_in_client.post(
        f"/admin/companies/{group_id}/edit",
        data={"canonical_name": "Infosys Ltd"},
        follow_redirects=True
    )
    assert edit_resp.status_code == 200
    assert "Infosys Ltd" in edit_resp.data.decode("utf-8")
