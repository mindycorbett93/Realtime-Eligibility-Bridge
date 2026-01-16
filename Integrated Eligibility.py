import pandas as pd
import logging
from datetime import datetime

class EligibilityInquiryEngine:
    def __init__(self, reference_file='status_descriptors.csv'):
        """
        Dynamically loads ALL descriptors from your uploaded GitHub CSV.
        """
        try:
            df = pd.read_csv(reference_file)
            # Create lookup dictionaries from your spreadsheet
            self.inq_map = dict(zip(df['Inquiry Status Code'].astype(str), df['Inquiry Details']))
            self.elig_map = dict(zip(df['Status Code'].astype(str), df['Status Description']))
            self.svc_map = dict(zip(df['Service Type Code'].astype(str), df['Service Type Description']))
            logging.info("Reference tables loaded successfully.")
        except Exception as e:
            logging.error(f"Mapping failed: Ensure {reference_file} is in the repo. {e}")

    def parse_raw_271(self, edi_content):
        """
        High-fidelity parser for ANSI X12 271 segments.
        """
        # Healthcare EDI segments are typically separated by '~' and elements by '*'
        segments = [seg.split('*') for seg in edi_content.split('~')]
        extraction_list = []
        
        # Temporary variables to hold loop data
        patient_data = {"L_Name": "", "F_Name": "", "AAA01": "Y", "AAA03": "", "EB01": "", "EB07": "0.00", "EQ01": ""}

        for seg in segments:
            tag = seg[0]
            
            # NM1 Segment: Patient/Subscriber Name
            if tag == 'NM1' and seg[1] == 'IL':
                patient_data["L_Name"] = seg[3]
                patient_data["F_Name"] = seg[4] if len(seg) > 4 else ""

            # AAA Segment: Reject Reason (Situational)
            elif tag == 'AAA':
                patient_data["AAA01"] = seg[1] # Valid Request Indicator (Y/N)
                patient_data["AAA03"] = seg[3] # Reject Reason Code

            # EB Segment: Eligibility/Benefit (Required)
            elif tag == 'EB':
                patient_data["EB01"] = seg[1] # Status Code (1, 6, I, etc.)
                patient_data["EB03"] = seg[3] # Service Type Code
                patient_data["EB07"] = seg[7] if len(seg) > 7 else "0.00" # Benefit Amount

            # SE Segment: End of Transaction
            elif tag == 'SE':
                # Map extracted codes to descriptions using the CSV lookup
                row = {
                    "Patient Last Name": patient_data["L_Name"],
                    "Patient First Name": patient_data["F_Name"],
                    "Inquiry Date": datetime.now().strftime("%m/%d/%Y"),
                    "271 Status": "Verified" if patient_data["AAA01"] == 'Y' else "Not Verified",
                    "271 Details": self.inq_map.get(str(patient_data["AAA03"]), "Validated"),
                    "Eligibility Status": self.elig_map.get(str(patient_data["EB01"]), "See Raw 271"),
                    "Patient Responsibility": patient_data["EB07"],
                    "Service Type": self.svc_map.get(str(patient_data["EB03"]), "General")
                }
                extraction_list.append(row)
        
        return pd.DataFrame(extraction_list)

# --- DEMONSTRATION ---
# This EDI string mimics the '271 Elig Resp Example.pdf'
raw_edi = "ISA*00*...~NM1*IL*1*SMITH*JOHN~AAA*N**75~EB*6**30~SE*10*0001~"
engine = EligibilityInquiryEngine()
final_report = engine.parse_raw_271(raw_edi)
print(final_report.to_string())