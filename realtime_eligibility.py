#!/usr/bin/env python3
"""
Real-Time Eligibility Processor for EDI 270/271 Transactions.

Reads EDI 270 (Eligibility Inquiry) and 271 (Eligibility Response) files,
parses segments, and extracts patient eligibility, provider information,
covered services, financial details, and pre-authorization requirements.

Outputs per-practice CSV summaries, coverage alerts, and a consolidated
eligibility dashboard (JSON) plus a human-readable text report.

Usage:
    python scripts/realtime_eligibility.py
    python scripts/realtime_eligibility.py --input-dir test_data/eligibility
    python scripts/realtime_eligibility.py --practice-type cardiology --verbose
"""

import argparse
import csv
import json
import os
import random
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
# ---------------------------------------------------------------------------
# Attempt to import shared test-data commons (for generating sample EDI files
# when none exist yet).  Falls back to inline constants when the import is
# not available.
# ---------------------------------------------------------------------------

try:
    from generators.test_data_commons import (
        PRACTICE_TYPES,
        PRACTICE_DISPLAY_NAMES,
        PRACTICE_TAXONOMY_CODES,
        PAYERS,
        FIRST_NAMES_M,
        FIRST_NAMES_F,
        LAST_NAMES,
        PROVIDER_FIRST_NAMES,
        PROVIDER_LAST_NAMES,
        PROVIDER_SUFFIXES,
        SPECIALTY_CPT_CODES,
        get_random_patient,
        get_random_provider,
        get_random_payer,
        format_date_edi,
        generate_member_id,
    )
    _COMMONS_AVAILABLE = True
except ImportError:
    _COMMONS_AVAILABLE = False
    PRACTICE_TYPES = [
        "primary_care", "internal_medicine", "allergy_immunology",
        "orthopaedics", "cardiology", "behavioral_health",
        "radiology", "pathology", "gastroenterology",
        "ob_gyn", "dermatology", "anesthesiology",
        "urgent_care", "pediatrics", "clinical_laboratory",
    ]
    PRACTICE_DISPLAY_NAMES = {pt: pt.replace("_", " ").title() for pt in PRACTICE_TYPES}

# ============================================================================
# CONSTANTS -- EDI 270/271 reference data
# ============================================================================

SEGMENT_TERMINATOR = "~"
ELEMENT_SEPARATOR = "*"
SUB_ELEMENT_SEPARATOR = ":"

# X12 service-type codes (EB01 qualifiers used in 271 EB segments)
SERVICE_TYPE_CODES = {
    "1": "Medical Care",
    "2": "Surgical",
    "3": "Consultation",
    "4": "Diagnostic X-Ray",
    "5": "Diagnostic Lab",
    "6": "Radiation Therapy",
    "7": "Anesthesia",
    "8": "Surgical Assistance",
    "12": "Durable Medical Equipment",
    "14": "Renal Supplies In The Home",
    "23": "Diagnostic Dental",
    "24": "Periodontics",
    "25": "Prosthodontics",
    "26": "Oral Surgery",
    "27": "Orthodontics",
    "30": "Health Benefit Plan Coverage",
    "33": "Chiropractic",
    "35": "Dental Care",
    "37": "Optometry",
    "38": "Eye Exam",
    "41": "Optometry/Vision",
    "42": "Home Health Care",
    "45": "Hospice",
    "47": "Hospital",
    "48": "Hospital Inpatient",
    "50": "Hospital Outpatient",
    "51": "Hospital Emergency",
    "52": "Hospital Emergency Medical",
    "53": "Hospital Ambulatory Surgical",
    "54": "Long Term Care",
    "56": "Medically Related Transportation",
    "60": "General Benefits",
    "61": "In-vitro Fertilization",
    "62": "MRI/CAT Scan",
    "63": "Donor Procedures",
    "65": "Newborn Care",
    "67": "Smoking Cessation",
    "68": "Well Baby Care",
    "69": "Maternity",
    "70": "Transplant",
    "71": "Audiology Exam",
    "72": "Inhalation Therapy",
    "73": "Diagnostic Medical",
    "76": "Dialysis",
    "82": "Chemotherapy",
    "83": "Radiation Therapy (Duplicate)",
    "84": "Physical Therapy",
    "85": "Occupational Therapy",
    "86": "Speech Therapy",
    "88": "Pharmacy",
    "89": "Free Standing Prescription Drug",
    "90": "Mail Order Prescription Drug",
    "91": "Brand Name Prescription Drug",
    "92": "Generic Prescription Drug",
    "93": "Podiatry",
    "94": "Podiatry - Office Visits",
    "96": "Professional (Physician) Visit - Office",
    "98": "Professional (Physician) Visit - Inpatient",
    "99": "Professional (Physician) Visit - Outpatient",
    "A4": "Psychiatric",
    "A6": "Psychotherapy",
    "A7": "Psychiatric - Inpatient",
    "A8": "Psychiatric - Outpatient",
    "AB": "Optometry",
    "AE": "Physical Medicine",
    "AF": "Speech Therapy (Duplicate)",
    "AG": "Skilled Nursing Care",
    "AJ": "Alcoholism",
    "AK": "Drug Addiction",
    "AL": "Vision",
    "BB": "Partial Hospitalization (Psychiatric)",
    "UC": "Urgent Care",
}

# Coverage-status mapping from EB01 qualifiers
ELIGIBILITY_BENEFIT_CODES = {
    "1": "Active",
    "2": "Active - Full Risk Capitation",
    "3": "Active - Services Capitated",
    "4": "Active - Services Capitated to Primary Care Physician",
    "5": "Active - Pending Investigation",
    "6": "Inactive",
    "7": "Inactive - Pending Eligibility Update",
    "8": "Inactive - Pending Investigation",
    "A": "Co-Insurance",
    "B": "Co-Payment",
    "C": "Deductible",
    "D": "Benefit Description",
    "E": "Exclusions",
    "F": "Limitations",
    "G": "Out of Pocket (Stop Loss)",
    "H": "Unlimited",
    "I": "Non-Covered",
    "J": "Cost Containment",
    "K": "Reserve",
    "L": "Primary Care Provider",
    "M": "Pre-existing Condition",
    "MC": "Managed Care Coordinator",
    "N": "Services Restricted to Following Provider",
    "O": "Not Deemed a Medical Necessity",
    "P": "Benefit Disclaimer",
    "Q": "Second Surgical Opinion Required",
    "R": "Other or Additional Payor",
    "S": "Prior Year(s) History",
    "T": "Card(s) Reported Lost/Stolen",
    "U": "Contact Following Entity for Information",
    "V": "Cannot Process",
    "W": "Other Source of Data",
    "X": "Health Care Facility",
    "Y": "Spend Down",
    "CB": "Coverage Basis",
}

# Insurance type codes (SBR09)
INSURANCE_TYPE_MAP = {
    "12": "Medicare Secondary Working Aged Beneficiary",
    "13": "Medicare Secondary End-Stage Renal Disease",
    "14": "Medicare Secondary, No-fault Insurance",
    "15": "Medicare Secondary Workers Compensation",
    "16": "Medicare Secondary Public Health Service",
    "41": "Medicare Secondary Black Lung",
    "42": "Medicare Secondary Veterans Administration",
    "43": "Medicare Secondary Disabled Beneficiary Under 65",
    "47": "Medicare Secondary, Other Liability Insurance",
    "AP": "Auto Insurance Policy",
    "C1": "Commercial",
    "CO": "Consolidated Omnibus Budget Reconciliation Act (COBRA)",
    "GP": "Group Policy",
    "HM": "Health Maintenance Organization (HMO)",
    "HN": "Health Maintenance Organization (HMO) - Medicare Risk",
    "IP": "Individual Policy",
    "MA": "Medicare Part A",
    "MB": "Medicare Part B",
    "MC": "Medicaid",
    "MP": "Medicare Primary",
    "OT": "Other",
    "PP": "Preferred Provider Organization (PPO)",
    "SP": "Supplemental Policy",
}

# Coverage level codes (EB03)
COVERAGE_LEVEL_MAP = {
    "CHD": "Children Only",
    "DEP": "Dependents Only",
    "ECH": "Employee and Children",
    "EMP": "Employee Only",
    "ESP": "Employee and Spouse",
    "FAM": "Family",
    "IND": "Individual",
    "SPC": "Spouse and Children",
    "SPO": "Spouse Only",
}

# Time-period qualifier (EB06)
TIME_PERIOD_MAP = {
    "6": "Hour",
    "7": "Day",
    "13": "24 Hours",
    "21": "Years",
    "22": "Service Year",
    "23": "Calendar Year",
    "24": "Year to Date",
    "25": "Contract",
    "26": "Episode",
    "27": "Visit",
    "28": "Outlier",
    "29": "Remaining",
    "30": "Exceeded",
    "31": "Not Exceeded",
    "32": "Lifetime",
    "33": "Lifetime Remaining",
    "34": "Month",
    "35": "Week",
    "36": "Admission",
}

# Relationship codes (INS02 / 2000C loop)
RELATIONSHIP_MAP = {
    "18": "Self",
    "01": "Spouse",
    "19": "Child",
    "20": "Employee",
    "21": "Unknown",
    "34": "Other Adult",
    "39": "Organ Donor",
    "40": "Cadaver Donor",
    "53": "Life Partner",
    "G8": "Other Relationship",
}

# Plan-type shorthand for display
PLAN_TYPE_SHORT = {
    "HM": "HMO", "HN": "HMO-Medicare", "PP": "PPO", "MA": "Medicare A",
    "MB": "Medicare B", "MP": "Medicare", "MC": "Medicaid", "C1": "Commercial",
    "GP": "Group", "IP": "Individual", "CO": "COBRA", "SP": "Supplement",
    "OT": "Other",
}

# Plan names for realistic output (mirrors generators/generate_eligibility.py)
PLAN_NAMES = [
    "Gold PPO 1000", "Silver HMO 2500", "Platinum PPO 500", "Bronze HDHP 5000",
    "Premier Choice PPO", "Essential Care HMO", "Advantage Plus PPO",
    "Value Select HMO", "Comprehensive PPO 1500", "Basic HDHP 6000",
    "Standard PPO 2000", "Freedom Select PPO",
]

# EB05 labels used by generate_eligibility.py (for parser recognition)
EB05_LABELS = {
    "DED", "DED_REMAINING", "COPAY", "COINSURANCE",
    "OOP_MAX", "OOP_REMAINING", "LIFETIME_MAX",
}

# Practice-type to typical service-type codes mapping
PRACTICE_SERVICE_TYPES = {
    "primary_care": ["30", "96", "88", "73", "5"],
    "internal_medicine": ["30", "96", "48", "50", "5"],
    "allergy_immunology": ["30", "96", "73", "5", "88"],
    "orthopaedics": ["2", "84", "62", "96", "12"],
    "cardiology": ["30", "96", "73", "62", "47"],
    "behavioral_health": ["A4", "A6", "A7", "A8", "30"],
    "radiology": ["4", "62", "6", "73", "96"],
    "pathology": ["5", "73", "96", "30", "88"],
    "gastroenterology": ["30", "96", "2", "73", "50"],
    "ob_gyn": ["69", "30", "96", "73", "47"],
    "dermatology": ["30", "96", "2", "73", "88"],
    "anesthesiology": ["7", "30", "96", "84", "73"],
    "urgent_care": ["UC", "51", "96", "4", "5"],
    "pediatrics": ["68", "30", "96", "88", "5"],
    "clinical_laboratory": ["5", "73", "30", "96", "88"],
}


# ============================================================================
# EDI 270/271 TEST DATA GENERATOR
# ============================================================================

def _generate_edi_271_files(input_dir, practice_types, verbose=False):
    """
    Generate sample EDI 271 (Eligibility Response) files in the practice-type
    subdirectories under *input_dir*.  Each practice type gets 8 files with
    3-5 patient eligibility responses per file, providing a realistic mix of
    active, inactive, in-network, out-of-network, and various financial tiers.
    """
    if not _COMMONS_AVAILABLE:
        print("  [WARN] generators.test_data_commons not available; "
              "generating minimal test data with inline constants.")

    files_created = 0
    for pt_idx, pt in enumerate(practice_types):
        pt_dir = os.path.join(input_dir, pt)
        os.makedirs(pt_dir, exist_ok=True)

        for file_idx in range(1, 9):  # 8 files per practice type
            seed_base = pt_idx * 100000 + file_idx * 1000
            random.seed(seed_base)

            num_patients = random.randint(3, 5)
            segments = []

            # -- ISA / GS / ST envelope ---------------------------------
            now = datetime.now()
            isa_date = now.strftime("%y%m%d")
            isa_time = now.strftime("%H%M")
            ctrl = f"{seed_base:09d}"

            segments.append(
                f"ISA*00*          *00*          *ZZ*RECEIVER       "
                f"*ZZ*SENDER         *{isa_date}*{isa_time}*^*00501*{ctrl}*0*P*:"
            )
            segments.append(f"GS*HB*RECEIVER*SENDER*{now.strftime('%Y%m%d')}*{isa_time}*{ctrl}*X*005010X279A1")
            segments.append(f"ST*271*{ctrl[-4:]}*005010X279A1")

            # -- BHT (Beginning of Hierarchical Transaction) ------------
            segments.append(f"BHT*0022*11*{ctrl}*{now.strftime('%Y%m%d')}*{isa_time}")

            hl_counter = 0

            # -- HL Information Source (Payer) loop ----------------------
            hl_counter += 1
            hl_payer = hl_counter
            payer = _get_payer(seed_base + 1)
            segments.append(f"HL*{hl_payer}**20*1")
            segments.append(f"NM1*PR*2*{payer['name']}*****PI*{payer['payer_id']}")

            for pat_idx in range(num_patients):
                pat_seed = seed_base + (pat_idx + 1) * 100
                random.seed(pat_seed)

                patient = _get_patient(pat_seed)
                provider = _get_provider(pt, pat_seed + 50)

                # -- HL Information Receiver (Provider) loop ------------
                hl_counter += 1
                hl_provider = hl_counter
                segments.append(f"HL*{hl_provider}*{hl_payer}*21*1")
                segments.append(
                    f"NM1*1P*1*{provider['last']}*{provider['first']}*"
                    f"***XX*{provider['npi']}"
                )
                # Provider taxonomy / participation
                random.seed(pat_seed + 51)
                in_network = random.random() < 0.75
                participating = "Y" if in_network else random.choice(["Y", "N"])
                taxonomy = PRACTICE_TAXONOMY_CODES.get(pt, "208D00000X") if _COMMONS_AVAILABLE else "208D00000X"
                segments.append(f"PRV*PE*PXC*{taxonomy}")
                segments.append(f"REF*EO*{'ACTIVE' if in_network else 'NOT_CONTRACTED'}")
                segments.append(f"REF*9K*{participating}")

                # -- HL Subscriber loop ---------------------------------
                hl_counter += 1
                hl_subscriber = hl_counter
                relationship_code = random.choice(["18", "18", "18", "01", "19"])
                segments.append(f"HL*{hl_subscriber}*{hl_provider}*22*0")

                # Trace / control number
                segments.append(f"TRN*1*{pat_seed}*9RECEIVER")

                # Subscriber name (NM1*IL)
                segments.append(
                    f"NM1*IL*1*{patient['last']}*{patient['first']}*"
                    f"***MI*{patient['member_id']}"
                )

                # Subscriber demographics
                segments.append(
                    f"DMG*D8*{patient['dob']}*{patient['gender']}"
                )

                # Subscriber address
                segments.append(f"N3*{patient['street']}")
                segments.append(f"N4*{patient['city']}*{patient['state']}*{patient['zip']}")

                # INS segment (relationship)
                segments.append(f"INS*Y*{relationship_code}*001*25")

                # DTP - coverage dates
                random.seed(pat_seed + 60)
                # Determine coverage status tier based on file_idx
                if file_idx <= 4:
                    coverage_active = random.random() < 0.90
                    coverage_terminated = False
                elif file_idx <= 6:
                    coverage_active = random.random() < 0.70
                    coverage_terminated = random.random() < 0.15
                else:
                    coverage_active = random.random() < 0.50
                    coverage_terminated = random.random() < 0.30

                eff_date = now - timedelta(days=random.randint(180, 1095))
                if coverage_terminated:
                    term_date = now - timedelta(days=random.randint(1, 120))
                elif not coverage_active:
                    term_date = now - timedelta(days=random.randint(1, 60))
                else:
                    term_date = None

                segments.append(f"DTP*356*D8*{eff_date.strftime('%Y%m%d')}")
                if term_date:
                    segments.append(f"DTP*357*D8*{term_date.strftime('%Y%m%d')}")

                # Plan identification
                random.seed(pat_seed + 70)
                plan_name = random.choice(PLAN_NAMES)
                group_num = f"GRP{random.randint(10000, 99999)}"
                group_name = f"{payer['name']} {plan_name} Group"
                segments.append(f"REF*18*{group_num}")
                segments.append(f"REF*1L*{group_name}")

                # ----- EB (Eligibility/Benefit) segments ---------------
                # Format matches generators/generate_eligibility.py:
                #   Labels (DED, COPAY, etc.) in EB05 (seg[5])
                #   Amounts at segment end (seg[10])
                #   Plan name in EB07 (seg[7]) for EB*1 active coverage

                # EB - Active/Inactive coverage status
                if coverage_active and not coverage_terminated:
                    eb01 = "1"  # Active
                elif coverage_terminated:
                    eb01 = "6"  # Inactive
                else:
                    eb01 = "6"  # Inactive

                # Active/Inactive coverage with plan name in EB07
                segments.append(f"EB*{eb01}*IND***30**{plan_name}")

                # Plan description segment
                segments.append(f"EB*D*IND***30****{plan_name}")

                # --- Financial benefit segments for each service type ---
                svc_types = PRACTICE_SERVICE_TYPES.get(pt, ["30", "96", "5"])
                random.seed(pat_seed + 80)

                # Individual deductible
                ind_deductible = random.choice([500.0, 750.0, 1000.0, 1500.0, 2000.0, 2500.0, 3000.0])
                ind_deductible_met = round(random.uniform(0, ind_deductible), 2)
                ind_deductible_remaining = round(ind_deductible - ind_deductible_met, 2)

                # Family deductible
                fam_deductible = round(ind_deductible * random.choice([2.0, 2.5, 3.0]), 2)
                fam_deductible_met = round(random.uniform(0, fam_deductible), 2)
                fam_deductible_remaining = round(fam_deductible - fam_deductible_met, 2)

                # Copay per visit type
                copay_office = random.choice([20.0, 25.0, 30.0, 35.0, 40.0, 50.0])
                copay_specialist = random.choice([35.0, 40.0, 50.0, 60.0, 75.0])
                copay_er = random.choice([100.0, 150.0, 200.0, 250.0])
                copay_urgent = random.choice([50.0, 75.0, 100.0])

                # Coinsurance
                coinsurance_in = random.choice([10, 15, 20, 25, 30])
                coinsurance_out = random.choice([30, 40, 50, 60])

                # Out-of-pocket maximum
                oop_max = random.choice([4000.0, 5000.0, 6000.0, 7500.0, 8000.0, 10000.0])
                oop_met = round(random.uniform(0, oop_max), 2)
                oop_remaining = round(oop_max - oop_met, 2)

                # Lifetime max (only some plans)
                has_lifetime_max = random.random() < 0.25
                lifetime_max = random.choice([500000.0, 1000000.0, 2000000.0]) if has_lifetime_max else 0.0

                # Individual deductible (label in EB05, amount at end)
                segments.append(
                    f"EB*C*IND*30**DED*****{ind_deductible:.2f}"
                )
                segments.append("MSG*In-Network Individual Deductible")
                # Individual deductible remaining
                segments.append(
                    f"EB*C*IND*30**DED_REMAINING*****{ind_deductible_remaining:.2f}"
                )
                segments.append("MSG*In-Network Individual Deductible Remaining")
                # Family deductible
                segments.append(
                    f"EB*C*FAM*30**DED*****{fam_deductible:.2f}"
                )
                segments.append("MSG*In-Network Family Deductible")
                segments.append(
                    f"EB*C*FAM*30**DED_REMAINING*****{fam_deductible_remaining:.2f}"
                )
                segments.append("MSG*In-Network Family Deductible Remaining")

                # Copay - plan level (office visit)
                segments.append(
                    f"EB*B*IND*30**COPAY*****{copay_office:.2f}"
                )
                segments.append("MSG*In-Network Office Visit Copay")

                # Specialist copay
                segments.append(
                    f"EB*B*IND*1**COPAY*****{copay_specialist:.2f}"
                )
                segments.append("MSG*In-Network Specialist Visit Copay")

                # Coinsurance (in-network)
                segments.append(
                    f"EB*A*IND*30**COINSURANCE*****{coinsurance_in}"
                )
                segments.append("MSG*In-Network Coinsurance Percentage After Deductible")

                # Out-of-pocket max
                segments.append(
                    f"EB*G*IND*30**OOP_MAX*****{oop_max:.2f}"
                )
                segments.append("MSG*In-Network Individual Out-of-Pocket Maximum")
                # Out-of-pocket remaining
                segments.append(
                    f"EB*G*IND*30**OOP_REMAINING*****{oop_remaining:.2f}"
                )
                segments.append("MSG*In-Network Individual Out-of-Pocket Remaining")

                # Lifetime max if applicable
                if has_lifetime_max:
                    segments.append(
                        f"EB*F*IND*30**LIFETIME_MAX*****{lifetime_max:.2f}"
                    )
                    segments.append("MSG*Lifetime Maximum Benefit")

                # Per-service-type benefits
                for svc_code in svc_types:
                    svc_desc = SERVICE_TYPE_CODES.get(svc_code, "General")

                    # Copay for this service
                    if svc_code in ("96", "UC"):
                        svc_copay = copay_office
                    elif svc_code in ("51", "52"):
                        svc_copay = copay_er
                    elif svc_code in ("2", "48", "47"):
                        svc_copay = copay_specialist
                    else:
                        svc_copay = copay_office

                    # Active coverage for this service
                    segments.append(f"EB*1*IND*{svc_code}")

                    # In-network copay
                    segments.append(
                        f"EB*B*IND*{svc_code}**COPAY*****{svc_copay:.2f}"
                    )
                    # In-network coinsurance
                    segments.append(
                        f"EB*A*IND*{svc_code}**COINSURANCE*****{coinsurance_in}"
                    )
                    segments.append(f"MSG*{svc_desc} - In-Network benefit covered")

                    # Pre-auth requirement (varies by service type and random)
                    random.seed(pat_seed + 80 + hash(svc_code) % 1000)
                    needs_preauth = svc_code in ("2", "48", "62", "7", "69", "47", "6", "70") or random.random() < 0.15
                    if needs_preauth:
                        segments.append(
                            f"EB*CB*IND*{svc_code}**30"
                        )
                        segments.append(
                            f"MSG*PRE-AUTH REQUIRED: {svc_desc.upper()}"
                        )

                # Plan-level copay details
                segments.append(f"EB*B*IND*96**COPAY*****{copay_office:.2f}")
                segments.append(f"EB*B*IND*98**COPAY*****{copay_specialist:.2f}")
                segments.append(f"EB*B*IND*51**COPAY*****{copay_er:.2f}")
                segments.append(f"EB*B*IND*UC**COPAY*****{copay_urgent:.2f}")

            # -- SE / GE / IEA trailer ----------------------------------
            seg_count = len(segments) + 1  # +1 for SE itself
            segments.append(f"SE*{seg_count}*{ctrl[-4:]}")
            segments.append(f"GE*1*{ctrl}")
            segments.append(f"IEA*1*{ctrl}")

            # Write EDI file
            edi_content = SEGMENT_TERMINATOR.join(segments) + SEGMENT_TERMINATOR
            filename = f"eligibility_271_{pt}_{file_idx:03d}.edi"
            filepath = os.path.join(pt_dir, filename)
            with open(filepath, "w") as fh:
                fh.write(edi_content)
            files_created += 1

            if verbose:
                print(f"    Generated {filepath} ({num_patients} patients)")

    return files_created


def _get_patient(seed):
    """Return patient dict, using commons if available."""
    if _COMMONS_AVAILABLE:
        return get_random_patient(seed)
    random.seed(seed)
    gender = random.choice(["M", "F"])
    first = f"Patient{seed % 1000}"
    last = f"Last{seed % 500}"
    dob = datetime(random.randint(1940, 2005), random.randint(1, 12), random.randint(1, 28))
    return {
        "first": first, "last": last, "gender": gender,
        "dob": dob.strftime("%Y%m%d"),
        "street": f"{random.randint(100, 9999)} Main St",
        "city": "Anytown", "state": "CA", "zip": "90001",
        "member_id": f"MEM{random.randint(10000000, 99999999)}",
        "patient_id": f"PAT{random.randint(100000, 999999)}",
    }


def _get_provider(specialty, seed):
    """Return provider dict, using commons if available."""
    if _COMMONS_AVAILABLE:
        return get_random_provider(specialty, seed)
    random.seed(seed)
    return {
        "first": f"Dr{seed % 100}",
        "last": f"Provider{seed % 200}",
        "suffix": "MD",
        "npi": f"{1000000000 + seed % 50000}",
        "taxonomy": "208D00000X",
        "full_name": f"Dr{seed % 100} Provider{seed % 200}, MD",
    }


def _get_payer(seed):
    """Return payer dict, using commons if available."""
    if _COMMONS_AVAILABLE:
        return get_random_payer(seed)
    random.seed(seed)
    payers = [
        {"id": "00001", "name": "Aetna", "payer_id": "60054", "plan_type": "PPO"},
        {"id": "00002", "name": "Blue Cross Blue Shield", "payer_id": "BCBS1", "plan_type": "HMO"},
        {"id": "00003", "name": "Cigna", "payer_id": "62308", "plan_type": "PPO"},
        {"id": "00004", "name": "UnitedHealthcare", "payer_id": "87726", "plan_type": "PPO"},
        {"id": "00006", "name": "Medicare Part B", "payer_id": "CMS", "plan_type": "Medicare"},
        {"id": "00007", "name": "Medicaid", "payer_id": "MDCD", "plan_type": "Medicaid"},
    ]
    return random.choice(payers)


# ============================================================================
# EDI 270/271 PARSER
# ============================================================================

class EDI271Parser:
    """
    Parses EDI 271 (Health Care Eligibility Benefit Response) transactions.

    Segments are terminated by ~ and elements separated by *.
    Sub-elements within a single element are separated by :.
    """

    def __init__(self, verbose=False):
        self.verbose = verbose

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def parse_file(self, filepath):
        """
        Parse one EDI 271 file and return a list of patient-eligibility dicts.
        """
        with open(filepath, "r") as fh:
            raw = fh.read()

        segments = self._tokenize(raw)
        return self._walk_segments(segments, filepath)

    # ------------------------------------------------------------------
    # Tokenizer
    # ------------------------------------------------------------------

    def _tokenize(self, raw):
        """Split raw EDI text into a list of segment-element lists."""
        raw = raw.replace("\n", "").replace("\r", "")
        seg_strings = [s.strip() for s in raw.split(SEGMENT_TERMINATOR) if s.strip()]
        result = []
        for seg_str in seg_strings:
            elements = seg_str.split(ELEMENT_SEPARATOR)
            result.append(elements)
        return result

    # ------------------------------------------------------------------
    # Segment walker -- builds patient records from the HL hierarchy
    # ------------------------------------------------------------------

    def _walk_segments(self, segments, filepath):
        """
        Walk through all segments in a 271 transaction and extract
        structured eligibility records for each patient/subscriber.
        """
        patients = []
        current_payer = {}
        current_provider = {}
        current_patient = None
        context = "envelope"  # envelope | payer | provider | subscriber

        i = 0
        while i < len(segments):
            seg = segments[i]
            seg_id = seg[0] if seg else ""

            # ---- Envelope / header segments ----------------------------
            if seg_id == "ISA":
                pass  # interchange header

            elif seg_id == "GS":
                pass  # functional group header

            elif seg_id == "ST":
                # Only process 271 (response) transactions.
                # Skip 270 (inquiry) sections entirely.
                tx_type = self._elem(seg, 1)
                if tx_type == "270":
                    # Fast-forward past the 270 until its SE trailer
                    i += 1
                    while i < len(segments):
                        if segments[i][0] == "SE":
                            break
                        i += 1
                    i += 1
                    continue

            elif seg_id == "BHT":
                pass  # beginning of hierarchical transaction

            # ---- HL (Hierarchical Level) routing -----------------------
            elif seg_id == "HL":
                hl_level = self._elem(seg, 3)  # 20=payer, 21=provider, 22=subscriber
                if hl_level == "20":
                    context = "payer"
                    current_payer = {}
                elif hl_level == "21":
                    context = "provider"
                    current_provider = {}
                elif hl_level == "22":
                    # Flush previous patient if exists
                    if current_patient is not None:
                        patients.append(current_patient)
                    context = "subscriber"
                    current_patient = self._new_patient_record(filepath)
                    # Inherit payer + provider into patient
                    current_patient["payer_name"] = current_payer.get("name", "")
                    current_patient["payer_id"] = current_payer.get("payer_id", "")
                    current_patient["provider_npi"] = current_provider.get("npi", "")
                    current_patient["provider_name"] = current_provider.get("name", "")
                    current_patient["network_status"] = current_provider.get("network_status", "Unknown")
                    current_patient["participating"] = current_provider.get("participating", "Unknown")
                    current_patient["provider_taxonomy"] = current_provider.get("taxonomy", "")

            # ---- NM1 (Name) ------------------------------------------
            elif seg_id == "NM1":
                entity_code = self._elem(seg, 1)
                if context == "payer" and entity_code == "PR":
                    current_payer["name"] = self._elem(seg, 3)
                    current_payer["payer_id"] = self._elem(seg, 9)
                elif context == "provider" and entity_code == "1P":
                    prov_last = self._elem(seg, 3)
                    prov_first = self._elem(seg, 4)
                    current_provider["name"] = f"{prov_first} {prov_last}".strip()
                    current_provider["npi"] = self._elem(seg, 9)
                elif context == "subscriber" and entity_code == "IL" and current_patient:
                    current_patient["patient_last"] = self._elem(seg, 3)
                    current_patient["patient_first"] = self._elem(seg, 4)
                    current_patient["patient_name"] = (
                        f"{self._elem(seg, 4)} {self._elem(seg, 3)}".strip()
                    )
                    current_patient["member_id"] = self._elem(seg, 9)

            # ---- DMG (Demographics) -----------------------------------
            elif seg_id == "DMG" and context == "subscriber" and current_patient:
                current_patient["dob"] = self._elem(seg, 2)
                current_patient["gender"] = self._elem(seg, 3)

            # ---- N3 / N4 (Address) ------------------------------------
            elif seg_id == "N3" and context == "subscriber" and current_patient:
                current_patient["address"] = self._elem(seg, 1)

            elif seg_id == "N4" and context == "subscriber" and current_patient:
                current_patient["city"] = self._elem(seg, 1)
                current_patient["state"] = self._elem(seg, 2)
                current_patient["zip"] = self._elem(seg, 3)

            # ---- INS (Subscriber relationship) ------------------------
            elif seg_id == "INS" and context == "subscriber" and current_patient:
                rel_code = self._elem(seg, 2)
                current_patient["relationship"] = RELATIONSHIP_MAP.get(rel_code, rel_code)

            # ---- TRN (Trace) ------------------------------------------
            elif seg_id == "TRN" and context == "subscriber" and current_patient:
                current_patient["trace_number"] = self._elem(seg, 2)

            # ---- DTP (Date/Time) --------------------------------------
            elif seg_id == "DTP" and context == "subscriber" and current_patient:
                qualifier = self._elem(seg, 1)
                date_format = self._elem(seg, 2)   # D8 = single, RD8 = range
                date_val = self._elem(seg, 3)

                # Start / effective qualifiers
                if qualifier in ("307", "346", "348", "356", "539"):
                    if date_format == "RD8" and "-" in date_val:
                        parts = date_val.split("-", 1)
                        current_patient["effective_date"] = parts[0]
                        current_patient["term_date"] = parts[1]
                    else:
                        current_patient["effective_date"] = date_val

                # End / termination qualifiers
                elif qualifier in ("347", "349", "357", "540"):
                    current_patient["term_date"] = date_val

                # Plan date
                elif qualifier == "291":
                    if date_format == "RD8" and "-" in date_val:
                        parts = date_val.split("-", 1)
                        current_patient["plan_begin_date"] = parts[0]
                        current_patient["plan_end_date"] = parts[1]
                    else:
                        current_patient["plan_begin_date"] = date_val

                # Benefit date
                elif qualifier == "292":
                    if date_format == "RD8" and "-" in date_val:
                        parts = date_val.split("-", 1)
                        current_patient["benefit_begin_date"] = parts[0]
                        current_patient["benefit_end_date"] = parts[1]
                    else:
                        current_patient["benefit_begin_date"] = date_val

            # ---- REF (Reference) --------------------------------------
            elif seg_id == "REF":
                ref_qual = self._elem(seg, 1)
                ref_val = self._elem(seg, 2)
                if context == "provider":
                    if ref_qual == "EO":
                        current_provider["network_status"] = (
                            "In-Network" if ref_val in ("IN", "ACTIVE") else "Out-of-Network"
                        )
                    elif ref_qual == "9K":
                        current_provider["participating"] = (
                            "Yes" if ref_val == "Y" else "No"
                        )
                elif context == "subscriber" and current_patient:
                    if ref_qual == "EO":
                        # REF*EO can also appear in subscriber section
                        # (duplicate from generate_eligibility.py)
                        net = ("In-Network" if ref_val in ("IN", "ACTIVE")
                               else "Out-of-Network")
                        current_patient["network_status"] = net
                    elif ref_qual == "18":
                        current_patient["group_number"] = ref_val
                    elif ref_qual == "1L":
                        current_patient["group_name"] = ref_val
                    elif ref_qual == "6P":
                        # REF*6P may carry a plan-type code (HM, PP …)
                        # OR a patient ID (generate_eligibility.py).
                        # Only store as plan_type when it maps to a
                        # known code; otherwise just record the raw val.
                        mapped = PLAN_TYPE_SHORT.get(
                            ref_val, INSURANCE_TYPE_MAP.get(ref_val)
                        )
                        if mapped:
                            current_patient["plan_type_code"] = ref_val
                            if not current_patient.get("plan_type"):
                                current_patient["plan_type"] = mapped

            # ---- PRV (Provider) ---------------------------------------
            elif seg_id == "PRV" and context == "provider":
                current_provider["taxonomy"] = self._elem(seg, 3)

            # ---- EB (Eligibility/Benefit) -----------------------------
            elif seg_id == "EB" and current_patient:
                self._parse_eb_segment(seg, current_patient)

            # ---- MSG (Message) ----------------------------------------
            elif seg_id == "MSG" and current_patient:
                msg_text = self._elem(seg, 1)
                if msg_text:
                    current_patient.setdefault("messages", []).append(msg_text)
                    if "PRE-AUTHORIZATION" in msg_text.upper() or "PREAUTH" in msg_text.upper():
                        current_patient.setdefault("preauth_messages", []).append(msg_text)

            # ---- Trailer segments -------------------------------------
            elif seg_id in ("SE", "GE", "IEA"):
                pass

            i += 1

        # Flush last patient
        if current_patient is not None:
            patients.append(current_patient)

        # Post-process patients
        for pat in patients:
            self._finalize_patient(pat)

        return patients

    # ------------------------------------------------------------------
    # EB segment parser
    # ------------------------------------------------------------------

    def _parse_eb_segment(self, seg, patient):
        """
        Parse an EB (Eligibility/Benefit Information) segment.

        Supports TWO formats:
          Old (inline generator):  labels in EB06/EB07 (time qualifier + amount)
          New (generate_eligibility.py):  labels in EB05, amounts at end (EB10)

        Elements:
            EB01 - Eligibility/Benefit Information Code
            EB02 - Coverage Level Code
            EB03 - Service Type Code(s)
            EB04 - Insurance Type Code
            EB05 - Plan Coverage Description  (or label: DED, COPAY, etc.)
            EB06 - Time Period Qualifier
            EB07 - Monetary Amount  (old format) or Plan Name (new EB*1)
            EB08 - Percent
            EB09 - Quantity Qualifier
            EB10 - Quantity  (new format: monetary amount or percent)
            EB11 - Authorization/Certification Indicator (Y/N)
            EB12 - In Plan Network Indicator (Y/N)
        """
        eb01 = self._elem(seg, 1)
        eb02 = self._elem(seg, 2)
        eb03 = self._elem(seg, 3)
        eb05 = self._elem(seg, 5)
        eb06 = self._elem(seg, 6)
        eb07 = self._elem(seg, 7)
        eb10 = self._elem(seg, 10) if len(seg) > 10 else ""
        eb12 = self._elem(seg, 11) if len(seg) > 11 else ""

        coverage_level = COVERAGE_LEVEL_MAP.get(eb02, eb02)
        service_type = SERVICE_TYPE_CODES.get(eb03, eb03) if eb03 else "General"
        time_period = TIME_PERIOD_MAP.get(eb06, eb06)
        is_out_of_network = eb12 == "N"
        benefit_type = ELIGIBILITY_BENEFIT_CODES.get(eb01, eb01)

        # Detect format: if EB05 is a known label, use new-format parsing
        uses_eb05_label = eb05 in EB05_LABELS

        # ----- Extract monetary amount (dual-format) -----
        # New format: amount at seg[10]; Old format: amount at seg[7]
        amount = 0.0
        if uses_eb05_label and eb10:
            try:
                amount = float(eb10)
            except (ValueError, TypeError):
                amount = 0.0
        elif eb07:
            try:
                amount = float(eb07)
            except (ValueError, TypeError):
                amount = 0.0

        # ===== COVERAGE STATUS (EB01 = 1-5 Active, 6-8 Inactive) =====
        if eb01 in ("1", "2", "3", "4", "5"):
            patient["coverage_status"] = "Active"
            # New format: plan name lives in EB07 for EB*1 segments
            if eb07 and not eb07.replace(".", "").replace("-", "").isdigit():
                patient["plan_type"] = eb07
        elif eb01 in ("6", "7", "8"):
            if patient.get("coverage_status") != "Active":
                patient["coverage_status"] = "Inactive"

        # ===== PLAN DESCRIPTION (EB01 = D) =====
        elif eb01 == "D":
            # Plan name can be in EB07 (seg[7]) or later elements
            for idx in (7, 8, 9, 10):
                val = self._elem(seg, idx) if len(seg) > idx else ""
                if val and not val.replace(".", "").replace("-", "").isdigit():
                    if not patient.get("plan_type"):
                        patient["plan_type"] = val
                    break

        # ===== DEDUCTIBLE (EB01 = C) =====
        elif eb01 == "C":
            if uses_eb05_label:
                # New format: EB05 label tells us what kind
                if eb05 == "DED_REMAINING":
                    if eb02 == "FAM":
                        patient["family_deductible_remaining"] = amount
                    else:
                        patient["deductible_remaining"] = amount
                elif eb05 == "DED":
                    if eb02 == "FAM":
                        patient["family_deductible"] = amount
                    else:
                        patient["deductible"] = amount
            else:
                # Old format: EB06 time-period qualifier
                if eb02 in ("IND", ""):
                    if eb06 == "29":
                        patient["deductible_remaining"] = amount
                    elif eb06 in ("23", "24", "25"):
                        patient["deductible"] = amount
                elif eb02 == "FAM":
                    if eb06 == "29":
                        patient["family_deductible_remaining"] = amount
                    elif eb06 in ("23", "24", "25"):
                        patient["family_deductible"] = amount

        # ===== COPAY (EB01 = B) =====
        elif eb01 == "B":
            # New format puts amount at end; old format in EB07
            if amount > 0:
                svc_label = eb03 if eb03 else "general"
                copay_key = f"copay_{svc_label}"
                if not is_out_of_network:
                    patient.setdefault("copays", {})[copay_key] = amount
                    if svc_label in ("96", "UC", "30", "general"):
                        patient["copay"] = amount
                else:
                    patient.setdefault("copays_oon", {})[copay_key] = amount

        # ===== COINSURANCE (EB01 = A) =====
        elif eb01 == "A":
            pct = 0
            if uses_eb05_label and eb10:
                try:
                    pct = int(float(eb10))
                except (ValueError, TypeError):
                    pct = 0
            elif eb07:
                try:
                    pct = int(float(eb07))
                except (ValueError, TypeError):
                    pct = 0
            if pct > 0:
                if is_out_of_network:
                    patient.setdefault("coinsurance_oon", {})[eb03 or "general"] = pct
                    if not patient.get("coinsurance_pct_oon"):
                        patient["coinsurance_pct_oon"] = pct
                else:
                    patient.setdefault("coinsurance_in", {})[eb03 or "general"] = pct
                    if not patient.get("coinsurance_pct"):
                        patient["coinsurance_pct"] = pct

        # ===== OUT-OF-POCKET / STOP LOSS (EB01 = G) =====
        elif eb01 == "G":
            if uses_eb05_label:
                if eb05 == "OOP_REMAINING":
                    patient["oop_remaining"] = amount
                elif eb05 == "OOP_MAX":
                    patient["oop_max"] = amount
            else:
                if eb02 in ("IND", ""):
                    if eb06 == "29":
                        patient["oop_remaining"] = amount
                    elif eb06 in ("23", "24", "25"):
                        patient["oop_max"] = amount

        # ===== LIMITATIONS (EB01 = F) -- lifetime max =====
        elif eb01 == "F":
            if uses_eb05_label and eb05 == "LIFETIME_MAX":
                patient["lifetime_max"] = amount
            elif eb06 == "32":
                patient["lifetime_max"] = amount

        # ===== PRE-AUTH / COST CONTAINMENT (EB01 = J or CB) =====
        elif eb01 in ("J", "CB"):
            svc = SERVICE_TYPE_CODES.get(eb03, eb03) if eb03 else "General"
            patient.setdefault("preauth_services", []).append({
                "service_type_code": eb03,
                "service_type": svc,
                "coverage_level": coverage_level,
            })

        # Track services covered
        if eb03 and eb01 not in ("J", "CB"):
            svc_record = {
                "service_type_code": eb03,
                "service_type": service_type,
                "benefit_type": benefit_type,
                "coverage_level": coverage_level,
                "amount": amount,
                "time_period": time_period,
                "in_network": not is_out_of_network,
            }
            patient.setdefault("services", []).append(svc_record)

    # ------------------------------------------------------------------
    # Patient record initialization / finalization
    # ------------------------------------------------------------------

    def _new_patient_record(self, filepath):
        """Return a blank patient-eligibility dict."""
        return {
            "source_file": os.path.basename(filepath),
            "patient_name": "",
            "patient_first": "",
            "patient_last": "",
            "member_id": "",
            "dob": "",
            "gender": "",
            "address": "",
            "city": "",
            "state": "",
            "zip": "",
            "relationship": "",
            "coverage_status": "Unknown",
            "plan_type": "",
            "plan_type_code": "",
            "payer_name": "",
            "payer_id": "",
            "group_number": "",
            "group_name": "",
            "effective_date": "",
            "term_date": "",
            "plan_begin_date": "",
            "plan_end_date": "",
            "benefit_begin_date": "",
            "benefit_end_date": "",
            "provider_npi": "",
            "provider_name": "",
            "provider_taxonomy": "",
            "network_status": "Unknown",
            "participating": "Unknown",
            "trace_number": "",
            "deductible": 0.0,
            "deductible_remaining": 0.0,
            "family_deductible": 0.0,
            "family_deductible_remaining": 0.0,
            "copay": 0.0,
            "copays": {},
            "copays_oon": {},
            "coinsurance_pct": 0,
            "coinsurance_pct_oon": 0,
            "coinsurance_in": {},
            "coinsurance_oon": {},
            "oop_max": 0.0,
            "oop_remaining": 0.0,
            "lifetime_max": 0.0,
            "services": [],
            "preauth_services": [],
            "preauth_messages": [],
            "messages": [],
        }

    def _finalize_patient(self, patient):
        """
        Post-process a patient record after all segments have been consumed.
        Determines coverage status from term_date if not explicitly set.
        """
        # If we have a termination date in the past, mark as Terminated
        if patient.get("term_date"):
            try:
                td = datetime.strptime(patient["term_date"], "%Y%m%d")
                if td < datetime.now():
                    if patient["coverage_status"] in ("Unknown", "Inactive"):
                        patient["coverage_status"] = "Terminated"
            except (ValueError, TypeError):
                pass

        # Default copay from copays dict if not set
        if patient["copay"] == 0.0 and patient.get("copays"):
            # Use the first available copay
            for key in ("copay_96", "copay_UC", "copay_30"):
                if key in patient["copays"]:
                    patient["copay"] = patient["copays"][key]
                    break
            if patient["copay"] == 0.0:
                vals = list(patient["copays"].values())
                if vals:
                    patient["copay"] = vals[0]

        # Consolidate coinsurance for display
        if patient.get("coinsurance_pct") and not patient.get("coinsurance"):
            in_pct = patient.get("coinsurance_pct", 0)
            out_pct = patient.get("coinsurance_pct_oon", 0)
            if in_pct and out_pct:
                patient["coinsurance"] = f"{in_pct}% In / {out_pct}% Out"
            elif in_pct:
                patient["coinsurance"] = f"{in_pct}%"

        # Set preauth label
        patient["preauth_services_label"] = "Yes" if patient.get("preauth_services") else "No"

        # Generate appointment and verification timestamps
        # Appointment date: a future date within 1-30 days
        now = datetime.now()
        import hashlib
        pat_hash = int(hashlib.md5(patient.get("member_id", "").encode()).hexdigest()[:8], 16)
        appt_offset = (pat_hash % 30) + 1
        appt_date = now + timedelta(days=appt_offset)
        patient["appointment_date"] = appt_date.strftime("%m/%d/%Y")
        # Verification date/time: now (when the eligibility check ran)
        patient["verification_date"] = now.strftime("%m/%d/%Y")
        patient["verification_time"] = now.strftime("%I:%M %p")

        # Format dates for display
        for date_field in ("dob", "effective_date", "term_date",
                           "plan_begin_date", "plan_end_date",
                           "benefit_begin_date", "benefit_end_date"):
            val = patient.get(date_field, "")
            if val and len(val) == 8:
                try:
                    patient[f"{date_field}_formatted"] = (
                        f"{val[4:6]}/{val[6:8]}/{val[:4]}"
                    )
                except (IndexError, ValueError):
                    patient[f"{date_field}_formatted"] = val

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _elem(seg, idx):
        """Safely get element at index, returning empty string if absent."""
        if idx < len(seg):
            return seg[idx].strip()
        return ""


# ============================================================================
# ALERT GENERATOR
# ============================================================================

def generate_alerts(patient):
    """
    Produce a list of coverage alert dicts for a given patient record.
    Each alert has: alert_type, alert_description, action_required.
    """
    alerts = []

    # 1. Inactive / Terminated coverage
    status = patient.get("coverage_status", "Unknown")
    if status in ("Inactive", "Terminated"):
        alerts.append({
            "alert_type": "INACTIVE_COVERAGE",
            "alert_description": (
                f"Patient coverage is {status}. "
                f"Term date: {patient.get('term_date_formatted', patient.get('term_date', 'N/A'))}."
            ),
            "action_required": (
                "Verify coverage with payer. Collect self-pay or update insurance on file."
            ),
        })

    # 2. Expired coverage (term_date in the past)
    if patient.get("term_date"):
        try:
            td = datetime.strptime(patient["term_date"], "%Y%m%d")
            if td < datetime.now():
                alerts.append({
                    "alert_type": "EXPIRED_COVERAGE",
                    "alert_description": (
                        f"Coverage expired on {patient.get('term_date_formatted', patient['term_date'])}."
                    ),
                    "action_required": (
                        "Contact patient to obtain updated insurance information before rendering services."
                    ),
                })
        except (ValueError, TypeError):
            pass

    # 3. Out-of-network
    if patient.get("network_status") == "Out-of-Network":
        alerts.append({
            "alert_type": "OUT_OF_NETWORK",
            "alert_description": (
                f"Provider {patient.get('provider_name', 'N/A')} (NPI: {patient.get('provider_npi', 'N/A')}) "
                f"is out-of-network for {patient.get('payer_name', 'payer')}."
            ),
            "action_required": (
                "Inform patient of potential higher out-of-pocket costs. "
                "Consider referring to in-network provider or obtain ABN."
            ),
        })

    # 4. High deductible remaining (>75% unmet)
    deductible = patient.get("deductible", 0)
    remaining = patient.get("deductible_remaining", 0)
    if deductible > 0 and remaining > 0:
        pct_remaining = remaining / deductible
        if pct_remaining > 0.75:
            alerts.append({
                "alert_type": "HIGH_DEDUCTIBLE_REMAINING",
                "alert_description": (
                    f"Individual deductible: ${deductible:,.2f}. "
                    f"Remaining: ${remaining:,.2f} ({pct_remaining:.0%} unmet)."
                ),
                "action_required": (
                    "Discuss expected patient responsibility. "
                    "Consider payment plan options. Collect estimated amount at time of service."
                ),
            })

    # 5. Pre-authorization needed
    if patient.get("preauth_services"):
        svc_list = ", ".join(
            s.get("service_type", s.get("service_type_code", ""))
            for s in patient["preauth_services"]
        )
        alerts.append({
            "alert_type": "PREAUTH_REQUIRED",
            "alert_description": (
                f"Pre-authorization required for: {svc_list}."
            ),
            "action_required": (
                "Obtain pre-authorization from payer before scheduling or rendering services. "
                "Failure to obtain authorization may result in claim denial."
            ),
        })

    # 6. Unknown coverage status
    if status == "Unknown":
        alerts.append({
            "alert_type": "UNKNOWN_COVERAGE",
            "alert_description": "Coverage status could not be determined from eligibility response.",
            "action_required": "Contact payer directly to verify patient eligibility before visit.",
        })

    return alerts


# ============================================================================
# OUTPUT WRITERS
# ============================================================================

def write_eligibility_summary_csv(patients, filepath):
    """
    Write the eligibility summary CSV for one practice type.

    Columns: patient_name, member_id, dob, coverage_status, plan_type,
             payer_name, effective_date, term_date, provider_npi,
             provider_name, network_status
    """
    fieldnames = [
        "patient_name", "member_id", "dob", "coverage_status", "plan_type",
        "payer_name", "effective_date", "term_date", "provider_npi",
        "provider_name", "network_status",
    ]
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for pat in patients:
            row = {k: pat.get(k, "") for k in fieldnames}
            # Format dates for CSV
            for df in ("dob", "effective_date", "term_date"):
                val = pat.get(f"{df}_formatted", pat.get(df, ""))
                row[df] = val
            writer.writerow(row)
    return filepath


def write_benefits_detail_csv(patients, filepath):
    """
    Write the benefits detail CSV.

    Columns: member_id, service_type, coverage_level, deductible,
             deductible_remaining, copay, coinsurance_pct, oop_max,
             oop_remaining, preauth_required
    """
    fieldnames = [
        "member_id", "service_type", "coverage_level", "deductible",
        "deductible_remaining", "copay", "coinsurance_pct", "oop_max",
        "oop_remaining", "preauth_required",
    ]
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    # Collect unique service types per patient
    rows = []
    for pat in patients:
        seen_services = set()
        preauth_svc_codes = {
            s.get("service_type_code", "") for s in pat.get("preauth_services", [])
        }
        for svc in pat.get("services", []):
            svc_code = svc.get("service_type_code", "")
            svc_type = svc.get("service_type", svc_code)
            if svc_code in seen_services:
                continue
            seen_services.add(svc_code)

            # Get copay for this service type
            copay_key = f"copay_{svc_code}"
            copay = pat.get("copays", {}).get(copay_key, pat.get("copay", 0.0))

            # Get coinsurance for this service
            coins = pat.get("coinsurance_in", {}).get(svc_code, pat.get("coinsurance_pct", 0))

            rows.append({
                "member_id": pat.get("member_id", ""),
                "service_type": svc_type,
                "coverage_level": svc.get("coverage_level", "Individual"),
                "deductible": f"{pat.get('deductible', 0.0):.2f}",
                "deductible_remaining": f"{pat.get('deductible_remaining', 0.0):.2f}",
                "copay": f"{copay:.2f}",
                "coinsurance_pct": f"{coins}",
                "oop_max": f"{pat.get('oop_max', 0.0):.2f}",
                "oop_remaining": f"{pat.get('oop_remaining', 0.0):.2f}",
                "preauth_required": "Yes" if svc_code in preauth_svc_codes else "No",
            })

        # If no services parsed, still output a row with plan-level data
        if not seen_services:
            rows.append({
                "member_id": pat.get("member_id", ""),
                "service_type": "Health Benefit Plan Coverage",
                "coverage_level": "Individual",
                "deductible": f"{pat.get('deductible', 0.0):.2f}",
                "deductible_remaining": f"{pat.get('deductible_remaining', 0.0):.2f}",
                "copay": f"{pat.get('copay', 0.0):.2f}",
                "coinsurance_pct": f"{pat.get('coinsurance_pct', 0)}",
                "oop_max": f"{pat.get('oop_max', 0.0):.2f}",
                "oop_remaining": f"{pat.get('oop_remaining', 0.0):.2f}",
                "preauth_required": "Yes" if pat.get("preauth_services") else "No",
            })

    with open(filepath, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return filepath


def write_coverage_alerts_csv(patients, filepath):
    """
    Write coverage alerts CSV.

    Columns: member_id, patient_name, alert_type, alert_description, action_required
    """
    fieldnames = [
        "member_id", "patient_name", "alert_type",
        "alert_description", "action_required",
    ]
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    rows = []
    for pat in patients:
        alerts = generate_alerts(pat)
        for alert in alerts:
            rows.append({
                "member_id": pat.get("member_id", ""),
                "patient_name": pat.get("patient_name", ""),
                "alert_type": alert["alert_type"],
                "alert_description": alert["alert_description"],
                "action_required": alert["action_required"],
            })

    with open(filepath, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return filepath


def write_dashboard_json(all_practice_data, filepath):
    """
    Write consolidated eligibility dashboard JSON across all practice types.
    """
    dashboard = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {},
        "practice_types": {},
    }

    total_patients = 0
    total_active = 0
    total_inactive = 0
    total_terminated = 0
    total_in_network = 0
    total_out_of_network = 0
    total_alerts = 0
    total_preauth_flags = 0
    all_deductibles = []
    all_copays = []
    all_oop = []

    for pt, patients in all_practice_data.items():
        pt_active = sum(1 for p in patients if p.get("coverage_status") == "Active")
        pt_inactive = sum(1 for p in patients if p.get("coverage_status") == "Inactive")
        pt_terminated = sum(1 for p in patients if p.get("coverage_status") == "Terminated")
        pt_in_net = sum(1 for p in patients if p.get("network_status") == "In-Network")
        pt_out_net = sum(1 for p in patients if p.get("network_status") == "Out-of-Network")

        pt_alerts = sum(len(generate_alerts(p)) for p in patients)
        pt_preauth = sum(1 for p in patients if p.get("preauth_services"))

        pt_deductibles = [p.get("deductible", 0) for p in patients if p.get("deductible", 0) > 0]
        pt_copays = [p.get("copay", 0) for p in patients if p.get("copay", 0) > 0]
        pt_oop = [p.get("oop_max", 0) for p in patients if p.get("oop_max", 0) > 0]

        # Plan type breakdown
        plan_counts = defaultdict(int)
        for p in patients:
            plan_label = p.get("plan_type", "Unknown") or "Unknown"
            plan_counts[plan_label] += 1

        display_name = PRACTICE_DISPLAY_NAMES.get(pt, pt)
        dashboard["practice_types"][pt] = {
            "display_name": display_name,
            "total_patients": len(patients),
            "coverage": {
                "active": pt_active,
                "inactive": pt_inactive,
                "terminated": pt_terminated,
            },
            "network": {
                "in_network": pt_in_net,
                "out_of_network": pt_out_net,
            },
            "plan_types": dict(plan_counts),
            "financials": {
                "avg_deductible": round(sum(pt_deductibles) / len(pt_deductibles), 2) if pt_deductibles else 0,
                "avg_copay": round(sum(pt_copays) / len(pt_copays), 2) if pt_copays else 0,
                "avg_oop_max": round(sum(pt_oop) / len(pt_oop), 2) if pt_oop else 0,
            },
            "alerts_generated": pt_alerts,
            "preauth_flags": pt_preauth,
        }

        total_patients += len(patients)
        total_active += pt_active
        total_inactive += pt_inactive
        total_terminated += pt_terminated
        total_in_network += pt_in_net
        total_out_of_network += pt_out_net
        total_alerts += pt_alerts
        total_preauth_flags += pt_preauth
        all_deductibles.extend(pt_deductibles)
        all_copays.extend(pt_copays)
        all_oop.extend(pt_oop)

    dashboard["summary"] = {
        "total_patients_processed": total_patients,
        "total_practice_types": len(all_practice_data),
        "coverage_breakdown": {
            "active": total_active,
            "inactive": total_inactive,
            "terminated": total_terminated,
        },
        "network_breakdown": {
            "in_network": total_in_network,
            "out_of_network": total_out_of_network,
        },
        "financial_averages": {
            "avg_deductible": round(sum(all_deductibles) / len(all_deductibles), 2) if all_deductibles else 0,
            "avg_copay": round(sum(all_copays) / len(all_copays), 2) if all_copays else 0,
            "avg_oop_max": round(sum(all_oop) / len(all_oop), 2) if all_oop else 0,
        },
        "total_alerts_generated": total_alerts,
        "total_preauth_flags": total_preauth_flags,
    }

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as fh:
        json.dump(dashboard, fh, indent=2)
    return filepath


def write_text_report(all_practice_data, filepath):
    """
    Write a human-readable eligibility report summarizing all practice types.
    """
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    lines = []

    lines.append("=" * 80)
    lines.append("REAL-TIME ELIGIBILITY VERIFICATION REPORT")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 80)
    lines.append("")

    grand_total = 0
    grand_active = 0
    grand_inactive = 0
    grand_terminated = 0
    grand_in_network = 0
    grand_out_network = 0
    grand_alerts = 0
    grand_preauth = 0
    grand_deductibles = []
    grand_copays = []

    for pt in sorted(all_practice_data.keys()):
        patients = all_practice_data[pt]
        display_name = PRACTICE_DISPLAY_NAMES.get(pt, pt)

        active = sum(1 for p in patients if p.get("coverage_status") == "Active")
        inactive = sum(1 for p in patients if p.get("coverage_status") == "Inactive")
        terminated = sum(1 for p in patients if p.get("coverage_status") == "Terminated")
        unknown = sum(1 for p in patients if p.get("coverage_status") == "Unknown")
        in_net = sum(1 for p in patients if p.get("network_status") == "In-Network")
        out_net = sum(1 for p in patients if p.get("network_status") == "Out-of-Network")
        alerts = sum(len(generate_alerts(p)) for p in patients)
        preauth_count = sum(1 for p in patients if p.get("preauth_services"))

        deductibles = [p.get("deductible", 0) for p in patients if p.get("deductible", 0) > 0]
        copays = [p.get("copay", 0) for p in patients if p.get("copay", 0) > 0]
        oop_maxes = [p.get("oop_max", 0) for p in patients if p.get("oop_max", 0) > 0]
        ded_remaining = [p.get("deductible_remaining", 0) for p in patients if p.get("deductible_remaining", 0) > 0]

        lines.append("-" * 80)
        lines.append(f"  PRACTICE TYPE: {display_name}")
        lines.append("-" * 80)
        lines.append(f"  Total Patients Processed:      {len(patients)}")
        lines.append(f"  Coverage Status:")
        lines.append(f"    Active:                      {active}")
        lines.append(f"    Inactive:                    {inactive}")
        lines.append(f"    Terminated:                  {terminated}")
        if unknown > 0:
            lines.append(f"    Unknown:                     {unknown}")
        lines.append(f"  Network Status:")
        lines.append(f"    In-Network:                  {in_net}")
        lines.append(f"    Out-of-Network:              {out_net}")

        if deductibles:
            avg_ded = sum(deductibles) / len(deductibles)
            lines.append(f"  Financial Summary:")
            lines.append(f"    Avg Deductible:              ${avg_ded:,.2f}")
            if ded_remaining:
                avg_rem = sum(ded_remaining) / len(ded_remaining)
                lines.append(f"    Avg Deductible Remaining:    ${avg_rem:,.2f}")
            if copays:
                avg_cop = sum(copays) / len(copays)
                lines.append(f"    Avg Copay:                   ${avg_cop:,.2f}")
            if oop_maxes:
                avg_oop = sum(oop_maxes) / len(oop_maxes)
                lines.append(f"    Avg OOP Maximum:             ${avg_oop:,.2f}")

        lines.append(f"  Alerts Generated:              {alerts}")
        lines.append(f"  Pre-Auth Requirements Flagged: {preauth_count}")
        lines.append("")

        grand_total += len(patients)
        grand_active += active
        grand_inactive += inactive
        grand_terminated += terminated
        grand_in_network += in_net
        grand_out_network += out_net
        grand_alerts += alerts
        grand_preauth += preauth_count
        grand_deductibles.extend(deductibles)
        grand_copays.extend(copays)

    # Summary section
    lines.append("=" * 80)
    lines.append("  CONSOLIDATED SUMMARY")
    lines.append("=" * 80)
    lines.append(f"  Total Practice Types:          {len(all_practice_data)}")
    lines.append(f"  Total Patients Processed:      {grand_total}")
    lines.append(f"")
    lines.append(f"  Coverage Breakdown:")
    lines.append(f"    Active:                      {grand_active} ({grand_active/max(grand_total,1)*100:.1f}%)")
    lines.append(f"    Inactive:                    {grand_inactive} ({grand_inactive/max(grand_total,1)*100:.1f}%)")
    lines.append(f"    Terminated:                  {grand_terminated} ({grand_terminated/max(grand_total,1)*100:.1f}%)")
    lines.append(f"")
    lines.append(f"  Network Breakdown:")
    lines.append(f"    In-Network:                  {grand_in_network} ({grand_in_network/max(grand_total,1)*100:.1f}%)")
    lines.append(f"    Out-of-Network:              {grand_out_network} ({grand_out_network/max(grand_total,1)*100:.1f}%)")
    lines.append(f"")

    if grand_deductibles:
        lines.append(f"  Financial Averages (All Practice Types):")
        lines.append(f"    Avg Deductible:              ${sum(grand_deductibles)/len(grand_deductibles):,.2f}")
        if grand_copays:
            lines.append(f"    Avg Copay:                   ${sum(grand_copays)/len(grand_copays):,.2f}")
    lines.append(f"")
    lines.append(f"  Total Alerts Generated:        {grand_alerts}")
    lines.append(f"  Total Pre-Auth Flags:          {grand_preauth}")
    lines.append("")
    lines.append("=" * 80)
    lines.append("  END OF REPORT")
    lines.append("=" * 80)

    with open(filepath, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return filepath


# ============================================================================
# MAIN PROCESSING PIPELINE
# ============================================================================

def process_practice_type(practice_type, input_dir, output_dir, parser, verbose=False):
    """
    Process all EDI 271 files for a single practice type.

    Returns: list of patient-eligibility dicts
    """
    pt_dir = os.path.join(input_dir, practice_type)
    if not os.path.isdir(pt_dir):
        if verbose:
            print(f"  [SKIP] No directory found for {practice_type}: {pt_dir}")
        return []

    edi_files = sorted(
        f for f in os.listdir(pt_dir)
        if f.lower().endswith(".edi")
    )

    if not edi_files:
        if verbose:
            print(f"  [SKIP] No .edi files in {pt_dir}")
        return []

    all_patients = []
    for edi_file in edi_files:
        filepath = os.path.join(pt_dir, edi_file)
        try:
            patients = parser.parse_file(filepath)
            all_patients.extend(patients)
            if verbose:
                print(f"    Parsed {edi_file}: {len(patients)} patient(s)")
        except Exception as e:
            print(f"    [ERROR] Failed to parse {edi_file}: {e}")

    if verbose:
        print(f"  {practice_type}: {len(all_patients)} total patients from {len(edi_files)} file(s)")

    # Stamp practice_type on every patient record
    display_name = PRACTICE_DISPLAY_NAMES.get(practice_type, practice_type)
    for pat in all_patients:
        pat["practice_type"] = display_name

    # Skip per-practice output files; consolidation happens in main()
    return all_patients


def main():
    """
    Main entry point. Parses arguments, optionally generates test EDI data,
    processes 270/271 files, and writes output reports.
    """
    parser = argparse.ArgumentParser(
        description="Process EDI 270/271 eligibility files and extract "
                    "patient eligibility, benefits, and coverage data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/realtime_eligibility.py\n"
            "  python scripts/realtime_eligibility.py --practice-type cardiology --verbose\n"
            "  python scripts/realtime_eligibility.py --input-dir test_data/eligibility "
            "--output-dir test_data/eligibility/results\n"
        ),
    )
    parser.add_argument(
        "--input-dir",
        default=os.path.join(_PROJECT_ROOT, "test_data", "eligibility"),
        help="Directory containing practice-type subdirectories with .edi files "
             "(default: test_data/eligibility)",
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(_PROJECT_ROOT, "Results", "Realtime_Eligibility"),
        help="Directory for output CSV, JSON, TXT, and Excel files "
             "(default: Results/Realtime_Eligibility)",
    )
    parser.add_argument(
        "--practice-type",
        default=None,
        help="Process a single practice type only (e.g., cardiology)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output during processing",
    )

    args = parser.parse_args()
    input_dir = args.input_dir
    output_dir = args.output_dir
    verbose = args.verbose

    # Determine which practice types to process
    if args.practice_type:
        if args.practice_type not in PRACTICE_TYPES:
            print(f"[ERROR] Unknown practice type: {args.practice_type}")
            print(f"Valid types: {', '.join(PRACTICE_TYPES)}")
            sys.exit(1)
        practice_types = [args.practice_type]
    else:
        practice_types = list(PRACTICE_TYPES)

    print("=" * 70)
    print("Real-Time Eligibility Verification Processor (EDI 270/271)")
    print("=" * 70)
    print(f"  Input directory:  {input_dir}")
    print(f"  Output directory: {output_dir}")
    print(f"  Practice types:   {len(practice_types)}")
    print()

    # Check if EDI files exist; if not, generate test data
    has_edi_files = False
    for pt in practice_types:
        pt_dir = os.path.join(input_dir, pt)
        if os.path.isdir(pt_dir):
            edi_files = [f for f in os.listdir(pt_dir) if f.lower().endswith(".edi")]
            if edi_files:
                has_edi_files = True
                break

    if not has_edi_files:
        print("  No EDI files found. Generating test 271 eligibility response data...")
        files_created = _generate_edi_271_files(input_dir, practice_types, verbose)
        print(f"  Generated {files_created} EDI 271 test files.")
        print()

    # Process each practice type
    edi_parser = EDI271Parser(verbose=verbose)
    all_practice_data = {}

    print("  Processing eligibility files...")
    print()

    for pt in practice_types:
        if verbose:
            print(f"  [{practice_types.index(pt) + 1}/{len(practice_types)}] "
                  f"{PRACTICE_DISPLAY_NAMES.get(pt, pt)}")

        patients = process_practice_type(pt, input_dir, output_dir, edi_parser, verbose)
        if patients:
            all_practice_data[pt] = patients

    # Write consolidated outputs
    if all_practice_data:
        print()
        print("  Writing consolidated outputs...")

        # Consolidated eligibility summary CSV
        all_patients = []
        for pts in all_practice_data.values():
            all_patients.extend(pts)

        # Build practice-level summary data (used for CSV and Excel Summary tab)
        summary_data = []
        for pt_key in sorted(all_practice_data.keys()):
            pts = all_practice_data[pt_key]
            display_name = PRACTICE_DISPLAY_NAMES.get(pt_key, pt_key)
            active = sum(1 for p in pts if p.get("coverage_status") == "Active")
            inactive = sum(1 for p in pts if p.get("coverage_status") == "Inactive")
            terminated = sum(1 for p in pts if p.get("coverage_status") == "Terminated")
            in_net = sum(1 for p in pts if p.get("network_status") == "In-Network")
            out_net = sum(1 for p in pts if p.get("network_status") == "Out-of-Network")
            alerts_count = sum(len(generate_alerts(p)) for p in pts)
            preauth = sum(1 for p in pts if p.get("preauth_services"))
            summary_data.append({
                "Practice_Type": display_name,
                "Total_Members": len(pts),
                "Active_Coverage": active,
                "Inactive_Coverage": inactive,
                "Terminated_Coverage": terminated,
                "In_Network_Providers": in_net,
                "Out_of_Network_Providers": out_net,
                "Alerts_Generated": alerts_count,
                "PreAuth_Required": preauth,
            })

        consolidated_summary_path = os.path.join(output_dir, "eligibility_all_practices_summary.csv")
        summary_fieldnames = [
            "Practice_Type", "Total_Members", "Active_Coverage",
            "Inactive_Coverage", "Terminated_Coverage",
            "In_Network_Providers", "Out_of_Network_Providers",
            "Alerts_Generated", "PreAuth_Required",
        ]
        os.makedirs(os.path.dirname(consolidated_summary_path), exist_ok=True)
        with open(consolidated_summary_path, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=summary_fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in summary_data:
                writer.writerow(row)
        print(f"    -> {consolidated_summary_path}")

        dashboard_path = os.path.join(output_dir, "eligibility_dashboard.json")
        write_dashboard_json(all_practice_data, dashboard_path)
        print(f"    -> {dashboard_path}")

        report_path = os.path.join(output_dir, "eligibility_report.txt")
        write_text_report(all_practice_data, report_path)
        print(f"    -> {report_path}")

        # Create Excel export with Summary, Details, and Adjustment Codes Mapping
        try:
            from generators.excel_exporter import create_summary_details_excel
            _excel_enabled = True
        except ImportError:
            _excel_enabled = False

        if _excel_enabled:
            # Build patient-level summary for the Excel Summary tab
            # (the practice-level summary_data is used for the separate CSV)
            excel_summary_data = []
            for pat in all_patients:
                excel_summary_data.append({
                    "Patient_Name": pat.get("patient_name", ""),
                    "Member_ID": pat.get("member_id", ""),
                    "DOB": pat.get("dob_formatted", pat.get("dob", "")),
                    "Practice_Type": pat.get("practice_type", ""),
                    "Coverage_Status": pat.get("coverage_status", ""),
                    "Payer_Name": pat.get("payer_name", ""),
                    "Plan_Type": pat.get("plan_type", ""),
                    "Effective_Date": pat.get("effective_date_formatted", pat.get("effective_date", "")),
                    "Term_Date": pat.get("term_date_formatted", pat.get("term_date", "")),
                    "Provider_NPI": pat.get("provider_npi", ""),
                    "Provider_Name": pat.get("provider_name", ""),
                    "Network_Status": pat.get("network_status", "Unknown"),
                })

            # Prepare details data (comprehensive: all patients with all benefit fields + individual alert rows)
            details_data = []
            all_alerts = []
            alert_type_counter = {}
            
            for pat in all_patients:
                # Generate all alerts for this patient
                alerts = generate_alerts(pat)
                
                # Track alert counts
                for alert in alerts:
                    alert_type_counter[alert.get("alert_type", "Unknown")] = alert_type_counter.get(alert.get("alert_type", "Unknown"), 0) + 1
                    all_alerts.append(alert)
                
                # Build unique service types from parsed EB benefit records
                service_types = list(dict.fromkeys(
                    s.get("service_type", s.get("service_type_code", ""))
                    for s in pat.get("services", [])
                    if s.get("service_type") and s.get("service_type") != "General"
                ))
                if not service_types:
                    service_types = ["General"]
                
                # Consolidate alerts into single semicolon-delimited values
                alert_types = "; ".join(a.get("alert_type", "") for a in alerts) if alerts else ""
                alert_descs = "; ".join(a.get("alert_description", "") for a in alerts) if alerts else ""
                actions_req = "; ".join(a.get("action_required", "") for a in alerts) if alerts else ""
                
                # ONE row per patient
                details_data.append({
                    "Patient_Name": pat.get("patient_name", ""),
                    "Member_ID": pat.get("member_id", ""),
                    "DOB": pat.get("dob_formatted", pat.get("dob", "")),
                    "Practice_Type": pat.get("practice_type", ""),
                    "Payer_Name": pat.get("payer_name", ""),
                    "Plan_Type": pat.get("plan_type", ""),
                    "Coverage_Status": pat.get("coverage_status", ""),
                    "Network_Status": pat.get("network_status", "Unknown"),
                    "Effective_Date": pat.get("effective_date_formatted", pat.get("effective_date", "")),
                    "Term_Date": pat.get("term_date_formatted", pat.get("term_date", "")),
                    "Appointment_Date": pat.get("appointment_date", ""),
                    "Verification_Date": pat.get("verification_date", ""),
                    "Verification_Time": pat.get("verification_time", ""),
                    "Service_Type": "; ".join(service_types),
                    "Copay": pat.get("copay", 0),
                    "Coinsurance": pat.get("coinsurance", ""),
                    "Deductible_Amount": pat.get("deductible", 0),
                    "Deductible_Remaining": pat.get("deductible_remaining", 0),
                    "Out_of_Pocket_Amount": pat.get("oop_max", 0),
                    "Out_of_Pocket_Remaining": pat.get("oop_remaining", 0),
                    "In_Network_Deductible": pat.get("in_network_deductible", 0),
                    "Out_of_Network_Deductible": pat.get("out_of_network_deductible", 0),
                    "In_Network_OOP": pat.get("in_network_oop", 0),
                    "Out_of_Network_OOP": pat.get("out_of_network_oop", 0),
                    "PreAuth_Required": pat.get("preauth_services_label", "No"),
                    "PreAuth_Services": "; ".join(s.get("service_type", s.get("service_type_code", "")) for s in pat.get("preauth_services", [])) if pat.get("preauth_services") else "",
                    "Provider_NPI": pat.get("provider_npi", ""),
                    "Provider_Name": pat.get("provider_name", ""),
                    "Alert_Type": alert_types,
                    "Alert_Description": alert_descs,
                    "Action_Required": actions_req,
                })
            
            # Prepare rollup data (counts and percentages by category)
            total_patient_records = len(all_patients)
            total_detail_rows = len(details_data)
            total_alerts_all = sum(len(generate_alerts(p)) for p in all_patients)
            
            # Coverage status rollup
            coverage_status_counts = {}
            for pat in all_patients:
                status = pat.get("coverage_status", "Unknown")
                coverage_status_counts[status] = coverage_status_counts.get(status, 0) + 1
            
            # Network status rollup
            network_status_counts = {}
            for pat in all_patients:
                status = pat.get("network_status", "Unknown")
                network_status_counts[status] = network_status_counts.get(status, 0) + 1
            
            # Alert type rollup
            alert_type_counts = {}
            for pat in all_patients:
                for alert in generate_alerts(pat):
                    alert_type = alert.get("alert_type", "Unknown")
                    alert_type_counts[alert_type] = alert_type_counts.get(alert_type, 0) + 1
            
            # PreAuth rollup
            preauth_required = sum(1 for p in all_patients if p.get("preauth_services"))
            preauth_not_required = total_patient_records - preauth_required
            
            # Plan type rollup
            plan_type_counts = {}
            for pat in all_patients:
                plan = pat.get("plan_type", "Unknown")
                plan_type_counts[plan] = plan_type_counts.get(plan, 0) + 1
            
            # Build rollup_data list for Rollup sheet
            rollup_data = []
            
            # Coverage Status section
            rollup_data.append({"Category": "COVERAGE STATUS", "Value": "", "Count": "", "Percentage": ""})
            for status, count in sorted(coverage_status_counts.items()):
                pct = (count / total_patient_records * 100) if total_patient_records > 0 else 0
                rollup_data.append({
                    "Category": "Coverage Status",
                    "Value": status,
                    "Count": count,
                    "Percentage": f"{pct:.1f}%"
                })
            rollup_data.append({"Category": "", "Value": "", "Count": "", "Percentage": ""})
            
            # Network Status section
            rollup_data.append({"Category": "NETWORK STATUS", "Value": "", "Count": "", "Percentage": ""})
            for status, count in sorted(network_status_counts.items()):
                pct = (count / total_patient_records * 100) if total_patient_records > 0 else 0
                rollup_data.append({
                    "Category": "Network Status",
                    "Value": status,
                    "Count": count,
                    "Percentage": f"{pct:.1f}%"
                })
            rollup_data.append({"Category": "", "Value": "", "Count": "", "Percentage": ""})
            
            # Alert Type section
            rollup_data.append({"Category": "ALERTS GENERATED", "Value": "", "Count": "", "Percentage": ""})
            for alert_type, count in sorted(alert_type_counts.items()):
                pct = (count / total_alerts_all * 100) if total_alerts_all > 0 else 0
                rollup_data.append({
                    "Category": "Alert Type",
                    "Value": alert_type,
                    "Count": count,
                    "Percentage": f"{pct:.1f}%"
                })
            rollup_data.append({"Category": "", "Value": "", "Count": "", "Percentage": ""})
            
            # PreAuth Required section
            rollup_data.append({"Category": "PRE-AUTHORIZATION REQUIRED", "Value": "", "Count": "", "Percentage": ""})
            preauth_pct = (preauth_required / total_patient_records * 100) if total_patient_records > 0 else 0
            no_preauth_pct = (preauth_not_required / total_patient_records * 100) if total_patient_records > 0 else 0
            rollup_data.append({
                "Category": "Pre-Authorization",
                "Value": "Required",
                "Count": preauth_required,
                "Percentage": f"{preauth_pct:.1f}%"
            })
            rollup_data.append({
                "Category": "Pre-Authorization",
                "Value": "Not Required",
                "Count": preauth_not_required,
                "Percentage": f"{no_preauth_pct:.1f}%"
            })
            rollup_data.append({"Category": "", "Value": "", "Count": "", "Percentage": ""})
            
            # Plan Type section
            rollup_data.append({"Category": "PLAN TYPE", "Value": "", "Count": "", "Percentage": ""})
            for plan_type, count in sorted(plan_type_counts.items()):
                pct = (count / total_patient_records * 100) if total_patient_records > 0 else 0
                rollup_data.append({
                    "Category": "Plan Type",
                    "Value": plan_type,
                    "Count": count,
                    "Percentage": f"{pct:.1f}%"
                })
            rollup_data.append({"Category": "", "Value": "", "Count": "", "Percentage": ""})

            # Payer Name section
            payer_name_counts = {}
            for pat in all_patients:
                payer = pat.get("payer_name", "Unknown")
                payer_name_counts[payer] = payer_name_counts.get(payer, 0) + 1

            rollup_data.append({"Category": "PAYER NAME", "Value": "", "Count": "", "Percentage": ""})
            for payer, count in sorted(payer_name_counts.items()):
                pct = (count / total_patient_records * 100) if total_patient_records > 0 else 0
                rollup_data.append({
                    "Category": "Payer Name",
                    "Value": payer,
                    "Count": count,
                    "Percentage": f"{pct:.1f}%"
                })

            rollup_data.append({"Category": "", "Value": "", "Count": "", "Percentage": ""})
            rollup_data.append({"Category": "SUMMARY", "Value": "Total Patients", "Count": total_patient_records, "Percentage": "100%"})
            rollup_data.append({"Category": "SUMMARY", "Value": "Total Detail Rows (with alerts)", "Count": total_detail_rows, "Percentage": ""})
            rollup_data.append({"Category": "SUMMARY", "Value": "Total Alerts", "Count": total_alerts_all, "Percentage": ""})
            
            # Create Excel file with Summary, Details, and Rollup sheets
            print(f"    [INFO] Summary rows: {len(excel_summary_data)}; Details rows: {len(details_data)}; Rollup rows: {len(rollup_data) if rollup_data else 0}")

            excel_path = create_summary_details_excel(
                output_dir,
                "eligibility_analysis",
                excel_summary_data,
                details_data,
                rollup_data,
                None  # No adjustment mapping for eligibility reports
            )
            print(f"    -> {excel_path}")
        else:
            print("    [INFO] Excel export disabled (openpyxl not installed)")

    # Print summary
    print()
    print("-" * 70)
    print("  PROCESSING SUMMARY")
    print("-" * 70)

    total_patients = sum(len(pts) for pts in all_practice_data.values())
    total_active = sum(
        sum(1 for p in pts if p.get("coverage_status") == "Active")
        for pts in all_practice_data.values()
    )
    total_inactive = sum(
        sum(1 for p in pts if p.get("coverage_status") in ("Inactive", "Terminated"))
        for pts in all_practice_data.values()
    )
    total_in_net = sum(
        sum(1 for p in pts if p.get("network_status") == "In-Network")
        for pts in all_practice_data.values()
    )
    total_out_net = sum(
        sum(1 for p in pts if p.get("network_status") == "Out-of-Network")
        for pts in all_practice_data.values()
    )
    total_alerts = sum(
        sum(len(generate_alerts(p)) for p in pts)
        for pts in all_practice_data.values()
    )
    total_preauth = sum(
        sum(1 for p in pts if p.get("preauth_services"))
        for pts in all_practice_data.values()
    )

    for pt in sorted(all_practice_data.keys()):
        pts = all_practice_data[pt]
        active = sum(1 for p in pts if p.get("coverage_status") == "Active")
        display = PRACTICE_DISPLAY_NAMES.get(pt, pt)
        print(f"  {display:<42s}  {len(pts):>4} patients  ({active} active)")

    print()
    print(f"  Total patients processed:     {total_patients}")
    print(f"  Active coverage:              {total_active}")
    print(f"  Inactive/Terminated coverage: {total_inactive}")
    print(f"  In-Network providers:         {total_in_net}")
    print(f"  Out-of-Network providers:     {total_out_net}")
    print(f"  Coverage alerts generated:    {total_alerts}")
    print(f"  Pre-auth requirements:        {total_preauth}")
    print()

    all_deductibles = [
        p.get("deductible", 0)
        for pts in all_practice_data.values()
        for p in pts
        if p.get("deductible", 0) > 0
    ]
    all_copays = [
        p.get("copay", 0)
        for pts in all_practice_data.values()
        for p in pts
        if p.get("copay", 0) > 0
    ]
    if all_deductibles:
        print(f"  Avg deductible:               ${sum(all_deductibles)/len(all_deductibles):,.2f}")
    if all_copays:
        print(f"  Avg copay:                    ${sum(all_copays)/len(all_copays):,.2f}")
    print()

    print(f"  Output files written to: {output_dir}")
    print("=" * 70)


if __name__ == "__main__":
    main()