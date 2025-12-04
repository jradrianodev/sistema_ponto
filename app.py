import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import streamlit.components.v1 as components

# --- Configurações ---
NOME_PLANILHA = "Controle de Ponto"

# Configurar Fuso Horário Brasil (UTC-3)
FUSO_BRASIL = timezone(timedelta(hours=-3))

st.set_page_config(page_title="Ponto Inteligente", page_icon="🧠", layout="wide")

# --- HTML/JS para o Relógio Ticando (Igual ao anterior) ---
def exibir_relogio_real():
    relogio_html = """
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        body { font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100px; margin: 0; background-color: transparent; }
        .container { background-color: #f0f2f6; padding: 15px 30px; border-radius: 12px; text-align: center; border: 1px solid #dcdcdc; box-shadow: 2px 2px 10px rgba(0,0,0,0.05); }
        .label { font-size: 14px; color: #555; margin-bottom: 5px; }
        .clock { font-size: 32px; font-weight: bold; color: #0068c9; font-family: 'Courier New', monospace; }
    </style>
    </head>
    <body>
        <div class="container">
            <div class="label">Horário Atual (Brasília)</div>
            <div class="clock" id="clock">Carregando...</div>
        </div>
        <script>
            function updateClock() {
                var now = new Date();
                var utc = now.getTime() + (now.getTimezoneOffset() * 60000);
                var brasiliaTime = new Date(utc + (3600000 * -3));
                var timeString = brasiliaTime.toLocaleTimeString('pt-BR', { hour12: false });
                document.getElementById('clock').innerHTML = timeString;
            }
            setInterval(updateClock, 1000);
            updateClock();
        </script>
    </body>
    </html>
    """
    components.html(relogio_html, height=130)

# --- Conexão Google Sheets ---
def conectar_gsheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    try:
        return client.open(NOME_PLANILHA).sheet1
    except Exception as e:
        st.error(f"Erro ao abrir planilha: {e}")
        return None

# --- Lógica de Registro (Bater Ponto) ---
def registrar_ponto(tipo_coluna):
    sheet = conectar_gsheets()
    if not sheet: return

    agora = datetime.now(FUSO_BRASIL)
    data_hoje = agora.strftime("%Y-%m-%d")
    hora_agora = agora.strftime("%H:%M:%S")
    
    dados = sheet.get_all_records()
    df = pd.DataFrame(dados)
    
    if not df.empty:
        df['Data'] = df['Data'].astype(str)
        linha_index = df.index[df['Data'] == data_hoje].tolist()
    else:
        linha_index = []

    colunas_map = {"Entrada": 2, "Almoco_Inicio": 3, "Almoco_Fim": 4, "Saida": 5}
    col_num = colunas_map[tipo_coluna]

    with st.spinner('Salvando...'):
        if not linha_index:
            nova_linha = [data_hoje, "", "", "", ""]
            nova_linha[col_num - 1] = hora_agora
            sheet.append_row(nova_linha)
            st.success(f"✅ {tipo_coluna} registrado: {hora_agora}")
        else:
            row_number = linha_index[0] + 2 
            valor_atual = sheet.cell(row_number, col_num).value
            if not valor_atual:
                sheet.update_cell(row_number, col_num, hora_agora)
                st.success(f"✅ {tipo_coluna} registrado: {hora_agora}")
            else:
                st.warning(f"⚠️ Já existe registro às {valor_atual}")

# --- 🧠 LÓGICA DE CÁLCULO INTELIGENTE ---
def calcular_saldo_diario(row):
    fmt = "%H:%M:%S"
    
    # 1. Descobrir o dia da semana e definir a meta
    try:
        data_obj = datetime.strptime(str(row['Data']), "%Y-%m-%d")
        dia_semana = data_obj.weekday() # 0=Segunda, 5=Sábado, 6=Domingo
        nome_dia = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"][dia_semana]
    except:
        return "Erro Data", "---", "---"

    # Define a meta baseada no dia
    if dia_semana < 5: # Segunda a Sexta
        meta = timedelta(hours=8)
        meta_str = "8h"
    elif dia_semana == 5: # Sábado
        meta = timedelta(hours=4)
        meta_str = "4h"
    else: # Domingo
        meta = timedelta(hours=0)
        meta_str = "0h (Extra)"

    # 2. Calcular horas trabalhadas
    entrada = str(row['Entrada']).strip()
    almoco_sai = str(row['Almoco_Inicio']).strip()
    almoco_volta = str(row['Almoco_Fim']).strip()
    saida = str(row['Saida']).strip()

    try:
        t_entrada = datetime.strptime(entrada, fmt) if entrada else None
        t_saida = datetime.strptime(saida, fmt) if saida else None
        t_alm_sai = datetime.strptime(almoco_sai, fmt) if almoco_sai else None
        t_alm_volta = datetime.strptime(almoco_volta, fmt) if almoco_volta else None
        
        trabalhado = timedelta(0)

        # Lógica para dia normal (com almoço)
        if t_entrada and t_saida and t_alm_sai and t_alm_volta:
            manha = t_alm_sai - t_entrada
            tarde = t_saida - t_alm_volta
            trabalhado = manha + tarde
        
        # Lógica para dia direto (Sábado sem almoço ou meio expediente)
        elif t_entrada and t_saida and not t_alm_sai and not t_alm_volta:
            trabalhado = t_saida - t_entrada
        
        # Se faltar batida, não calcula
        else:
            return f"{nome_dia} ({meta_str})", "Em Aberto", "---"

        # 3. Calcular Saldo
        saldo = trabalhado - meta
        total_segundos = int(saldo.total_seconds())
        
        # Formatar saldo visualmente
        sinal = "+" if total_segundos >= 0 else "-"
        horas = abs(total_segundos) // 3600
        minutos = (abs(total_segundos) % 3600) // 60
        str_saldo = f"{sinal}{horas:02d}:{minutos:02d}"

        # Formatar horas trabalhadas
        trab_seg = int(trabalhado.total_seconds())
        h_trab = trab_seg // 3600
        m_trab = (trab_seg % 3600) // 60
        str_trabalhado = f"{h_trab:02d}:{m_trab:02d}"

        return f"{nome_dia} ({meta_str})", str_trabalhado, str_saldo

    except:
        return f"{nome_dia}", "Erro Hora", "Erro"

# --- Interface Principal ---
st.title("🧠 Ponto Inteligente")
exibir_relogio_real()

tab1, tab2 = st.tabs(["📝 Registrar Ponto", "📊 Espelho e Banco de Horas"])

with tab1:
    st.write("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶️ 1. Entrada", use_container_width=True): registrar_ponto("Entrada")
        if st.button("🍽️ 2. Saída Almoço", use_container_width=True): registrar_ponto("Almoco_Inicio")
    with col2:
        if st.button("🔙 3. Volta Almoço", use_container_width=True): registrar_ponto("Almoco_Fim")
        if st.button("🛑 4. Saída Geral", use_container_width=True): registrar_ponto("Saida")

with tab2:
    st.write("### 📅 Extrato Detalhado")
    if st.button("🔄 Atualizar Dados"): st.rerun()

    sheet = conectar_gsheets()
    if sheet:
        dados = sheet.get_all_records()
        df = pd.DataFrame(dados)
        
        if not df.empty:
            # Aplica a inteligência linha por linha
            resultados = df.apply(calcular_saldo_diario, axis=1, result_type='expand')
            df['Dia (Meta)'] = resultados[0]
            df['Horas Feitas'] = resultados[1]
            df['Saldo Banco'] = resultados[2]

            # Reorganiza colunas para ficar bonito
            df_final = df[['Data', 'Dia (Meta)', 'Entrada', 'Almoco_Inicio', 'Almoco_Fim', 'Saida', 'Horas Feitas', 'Saldo Banco']]
            
            # Ordena por data (mais recente em cima)
            df_final = df_final.sort_values(by="Data", ascending=False)

            # Estilização Condicional (Cores)
            def colorir_saldo(val):
                if val.startswith("+"): return 'color: green; font-weight: bold'
                if val.startswith("-"): return 'color: red; font-weight: bold'
                return ''

            st.dataframe(df_final.style.map(colorir_saldo, subset=['Saldo Banco']), use_container_width=True)
            
            st.info("💡 **Dica:** Sábados sem registro de almoço são calculados direto (Saída - Entrada).")
        else:
            st.warning("Nenhum dado encontrado.")