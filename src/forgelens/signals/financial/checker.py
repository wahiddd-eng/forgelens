"""Financial-consistency signal: do the printed numbers add up?

Checks, all on values read from the PDF itself:

1. **Running balance** — each row's balance equals the previous balance minus its debit
   plus its credit.
2. **Row format** — each row has exactly one of a debit or a credit.
3. **Opening balance** — the summary's opening balance matches the opening-balance row.
4. **Totals** — the summary's total debits and credits equal the sums of the table.
5. **Counts** — the debit and credit counts in the summary match the table.
6. **Closing balance** — the summary's closing balance equals the last row's balance and
   opening + credits − debits.

A genuine generated statement passes every check. A forger who changes one number without
fixing the rest fails at least one, and the findings say exactly where.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path

from ...generator.money import format_inr
from .extract import ParsedStatement, parse_statement

TOLERANCE = Decimal("0.005")


@dataclass
class Finding:
    check: str
    message: str
    row: int | None = None
    page: int | None = None
    expected: str | None = None
    found: str | None = None


@dataclass
class FinancialReport:
    """Result of the financial-consistency signal for one statement."""

    parsed_rows: int
    findings: list[Finding] = field(default_factory=list)
    checks_run: list[str] = field(default_factory=list)
    parse_warnings: list[str] = field(default_factory=list)

    @property
    def consistent(self) -> bool:
        return self.parsed_rows > 0 and not self.findings

    @property
    def score(self) -> float:
        """Suspicion score in [0, 1]: 0 when every check passes, rising with failures."""
        if self.parsed_rows == 0:
            return 0.5  # could not read the table: no evidence either way
        if not self.findings:
            return 0.0
        kinds = {f.check for f in self.findings}
        return min(1.0, 0.6 + 0.1 * len(kinds) + 0.02 * len(self.findings))

    def features(self) -> dict[str, float]:
        """Numeric features for the fusion classifier."""
        count = lambda name: sum(1 for f in self.findings if f.check == name)
        return {
            "fin_parsed_rows": float(self.parsed_rows),
            "fin_parse_failed": float(self.parsed_rows == 0),
            "fin_row_breaks": float(count("running_balance")),
            "fin_row_format_errors": float(count("row_format")),
            "fin_opening_mismatch": float(count("opening_balance") > 0),
            "fin_total_mismatches": float(count("totals")),
            "fin_count_mismatches": float(count("counts")),
            "fin_closing_mismatches": float(count("closing_balance")),
            "fin_score": self.score,
        }

    def to_dict(self) -> dict:
        return {
            "signal": "financial_consistency",
            "consistent": self.consistent,
            "score": round(self.score, 4),
            "parsed_rows": self.parsed_rows,
            "checks_run": self.checks_run,
            "findings": [asdict(f) for f in self.findings],
            "parse_warnings": self.parse_warnings,
            "features": self.features(),
        }


def _differs(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) > TOLERANCE


def check_parsed(parsed: ParsedStatement) -> FinancialReport:
    report = FinancialReport(parsed_rows=len(parsed.rows), parse_warnings=list(parsed.warnings))
    if not parsed.rows:
        return report
    add = report.findings.append
    summary = parsed.summary

    # 2. Row format
    report.checks_run.append("row_format")
    for r in parsed.rows:
        if (r.debit is None) == (r.credit is None):
            add(Finding("row_format", f"Row {r.index + 1} ({r.date}) should have exactly one of a "
                        "debit or a credit", row=r.index, page=r.page))
        if r.balance is None:
            add(Finding("row_format", f"Row {r.index + 1} ({r.date}) has no balance",
                        row=r.index, page=r.page))

    # 1. Running balance
    opening = None
    if parsed.opening_row and parsed.opening_row.balance is not None:
        opening = parsed.opening_row.balance
    elif "opening" in summary:
        opening = summary["opening"]
    if opening is not None:
        report.checks_run.append("running_balance")
        previous = opening
        for r in parsed.rows:
            if r.balance is None:
                continue
            expected = previous - (r.debit or 0) + (r.credit or 0)
            if _differs(expected, r.balance):
                movement = (f"credit ₹{format_inr(r.credit)}" if r.credit is not None
                            else f"debit ₹{format_inr(r.debit or Decimal(0))}")
                add(Finding(
                    "running_balance",
                    f"Row {r.index + 1} ({r.date}): balance shows ₹{format_inr(r.balance)}, but "
                    f"previous balance ₹{format_inr(previous)} with {movement} gives "
                    f"₹{format_inr(expected)}",
                    row=r.index, page=r.page, expected=str(expected), found=str(r.balance)))
            previous = r.balance

    # 3. Opening balance
    if parsed.opening_row and parsed.opening_row.balance is not None and "opening" in summary:
        report.checks_run.append("opening_balance")
        if _differs(summary["opening"], parsed.opening_row.balance):
            add(Finding("opening_balance",
                        f"Summary opening balance ₹{format_inr(summary['opening'])} differs from "
                        f"the table's ₹{format_inr(parsed.opening_row.balance)}",
                        expected=str(parsed.opening_row.balance), found=str(summary["opening"])))

    # 4. Totals and 5. counts
    debits = sum((r.debit for r in parsed.rows if r.debit is not None), Decimal(0))
    credits = sum((r.credit for r in parsed.rows if r.credit is not None), Decimal(0))
    for key, total, label in (("total_debits", debits, "debits"), ("total_credits", credits,
                                                                   "credits")):
        if key in summary:
            report.checks_run.append(f"totals:{label}")
            if _differs(summary[key], total):
                add(Finding("totals", f"Summary total {label} ₹{format_inr(summary[key])} differs "
                            f"from the sum of the table, ₹{format_inr(total)}",
                            expected=str(total), found=str(summary[key])))
    n_debits = sum(1 for r in parsed.rows if r.debit is not None)
    n_credits = sum(1 for r in parsed.rows if r.credit is not None)
    for key, n, label in (("total_debits", n_debits, "debit"), ("total_credits", n_credits,
                                                                "credit")):
        if key in parsed.summary_counts:
            report.checks_run.append(f"counts:{label}")
            if parsed.summary_counts[key] != n:
                add(Finding("counts", f"Summary lists {parsed.summary_counts[key]} {label}s but the "
                            f"table has {n}", expected=str(n),
                            found=str(parsed.summary_counts[key])))

    # 6. Closing balance
    last = next((r.balance for r in reversed(parsed.rows) if r.balance is not None), None)
    if "closing" in summary:
        report.checks_run.append("closing_balance")
        if last is not None and _differs(summary["closing"], last):
            add(Finding("closing_balance",
                        f"Summary closing balance ₹{format_inr(summary['closing'])} differs from "
                        f"the last row's balance ₹{format_inr(last)}",
                        expected=str(last), found=str(summary["closing"])))
        if opening is not None:
            implied = opening + credits - debits
            if _differs(summary["closing"], implied):
                add(Finding("closing_balance",
                            f"Opening ₹{format_inr(opening)} + credits ₹{format_inr(credits)} − "
                            f"debits ₹{format_inr(debits)} = ₹{format_inr(implied)}, but the "
                            f"closing balance shows ₹{format_inr(summary['closing'])}",
                            expected=str(implied), found=str(summary["closing"])))
    return report


def check_statement(pdf_path: str | Path) -> FinancialReport:
    """Run the financial-consistency signal on a statement PDF."""
    return check_parsed(parse_statement(pdf_path))
