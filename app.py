import streamlit as st
import pandas as pd
import gspread
import google.auth
import re
import time
from datetime import datetime

credenciales_dict = dict(st.secrets["gcp_service_account"])
client = gspread.service_account_from_dict(credenciales_dict)

# =========================================================
# CONFIGURACIÓN GENERAL
# =========================================================
ID_SHEET_PRINCIPAL = "1Xime2RgUH9TLh7xbc8cmTJnTmP2OCbpmGqjynTlYZu4"
ID_CARPETA_DATA_CRUDA = "19pvAK611xwEj3SL27ceYZyI7q5rTv1oM"

HOJA_AUDITORIAS = "AUDITORIAS"
HOJA_CLIENTES = "CLIENTES"
HOJA_SENSORES = "EQUIPOS_MEDICIÓN"
HOJA_INVENTARIO = "INVENTARIO_COMPRESORES"
HOJA_DETALLE = "DETALLE_AUDITORIA_EQUIPOS"

# Mapeo exacto para actualización de celdas específicas en Fase 2 (1-based index)
COL_ESTADO_AUD = 10  # Columna J 
COL_URL_DATA_AUD = 24 # Columna X 

st.set_page_config(page_title="SAIRCOM CRM PRO", layout="wide")

@st.cache_resource
def conectar():
    creds, _ = google.auth.default()
    return gspread.authorize(creds)

def get_next_id_smart(worksheet, prefix):
    try:
        ids = worksheet.col_values(1)[1:]
        if not ids: return f"{prefix}-001"
        numeros = [int(re.search(r'(\d+)$', x).group(1)) for x in ids if re.search(r'(\d+)$', x)]
        return f"{prefix}-{(max(numeros) + 1 if numeros else 1):03d}"
    except:
        return f"{prefix}-001"

def insertar_en_tabla(worksheet, fila_datos):
    col_a = worksheet.col_values(1)
    nueva_fila_idx = len(col_a) + 1
    rango = f"A{nueva_fila_idx}"
    worksheet.update(rango, [fila_datos], value_input_option='USER_ENTERED')

try:
    client = conectar()
    sh = client.open_by_key(ID_SHEET_PRINCIPAL)
    
    ws_aud = sh.worksheet(HOJA_AUDITORIAS)
    df_aud = pd.DataFrame(ws_aud.get_all_records())
    
    ws_cli = sh.worksheet(HOJA_CLIENTES)
    df_clientes = pd.DataFrame(ws_cli.get_all_records())
    
    ws_detalle = sh.worksheet(HOJA_DETALLE)
    ws_inv = sh.worksheet(HOJA_INVENTARIO)

    try:
        ws_equ = sh.worksheet(HOJA_SENSORES)
        df_equ = pd.DataFrame(ws_equ.get_all_records())
        df_disp = df_equ[df_equ['ESTADO'] == 'Disponible']
        dict_sensores = dict(zip(df_disp['N_SERIE'].astype(str), df_disp['ID_EQUIPO']))
        lista_series = ["Seleccionar Sensor..."] + list(dict_sensores.keys())
    except:
        lista_series = ["Sensores no disponibles"]
        dict_sensores = {}

    # ==========================================
    # MODAL FASE 1: PLANIFICACIÓN
    # ==========================================
    @st.dialog("📝 Planificar Nueva Auditoría")
    def modal_fase1():
        opciones_cli = ["+ NUEVO CLIENTE"] + df_clientes['Razon_Social_Empresa'].tolist()
        cliente_sel = st.selectbox("Cliente", opciones_cli)

        if cliente_sel == "+ NUEVO CLIENTE":
            razon = st.text_input("Razón Social *")
            contacto = st.text_input("Contacto")
        
        c1, c2 = st.columns(2)
        with c1:
            servicio_opt = ["AUDITORIA PREMIÚM", "AUDITORIA DE AIRE COMPRIMIDO", "AUDITORIA DE FUGAS"]
            servicio_sel = st.selectbox("Servicio", servicio_opt)
            mapeo_tipos = {
                "AUDITORIA PREMIÚM": "Eficiencia energetica",
                "AUDITORIA DE AIRE COMPRIMIDO": "Rendimiento del equipo",
                "AUDITORIA DE FUGAS": "Detección Ultrasonido"
            }
            tipo_auto = mapeo_tipos.get(servicio_sel, "")
            st.info(f"Tipo: **{tipo_auto}**")
            fecha = st.date_input("Fecha de Servicio")

        with c2:
            asesor = st.text_input("Gestor", value="Mauricio Alexis")
            obs = st.text_area("Observaciones Generales")

        with st.expander("📍 Datos del Cliente (Dirección, Maps, Tarifa)"):
            tarifa = st.text_input("Tarifa Eléctrica ($/kWh)")
            direccion = st.text_input("Dirección de la Planta")
            maps_link = st.text_input("Enlace Google Maps")
        
        if st.button("Guardar Registro", type="primary"):
            with st.spinner("Sincronizando con Sheets..."):
                
                # --- LÓGICA DE HOJA CLIENTES ---
                if cliente_sel == "+ NUEVO CLIENTE" and razon:
                    id_cli = get_next_id_smart(ws_cli, "CLI")
                    # Mapeo Cliente: A=ID, B=Razon, C=Dirección, D=Contacto, E=Tarifa, F=Maps
                    fila_cliente = [""] * 6
                    fila_cliente[0] = id_cli       # A: ID
                    fila_cliente[1] = razon        # B: Razón Social
                    fila_cliente[2] = direccion    # C: Dirección
                    fila_cliente[3] = contacto     # D: Contacto
                    fila_cliente[4] = tarifa       # E: Tarifa
                    fila_cliente[5] = maps_link    # F: Maps
                    insertar_en_tabla(ws_cli, fila_cliente)
                else:
                    id_cli = df_clientes[df_clientes['Razon_Social_Empresa'] == cliente_sel]['ID_Cliente'].values[0]
                    # Actualizar cliente existente en sus columnas específicas
                    if direccion or maps_link or tarifa:
                        celda_cli = ws_cli.find(id_cli)
                        if celda_cli:
                            row_cli = celda_cli.row
                            if direccion: ws_cli.update_cell(row_cli, 3, direccion) # Col C
                            if tarifa: ws_cli.update_cell(row_cli, 5, tarifa)       # Col E
                            if maps_link: ws_cli.update_cell(row_cli, 6, maps_link) # Col F

                # --- LÓGICA DE HOJA AUDITORIAS ---
                meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
                id_a = get_next_id_smart(ws_aud, "AUD-2026")
                
                # Arreglo de 24 espacios (0 a 23) para llegar hasta la columna X
                nueva_fila = [""] * 24 
                nueva_fila[0] = id_a            # Columna A: ID Auditoria
                nueva_fila[1] = id_cli          # Columna B: ID Cliente
                nueva_fila[2] = servicio_sel    # Columna C: Servicio
                nueva_fila[3] = tipo_auto       # Columna D: Tipo
                nueva_fila[6] = asesor          # Columna G: Gestor
                nueva_fila[7] = meses[fecha.month-1] # Columna H: Mes
                nueva_fila[8] = fecha.year      # Columna I: Año
                nueva_fila[9] = "Planificado"   # Columna J: Estado
                nueva_fila[10] = str(fecha)     # Columna K: Fecha
                nueva_fila[22] = obs            # Columna W: Observaciones
                # La columna X (23) queda vacía hasta la fase 2
                
                insertar_en_tabla(ws_aud, nueva_fila)
                st.success(f"Registrado exitosamente como {id_a}")
                st.rerun()

    # ==========================================
    # MODAL FASE 2: CAMPO 
    # ==========================================
    @st.dialog("🛠️ Registro Técnico de Compresores")
    def modal_fase2(id_aud, id_cliente):
        n_comp = st.number_input("¿Cuántos compresores?", 1, 15, 1)
        equipos_data = []

        for i in range(n_comp):
            st.markdown(f"### 📦 Compresor #{i+1}")
            col1, col2, col3 = st.columns(3)
            with col1:
                marca = st.text_input("Marca", key=f"ma_{i}")
                modelo = st.text_input("Modelo", key=f"mo_{i}")
                serie = st.text_input("N° Serie", key=f"se_{i}")
                tipo_c = st.selectbox("Tipo de control", ["Carga/Descarga", "VSD", "Desplazamiento Variable"], key=f"ti_{i}")
            with col2:
                potencia = st.text_input("Potencia", key=f"po_{i}")
                caudal = st.text_input("Caudal", key=f"ca_{i}")
                presion = st.text_input("Presión Placa", key=f"pr_{i}")
                voltaje = st.text_input("Voltaje", key=f"vo_{i}")
            with col3:
                p_carga = st.text_input("P. Carga", key=f"pc_{i}")
                p_vacio = st.text_input("P. Vacío", key=f"pv_{i}")
                horo = st.text_input("Horómetro", key=f"ho_{i}")
                sensor_sel = st.selectbox("Sensor (N° Serie)", lista_series, key=f"ss_{i}")
            
            notas_campo = st.text_area("Notas de campo / Observaciones del Auditor", key=f"nt_{i}")

            equipos_data.append({
                "marca": marca, "modelo": modelo, "serie": serie, "tipo": tipo_c,
                "potencia": potencia, "caudal": caudal, "presion": presion,
                "voltaje": voltaje, "p_carga": p_carga, "p_vacio": p_vacio,
                "horometro": horo, "sensor": dict_sensores.get(sensor_sel, "N/A"),
                "notas": notas_campo
            })

        if st.button("🏁 Finalizar y Vincular Todo", type="primary"):
            with st.spinner("Creando estructura de datos crudos..."):
                nombre_archivo = f"DATA_CRUDO_{id_aud}_{id_cliente}"
                new_sh = client.create(nombre_archivo, folder_id=ID_CARPETA_DATA_CRUDA)
                url_excel_crudo = new_sh.url 
                
                # 1. Preparar Hoja Resumen
                ws_datos = new_sh.get_worksheet(0)
                ws_datos.update_title("Datos_Auditoria")
                labels = [["Equipos"],["Marca"],["Modelo"],["Serie"],["Tipo"],["Presion_Placa"],["Caudal"],["Potencia_Carga"],["Potencia_Vacio"],["Horometro"],["Voltaje"],["Sensor"]]
                ws_datos.update('A1', labels)

                # 2. Hoja PRESIÓN
                ws_presion = new_sh.add_worksheet(title="PRESIÓN", rows=1000, cols=3)
                ws_presion.update('A1', [["Fecha", "Tiempo", "Datos"]])

                # 3. Guardar registros y crear hojas de equipos
                for idx, comp in enumerate(equipos_data):
                    id_c = get_next_id_smart(ws_inv, "COMP")
                    id_det = get_next_id_smart(ws_detalle, "DET")
                    
                    insertar_en_tabla(ws_inv, [id_c, id_cliente, comp['marca'], comp['modelo'], comp['serie'], comp['tipo'], comp['potencia'], comp['caudal']])
                    insertar_en_tabla(ws_detalle, [id_det, id_aud, id_cliente, comp['horometro'], comp['sensor'], comp['notas'], id_c])
                    
                    col_letra = chr(66 + idx)
                    v_col = [[id_c],[comp['marca']],[comp['modelo']],[comp['serie']],[comp['tipo']],[comp['presion']],[comp['caudal']],[comp['p_carga']],[comp['p_vacio']],[comp['horometro']],[comp['voltaje']],[comp['sensor']]]
                    ws_datos.update(f'{col_letra}1', v_col)
                    
                    ws_comp = new_sh.add_worksheet(title=id_c, rows=5000, cols=5)
                    ws_comp.update('A1', [["Fecha", "Tiempo", "Amperaje", "Potencia", "Caudal"]])

                # 4. Actualizar estado y link en columnas J (10) y X (24)
                celda = ws_aud.find(id_aud)
                if celda:
                    ws_aud.update_cell(celda.row, COL_ESTADO_AUD, "Toma de datos")
                    ws_aud.update_cell(celda.row, COL_URL_DATA_AUD, url_excel_crudo)
                
                st.success("✅ Estructura técnica creada. Enlace guardado en Sheets.")
                st.balloons()
                time.sleep(2)
                st.rerun()

    # --- UI PRINCIPAL ---
    st.title("🚀 Panel SAIRCOM")
    if st.button("➕ Planificar Nueva Auditoría", type="primary"): modal_fase1()

    st.divider()
    t1, t2 = st.tabs(["📋 Campo", "📊 Informes"])

    with t1:
        df_fresh = pd.DataFrame(ws_aud.get_all_records())
        df_fresh.columns = df_fresh.columns.astype(str).str.strip()
        if 'Estado_Medicion_Auditoria' in df_fresh.columns:
            estado_limpio = df_fresh['Estado_Medicion_Auditoria'].astype(str).str.strip().str.upper()
            pendientes = df_fresh[estado_limpio == 'PLANIFICADO']
            if pendientes.empty:
                st.info("No hay auditorías pendientes.")
            else:
                for _, row in pendientes.iterrows():
                    with st.container(border=True):
                        c1, c2 = st.columns([4, 1])
                        c1.write(f"**{row['ID_Auditoria']}** | {row['ID_Cliente']} | {row['Servicio']}")
                        if c2.button("⚙️ Iniciar Campo", key=f"btn_{row['ID_Auditoria']}"):
                            modal_fase2(row['ID_Auditoria'], row['ID_Cliente'])
except Exception as e:
    st.error(f"Error: {e}")
