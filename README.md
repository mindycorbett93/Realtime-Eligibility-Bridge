**Healthcare RCM:** Realtime Eligibility Bridge
**Technical Lead:** Melinda Corbett, CPSO, CPC, CPPM, CPB  
**Target Impact:** Realtime Eligibility Bridge

EDI 270/271 eligibility processor that parses eligibility inquiry and response transactions, extracts patient coverage data, and produces detailed eligibility reports across 16 medical practice types. Includes an integrated eligibility bridge engine prototype.

## Repository Structure

```
Realtime_Eligibility_Bridge/
├── realtime_eligibility.py               # Main entry point — 270/271 processing pipeline
├── Realtime_Integrated_Eligibility.py    # Engine prototype (eligibility bridge simulation)
└── generators/
    ├── generate_eligibility.py           # EDI 270/271 test data generator
    ├── excel_exporter.py                 # Summary/Details/Rollup Excel report builder
    ├── test_data_commons.py              # Shared data catalog (practice types, CPT codes, payers)
    └── __init__.py
```

## What It Does

1. **EDI 270/271 Parsing** — Reads EDI eligibility inquiry (270) and response (271) files with comprehensive DTP date segment handling (plan begin/end, benefit begin/end, eligibility, service dates).
2. **Patient Extraction** — Extracts demographics, payer/plan information, covered services, financial limits (copay, coinsurance, deductible, out-of-pocket), and pre-authorization requirements.
3. **Coverage Analysis** — Classifies coverage status (Active, Inactive, Pending), identifies service-specific limitations, and flags pre-auth requirements.
4. **Reporting** — Produces multi-format outputs:
   - **Details CSV** — Patient-level eligibility data with Payer_Name, Plan_Type, coverage dates, and financial details
   - **Summary CSV** — Practice-level aggregation (total patients, active %, payer distribution)
   - **Rollup CSV** — Payer-level aggregation across all practices
   - **Excel Workbook** — Summary (patient-level), Details, and Rollup tabs
   - **Dashboard JSON** + **Text Report** — Consolidated eligibility metrics

## Prerequisites

- Python 3.12+
- openpyxl (`pip install openpyxl`)

## Usage

```bash
# Generate test eligibility data (if needed)
python generators/generate_eligibility.py

# Run the full eligibility analysis
python realtime_eligibility.py

# Target a specific practice type
python realtime_eligibility.py --practice-type cardiology --verbose

# Custom input directory
python realtime_eligibility.py --input-dir test_data/eligibility
```

## Output

Results are written to `Results/Realtime_Eligibility/` with per-practice CSVs and consolidated reports:
- `{practice_type}_eligibility_details.csv`
- `eligibility_summary.csv`
- `eligibility_rollup.csv`
- `eligibility_report.xlsx`
- `eligibility_dashboard.json`
- `eligibility_report.txt`

## 🎓 About the Author
Melinda Corbett is an Executive Transformation Leader with 12+ years of experience in healthcare operations and AI-driven optimization.She specializes in translating complex aggregate platform data into board-level narratives.
