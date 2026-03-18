import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from fpdf import FPDF
from datetime import datetime

# ==========================================
# CONFIGURACIÓN DE PÁGINA
# ==========================================
st.set_page_config(page_title="Generador de Reportes de Producción", layout="centered")
st.title("📊 Generador de Reporte Ejecutivo (PDF)")

# ==========================================
# 1. FUENTE DE DATOS FIJA
# ==========================================
SHEET_ID = "1TdQ3yNxx29SgQ7u8oexxlnL80rAcXQuP118wQVBd9ew"
GID = "315437448"
url_csv = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

@st.cache_data(ttl=600)
def cargar_datos(url):
    return pd.read_csv(url)

try:
    st.info("Obteniendo datos de producción desde Google Sheets...")
    df_raw = cargar_datos(url_csv)
    
    # Pre-procesamiento de fechas
    df_raw['Fecha'] = pd.to_datetime(df_raw['Fecha'], errors='coerce')
    df_raw = df_raw.dropna(subset=['Fecha'])

    # ==========================================
    # 2. FILTROS (FECHA Y MÁQUINA MÚLTIPLE)
    # ==========================================
    st.markdown("### Configuración del Reporte")
    
    fecha_min = df_raw['Fecha'].min().date()
    fecha_max = df_raw['Fecha'].max().date()
    
    rango_fechas = st.date_input(
        "📅 1. Selecciona el rango de fechas:",
        value=(fecha_min, fecha_max),
        min_value=fecha_min,
        max_value=fecha_max
    )

    if len(rango_fechas) == 2:
        inicio, fin = rango_fechas
        mask = (df_raw['Fecha'].dt.date >= inicio) & (df_raw['Fecha'].dt.date <= fin)
        df_filtrado_fecha = df_raw.loc[mask].copy()
    else:
        st.warning("Por favor, selecciona un rango de fechas completo (Inicio y Fin).")
        st.stop()

    # --- LIMPIEZA Y UNIFICACIÓN DE MÁQUINAS ---
    df_filtrado_fecha = df_filtrado_fecha.dropna(how='all')
    df_filtrado_fecha['Máquina'] = df_filtrado_fecha['Máquina'].astype(str).str.strip()
    df_filtrado_fecha = df_filtrado_fecha[~df_filtrado_fecha['Máquina'].str.lower().isin(['nan', 'none', '', 'null'])]

    # UNIFICAR CELDA 15A y 15B como una sola: "Cell 15 Famma"
    df_filtrado_fecha['Máquina'] = df_filtrado_fecha['Máquina'].apply(
        lambda x: 'Cell 15 Famma' if 'Cell 15A' in x or 'Cell 15B' in x else x
    )

    # Opciones de máquina (Selector múltiple) - Ahora mostrará Cell 15 Famma unificada
    lista_maquinas = sorted(df_filtrado_fecha['Máquina'].unique().tolist())
    
    maquinas_seleccionadas = st.multiselect(
        "⚙️ 2. Selecciona la(s) Máquina(s) a incluir en el PDF:", 
        options=lista_maquinas,
        default=lista_maquinas # Por defecto selecciona todas
    )

    if not maquinas_seleccionadas:
        st.warning("Por favor, selecciona al menos una máquina para generar el reporte.")
        st.stop()

    # Filtrar el DataFrame final por las máquinas seleccionadas
    df = df_filtrado_fecha[df_filtrado_fecha['Máquina'].isin(maquinas_seleccionadas)].copy()

    st.success(f"Datos listos para procesar ({len(df)} registros encontrados).")
    st.divider()

    # ==========================================
    # 3. CÁLCULOS BASE (Ocultos)
    # ==========================================
    with st.spinner("Procesando datos y calculando métricas..."):
        columnas_num = ['Buenas', 'Retrabajo', 'Observadas', 'Tiempo Producción (Min)', 'Tiempo Ciclo', 'Hora']
        for col in columnas_num:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(',', '.', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        df = df[df['Tiempo Producción (Min)'] > 0]
        df['Hora_Real'] = df['Hora'].astype(int)
        df['Orden_Hora'] = df['Hora_Real'].apply(lambda x: x if x >= 6 else x + 24)
        df['Total_Piezas_Fabricadas'] = df['Buenas'] + df['Retrabajo'] + df['Observadas']
        df['Horas_Decimal'] = df['Tiempo Producción (Min)'] / 60

        def calcular_sub_bloque(g):
            if g.empty: return pd.Series({'Total_Piezas': 0.0, 'Total_Horas': 0.0, 'Cantidad_Productos': 0, 'Ciclos_Maquina': 0.0})
            total_piezas = float(g['Total_Piezas_Fabricadas'].sum())
            cantidad_productos = int(g['Código Producto'].nunique())
            # Al estar unificadas 15A y 15B, toman el tiempo productivo registrado en esa hora
            total_horas = float(g['Horas_Decimal'].iloc[0]) if not g.empty else 0.0
            ciclos_maquina = total_piezas / cantidad_productos if cantidad_productos > 0 else 0.0
            return pd.Series([total_piezas, total_horas, cantidad_productos, ciclos_maquina], 
                             index=['Total_Piezas', 'Total_Horas', 'Cantidad_Productos', 'Ciclos_Maquina'])

        despliegue_hora = df.groupby(['Fecha', 'Máquina', 'Hora_Real', 'Orden_Hora', 'Horas_Decimal']).apply(calcular_sub_bloque).reset_index()
        despliegue_hora = despliegue_hora.dropna(subset=['Total_Piezas', 'Total_Horas', 'Cantidad_Productos'])
        despliegue_hora['Pzs_Hora_Bloque'] = np.where(despliegue_hora['Total_Horas'] > 0, despliegue_hora['Total_Piezas'] / despliegue_hora['Total_Horas'], 0)
        despliegue_hora['Ciclos_Hora_Bloque'] = np.where(despliegue_hora['Total_Horas'] > 0, despliegue_hora['Ciclos_Maquina'] / despliegue_hora['Total_Horas'], 0)
        despliegue_hora = despliegue_hora[(despliegue_hora['Cantidad_Productos'] > 0) & (despliegue_hora['Total_Horas'] > 0) & (despliegue_hora['Pzs_Hora_Bloque'] > 0)]

        resumen_general = despliegue_hora.groupby(['Máquina', 'Cantidad_Productos']).agg(
            Promedio_Pzs_Hora=('Pzs_Hora_Bloque', 'mean')
        ).reset_index().round(2)

        comp_prod = df.groupby(['Máquina', 'Código Producto']).agg(
            Suma_Piezas=('Total_Piezas_Fabricadas', 'sum'),
            Suma_Horas=('Horas_Decimal', 'sum'),
            Promedio_Tiempo_Ciclo=('Tiempo Ciclo', 'mean')
        ).reset_index().dropna()

        comp_prod = comp_prod[comp_prod['Suma_Horas'] > 0]
        comp_prod['Real_Pzs_Hora'] = comp_prod['Suma_Piezas'] / comp_prod['Suma_Horas']
        comp_prod['Estimado_Pzs_Hora'] = np.where(comp_prod['Promedio_Tiempo_Ciclo'] > 0, 60 / comp_prod['Promedio_Tiempo_Ciclo'], 0)
        comp_prod['Diferencia'] = comp_prod['Real_Pzs_Hora'] - comp_prod['Estimado_Pzs_Hora']
        comp_prod = comp_prod[['Máquina', 'Código Producto', 'Real_Pzs_Hora', 'Estimado_Pzs_Hora', 'Diferencia']].round(2)

        prom_h = despliegue_hora.groupby(['Máquina', 'Hora_Real', 'Orden_Hora']).agg(P=('Pzs_Hora_Bloque', 'mean')).reset_index().sort_values('Orden_Hora')

    # ==========================================
    # 4. GENERACIÓN DEL PDF EJECUTIVO
    # ==========================================
    with st.spinner("Armando el documento PDF..."):
        pdf = FPDF()
        AZUL_TITULO = (0, 51, 102)
        AZUL_FONDO = (204, 229, 255)

        pdf.add_page()
        pdf.set_font("Arial", "B", 18)
        pdf.set_text_color(*AZUL_TITULO)
        pdf.cell(190, 10, "REPORTE DE PRODUCCION EJECUTIVO", 0, 1, 'C')
        
        pdf.set_font("Arial", "I", 11)
        pdf.set_text_color(100, 100, 100)
        
        texto_maquinas = "Multiples Seleccionadas" if len(maquinas_seleccionadas) > 1 else maquinas_seleccionadas[0]
        pdf.cell(190, 8, f"Periodo: {inicio} al {fin} | Maquina(s): {texto_maquinas}", 0, 1, 'C')
        pdf.ln(5)

        # ---- SECCIÓN 1: Rendimiento General ----
        pdf.set_font("Arial", "B", 12)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(190, 10, "1. Rendimiento General (Por N. de Productos)", 0, 1)
        
        pdf.set_font("Arial", "B", 10)
        pdf.set_fill_color(*AZUL_FONDO)
        pdf.cell(80, 8, "Maquina", 1, 0, 'C', True)
        pdf.cell(50, 8, "N. Productos", 1, 0, 'C', True)
        pdf.cell(60, 8, "Promedio (Pzs/h)", 1, 1, 'C', True)
        
        pdf.set_font("Arial", "", 9)
        for _, r in resumen_general.iterrows():
            pdf.cell(80, 7, str(r['Máquina'])[:35], 1)
            pdf.cell(50, 7, str(int(r['Cantidad_Productos'])), 1, 0, 'C')
            pdf.cell(60, 7, f"{r['Promedio_Pzs_Hora']:.2f}", 1, 1, 'C')
        pdf.ln(5)

        # ---- SECCIÓN 2: Real vs Estimado ----
        pdf.set_font("Arial", "B", 12)
        pdf.cell(190, 10, "2. Rendimiento por Producto (Real vs Estimado)", 0, 1)
        
        pdf.set_font("Arial", "B", 9)
        pdf.set_fill_color(*AZUL_FONDO)
        pdf.cell(50, 8, "Maquina", 1, 0, 'C', True)
        pdf.cell(65, 8, "Codigo Producto", 1, 0, 'C', True)
        pdf.cell(25, 8, "Real", 1, 0, 'C', True)
        pdf.cell(25, 8, "Estimado", 1, 0, 'C', True)
        pdf.cell(25, 8, "Diferencia", 1, 1, 'C', True)
        
        pdf.set_font("Arial", "", 9)
        for _, r in comp_prod.iterrows():
            pdf.cell(50, 7, str(r['Máquina'])[:25], 1)
            pdf.cell(65, 7, str(r['Código Producto'])[:30], 1)
            pdf.cell(25, 7, f"{r['Real_Pzs_Hora']:.2f}", 1, 0, 'C')
            pdf.cell(25, 7, f"{r['Estimado_Pzs_Hora']:.2f}", 1, 0, 'C')
            
            # Color en Diferencia
            if r['Diferencia'] > 0:
                pdf.set_text_color(0, 150, 0)
                diff_text = f"+{r['Diferencia']:.2f}"
            else:
                pdf.set_text_color(200, 0, 0)
                diff_text = f"{r['Diferencia']:.2f}"
                
            pdf.cell(25, 7, diff_text, 1, 1, 'C')
            pdf.set_text_color(0,0,0)
        pdf.ln(5)

        # ---- SECCIÓN 3: Histórico Diario ----
        for m_id in maquinas_seleccionadas:
            dat_pdf = prom_h[prom_h['Máquina'] == m_id]
            if dat_pdf.empty: continue

            pdf.add_page()
            pdf.set_font("Arial", "B", 12)
            pdf.cell(190, 10, f"3. Rendimiento Historico Diario: {m_id}", 0, 1)
            
            # Tabla del histórico
            pdf.set_font("Arial", "B", 10)
            pdf.set_fill_color(*AZUL_FONDO)
            pdf.cell(70, 8, "Maquina", 1, 0, 'C', True)
            pdf.cell(50, 8, "Hora", 1, 0, 'C', True)
            pdf.cell(70, 8, "Promedio (Pzs/h)", 1, 1, 'C', True)
            
            pdf.set_font("Arial", "", 9)
            for _, r in dat_pdf.iterrows():
                pdf.cell(70, 7, str(r['Máquina'])[:30], 1, 0, 'C')
                pdf.cell(50, 7, f"{r['Hora_Real']}:00", 1, 0, 'C')
                pdf.cell(70, 7, f"{r['P']:.2f}", 1, 1, 'C')
            
            # Gráfico temporal
            fig_t, ax_t = plt.subplots(figsize=(10, 3.5))
            ax_t.plot(dat_pdf['Hora_Real'].astype(str) + ":00", dat_pdf['P'], marker='o', color='#00509E')
            ax_t.set_title(f"Tendencia - {m_id}")
            ax_t.set_ylabel("Promedio (Pzs/h)")
            ax_t.grid(True, linestyle='--', alpha=0.6)
            
            t_name = f"t_{m_id}.png".replace(" ","").replace("/","")
            fig_t.savefig(t_name, bbox_inches='tight')
            plt.close(fig_t)
            
            pdf.ln(5)
            pdf.image(t_name, x=15, w=180)
            if os.path.exists(t_name):
                os.remove(t_name)

        # ==========================================
        # DESCARGA DEL ARCHIVO (CON FECHAS DINÁMICAS)
        # ==========================================
        # Formateamos las fechas de YYYY-MM-DD a un string limpio
        fecha_str = f"{inicio.strftime('%d%m%y')}_al_{fin.strftime('%d%m%y')}"
        
        if len(maquinas_seleccionadas) > 1:
            nombre_archivo = f"Reporte_Produccion_Multi_{fecha_str}.pdf"
        else:
            nombre_limpio = maquinas_seleccionadas[0].replace(' ', '_')
            nombre_archivo = f"Reporte_Produccion_{nombre_limpio}_{fecha_str}.pdf"
            
        pdf.output(nombre_archivo)

    # Botón gigante y claro para la descarga final
    with open(nombre_archivo, "rb") as f:
        st.download_button(
            label="📥 Descargar Reporte Ejecutivo en PDF", 
            data=f, 
            file_name=nombre_archivo,
            mime="application/pdf",
            use_container_width=True
        )

    if os.path.exists(nombre_archivo):
        os.remove(nombre_archivo)

except Exception as e:
    st.error(f"Error de procesamiento: {e}")
