"""Data classes describing a generated statement and its ground truth."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class Customer:
    """A synthetic account holder. All fields are invented."""

    name: str
    address_lines: list[str]
    phone_masked: str
    email_masked: str
    customer_id: str
    account_number: str
    account_type: str
    branch_name: str
    branch_city: str
    ifsc: str
    micr: str
    nominee_registered: bool
    salaried: bool
    employer: str | None


@dataclass
class Transaction:
    """One row of the statement. Exactly one of ``debit`` and ``credit`` is non-zero."""

    txn_date: date
    value_date: date
    narration: str
    reference: str
    debit: Decimal
    credit: Decimal
    balance: Decimal = Decimal("0.00")
    category: str = ""


@dataclass
class Statement:
    """A complete genuine statement plus the seed and settings that produced it."""

    statement_id: str
    bank_id: str
    layout: str
    seed: int
    period_start: date
    period_end: date
    generated_on: date
    customer: Customer
    opening_balance: Decimal
    transactions: list[Transaction] = field(default_factory=list)
    number_format: dict = field(default_factory=dict)  # grouping, balance_suffix, date_format

    @property
    def closing_balance(self) -> Decimal:
        return self.transactions[-1].balance if self.transactions else self.opening_balance

    @property
    def total_debits(self) -> Decimal:
        return sum((t.debit for t in self.transactions), Decimal("0.00"))

    @property
    def total_credits(self) -> Decimal:
        return sum((t.credit for t in self.transactions), Decimal("0.00"))

    @property
    def debit_count(self) -> int:
        return sum(1 for t in self.transactions if t.debit > 0)

    @property
    def credit_count(self) -> int:
        return sum(1 for t in self.transactions if t.credit > 0)

    @classmethod
    def from_ground_truth(cls, record: dict) -> Statement:
        """Rebuild a statement from its ground-truth record (the inverse of ``ground_truth``)."""
        txns = [
            Transaction(
                txn_date=date.fromisoformat(t["txn_date"]),
                value_date=date.fromisoformat(t["value_date"]),
                narration=t["narration"],
                reference=t["reference"],
                debit=Decimal(t["debit"]),
                credit=Decimal(t["credit"]),
                balance=Decimal(t["balance"]),
                category=t.get("category", ""),
            )
            for t in record["transactions"]
        ]
        return cls(
            statement_id=record["statement_id"],
            bank_id=record["bank_id"],
            layout=record.get("template", ""),
            seed=record["seed"],
            period_start=date.fromisoformat(record["period_start"]),
            period_end=date.fromisoformat(record["period_end"]),
            generated_on=date.fromisoformat(record["generated_on"]),
            customer=Customer(**record["customer"]),
            opening_balance=Decimal(record["opening_balance"]),
            transactions=txns,
            number_format=dict(record.get("format", {})),
        )

    def ground_truth(self) -> dict:
        """Return a JSON-serialisable record of everything in the statement.

        This is the label file saved next to each PDF. Forgery scripts later compare a
        forged copy against this record to know exactly which fields were changed.
        """
        customer = asdict(self.customer)
        return {
            "statement_id": self.statement_id,
            "label": "genuine",
            "bank_id": self.bank_id,
            "template": self.layout,
            "format": dict(self.number_format),
            "seed": self.seed,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "generated_on": self.generated_on.isoformat(),
            "customer": customer,
            "opening_balance": str(self.opening_balance),
            "closing_balance": str(self.closing_balance),
            "total_debits": str(self.total_debits),
            "total_credits": str(self.total_credits),
            "debit_count": self.debit_count,
            "credit_count": self.credit_count,
            "transactions": [
                {
                    "row": i,
                    "txn_date": t.txn_date.isoformat(),
                    "value_date": t.value_date.isoformat(),
                    "narration": t.narration,
                    "reference": t.reference,
                    "debit": str(t.debit),
                    "credit": str(t.credit),
                    "balance": str(t.balance),
                    "category": t.category,
                }
                for i, t in enumerate(self.transactions)
            ],
        }
