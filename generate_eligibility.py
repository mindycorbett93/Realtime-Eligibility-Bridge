"""
Generator for Benefits and Eligibility test files (EDI 270/271 format).

Produces 12 EDI files per practice type (180 total) across 15 specialties.
Each file contains a paired 270 (Eligibility Inquiry) and 271 (Eligibility
Response) transaction separated by a clear delimiter.

Scenario mix per practice type:
  Files 001-004: Active coverage, in-network provider, standard copay/deductible
  Files 005-008: Active coverage with pre-auth required for specialty services
  Files 009-010: Coverage with high deductible / limited benefits
  Files 011-012: Inactive coverage, out-of-network, or coverage issues

Output path: test_data/eligibility/{practice_type}/elig_{practice}_{idx:03d}.edi
"""

import os
import sys

# Ensure project root is on sys.path so generators package is importable
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from generators.test_data_commons import *

# ============================================================
# SPECIALTY-SPECIFIC SERVICE TYPE CODES
# EDI 271 EB segments use STC (Service Type Codes) to describe
# the category of service being verified.
# ============================================================
SPECIALTY_SERVICE_TYPE_CODES = {
    "primary_care": [
        ("30", "Health Benefit Plan Coverage"),
        ("1", "Medical Care"),
        ("35", "Dental Care"),  # occasionally checked
        ("48", "Hospital - Inpatient"),
        ("50", "Hospital - Outpatient"),
        ("UC", "Urgent Care"),
        ("98", "Professional (Physician) Visit - Office"),
        ("AL", "Vision (Optometry)"),
        ("5", "Diagnostic Lab"),
        ("6", "Diagnostic X-Ray"),
        ("73", "Preventive"),
        ("86", "Emergency Services"),
    ],
    "internal_medicine": [
        ("30", "Health Benefit Plan Coverage"),
        ("1", "Medical Care"),
        ("48", "Hospital - Inpatient"),
        ("50", "Hospital - Outpatient"),
        ("98", "Professional (Physician) Visit - Office"),
        ("5", "Diagnostic Lab"),
        ("6", "Diagnostic X-Ray"),
        ("73", "Preventive"),
        ("86", "Emergency Services"),
        ("42", "Home Health Care"),
        ("88", "Skilled Nursing"),
        ("A6", "Cardiac Rehabilitation"),
    ],
    "allergy_immunology": [
        ("30", "Health Benefit Plan Coverage"),
        ("1", "Medical Care"),
        ("98", "Professional (Physician) Visit - Office"),
        ("5", "Diagnostic Lab"),
        ("73", "Preventive"),
        ("MH", "Mental Health"),
        ("50", "Hospital - Outpatient"),
        ("6", "Diagnostic X-Ray"),
        ("A7", "Allergy Testing"),
        ("A8", "Immunizations"),
        ("AE", "Physical Medicine"),
        ("UC", "Urgent Care"),
    ],
    "orthopaedics": [
        ("30", "Health Benefit Plan Coverage"),
        ("1", "Medical Care"),
        ("98", "Professional (Physician) Visit - Office"),
        ("BN", "Surgical"),
        ("6", "Diagnostic X-Ray"),
        ("BG", "MRI/CAT Scan"),
        ("50", "Hospital - Outpatient"),
        ("48", "Hospital - Inpatient"),
        ("AE", "Physical Medicine"),
        ("AJ", "Rehabilitation"),
        ("AI", "DME - Durable Medical Equipment"),
        ("73", "Preventive"),
    ],
    "cardiology": [
        ("30", "Health Benefit Plan Coverage"),
        ("1", "Medical Care"),
        ("98", "Professional (Physician) Visit - Office"),
        ("48", "Hospital - Inpatient"),
        ("50", "Hospital - Outpatient"),
        ("BN", "Surgical"),
        ("6", "Diagnostic X-Ray"),
        ("BG", "MRI/CAT Scan"),
        ("5", "Diagnostic Lab"),
        ("A6", "Cardiac Rehabilitation"),
        ("86", "Emergency Services"),
        ("73", "Preventive"),
    ],
    "behavioral_health": [
        ("30", "Health Benefit Plan Coverage"),
        ("MH", "Mental Health"),
        ("A4", "Psychiatric"),
        ("98", "Professional (Physician) Visit - Office"),
        ("1", "Medical Care"),
        ("AO", "Substance Abuse"),
        ("50", "Hospital - Outpatient"),
        ("48", "Hospital - Inpatient"),
        ("73", "Preventive"),
        ("5", "Diagnostic Lab"),
        ("AJ", "Rehabilitation"),
        ("UC", "Urgent Care"),
    ],
    "radiology": [
        ("30", "Health Benefit Plan Coverage"),
        ("6", "Diagnostic X-Ray"),
        ("BG", "MRI/CAT Scan"),
        ("1", "Medical Care"),
        ("98", "Professional (Physician) Visit - Office"),
        ("50", "Hospital - Outpatient"),
        ("48", "Hospital - Inpatient"),
        ("5", "Diagnostic Lab"),
        ("73", "Preventive"),
        ("BN", "Surgical"),
        ("86", "Emergency Services"),
        ("AE", "Physical Medicine"),
    ],
    "pathology": [
        ("30", "Health Benefit Plan Coverage"),
        ("5", "Diagnostic Lab"),
        ("1", "Medical Care"),
        ("6", "Diagnostic X-Ray"),
        ("98", "Professional (Physician) Visit - Office"),
        ("50", "Hospital - Outpatient"),
        ("48", "Hospital - Inpatient"),
        ("BN", "Surgical"),
        ("73", "Preventive"),
        ("BG", "MRI/CAT Scan"),
        ("86", "Emergency Services"),
        ("AE", "Physical Medicine"),
    ],
    "gastroenterology": [
        ("30", "Health Benefit Plan Coverage"),
        ("1", "Medical Care"),
        ("98", "Professional (Physician) Visit - Office"),
        ("BN", "Surgical"),
        ("50", "Hospital - Outpatient"),
        ("48", "Hospital - Inpatient"),
        ("5", "Diagnostic Lab"),
        ("6", "Diagnostic X-Ray"),
        ("BG", "MRI/CAT Scan"),
        ("73", "Preventive"),
        ("86", "Emergency Services"),
        ("AE", "Physical Medicine"),
    ],
    "ob_gyn": [
        ("30", "Health Benefit Plan Coverage"),
        ("1", "Medical Care"),
        ("98", "Professional (Physician) Visit - Office"),
        ("89", "Free Standing Prescription Drug"),
        ("7", "Maternity"),
        ("50", "Hospital - Outpatient"),
        ("48", "Hospital - Inpatient"),
        ("5", "Diagnostic Lab"),
        ("6", "Diagnostic X-Ray"),
        ("73", "Preventive"),
        ("BN", "Surgical"),
        ("86", "Emergency Services"),
    ],
    "dermatology": [
        ("30", "Health Benefit Plan Coverage"),
        ("1", "Medical Care"),
        ("98", "Professional (Physician) Visit - Office"),
        ("BN", "Surgical"),
        ("50", "Hospital - Outpatient"),
        ("5", "Diagnostic Lab"),
        ("6", "Diagnostic X-Ray"),
        ("73", "Preventive"),
        ("AE", "Physical Medicine"),
        ("BG", "MRI/CAT Scan"),
        ("86", "Emergency Services"),
        ("48", "Hospital - Inpatient"),
    ],
    "anesthesiology": [
        ("30", "Health Benefit Plan Coverage"),
        ("1", "Medical Care"),
        ("BN", "Surgical"),
        ("48", "Hospital - Inpatient"),
        ("50", "Hospital - Outpatient"),
        ("98", "Professional (Physician) Visit - Office"),
        ("AE", "Physical Medicine"),
        ("86", "Emergency Services"),
        ("5", "Diagnostic Lab"),
        ("6", "Diagnostic X-Ray"),
        ("BG", "MRI/CAT Scan"),
        ("AJ", "Rehabilitation"),
    ],
    "urgent_care": [
        ("30", "Health Benefit Plan Coverage"),
        ("UC", "Urgent Care"),
        ("1", "Medical Care"),
        ("98", "Professional (Physician) Visit - Office"),
        ("86", "Emergency Services"),
        ("5", "Diagnostic Lab"),
        ("6", "Diagnostic X-Ray"),
        ("50", "Hospital - Outpatient"),
        ("73", "Preventive"),
        ("AE", "Physical Medicine"),
        ("AI", "DME - Durable Medical Equipment"),
        ("89", "Free Standing Prescription Drug"),
    ],
    "pediatrics": [
        ("30", "Health Benefit Plan Coverage"),
        ("1", "Medical Care"),
        ("98", "Professional (Physician) Visit - Office"),
        ("73", "Preventive"),
        ("A8", "Immunizations"),
        ("5", "Diagnostic Lab"),
        ("6", "Diagnostic X-Ray"),
        ("50", "Hospital - Outpatient"),
        ("48", "Hospital - Inpatient"),
        ("AL", "Vision (Optometry)"),
        ("MH", "Mental Health"),
        ("86", "Emergency Services"),
    ],
    "clinical_laboratory": [
        ("30", "Health Benefit Plan Coverage"),
        ("5", "Diagnostic Lab"),
        ("1", "Medical Care"),
        ("98", "Professional (Physician) Visit - Office"),
        ("73", "Preventive"),
        ("50", "Hospital - Outpatient"),
        ("6", "Diagnostic X-Ray"),
        ("86", "Emergency Services"),
        ("48", "Hospital - Inpatient"),
        ("BG", "MRI/CAT Scan"),
        ("AE", "Physical Medicine"),
        ("UC", "Urgent Care"),
    ],
}

# Pre-auth service descriptions keyed by practice type
PREAUTH_SERVICES = {
    "primary_care": ["Specialist Referral", "Advanced Imaging (MRI/CT)"],
    "internal_medicine": ["Hospital Admission", "Advanced Imaging (MRI/CT)", "Cardiac Stress Testing"],
    "allergy_immunology": ["Rapid Desensitization", "Allergen Immunotherapy Series"],
    "orthopaedics": ["Total Joint Arthroplasty", "Arthroscopic Surgery", "MRI"],
    "cardiology": ["Cardiac Catheterization", "Coronary Stent Placement", "CABG Surgery"],
    "behavioral_health": ["Inpatient Psychiatric Admission", "Intensive Outpatient Program", "Psychological Testing"],
    "radiology": ["MRI with Contrast", "CT Angiography", "PET Scan"],
    "pathology": ["Genetic Testing", "Specialized Immunohistochemistry Panel"],
    "gastroenterology": ["Colonoscopy with Intervention", "Endoscopic Retrograde Cholangiopancreatography"],
    "ob_gyn": ["Cesarean Delivery", "Hysteroscopy", "Genetic Screening"],
    "dermatology": ["Mohs Micrographic Surgery", "Phototherapy Series", "Biologic Therapy"],
    "anesthesiology": ["Epidural Steroid Injection Series", "Nerve Block Series", "Pain Pump Implant"],
    "urgent_care": ["Advanced Imaging", "Specialist Referral", "Wound Repair > 7.5cm"],
    "pediatrics": ["Developmental Assessment", "Specialist Referral", "Advanced Imaging"],
    "clinical_laboratory": ["Genetic Testing", "Specialized Pathology Panel", "Flow Cytometry"],
}

# Plan names for variety in responses
PLAN_NAMES = [
    "Gold PPO 1000", "Silver HMO 2500", "Platinum PPO 500", "Bronze HDHP 5000",
    "Premier Choice PPO", "Essential Care HMO", "Advantage Plus PPO",
    "Value Select HMO", "Comprehensive PPO 1500", "Basic HDHP 6000",
    "Standard PPO 2000", "Freedom Select PPO",
]


# ============================================================
# EDI 270 BUILDER - Eligibility Inquiry
# ============================================================

def build_270(isa_control, gs_control, st_control, patient, provider, payer,
              practice_type, dos_date, service_type_codes):
    """
    Build a complete EDI 270 (Health Care Eligibility Benefit Inquiry)
    transaction.
    """
    segments = []
    date_str, time_str = format_datetime_edi(dos_date)
    today = datetime.now()
    today_date = format_date_edi(today)
    today_time = today.strftime("%H%M")

    # --- ISA - Interchange Control Header ---
    segments.append(
        f"ISA*00*          *00*          *ZZ*{provider['npi']:<15s}"
        f"*ZZ*{payer['payer_id']:<15s}"
        f"*{today.strftime('%y%m%d')}*{today_time}*^*00501*{isa_control:>09s}*0*P*:~"
    )

    # --- GS - Functional Group Header ---
    segments.append(
        f"GS*HS*{provider['npi']}*{payer['payer_id']}"
        f"*{today_date}*{today_time}*{gs_control}*X*005010X279A1~"
    )

    # --- ST - Transaction Set Header ---
    segments.append(f"ST*270*{st_control}*005010X279A1~")

    # --- BHT - Beginning of Hierarchical Transaction ---
    segments.append(
        f"BHT*0022*13*{st_control}*{today_date}*{today_time}~"
    )

    seg_count = 4  # ISA, GS, ST, BHT

    # --- HL - Information Source (Payer) - Level 1 ---
    segments.append("HL*1**20*1~")
    seg_count += 1

    # --- NM1 - Payer Name ---
    payer_name_clean = payer["name"].replace(" ", " ")
    segments.append(
        f"NM1*PR*2*{payer_name_clean}*****PI*{payer['payer_id']}~"
    )
    seg_count += 1

    # --- HL - Information Receiver (Provider) - Level 2 ---
    segments.append("HL*2*1*21*1~")
    seg_count += 1

    # --- NM1 - Provider Name (1P = Provider) ---
    segments.append(
        f"NM1*1P*1*{provider['last']}*{provider['first']}****XX*{provider['npi']}~"
    )
    seg_count += 1

    # --- REF - Provider Additional ID ---
    segments.append(f"REF*4A*{provider['taxonomy']}~")
    seg_count += 1

    # --- N3/N4 - Provider Address ---
    city_st_zip = random.choice(CITIES_STATES_ZIPS)
    segments.append(f"N3*{random.randint(100,9999)} Medical Center Dr~")
    segments.append(f"N4*{city_st_zip[0]}*{city_st_zip[1]}*{city_st_zip[2]}~")
    seg_count += 2

    # --- PRV - Provider Information ---
    segments.append(f"PRV*PE*PXC*{provider['taxonomy']}~")
    seg_count += 1

    # --- HL - Subscriber - Level 3 ---
    segments.append("HL*3*2*22*0~")
    seg_count += 1

    # --- TRN - Subscriber Trace Number ---
    trace_num = f"1{provider['npi']}{st_control}"
    segments.append(f"TRN*1*{trace_num}*{provider['npi']}~")
    seg_count += 1

    # --- NM1 - Subscriber/Patient Name (IL = Insured or Subscriber) ---
    gender_code = patient["gender"]
    segments.append(
        f"NM1*IL*1*{patient['last']}*{patient['first']}****MI*{patient['member_id']}~"
    )
    seg_count += 1

    # --- REF - Subscriber Additional ID ---
    segments.append(f"REF*6P*{patient['patient_id']}~")
    seg_count += 1

    # --- N3/N4 - Subscriber Address ---
    segments.append(f"N3*{patient['street']}~")
    segments.append(f"N4*{patient['city']}*{patient['state']}*{patient['zip']}~")
    seg_count += 2

    # --- DMG - Subscriber Demographics ---
    segments.append(f"DMG*D8*{patient['dob']}*{patient['gender']}~")
    seg_count += 1

    # --- DTP - Date of Service ---
    segments.append(f"DTP*291*D8*{date_str}~")
    seg_count += 1

    # --- EQ - Eligibility/Benefit Inquiry ---
    # Include multiple service type inquiries relevant to the specialty
    for stc_code, stc_desc in service_type_codes[:4]:
        segments.append(f"EQ*{stc_code}~")
        seg_count += 1

    # --- SE - Transaction Set Trailer ---
    se_count = seg_count + 1  # include the SE segment itself
    segments.append(f"SE*{se_count}*{st_control}~")

    # --- GE - Functional Group Trailer ---
    segments.append(f"GE*1*{gs_control}~")

    # --- IEA - Interchange Control Trailer ---
    segments.append(f"IEA*1*{isa_control:>09s}~")

    return "\n".join(segments)


# ============================================================
# EDI 271 BUILDER - Eligibility Response
# ============================================================

def build_271(isa_control, gs_control, st_control, patient, provider, payer,
              practice_type, dos_date, scenario, file_idx, seed):
    """
    Build a complete EDI 271 (Health Care Eligibility Benefit Response)
    transaction. The content varies by scenario bucket.
    """
    random.seed(seed + 5000)

    segments = []
    date_str, time_str = format_datetime_edi(dos_date)
    today = datetime.now()
    today_date = format_date_edi(today)
    today_time = today.strftime("%H%M")

    plan_name = random.choice(PLAN_NAMES)
    group_number = f"GRP{random.randint(100000, 999999)}"

    # Coverage date range
    eff_start = datetime(dos_date.year - random.randint(1, 5), 1, 1)
    eff_start_str = format_date_edi(eff_start)
    eff_end_str = format_date_edi(datetime(dos_date.year, 12, 31))

    stc_list = SPECIALTY_SERVICE_TYPE_CODES.get(
        practice_type,
        SPECIALTY_SERVICE_TYPE_CODES["primary_care"]
    )

    preauth_list = PREAUTH_SERVICES.get(
        practice_type,
        PREAUTH_SERVICES["primary_care"]
    )

    # Determine scenario parameters
    is_active = scenario in ("standard", "preauth", "high_deductible")
    is_in_network = scenario in ("standard", "preauth", "high_deductible")
    needs_preauth = scenario == "preauth"
    is_high_deductible = scenario == "high_deductible"
    is_problem = scenario == "problem"

    # For problem scenarios, randomly pick a sub-type
    problem_type = None
    if is_problem:
        problem_type = random.choice([
            "inactive", "out_of_network", "member_not_found", "terminated"
        ])
        if problem_type in ("inactive", "terminated"):
            is_active = False
        elif problem_type == "out_of_network":
            is_active = True
            is_in_network = False
        else:
            is_active = False

    # Dollar amounts
    if is_high_deductible:
        deductible_ind = random_amount(5000.00, 8000.00)
        deductible_fam = deductible_ind * 2
        oop_max_ind = random_amount(12000.00, 16000.00)
        oop_max_fam = oop_max_ind * 2
        copay = random_amount(50.00, 80.00)
        coinsurance_pct = random.choice([30, 40, 50])
        deductible_remaining = random_amount(deductible_ind * 0.5, deductible_ind)
        oop_remaining = random_amount(oop_max_ind * 0.6, oop_max_ind)
    else:
        deductible_ind = random_amount(500.00, 2500.00)
        deductible_fam = deductible_ind * 2
        oop_max_ind = random_amount(5000.00, 8000.00)
        oop_max_fam = oop_max_ind * 2
        copay = random_amount(15.00, 45.00)
        coinsurance_pct = random.choice([10, 15, 20, 25])
        deductible_remaining = random_amount(0.00, deductible_ind)
        oop_remaining = random_amount(deductible_ind, oop_max_ind)

    # --- ISA ---
    segments.append(
        f"ISA*00*          *00*          *ZZ*{payer['payer_id']:<15s}"
        f"*ZZ*{provider['npi']:<15s}"
        f"*{today.strftime('%y%m%d')}*{today_time}*^*00501*{isa_control:>09s}*0*P*:~"
    )

    # --- GS ---
    segments.append(
        f"GS*HB*{payer['payer_id']}*{provider['npi']}"
        f"*{today_date}*{today_time}*{gs_control}*X*005010X279A1~"
    )

    # --- ST ---
    segments.append(f"ST*271*{st_control}*005010X279A1~")

    # --- BHT ---
    segments.append(
        f"BHT*0022*11*{st_control}*{today_date}*{today_time}~"
    )

    seg_count = 4  # ISA, GS, ST, BHT

    # --- HL 1 - Information Source (Payer) ---
    segments.append("HL*1**20*1~")
    seg_count += 1

    # --- NM1 - Payer ---
    segments.append(
        f"NM1*PR*2*{payer['name']}*****PI*{payer['payer_id']}~"
    )
    seg_count += 1

    # --- PER - Payer Contact ---
    payer_phone = f"{random.randint(800,888)}{random.randint(200,999)}{random.randint(1000,9999)}"
    segments.append(
        f"PER*IC*CUSTOMER SERVICE*TE*{payer_phone}*UR*www.{payer['name'].lower().replace(' ', '')}provider.com~"
    )
    seg_count += 1

    # --- HL 2 - Information Receiver (Provider) ---
    segments.append("HL*2*1*21*1~")
    seg_count += 1

    # --- NM1 - Provider ---
    segments.append(
        f"NM1*1P*1*{provider['last']}*{provider['first']}****XX*{provider['npi']}~"
    )
    seg_count += 1

    # --- REF - Provider Enrollment Status ---
    if is_in_network:
        segments.append(f"REF*EO*ACTIVE~")
    else:
        segments.append(f"REF*EO*NOT_CONTRACTED~")
    seg_count += 1

    # --- N3/N4 - Provider Address ---
    prov_city, prov_state, prov_zip = random.choice(CITIES_STATES_ZIPS)
    segments.append(f"N3*{random.randint(100,9999)} Medical Center Dr~")
    segments.append(f"N4*{prov_city}*{prov_state}*{prov_zip}~")
    seg_count += 2

    # --- HL 3 - Subscriber ---
    segments.append("HL*3*2*22*0~")
    seg_count += 1

    # --- TRN - Trace ---
    trace_num = f"2{payer['payer_id']}{st_control}"
    segments.append(f"TRN*2*{trace_num}*{payer['payer_id']}~")
    seg_count += 1

    # --- NM1 - Subscriber ---
    segments.append(
        f"NM1*IL*1*{patient['last']}*{patient['first']}****MI*{patient['member_id']}~"
    )
    seg_count += 1

    # --- N3/N4 - Subscriber Address ---
    segments.append(f"N3*{patient['street']}~")
    segments.append(f"N4*{patient['city']}*{patient['state']}*{patient['zip']}~")
    seg_count += 2

    # --- DMG - Demographics ---
    segments.append(f"DMG*D8*{patient['dob']}*{patient['gender']}~")
    seg_count += 1

    # --- INS - Subscriber Information ---
    relationship = "18"  # Self
    ins_status = "Y" if is_active else "N"
    segments.append(f"INS*{ins_status}*{relationship}*001*25~")
    seg_count += 1

    # --- DTP - Plan Dates ---
    if is_active:
        segments.append(f"DTP*346*RD8*{eff_start_str}-{eff_end_str}~")
        seg_count += 1
    elif problem_type == "terminated":
        term_date = dos_date - timedelta(days=random.randint(30, 180))
        segments.append(f"DTP*346*RD8*{eff_start_str}-{format_date_edi(term_date)}~")
        seg_count += 1
        segments.append(f"DTP*347*D8*{format_date_edi(term_date)}~")
        seg_count += 1
    elif problem_type == "inactive":
        segments.append(f"DTP*346*RD8*{eff_start_str}-{format_date_edi(eff_start + timedelta(days=365))}~")
        seg_count += 1

    # ================================================================
    # EB SEGMENTS - The core eligibility/benefit information
    # ================================================================

    if is_problem and problem_type == "member_not_found":
        # --- AAA - Request Validation Error ---
        segments.append("AAA*N**72*N~")
        seg_count += 1
        segments.append("MSG*Patient not found in payer system. Verify member ID and date of birth.~")
        seg_count += 1
    elif is_problem and problem_type in ("inactive", "terminated"):
        # EB*6 = Inactive coverage
        segments.append("EB*6*IND***30~")
        seg_count += 1
        segments.append(f"MSG*Coverage {problem_type} as of service date. Member had {plan_name} group {group_number}.~")
        seg_count += 1

        # Still provide the plan info for reference
        segments.append(f"EB*D*IND***30****{plan_name}~")
        seg_count += 1
        segments.append(f"REF*18*{group_number}~")
        seg_count += 1

        if problem_type == "terminated":
            segments.append(
                f"MSG*Coverage terminated. Contact member to obtain updated insurance information. "
                f"COBRA eligibility may apply.~"
            )
            seg_count += 1
        else:
            segments.append(
                f"MSG*Coverage inactive. No active enrollment found for date of service {date_str}. "
                f"Verify eligibility dates with member.~"
            )
            seg_count += 1

    elif is_problem and problem_type == "out_of_network":
        # Active coverage but out-of-network
        segments.append(f"EB*1*IND***30**{plan_name}~")
        seg_count += 1

        # Plan description
        segments.append(f"EB*D*IND***30****{plan_name}~")
        seg_count += 1
        segments.append(f"REF*18*{group_number}~")
        seg_count += 1

        # DTP for eligibility dates
        segments.append(f"DTP*291*RD8*{eff_start_str}-{eff_end_str}~")
        seg_count += 1

        # Out-of-network deductible (higher)
        oon_deductible = deductible_ind * 2
        oon_oop = oop_max_ind * 2
        oon_coinsurance = min(coinsurance_pct * 2, 50)
        oon_copay = copay * 2

        segments.append(f"EB*C*IND*30**DED*****{oon_deductible:.2f}~")
        seg_count += 1
        segments.append("MSG*Out-of-Network Individual Deductible~")
        seg_count += 1

        segments.append(f"EB*C*FAM*30**DED*****{oon_deductible * 2:.2f}~")
        seg_count += 1
        segments.append("MSG*Out-of-Network Family Deductible~")
        seg_count += 1

        segments.append(f"EB*A*IND*30**COINSURANCE*****{oon_coinsurance}~")
        seg_count += 1
        segments.append("MSG*Out-of-Network Coinsurance Percentage - Member Responsibility~")
        seg_count += 1

        segments.append(f"EB*B*IND*30**COPAY*****{oon_copay:.2f}~")
        seg_count += 1
        segments.append("MSG*Out-of-Network Office Visit Copay~")
        seg_count += 1

        segments.append(f"EB*G*IND*30**OOP_MAX*****{oon_oop:.2f}~")
        seg_count += 1
        segments.append("MSG*Out-of-Network Individual Out-of-Pocket Maximum~")
        seg_count += 1

        # Provider network status
        segments.append(f"REF*EO*NOT_CONTRACTED~")
        seg_count += 1
        segments.append(
            f"MSG*Provider NPI {provider['npi']} is not in-network for {payer['name']} {plan_name}. "
            f"Out-of-network benefits apply. Balance billing may apply.~"
        )
        seg_count += 1

        # Specialty services
        for stc_code, stc_desc in stc_list[:3]:
            if stc_code != "30":
                segments.append(f"EB*1*IND*{stc_code}~")
                seg_count += 1
                segments.append(f"EB*A*IND*{stc_code}**COINSURANCE*****{oon_coinsurance}~")
                seg_count += 1
                segments.append(f"MSG*{stc_desc} - Out-of-Network benefits, subject to deductible~")
                seg_count += 1

    else:
        # --- ACTIVE COVERAGE SCENARIOS (standard, preauth, high_deductible) ---

        # EB*1 = Active Coverage
        segments.append(f"EB*1*IND***30**{plan_name}~")
        seg_count += 1

        # Plan description
        segments.append(f"EB*D*IND***30****{plan_name}~")
        seg_count += 1

        # Group/Plan reference
        segments.append(f"REF*18*{group_number}~")
        seg_count += 1

        # Eligibility dates
        segments.append(f"DTP*291*RD8*{eff_start_str}-{eff_end_str}~")
        seg_count += 1

        # --- In-Network Deductible ---
        segments.append(f"EB*C*IND*30**DED*****{deductible_ind:.2f}~")
        seg_count += 1
        segments.append("MSG*In-Network Individual Deductible~")
        seg_count += 1

        segments.append(f"EB*C*FAM*30**DED*****{deductible_fam:.2f}~")
        seg_count += 1
        segments.append("MSG*In-Network Family Deductible~")
        seg_count += 1

        # Deductible remaining
        segments.append(f"EB*C*IND*30**DED_REMAINING*****{deductible_remaining:.2f}~")
        seg_count += 1
        segments.append("MSG*In-Network Individual Deductible Remaining~")
        seg_count += 1

        # --- Copay ---
        segments.append(f"EB*B*IND*30**COPAY*****{copay:.2f}~")
        seg_count += 1
        segments.append("MSG*In-Network Office Visit Copay~")
        seg_count += 1

        # Specialist copay (higher)
        specialist_copay = copay + random_amount(10.00, 30.00)
        segments.append(f"EB*B*IND*1**COPAY*****{specialist_copay:.2f}~")
        seg_count += 1
        segments.append("MSG*In-Network Specialist Visit Copay~")
        seg_count += 1

        # --- Coinsurance ---
        segments.append(f"EB*A*IND*30**COINSURANCE*****{coinsurance_pct}~")
        seg_count += 1
        segments.append("MSG*In-Network Coinsurance Percentage After Deductible~")
        seg_count += 1

        # --- Out-of-Pocket Maximum ---
        segments.append(f"EB*G*IND*30**OOP_MAX*****{oop_max_ind:.2f}~")
        seg_count += 1
        segments.append("MSG*In-Network Individual Out-of-Pocket Maximum~")
        seg_count += 1

        segments.append(f"EB*G*FAM*30**OOP_MAX*****{oop_max_fam:.2f}~")
        seg_count += 1
        segments.append("MSG*In-Network Family Out-of-Pocket Maximum~")
        seg_count += 1

        # OOP remaining
        segments.append(f"EB*G*IND*30**OOP_REMAINING*****{oop_remaining:.2f}~")
        seg_count += 1
        segments.append("MSG*In-Network Individual Out-of-Pocket Remaining~")
        seg_count += 1

        # --- Provider In-Network Status ---
        segments.append(f"REF*EO*ACTIVE~")
        seg_count += 1
        segments.append(
            f"MSG*Provider NPI {provider['npi']} is in-network and actively enrolled with "
            f"{payer['name']} {plan_name}. In-network benefits apply.~"
        )
        seg_count += 1

        # --- Specialty-Specific Covered Services ---
        num_services = random.randint(3, 5)
        for stc_code, stc_desc in stc_list[:num_services]:
            if stc_code == "30":
                continue  # already covered above
            segments.append(f"EB*1*IND*{stc_code}~")
            seg_count += 1

            # Service-level copay or coinsurance
            if stc_code in ("98", "1", "UC"):
                segments.append(f"EB*B*IND*{stc_code}**COPAY*****{copay:.2f}~")
                seg_count += 1
            elif stc_code in ("48", "BN"):
                hosp_coins = coinsurance_pct
                segments.append(f"EB*A*IND*{stc_code}**COINSURANCE*****{hosp_coins}~")
                seg_count += 1
                segments.append(f"MSG*{stc_desc} subject to deductible then {hosp_coins}% coinsurance~")
                seg_count += 1
            elif stc_code in ("5", "6", "BG"):
                lab_copay = random_amount(0.00, 20.00)
                segments.append(f"EB*B*IND*{stc_code}**COPAY*****{lab_copay:.2f}~")
                seg_count += 1
            elif stc_code in ("MH", "A4"):
                mh_copay = random_amount(20.00, 50.00)
                segments.append(f"EB*B*IND*{stc_code}**COPAY*****{mh_copay:.2f}~")
                seg_count += 1
                segments.append(f"MSG*{stc_desc} - visit limit may apply, see plan documents~")
                seg_count += 1
            else:
                segments.append(f"EB*A*IND*{stc_code}**COINSURANCE*****{coinsurance_pct}~")
                seg_count += 1

            segments.append(f"MSG*{stc_desc} - In-Network benefit covered~")
            seg_count += 1

        # --- Pre-Authorization Requirements ---
        if needs_preauth:
            segments.append("EB*CB*IND***30~")
            seg_count += 1
            segments.append(
                f"MSG*Pre-authorization/pre-certification required for select services. "
                f"Contact {payer['name']} Utilization Management.~"
            )
            seg_count += 1

            for svc in preauth_list:
                segments.append(f"EB*CB*IND***30~")
                seg_count += 1
                segments.append(
                    f"MSG*PRE-AUTH REQUIRED: {svc}. Failure to obtain authorization "
                    f"may result in reduced or denied benefits.~"
                )
                seg_count += 1

            # Add auth contact info
            auth_phone = f"{random.randint(800,888)}{random.randint(200,999)}{random.randint(1000,9999)}"
            segments.append(
                f"MSG*Utilization Management Contact: {auth_phone}. "
                f"Auth requests may be submitted via provider portal.~"
            )
            seg_count += 1

        # --- High Deductible Notes ---
        if is_high_deductible:
            segments.append("EB*CB*IND***30~")
            seg_count += 1
            segments.append(
                f"MSG*HIGH DEDUCTIBLE HEALTH PLAN: Individual deductible of "
                f"${deductible_ind:.2f} must be met before plan pays. "
                f"Preventive services covered at 100%. "
                f"Remaining deductible: ${deductible_remaining:.2f}.~"
            )
            seg_count += 1

            # Limited benefits note
            segments.append(
                f"MSG*BENEFIT LIMITATION: After deductible, plan pays "
                f"{100 - coinsurance_pct}% for in-network services. "
                f"Member responsible for {coinsurance_pct}% coinsurance up to OOP max.~"
            )
            seg_count += 1

            # HSA note for HDHP
            if "HDHP" in plan_name or is_high_deductible:
                segments.append(
                    f"MSG*This plan is HSA-eligible. Member may have HSA funds available "
                    f"for qualified medical expenses.~"
                )
                seg_count += 1

    # --- Final summary MSG ---
    segments.append(
        f"MSG*Eligibility response for {patient['first']} {patient['last']} "
        f"DOB {patient['dob']} as of {date_str}. "
        f"Verify benefits for specific services. This is not a guarantee of payment.~"
    )
    seg_count += 1

    # --- SE ---
    se_count = seg_count + 1
    segments.append(f"SE*{se_count}*{st_control}~")

    # --- GE ---
    segments.append(f"GE*1*{gs_control}~")

    # --- IEA ---
    segments.append(f"IEA*1*{isa_control:>09s}~")

    return "\n".join(segments)


# ============================================================
# FILE ASSEMBLY - Pair 270 + 271 into one .edi
# ============================================================

def build_edi_file(practice_type, practice_idx, file_idx, seed):
    """
    Assemble a complete .edi file containing the 270 inquiry and 271
    response for a single patient encounter.
    """
    random.seed(seed)

    # Determine scenario bucket
    if 1 <= file_idx <= 4:
        scenario = "standard"
    elif 5 <= file_idx <= 8:
        scenario = "preauth"
    elif 9 <= file_idx <= 10:
        scenario = "high_deductible"
    else:
        scenario = "problem"

    # Generate entities
    patient = get_random_patient(seed)
    provider = get_random_provider(practice_type, seed + 100)
    payer = get_random_payer(seed + 200)

    # Date of service
    dos = get_random_date(start_days_ago=180, end_days_ago=1, seed=seed + 300)

    # Control numbers
    isa_270 = f"{practice_idx * 1000 + file_idx:09d}"
    gs_270 = f"{practice_idx * 1000 + file_idx}"
    st_270 = f"{practice_idx:02d}{file_idx:03d}0"

    isa_271 = f"{practice_idx * 1000 + file_idx + 500:09d}"
    gs_271 = f"{practice_idx * 1000 + file_idx + 500}"
    st_271 = f"{practice_idx:02d}{file_idx:03d}1"

    # Service type codes
    stc_list = SPECIALTY_SERVICE_TYPE_CODES.get(
        practice_type,
        SPECIALTY_SERVICE_TYPE_CODES["primary_care"]
    )

    # Build 270
    edi_270 = build_270(
        isa_control=isa_270,
        gs_control=gs_270,
        st_control=st_270,
        patient=patient,
        provider=provider,
        payer=payer,
        practice_type=practice_type,
        dos_date=dos,
        service_type_codes=stc_list,
    )

    # Build 271
    edi_271 = build_271(
        isa_control=isa_271,
        gs_control=gs_271,
        st_control=st_271,
        patient=patient,
        provider=provider,
        payer=payer,
        practice_type=practice_type,
        dos_date=dos,
        scenario=scenario,
        file_idx=file_idx,
        seed=seed,
    )

    # Assemble file with delimiter between 270 and 271
    delimiter = (
        "\n"
        "=" * 78 + "\n"
        "ELIGIBILITY INQUIRY / RESPONSE PAIR" + "\n"
        f"Practice Type : {PRACTICE_DISPLAY_NAMES.get(practice_type, practice_type)}" + "\n"
        f"Patient       : {patient['last']}, {patient['first']}" + "\n"
        f"Member ID     : {patient['member_id']}" + "\n"
        f"Provider      : {provider['full_name']} (NPI: {provider['npi']})" + "\n"
        f"Payer         : {payer['name']} ({payer['plan_type']})" + "\n"
        f"Date of Svc   : {format_date_edi(dos)}" + "\n"
        f"Scenario      : {scenario.upper().replace('_', ' ')}" + "\n"
        "=" * 78 + "\n"
    )

    header_270 = (
        "\n"
        "-" * 40 + "\n"
        "270 - ELIGIBILITY INQUIRY REQUEST" + "\n"
        "-" * 40 + "\n"
    )

    header_271 = (
        "\n"
        "-" * 40 + "\n"
        "271 - ELIGIBILITY BENEFIT RESPONSE" + "\n"
        "-" * 40 + "\n"
    )

    return delimiter + header_270 + edi_270 + "\n" + header_271 + edi_271 + "\n"


# ============================================================
# MAIN
# ============================================================

def main():
    """Generate 12 eligibility EDI files per practice type (180 total)."""
    base_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "test_data", "eligibility"
    )

    files_per_practice = 12
    total_files = 0
    seed_base = 270271  # thematic seed base

    print("=" * 65)
    print("EDI 270/271 Eligibility Test File Generator")
    print(f"Practice Types : {len(PRACTICE_TYPES)}")
    print(f"Files per Type : {files_per_practice}")
    print(f"Total Files    : {len(PRACTICE_TYPES) * files_per_practice}")
    print("=" * 65)

    for practice_idx, practice_type in enumerate(PRACTICE_TYPES):
        practice_dir = os.path.join(base_dir, practice_type)
        os.makedirs(practice_dir, exist_ok=True)

        display_name = PRACTICE_DISPLAY_NAMES.get(practice_type, practice_type)
        print(f"\n[{practice_idx + 1:>2}/{len(PRACTICE_TYPES)}] {display_name}")

        for file_idx in range(1, files_per_practice + 1):
            seed = seed_base + (practice_idx * 1000) + (file_idx * 7)

            edi_content = build_edi_file(
                practice_type=practice_type,
                practice_idx=practice_idx,
                file_idx=file_idx,
                seed=seed,
            )

            filename = f"elig_{practice_type}_{file_idx:03d}.edi"
            filepath = os.path.join(practice_dir, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(edi_content)

            # Scenario label for logging
            if 1 <= file_idx <= 4:
                scenario_label = "STANDARD"
            elif 5 <= file_idx <= 8:
                scenario_label = "PRE-AUTH"
            elif 9 <= file_idx <= 10:
                scenario_label = "HIGH DEDUCTIBLE"
            else:
                scenario_label = "COVERAGE ISSUE"

            print(f"    {filename}  [{scenario_label}]")
            total_files += 1

    print("\n" + "=" * 65)
    print(f"Generation complete. {total_files} files written.")
    print(f"Output directory: {base_dir}")
    print("=" * 65)


if __name__ == "__main__":
    main()
