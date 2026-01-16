ReadMe Summary: This enterprise module automates the extraction of patient insurance data from ANSI X12 271 response files. It adheres to the CMS 5010A1 standards for mandatory and situational segments, converting raw EDI data into the standardized Inquiry Data Extraction format used for operational reporting.
Key Features:
•	Hierarchical Parsing: Correctly attributes data across the 2000A (Source), 2000B (Receiver), and 2000C (Subscriber) loops.
•	Status Mapping: Translates AAA reject codes and EB status codes into full descriptions using your proprietary Status Descriptors.
•	Service Type Intelligence: Decodes EQ01 and EB03 codes to identify specific benefit categories (e.g., "Health Benefit Plan Coverage" vs "Urgent Care").
•	Automated Export: Generates a clean CSV output matching the requirements of your Inquiry Data Extraction mockup.[Eligibility Mapping.docx]
[271 Segment Table.docx](https://github.com/user-attachments/files/24683344/271.Segment.Table.docx)
