import pandas as pd
import pypdf
import os
import json

files_to_analyze = [
    "Acta Inv 2630.pdf",
    "CH-ValentinesDay-Easter2027-2026-C-20260826111645-51.xlsx",
    "PedidoConsolidado (1).xlsx",
    "Reporte_Camas_Piloto.xlsx",
    "Siembra Actual (16).xlsx",
    "Siembras_RPA_2.0.xlsm"
]

output = {}

for f in files_to_analyze:
    output[f] = {}
    if not os.path.exists(f):
        output[f] = "File not found"
        continue
        
    ext = os.path.splitext(f)[1].lower()
    
    if ext == '.pdf':
        try:
            reader = pypdf.PdfReader(f)
            text = ""
            for page in reader.pages[:3]: # First 3 pages
                text += page.extract_text() + "\n"
            output[f] = {"type": "PDF", "pages": len(reader.pages), "preview": text[:1000]}
        except Exception as e:
            output[f] = {"error": str(e)}
            
    elif ext in ['.xlsx', '.xlsm']:
        try:
            xl = pd.ExcelFile(f)
            sheets_info = {}
            for sheet in xl.sheet_names:
                df = xl.parse(sheet, nrows=5)
                # Keep only columns that have names
                columns = [str(c) for c in df.columns if not str(c).startswith("Unnamed:")]
                sheets_info[sheet] = {
                    "columns": columns,
                    "preview": df.to_dict(orient="records")[:2] if not df.empty else []
                }
            output[f] = {"type": "Excel", "sheets": sheets_info}
        except Exception as e:
            output[f] = {"error": str(e)}

with open("inputs_analysis.json", "w", encoding="utf-8") as out_f:
    json.dump(output, out_f, indent=4, default=str)

print("Analysis saved to inputs_analysis.json")

