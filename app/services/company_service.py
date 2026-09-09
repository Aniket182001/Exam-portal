import logging
from app.extensions import db
from app.models.company_group import CompanyGroup, CompanyAlias

logger = logging.getLogger(__name__)

NO_COMPANY_LABEL = "Independent / No Company"


def clean_company_display_name(name: str | None) -> str | None:
    """
    Cleans a raw company name for display:
    - Strips leading and trailing whitespace
    - Collapses repeated internal whitespace into a single space
    - Returns None if the string is empty or whitespace-only
    """
    if not name:
        return None
    cleaned = " ".join(name.strip().split())
    return cleaned if cleaned else None


def normalize_company_key(name: str | None) -> str:
    """
    Conservatively normalizes a company name for deterministic matching:
    - Returns empty string if None or blank
    - Strips leading and trailing whitespace
    - Collapses internal multiple whitespaces
    - Converts to lower case
    - Strips periods (e.g. 'Pvt. Ltd.' -> 'pvt ltd')
    Strictly avoids semantic word replacement, fuzzy matching, or guessing.
    """
    if not name:
        return ""
    text = name.strip().lower()
    text = text.replace(".", "")
    return " ".join(text.split())


def build_company_lookup_cache() -> dict[str, str]:
    """
    Preloads all canonical company groups and aliases into a normalized lookup dictionary:
    normalized_key -> canonical_name.
    Used for bulk resolution without repeated database queries.
    """
    cache: dict[str, str] = {}
    for group in CompanyGroup.query.all():
        cache[group.normalized_name] = group.canonical_name

    for alias in CompanyAlias.query.options(db.joinedload(CompanyAlias.company_group)).all():
        if alias.company_group:
            cache[alias.normalized_alias] = alias.company_group.canonical_name

    return cache


def resolve_canonical_company(
    raw_name: str | None,
    cache: dict[str, str] | None = None
) -> str | None:
    """
    Resolves a raw company string to its canonical company name:
    1. If raw_name is blank or None, returns None.
    2. Cleans raw_name for clean display.
    3. Normalizes to a lookup key.
    4. Checks for an exact match against CompanyGroup.normalized_name (or cache).
    5. Checks for an exact match against CompanyAlias.normalized_alias (or cache).
    6. If no match is found, safely returns the cleaned raw_name as its own group.
    """
    cleaned = clean_company_display_name(raw_name)
    if not cleaned:
        return None

    key = normalize_company_key(cleaned)
    if not key:
        return cleaned

    # Use preloaded cache if supplied
    if cache is not None:
        return cache.get(key, cleaned)

    # 1. Match canonical company
    group = CompanyGroup.query.filter_by(normalized_name=key).first()
    if group:
        return group.canonical_name

    # 2. Match explicitly configured alias
    alias = CompanyAlias.query.filter_by(normalized_alias=key).first()
    if alias and alias.company_group:
        return alias.company_group.canonical_name

    # 3. Unmapped: keep cleaned raw name as its own independent group
    return cleaned


def group_attempts_by_company(
    attempts: list,
    cache: dict[str, str] | None = None
) -> dict[str, list]:
    """
    Groups a sequence of StudentAttempt instances by resolved company name.
    Attempts with no company are grouped under 'Independent / No Company'.
    Returns a dictionary sorted with named companies first (alphabetically),
    followed by the unassigned bucket.
    """
    groups: dict[str, list] = {}

    for attempt in attempts:
        canonical = resolve_canonical_company(attempt.company_name, cache=cache)
        bucket = canonical if canonical else NO_COMPANY_LABEL

        if bucket not in groups:
            groups[bucket] = []
        groups[bucket].append(attempt)

    # Sort keys alphabetically, keeping NO_COMPANY_LABEL at the end if present
    sorted_keys = sorted([k for k in groups if k != NO_COMPANY_LABEL], key=lambda s: s.lower())
    if NO_COMPANY_LABEL in groups:
        sorted_keys.append(NO_COMPANY_LABEL)

    return {k: groups[k] for k in sorted_keys}


# ---------------------------------------------------------------------------
# Admin Management / CRUD helpers
# ---------------------------------------------------------------------------

def list_company_groups() -> list[CompanyGroup]:
    """Returns all company groups ordered alphabetically by canonical name."""
    return CompanyGroup.query.order_by(CompanyGroup.canonical_name.asc()).all()


def get_company_group(group_id: int) -> CompanyGroup | None:
    """Returns a CompanyGroup by ID or None."""
    return db.session.get(CompanyGroup, group_id)


def create_company_group(
    canonical_name: str,
    aliases: list[str] | None = None
) -> tuple[CompanyGroup | None, str | None]:
    """
    Creates a new CompanyGroup with optional aliases.
    Returns (CompanyGroup, None) on success, or (None, error_message) on failure.
    """
    cleaned_name = clean_company_display_name(canonical_name)
    if not cleaned_name:
        return None, "Company name cannot be blank."

    norm_name = normalize_company_key(cleaned_name)
    if not norm_name:
        return None, "Invalid company name."

    # Check for collision with existing canonical name
    if CompanyGroup.query.filter_by(normalized_name=norm_name).first():
        return None, f"A company with the name '{cleaned_name}' already exists."

    # Check for collision with existing alias
    if CompanyAlias.query.filter_by(normalized_alias=norm_name).first():
        return None, f"'{cleaned_name}' is already registered as an alias for another company."

    group = CompanyGroup(
        canonical_name=cleaned_name,
        normalized_name=norm_name
    )
    db.session.add(group)
    db.session.flush()

    # Process initial aliases if provided
    if aliases:
        for raw_alias in aliases:
            cleaned_alias = clean_company_display_name(raw_alias)
            if not cleaned_alias:
                continue
            norm_alias = normalize_company_key(cleaned_alias)
            if norm_alias == norm_name:
                continue  # Alias same as canonical, skip safely

            # Check if alias already exists
            if CompanyAlias.query.filter_by(normalized_alias=norm_alias).first():
                logger.warning("Alias '%s' already exists; skipping.", cleaned_alias)
                continue
            if CompanyGroup.query.filter_by(normalized_name=norm_alias).first():
                logger.warning("Alias '%s' matches a canonical company; skipping.", cleaned_alias)
                continue

            alias = CompanyAlias(
                company_group_id=group.id,
                alias_name=cleaned_alias,
                normalized_alias=norm_alias
            )
            db.session.add(alias)

    try:
        db.session.commit()
        return group, None
    except Exception as e:
        db.session.rollback()
        logger.error("Failed to create company group '%s': %s", cleaned_name, e)
        return None, "Database error creating company group."


def update_company_group(group_id: int, new_canonical_name: str) -> tuple[CompanyGroup | None, str | None]:
    """Updates the canonical name of an existing CompanyGroup."""
    group = db.session.get(CompanyGroup, group_id)
    if not group:
        return None, "Company not found."

    cleaned_name = clean_company_display_name(new_canonical_name)
    if not cleaned_name:
        return None, "Company name cannot be blank."

    norm_name = normalize_company_key(cleaned_name)

    # Check collision if name changed
    if norm_name != group.normalized_name:
        existing_group = CompanyGroup.query.filter_by(normalized_name=norm_name).first()
        if existing_group and existing_group.id != group.id:
            return None, f"A company with the name '{cleaned_name}' already exists."

        existing_alias = CompanyAlias.query.filter_by(normalized_alias=norm_name).first()
        if existing_alias and existing_alias.company_group_id != group.id:
            return None, f"'{cleaned_name}' is already an alias for another company."

    group.canonical_name = cleaned_name
    group.normalized_name = norm_name

    try:
        db.session.commit()
        return group, None
    except Exception as e:
        db.session.rollback()
        logger.error("Failed to update company group %s: %s", group_id, e)
        return None, "Database error updating company group."


def delete_company_group(group_id: int) -> bool:
    """Deletes a CompanyGroup and cascades its aliases."""
    group = db.session.get(CompanyGroup, group_id)
    if not group:
        return False
    try:
        db.session.delete(group)
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        logger.error("Failed to delete company group %s: %s", group_id, e)
        return False


def add_alias_to_group(group_id: int, alias_name: str) -> tuple[CompanyAlias | None, str | None]:
    """Adds a new alias to an existing CompanyGroup."""
    group = db.session.get(CompanyGroup, group_id)
    if not group:
        return None, "Company not found."

    cleaned_alias = clean_company_display_name(alias_name)
    if not cleaned_alias:
        return None, "Alias name cannot be blank."

    norm_alias = normalize_company_key(cleaned_alias)
    if norm_alias == group.normalized_name:
        return None, "Alias cannot be identical to the canonical company name."

    if CompanyAlias.query.filter_by(normalized_alias=norm_alias).first():
        return None, f"The alias '{cleaned_alias}' is already registered."

    if CompanyGroup.query.filter_by(normalized_name=norm_alias).first():
        return None, f"'{cleaned_alias}' already exists as a canonical company."

    alias = CompanyAlias(
        company_group_id=group.id,
        alias_name=cleaned_alias,
        normalized_alias=norm_alias
    )
    db.session.add(alias)
    try:
        db.session.commit()
        return alias, None
    except Exception as e:
        db.session.rollback()
        logger.error("Failed to add alias '%s' to group %s: %s", cleaned_alias, group_id, e)
        return None, "Database error adding alias."


def delete_alias(alias_id: int) -> bool:
    """Deletes a CompanyAlias."""
    alias = db.session.get(CompanyAlias, alias_id)
    if not alias:
        return False
    try:
        db.session.delete(alias)
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        logger.error("Failed to delete alias %s: %s", alias_id, e)
        return False
