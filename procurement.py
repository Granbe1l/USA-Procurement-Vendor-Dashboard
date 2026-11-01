"""Small, auditable signed-obligation and vendor ABC analysis.

Amounts are validated and aggregated in integer cents. ABC uses only vendors
whose signed net obligations are positive; transaction values are never made
absolute and deobligations remain in every signed total.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
AGENCIES = ("National Science Foundation", "Nuclear Regulatory Commission")
CANONICAL_COLUMNS = [
    "transaction_id", "vendor_id", "vendor_name", "award_id", "action_date",
    "agency", "state", "award_type", "obligation", "fiscal_year",
]
FIELD_ALIASES = {
    "transaction_id": ("transaction_id", "contract_transaction_unique_key"),
    "vendor_id": ("vendor_id", "recipient_uei"),
    "vendor_name": ("vendor_name", "recipient_name"),
    # Contract transaction exports name their parent award with this explicit key.
    "award_id": ("award_id", "contract_award_unique_key", "award_unique_key", "generated_unique_award_id"),
    "action_date": ("action_date",),
    "agency": ("agency", "awarding_agency_name"),
    "state": ("state", "recipient_state_code"),
    "award_type": ("award_type", "award_type_code", "contract_award_type"),
    "obligation": ("obligation", "federal_action_obligation"),
    "fiscal_year": ("fiscal_year",),
}
OPTIONAL_FIELDS = {"award_id", "state", "fiscal_year", "vendor_name"}
TYPE_CODES = {
    "A": "A", "B": "B", "C": "C", "D": "D",
    "BPA CALL": "A", "PURCHASE ORDER": "B", "DELIVERY ORDER": "C",
    "DEFINITIVE CONTRACT": "D", "A: BPA CALL": "A", "B: PURCHASE ORDER": "B",
    "C: DELIVERY ORDER": "C", "D: DEFINITIVE CONTRACT": "D",
}


def _text(value):
    return "" if pd.isna(value) else str(value).strip()


def _cents(value):
    """Accept US decimal amounts, including comma-grouped thousands.

    Values finer than a cent are rejected rather than silently rounded.
    """
    text = _text(value)
    if not re.fullmatch(r"[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", text):
        return None
    try:
        amount = Decimal(text.replace(",", ""))
        scaled = amount * 100
        if not amount.is_finite() or scaled != scaled.to_integral_value():
            return None
        return int(scaled)
    except (InvalidOperation, ValueError, OverflowError):
        return None


def _action_date(value):
    text = _text(value)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)?", text):
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def clean_transactions(frame: pd.DataFrame):
    """Map explicit source fields, validate scope, and return data plus audit.

    Exact copies are deduplicated. Every conflicting copy of a transaction ID
    is quarantined; no arbitrary first/last record is chosen. Raw files remain
    available for reviewing exclusions.
    """
    mapping, missing = {}, []
    for target, alternatives in FIELD_ALIASES.items():
        present = [name for name in alternatives if name in frame.columns]
        if present:
            mapping[target] = present[0]
        elif target not in OPTIONAL_FIELDS:
            missing.append(target)
    if missing:
        raise ValueError("Kolom wajib tidak tersedia: " + ", ".join(missing))
    data = pd.DataFrame({
        name: frame[mapping[name]].map(_text) if name in mapping else pd.Series("", index=frame.index)
        for name in CANONICAL_COLUMNS
    }).reset_index(drop=True)
    audit = {
        "initial_rows": int(len(data)), "column_mapping": mapping,
        "missing_optional_columns": sorted(OPTIONAL_FIELDS - set(mapping)),
        "missing_values": {name: int(data[name].eq("").sum()) for name in CANONICAL_COLUMNS},
        "observed_award_types": {str(k): int(v) for k, v in data.award_type.value_counts().items()},
        "observed_agencies": {str(k): int(v) for k, v in data.agency.value_counts().items()},
        "duplicate_policy": "Salinan identik dibuang; semua salinan transaction_id yang berbeda dikarantina.",
        "amount_policy": "USD diproses sebagai integer sen; nilai negatif dan nol dipertahankan. Presisi di bawah sen ditolak.",
        "vendor_policy": "UEI/vendor_id adalah identitas, bukan nama. ID kosong tetap dalam total kewajiban, dikecualikan dari metrik vendor dan ABC.",
        "abc_policy": "Hanya net vendor positif; kelas memakai kumulatif sebelum kelompok nilai seri: <80% A, <95% B, selainnya C.",
    }
    audit["duplicate_transaction_rows"] = int(data.loc[data.transaction_id.ne(""), "transaction_id"].duplicated(keep=False).sum())
    before = len(data)
    data = data.drop_duplicates(subset=CANONICAL_COLUMNS)
    audit["identical_duplicate_rows_removed"] = before - len(data)
    conflict = data.transaction_id.ne("") & data.transaction_id.duplicated(keep=False)
    audit["conflicting_transaction_ids"] = int(data.loc[conflict, "transaction_id"].nunique())
    # A case/spacing variant of the same exact agency name is still that agency.
    # No abbreviations, substrings, or fuzzy matches expand the selected scope.
    agency_lookup = {" ".join(name.casefold().split()): name for name in AGENCIES}
    normalized_agencies = data.agency.str.casefold().str.replace(r"\s+", " ", regex=True).map(agency_lookup)
    audit["agency_labels_normalized"] = int((normalized_agencies.notna() & normalized_agencies.ne(data.agency)).sum())
    data["agency"] = normalized_agencies.fillna(data.agency)
    amounts = pd.Series([_cents(value) for value in data.obligation], index=data.index, dtype=object)
    dates = data.action_date.map(_action_date)
    years = dates.map(lambda day: day.year + int(day.month >= 10) if day is not None else None)
    mapped_types = data.award_type.str.upper().map(TYPE_CODES)
    supplied_year = pd.to_numeric(data.fiscal_year.replace("", None), errors="coerce")
    masks = {
        "missing_transaction_id": data.transaction_id.eq(""),
        "conflicting_transaction_id": conflict,
        "invalid_obligation": amounts.isna(),
        "invalid_action_date": dates.isna(),
        "out_of_fiscal_year_scope": dates.notna() & ~years.isin([2024, 2025]),
        "agency_out_of_scope": ~data.agency.isin(AGENCIES),
        "noncontract_or_unknown_award_type": mapped_types.isna(),
        "inconsistent_fiscal_year": data.fiscal_year.ne("") & (supplied_year.isna() | supplied_year.ne(years)),
    }
    audit["quarantine_reasons"] = {key: int(mask.sum()) for key, mask in masks.items()}
    excluded = pd.Series(False, index=data.index)
    for mask in masks.values():
        excluded |= mask
    audit["quarantined_rows"] = int(excluded.sum())
    data = data.loc[~excluded].copy()
    data["obligation_cents"] = amounts.loc[data.index].astype("int64")
    data["obligation"] = data.obligation_cents / 100
    data["action_date"] = dates.loc[data.index].map(lambda day: day.isoformat())
    data["fiscal_year"] = years.loc[data.index].astype("int64")
    data["award_type"] = mapped_types.loc[data.index]
    data["state"] = data.state.str.upper()
    missing_names = data.vendor_name.eq("")
    data.loc[missing_names, "vendor_name"] = data.loc[missing_names, "vendor_id"]
    data.loc[data.vendor_id.eq("") & data.vendor_name.eq(""), "vendor_name"] = "Identitas vendor tidak tersedia"
    audit.update({
        "retained_rows": int(len(data)),
        "unique_transaction_ids": int(data.transaction_id.nunique()),
        "missing_vendor_rows": int(data.vendor_id.eq("").sum()),
        "missing_vendor_name_rows_labeled": int(missing_names.sum()),
        "missing_award_id_rows": int(data.award_id.eq("").sum()),
        "negative_obligation_rows": int(data.obligation_cents.lt(0).sum()),
        "zero_obligation_rows": int(data.obligation_cents.eq(0).sum()),
        "net_obligation_cents": int(data.obligation_cents.sum()),
        "row_reconciliation": {
            "raw": audit["initial_rows"], "exact_duplicates_removed": audit["identical_duplicate_rows_removed"],
            "quarantined": audit["quarantined_rows"], "retained": int(len(data)),
        },
    })
    if audit["initial_rows"] != audit["identical_duplicate_rows_removed"] + audit["quarantined_rows"] + len(data):
        raise ValueError("Jumlah baris tidak dapat direkonsiliasi.")
    return data.reset_index(drop=True), audit


def load_data(path=BASE_DIR / "data/processed/transactions.csv.gz"):
    """Load a local snapshot without API requests or inferred numeric IDs."""
    if Path(path).suffix == ".parquet":
        frame = pd.read_parquet(path)
        for column in CANONICAL_COLUMNS:
            if column in frame and column not in {"fiscal_year", "obligation"}:
                frame[column] = frame[column].fillna("").astype(str)
    else:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = set(CANONICAL_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError("Kolom data olahan tidak lengkap: " + ", ".join(sorted(missing)))
    frame["fiscal_year"] = pd.to_numeric(frame.fiscal_year, errors="raise").astype("int64")
    if "obligation_cents" in frame:
        frame["obligation_cents"] = pd.to_numeric(frame.obligation_cents, errors="raise").astype("int64")
        frame["obligation"] = frame.obligation_cents / 100
    else:
        cents = frame.obligation.map(_cents)
        if cents.isna().any():
            raise ValueError("Nilai kewajiban pada data olahan tidak valid.")
        frame["obligation_cents"] = cents.astype("int64")
        frame["obligation"] = frame.obligation_cents / 100
    return frame


def _representative_name(group):
    # Deterministic name label: latest nonempty name, then lexical order on ties.
    candidates = group.loc[group.vendor_name.ne("")].sort_values(["action_date", "vendor_name", "transaction_id"])
    return str(candidates.vendor_name.iloc[-1]) if len(candidates) else str(group.vendor_id.iloc[0])


def analyze(frame: pd.DataFrame, years=None, agencies=None, states=None, award_types=None):
    """Compute every view from the same filtered signed-obligation population."""
    selected = frame.copy()
    for col, values in [("fiscal_year", years), ("agency", agencies), ("state", states), ("award_type", award_types)]:
        if values is not None:
            candidates = [int(v) for v in values] if col == "fiscal_year" else list(values)
            selected = selected.loc[selected[col].isin(candidates)]
    if "obligation_cents" not in selected:
        cents = selected.obligation.map(_cents)
        if cents.isna().any():
            raise ValueError("Gunakan data yang telah dibersihkan; nilai kewajiban tidak valid.")
        selected["obligation_cents"] = cents.astype("int64")
    identified = selected.loc[selected.vendor_id.ne("")]
    grouped = identified.groupby("vendor_id", sort=True)
    vendor_cents = grouped.obligation_cents.sum()
    names = {vendor_id: _representative_name(group) for vendor_id, group in grouped}
    vendors = pd.DataFrame({
        "vendor_id": vendor_cents.index,
        "vendor_name": [names[vendor_id] for vendor_id in vendor_cents.index],
        "net_cents": vendor_cents.values,
    }).sort_values(["net_cents", "vendor_id"], ascending=[False, True], ignore_index=True)
    positive_total = int(vendors.loc[vendors.net_cents.gt(0), "net_cents"].sum())
    vendors["category"] = "Unclassified"
    vendors["share"] = pd.Series([None] * len(vendors), dtype=object)
    vendors["cumulative_share"] = pd.Series([None] * len(vendors), dtype=object)
    before = 0
    # Equal-value vendors share a class. Their line-chart cumulative positions
    # still advance vendor by vendor in stable vendor_id order.
    for amount, group in vendors.loc[vendors.net_cents.gt(0)].groupby("net_cents", sort=False):
        category = "A" if before * 100 < positive_total * 80 else "B" if before * 100 < positive_total * 95 else "C"
        after = before + int(amount) * len(group)
        vendors.loc[group.index, "category"] = category
        vendors.loc[group.index, "share"] = int(amount) / positive_total
        before = after
    positive_mask = vendors.net_cents.gt(0)
    if positive_total:
        vendors.loc[positive_mask, "cumulative_share"] = vendors.loc[positive_mask, "net_cents"].cumsum() / positive_total
    vendors["net_obligations"] = vendors.net_cents / 100
    distribution_rows = []
    for category in ["A", "B", "C", "Unclassified"]:
        group = vendors.loc[vendors.category.eq(category)]
        value = int(group.net_cents.sum())
        distribution_rows.append({
            "category": category, "vendor_count": len(group),
            "vendor_share": len(group) / len(vendors) if len(vendors) else None,
            "value": value / 100,
            "value_share": value / positive_total if positive_total and category != "Unclassified" else None,
        })
    net_cents = int(selected.obligation_cents.sum())
    a_cents = int(vendors.loc[vendors.category.eq("A"), "net_cents"].sum())
    kpi = {
        "net_obligations": net_cents / 100,
        "unique_vendors": int(len(vendors)),
        "total_awards": None if selected.award_id.eq("").any() else int(selected.award_id.nunique()),
        "transactions": int(len(selected)),
        "category_a_share": a_cents / positive_total if positive_total else None,
        "positive_vendor_value": positive_total / 100,
        "excluded_vendor_value": (net_cents - positive_total) / 100,
        "missing_vendor_rows": int(selected.vendor_id.eq("").sum()),
    }
    result = {"kpi": kpi, "vendors": vendors[["vendor_id", "vendor_name", "net_obligations", "category", "share", "cumulative_share"]], "distribution": pd.DataFrame(distribution_rows)}
    for name, column in [("trends", "fiscal_year"), ("agencies", "agency"), ("states", "state")]:
        totals = selected.groupby(column, dropna=False).obligation_cents.sum().reset_index()
        totals["net_obligations"] = totals.obligation_cents / 100
        result[name] = totals[[column, "net_obligations"]].sort_values(column).reset_index(drop=True)
    return result
