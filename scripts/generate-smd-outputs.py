#!/usr/bin/env python3
"""Create JLCPCB-ready SMD BOM and placement files in the project root."""

import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MASTER_BOM = ROOT / "IOT_LC.csv"
SMD_BOM_SOURCE = ROOT / "production/bom-smd.csv"
POSITIONS_SOURCE = ROOT / "production/positions.csv"
JLC_BOM = ROOT / "IOT_LC-bom-smd-jlcpcb.csv"
JLC_CPL = ROOT / "IOT_LC-smd-positions.csv"
PAD_ONLY_FOOTPRINT = "testpoint_pad"


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file, fieldnames=fields, quoting=csv.QUOTE_MINIMAL, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def designators(value):
    return [ref.strip() for ref in value.split(",") if ref.strip()]


def jlc_footprint(value):
    value = value.strip()
    match = re.fullmatch(r"[CR]_?(\d{4})", value, re.IGNORECASE)
    return match.group(1) if match else value


def jlc_comment(value):
    return value.replace("µ", "u").strip()


def jlc_resistor_comment(value):
    value = value.replace("Ω", "").replace(" ", "")
    return re.sub(
        r"(?<![\w.])(\d+)\.(\d+)(k|M)\b",
        lambda match: match.group(1) + match.group(3) + match.group(2),
        value,
        flags=re.IGNORECASE,
    )


def main():
    for path in (MASTER_BOM, SMD_BOM_SOURCE, POSITIONS_SOURCE):
        if not path.is_file():
            raise SystemExit(f"Required source file not found: {path.relative_to(ROOT)}")

    master_fields, master_rows = read_csv(MASTER_BOM)
    # The production SMD BOM is the assembly membership source. Project CSV
    # mounting labels can be stale after a KiCad BOM export.
    # The project BOM is user-edited and may use localized headers or a
    # different delimiter. Production BOM data remains the authoritative
    # assembly source; only use project metadata when the expected header is
    # present.
    master_by_ref = {}
    if "Reference" in master_fields:
        master_by_ref = {
            ref: row
            for row in master_rows
            for ref in designators(row["Reference"])
        }

    bom_fields, bom_rows = read_csv(SMD_BOM_SOURCE)
    required_bom_fields = {"Designator", "Footprint", "Value", "LCSC Part #", "Mounting"}
    if not required_bom_fields.issubset(bom_fields):
        raise SystemExit("production/bom-smd.csv is missing required component fields")

    part_by_ref = {}
    for row in bom_rows:
        if row["Mounting"].strip().upper() != "SMD":
            continue
        for ref in designators(row["Designator"]):
            if ref in part_by_ref:
                raise SystemExit(f"Duplicate reference in production/bom-smd.csv: {ref}")
            part_by_ref[ref] = row

    # Use production BOM membership, footprint and LCSC data. Keep project
    # Value and LCSC fields when available; Description stays a separate field.
    grouped = {}
    no_lcsc = []
    assembly_refs = set()
    for ref, part in part_by_ref.items():
        if PAD_ONLY_FOOTPRINT in part["Footprint"].lower():
            continue
        project = master_by_ref.get(ref, {})
        lcsc = project.get("LCSC Part #", "").strip() or part["LCSC Part #"].strip()
        if lcsc and not re.fullmatch(r"C\d+", lcsc):
            lcsc = ""
        footprint = jlc_footprint(part["Footprint"])
        comment = jlc_comment(project.get("Value", "").strip() or part["Value"].strip())
        description = project.get("Description", "").strip()
        if ref.upper().startswith("R"):
            comment = jlc_resistor_comment(comment)
        key = (comment, description, footprint, lcsc)
        grouped.setdefault(key, []).append(ref)
        assembly_refs.add(ref)
    jlc_bom_rows = [
        {
            "Comment": comment,
            "Description": description,
            "Designator": ",".join(refs),
            "Footprint": footprint,
            "LCSC Part #": lcsc,
        }
        for (comment, description, footprint, lcsc), refs in grouped.items()
    ]
    no_lcsc = [row["Designator"] for row in jlc_bom_rows if not row["LCSC Part #"]]

    position_fields, position_rows = read_csv(POSITIONS_SOURCE)
    required_position_fields = {"Designator", "Mid X", "Mid Y", "Rotation", "Layer"}
    if not required_position_fields.issubset(position_fields):
        raise SystemExit("production/positions.csv does not have JLCPCB CPL columns")
    position_map = {row["Designator"].strip(): row for row in position_rows}
    missing_positions = sorted(assembly_refs - position_map.keys())
    if missing_positions:
        raise SystemExit(f"SMD BOM references missing from production positions: {missing_positions}")

    jlc_cpl_rows = [
        {field: position_map[ref][field] for field in required_position_fields}
        for ref in sorted(assembly_refs)
    ]
    # Keep the exact JLCPCB column order.
    cpl_fields = ["Designator", "Mid X", "Mid Y", "Rotation", "Layer"]
    jlc_cpl_rows = [{field: row[field] for field in cpl_fields} for row in jlc_cpl_rows]

    write_csv(JLC_BOM, ["Comment", "Description", "Designator", "Footprint", "LCSC Part #"], jlc_bom_rows)
    write_csv(JLC_CPL, cpl_fields, jlc_cpl_rows)

    print(
        f"Wrote {len(jlc_bom_rows)} SMD BOM lines and {len(jlc_cpl_rows)} exact production placements."
    )
    if no_lcsc:
        print("BOM lines needing manual JLC part selection: " + "; ".join(no_lcsc))


if __name__ == "__main__":
    main()
