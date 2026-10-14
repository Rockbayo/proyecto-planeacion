import streamlit as st
import pandas as pd
from app.models.models import DistribucionMVA, Variedad
from sqlalchemy.orm import Session

def render_actas_module(db: Session):
    st.subheader("📄 Gestión MVA (Ajuste Manual)")
    st.markdown("""
    Edita la distribución MVA por temporada. Si no ingresas nada en 'Nuevo Porcentaje', se mantendrá el valor actual.
    Puedes agregar nuevas variedades al final de la tabla de cada temporada.
    """)
    
    finca_global = "CH"
    
    modo_edicion = st.toggle("Activar Modo Edición", key="modo_edicion_toggle")
    
    if modo_edicion:
        with st.expander("➕ Crear Nueva Variedad en el Catálogo"):
            with st.form("form_nueva_variedad", clear_on_submit=True):
                col1, col2, col3 = st.columns(3)
                nv_nombre = col1.text_input("Nombre de Variedad")
                nv_flor = col2.text_input("Flor (Ej: Cushion, Daisy)")
                nv_color = col3.text_input("Color (Ej: White, Yellow)")
                if st.form_submit_button("Guardar Nueva Variedad"):
                    if nv_nombre and nv_flor and nv_color:
                        existe = db.query(Variedad).filter(Variedad.nombre.ilike(nv_nombre)).first()
                        if existe:
                            st.warning("Esa variedad ya existe en el catálogo.")
                        else:
                            nueva = Variedad(nombre=nv_nombre, flor=nv_flor, color=nv_color, activo=True)
                            db.add(nueva)
                            db.commit()
                            st.success(f"Variedad '{nv_nombre}' agregada al catálogo. La página se recargará.")
                            st.rerun()
                    else:
                        st.error("Por favor completa todos los campos.")
    
    dist_records = db.query(DistribucionMVA).filter(DistribucionMVA.finca.in_([finca_global, "ALL"])).all()
    temporadas = sorted(list(set([r.temporada for r in dist_records])))
    if not temporadas:
        temporadas = ["EVERYDAY"]
        
    from app.models.models import FastTrackMVA
    ft_records = db.query(FastTrackMVA).filter(FastTrackMVA.finca.in_([finca_global, "ALL", "Todas las fincas"])).all()
        
    todas_variedades = db.query(Variedad).all()
    
    # Asegurar que los valores actuales en MVA o FT siempre estén en las listas para evitar que aparezcan vacíos
    flores_list = sorted(list(set(
        [str(v.flor).strip() for v in todas_variedades if v.flor] + 
        [str(r.flor).strip() for r in dist_records if r.flor] + 
        [str(r.flor).strip() for r in ft_records if r.flor]
    )))
    # Eliminar posibles vacíos de la lista
    flores_list = [x for x in flores_list if x]
    
    colores_list = sorted(list(set(
        [str(v.color).strip() for v in todas_variedades if v.color] + 
        [str(r.color).strip() for r in dist_records if r.color] + 
        [str(r.color).strip() for r in ft_records if r.color]
    )))
    colores_list = [x for x in colores_list if x]
    
    variedades_list = sorted(list(set(
        [str(v.nombre).strip() for v in todas_variedades if v.nombre] + 
        [str(r.variedad_nombre).strip() for r in dist_records if r.variedad_nombre] + 
        [str(r.variedad_nombre).strip() for r in ft_records if r.variedad_nombre]
    )))
    variedades_list = [x for x in variedades_list if x]
    
    if "mva_edits" not in st.session_state:
        st.session_state["mva_edits"] = {}
        
    tabs = st.tabs(temporadas)
    
    df_original_dict = {}
    
    for i, temp in enumerate(temporadas):
        with tabs[i]:
            temp_records = [r for r in dist_records if r.temporada == temp]
            df_temp = pd.DataFrame([{
                "Flor": str(r.flor).strip() if r.flor else None,
                "Color": str(r.color).strip() if r.color else None,
                "Variedad": str(r.variedad_nombre).strip() if r.variedad_nombre else None,
                "Porcentaje Actual (%)": round(r.porcentaje * 100, 2),
                "Nuevo Porcentaje (%)": None
            } for r in temp_records])
            
            if df_temp.empty:
                df_temp = pd.DataFrame(columns=["Flor", "Color", "Variedad", "Porcentaje Actual (%)", "Nuevo Porcentaje (%)"])
                
            df_original_dict[temp] = df_temp.copy()
                
            if modo_edicion:
                st.markdown(f"**Editando Temporada: {temp}**")
                edited_df = st.data_editor(
                    df_temp,
                    num_rows="dynamic",
                    key=f"editor_{temp}",
                    column_config={
                        "Flor": st.column_config.SelectboxColumn("Flor", options=flores_list, required=True),
                        "Color": st.column_config.SelectboxColumn("Color", options=colores_list, required=True),
                        "Variedad": st.column_config.SelectboxColumn("Variedad", options=variedades_list, required=True),
                        "Porcentaje Actual (%)": st.column_config.NumberColumn("Porcentaje Actual (%)", disabled=True),
                        "Nuevo Porcentaje (%)": st.column_config.NumberColumn("Nuevo Porcentaje (%)", min_value=0.0, max_value=100.0)
                    },
                    width='stretch'
                )
                st.session_state["mva_edits"][temp] = edited_df
            else:
                st.dataframe(df_temp.drop(columns=["Nuevo Porcentaje (%)"]), width='stretch')

    st.divider()
    st.markdown("### 🚀 Variedades en Fast Track")
    from app.models.models import FastTrackMVA
    
    ft_records = db.query(FastTrackMVA).filter(FastTrackMVA.finca.in_([finca_global, "ALL", "Todas las fincas"])).all()
    df_ft_original = pd.DataFrame([{
        "Flor": str(r.flor).strip() if r.flor else None,
        "Color": str(r.color).strip() if r.color else None,
        "Variedad": str(r.variedad_nombre).strip() if r.variedad_nombre else None,
        "Breeder": str(r.breeder).strip() if r.breeder else "",
        "Observaciones": str(r.observaciones).strip() if r.observaciones else ""
    } for r in ft_records])
    
    if df_ft_original.empty:
        df_ft_original = pd.DataFrame(columns=["Flor", "Color", "Variedad", "Breeder", "Observaciones"])
        
    if modo_edicion:
        edited_ft = st.data_editor(
            df_ft_original,
            num_rows="dynamic",
            key="editor_fasttrack",
            width='stretch',
            column_config={
                "Flor": st.column_config.SelectboxColumn("Flor", options=flores_list),
                "Color": st.column_config.SelectboxColumn("Color", options=colores_list),
                "Variedad": st.column_config.SelectboxColumn("Variedad", options=variedades_list, required=True),
                "Breeder": st.column_config.TextColumn("Breeder"),
                "Observaciones": st.column_config.TextColumn("Observaciones"),
            }
        )
        st.session_state["ft_edits"] = edited_ft
        
        if st.button("🗑️ Eliminar todos los registros Fast Track", type="secondary"):
            db.query(FastTrackMVA).filter(FastTrackMVA.finca.in_([finca_global, "ALL", "Todas las fincas"])).delete(synchronize_session=False)
            db.commit()
            st.success("Todos los registros de Fast Track han sido eliminados.")
            st.rerun()
            
    else:
        st.dataframe(df_ft_original, width='stretch')

    if modo_edicion:
        st.divider()
        if st.button("Verificar Cambios", type="primary"):
            st.session_state["show_mva_verification"] = True
            
    if st.session_state.get("show_mva_verification", False) and modo_edicion:
        st.markdown("### 🔍 Revisión de Cambios")
        
        cambios_detectados = False
        cambios_por_temporada = {}
        
        for temp in temporadas:
            df_edited = st.session_state["mva_edits"].get(temp)
            if df_edited is not None:
                df_orig = df_original_dict[temp]
                
                df_edited_clean = df_edited.copy()
                df_edited_clean["Nuevo Porcentaje (%)"] = df_edited_clean["Nuevo Porcentaje (%)"].fillna(df_edited_clean["Porcentaje Actual (%)"]).fillna(0)
                
                if not df_orig.empty:
                    df_comp = pd.merge(
                        df_orig[["Flor", "Color", "Variedad", "Porcentaje Actual (%)"]],
                        df_edited_clean[["Flor", "Color", "Variedad", "Nuevo Porcentaje (%)"]],
                        on=["Flor", "Color", "Variedad"],
                        how="outer"
                    ).fillna(0)
                else:
                    df_comp = df_edited_clean[["Flor", "Color", "Variedad", "Nuevo Porcentaje (%)"]].copy()
                    df_comp["Porcentaje Actual (%)"] = 0
                    
                df_comp = df_comp.rename(columns={
                    "Porcentaje Actual (%)": "_pct_num", 
                    "Nuevo Porcentaje (%)": "_pct_num_nuevo"
                })
                
                def get_status(row):
                    if row["_pct_num"] == 0 and row["_pct_num_nuevo"] > 0:
                        return "🟢 NUEVO"
                    elif row["_pct_num"] > 0 and row["_pct_num_nuevo"] == 0:
                        return "🔴 ELIMINADO"
                    elif row["_pct_num"] != row["_pct_num_nuevo"]:
                        return "🟡 CAMBIO"
                    return "⚪ IGUAL"
                    
                df_comp["Estado"] = df_comp.apply(get_status, axis=1)
                df_cambios = df_comp[df_comp["Estado"] != "⚪ IGUAL"]
                
                if not df_cambios.empty:
                    cambios_detectados = True
                    cambios_por_temporada[temp] = df_comp
                    
                    st.markdown(f"**Temporada {temp}:**")
                    df_display = df_cambios.sort_values(by="Estado").reset_index(drop=True)
                    df_display["Porcentaje Actual"] = df_display["_pct_num"].apply(lambda x: f"{x:.2f}%")
                    df_display["Porcentaje Nuevo"] = df_display["_pct_num_nuevo"].apply(lambda x: f"{x:.2f}%")
                    st.dataframe(df_display[["Flor", "Color", "Variedad", "Porcentaje Actual", "Porcentaje Nuevo", "Estado"]], width='stretch')
        
        # Check Fast Track changes
        if "ft_edits" in st.session_state:
            df_ft_edited = st.session_state["ft_edits"]
            if not df_ft_original.equals(df_ft_edited):
                cambios_detectados = True
                st.markdown("**Cambios detectados en Fast Track** (Se reemplazarán con la nueva tabla)")
                
        # Validar Sumas de Porcentaje
        errores_suma = False
        st.markdown("### 🧮 Validación de Porcentajes (Flor + Color)")
        
        for temp in temporadas:
            df_edited = st.session_state["mva_edits"].get(temp)
            if df_edited is not None:
                df_edited_clean = df_edited.copy()
                df_edited_clean["Nuevo Porcentaje (%)"] = pd.to_numeric(df_edited_clean["Nuevo Porcentaje (%)"].fillna(df_edited_clean["Porcentaje Actual (%)"]).fillna(0))
                
                if not df_edited_clean.empty:
                    resumen = df_edited_clean.groupby(["Flor", "Color"])["Nuevo Porcentaje (%)"].sum().reset_index()
                    resumen["Diferencia"] = round(abs(resumen["Nuevo Porcentaje (%)"] - 100.0), 2)
                    
                    errores_temp = resumen[resumen["Diferencia"] > 0.01] # Tolerancia pequeña por redondeos
                    
                    if not errores_temp.empty:
                        errores_suma = True
                        st.error(f"❌ **Error en la Temporada {temp}:** Existen colores cuya suma no es 100%.")
                        for _, err in errores_temp.iterrows():
                            st.write(f"  - **{err['Flor']} {err['Color']}**: Suma total = {err['Nuevo Porcentaje (%)']:.2f}%")
                    else:
                        st.success(f"✅ Temporada {temp}: Todas las agrupaciones suman 100%.")

        if cambios_detectados:
            if errores_suma:
                st.error("⚠️ No se puede aprobar la actualización hasta que todos los colores sumen exactamente 100%. Por favor corrige la tabla arriba y vuelve a Verificar Cambios.")
            else:
                col1, col2 = st.columns(2)
                if col1.button("✅ Aprobar y Actualizar Sistema", type="primary", use_container_width=True):
                    try:
                        for temp, df_comp in cambios_por_temporada.items():
                            db.query(DistribucionMVA).filter(
                                DistribucionMVA.temporada == temp,
                                DistribucionMVA.finca.in_([finca_global, "ALL"])
                            ).delete(synchronize_session=False)
                            
                            for _, row in df_comp[df_comp["_pct_num_nuevo"] > 0].iterrows():
                                new_mva = DistribucionMVA(
                                    finca=finca_global,
                                    temporada=temp,
                                    flor=row["Flor"],
                                    color=row["Color"],
                                    variedad_nombre=row["Variedad"],
                                    porcentaje=row["_pct_num_nuevo"] / 100.0
                                )
                                db.add(new_mva)
                                
                                v_db = db.query(Variedad).filter(Variedad.nombre == row["Variedad"]).first()
                                if not v_db:
                                    new_var = Variedad(
                                        nombre=row["Variedad"],
                                        flor=row["Flor"],
                                        color=row["Color"],
                                        activo=True
                                    )
                                    db.add(new_var)
                                    
                        # 2. Fast Track
                        if "ft_edits" in st.session_state:
                            df_ft_edited = st.session_state["ft_edits"]
                            db.query(FastTrackMVA).filter(FastTrackMVA.finca.in_([finca_global, "ALL", "Todas las fincas"])).delete(synchronize_session=False)
                            
                            for _, row in df_ft_edited.iterrows():
                                var_name = str(row.get("Variedad", "")).strip()
                                if var_name:
                                    new_ft = FastTrackMVA(
                                        finca=finca_global,
                                        flor=str(row.get("Flor", "")),
                                        color=str(row.get("Color", "")),
                                        variedad_nombre=var_name,
                                        breeder=str(row.get("Breeder", "")),
                                        observaciones=str(row.get("Observaciones", ""))
                                    )
                                    db.add(new_ft)
                                    
                                    v_db = db.query(Variedad).filter(Variedad.nombre == var_name).first()
                                    if not v_db:
                                        new_var = Variedad(
                                            nombre=var_name,
                                            flor=str(row.get("Flor", "")),
                                            color=str(row.get("Color", "")),
                                            activo=True
                                        )
                                        db.add(new_var)
                        
                        db.commit()
                        st.session_state["show_mva_verification"] = False
                        st.success("¡Base de datos actualizada correctamente!")
                        st.rerun()
                    except Exception as e:
                        db.rollback()
                        st.error(f"Error al actualizar la base de datos: {e}")
                
                if col2.button("❌ Cancelar", use_container_width=True):
                    st.session_state["show_mva_verification"] = False
                    st.rerun()
        else:
            st.info("No se detectaron cambios en ninguna temporada.")
