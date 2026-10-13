import pandas as pd
from app.core.database import SessionLocal
from app.models.models import Variedad

db = SessionLocal()
vars_db = db.query(Variedad).all()
db_map = {v.nombre.strip().lower(): {'flor': v.flor.strip(), 'color': v.color.strip()} for v in vars_db}
print(f"Total varieties in master DB: {len(db_map)}")

files_to_check = [
    ('Plan_Aprobado.csv', 'Variedad', 'Flor', 'Color'),
    ('Siembra Actual (16).xlsx', 'Variedad', 'Flor', 'Color'),
    ('PedidoConsolidado_master.xlsx', 'Variedad', 'Flor', 'Color'),
]

for fname, var_col, flor_col, color_col in files_to_check:
    try:
        if fname.endswith('.csv'):
            df = pd.read_csv(fname)
        else:
            df = pd.read_excel(fname)
            
        cols_lower = {str(c).strip().lower(): c for c in df.columns}
        v_c = cols_lower.get(var_col.lower())
        f_c = cols_lower.get(flor_col.lower()) or cols_lower.get('flower')
        c_c = cols_lower.get(color_col.lower())
        
        if not v_c:
            print(f"{fname}: column {var_col} not found")
            continue
            
        discrepancies = []
        not_in_db = []
        
        cols_sub = [v_c]
        if f_c: cols_sub.append(f_c)
        if c_c: cols_sub.append(c_c)
        
        df_unique = df[cols_sub].drop_duplicates().dropna(subset=[v_c])
        
        for _, row in df_unique.iterrows():
            v_name = str(row[v_c]).strip()
            v_norm = v_name.lower()
            f_val = str(row[f_c]).strip() if f_c and pd.notna(row[f_c]) else None
            c_val = str(row[c_c]).strip() if c_c and pd.notna(row[c_c]) else None
            
            if v_norm not in db_map:
                not_in_db.append(v_name)
            else:
                db_f = db_map[v_norm]['flor']
                db_c = db_map[v_norm]['color']
                
                f_mismatch = f_val and f_val.lower() != db_f.lower()
                c_mismatch = c_val and c_val.lower() != db_c.lower()
                
                if f_mismatch or c_mismatch:
                    discrepancies.append({
                        'Variedad': v_name,
                        'File_Flor': f_val,
                        'DB_Flor': db_f,
                        'File_Color': c_val,
                        'DB_Color': db_c
                    })
                    
        print(f"\n=== {fname} ===")
        print(f"Total unique varieties checked: {len(df_unique)}")
        print(f"Varieties not in DB: {len(not_in_db)} -> {not_in_db[:5]}")
        print(f"Discrepancies found with DB: {len(discrepancies)}")
        if discrepancies:
            print("Sample discrepancies:")
            for d in discrepancies[:10]:
                print(f"  {d['Variedad']}: File=[{d['File_Flor']}, {d['File_Color']}] vs DB=[{d['DB_Flor']}, {d['DB_Color']}]")
    except Exception as e:
        print(f"Error reading {fname}: {e}")

