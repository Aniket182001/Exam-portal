from datetime import datetime, timezone
from app.extensions import db


class CompanyGroup(db.Model):
    __tablename__ = "company_groups"

    id = db.Column(db.Integer, primary_key=True)
    canonical_name = db.Column(db.String(150), nullable=False, unique=True)
    normalized_name = db.Column(db.String(150), nullable=False, unique=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    aliases = db.relationship(
        "CompanyAlias",
        backref="company_group",
        cascade="all, delete-orphan",
        order_by="CompanyAlias.alias_name.asc()",
        lazy=True
    )

    def __repr__(self):
        return f"<CompanyGroup id={self.id} canonical_name='{self.canonical_name}'>"


class CompanyAlias(db.Model):
    __tablename__ = "company_aliases"

    id = db.Column(db.Integer, primary_key=True)
    company_group_id = db.Column(
        db.Integer,
        db.ForeignKey("company_groups.id", ondelete="CASCADE"),
        nullable=False
    )
    alias_name = db.Column(db.String(150), nullable=False)
    normalized_alias = db.Column(db.String(150), nullable=False, unique=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self):
        return f"<CompanyAlias id={self.id} alias_name='{self.alias_name}' group_id={self.company_group_id}>"
