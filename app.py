import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import streamlit.components.v1 as components

# --- Configurações ---
NOME_PLANILHA = "Controle de Ponto"
HORAS_DIARIAS = timedelta(hours=6)

# Configurar Fuso Horário Brasil (UTC-3)
FUSO_BRASIL = timezone(timedelta(hours=-3))

st.set_page_config(page_title="Ponto G-Sheets", page_icon="⏰")

# --- HTML/JS para o Relógio Ticando ---
def exibir_relogio_real():
    relogio_html = """
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        body {
            font-family: sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100px;
            margin: 0;
            background-color: transparent;
        }
        .container {
            background-color: #f0f2f6;
            padding: 15px 30px;
            border-radius: 12px;
            text-align: center;
            border: 1px solid #dcdcdc;
            box-shadow: 2px 2px 10px rgba(0,0,0,0.05);
        }
        .label {
            font-size: 14px;
            color: #555;
            margin-bottom: 5px;
        }
        .clock {
            font-size: 32px;
            font-weight: bold;
            color: #0068c9;
            font-family: 'Courier New', monospace;
        }
    </style>
    </head>
    <body>
        <div class="container">
            <div class="label">Horário Atual (Brasília)</div>
            <div class="clock" id="clock">Carregando...</div>
        </div>

        <script>
            function updateClock() {
                // Cria data baseada no UTC e converte para horário de Brasília (UTC-3)
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
    # Altura ajustada para caber o design sem barra de rolagem
    components.html(relogio_html, height=130)

# --- Conexão com Google Sheets ---
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

# --- Lógica de Registro ---
def registrar_ponto(tipo_coluna):
    sheet = conectar_gsheets()
    if not sheet: return

    # AGORA COM FUSO HORÁRIO CORRETO
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

    with st.spinner('Salvando no Google Sheets...'):
        if not linha_index:
            nova_linha = [data_hoje, "", "", "", ""]
            nova_linha[col_num - 1] = hora_agora
            sheet.append_row(nova_linha)
            st.success(f"Dia iniciado! {tipo_coluna} registrado às {hora_agora}")
        else:
            row_number = linha_index[0] + 2 
            valor_atual = sheet.cell(row_number, col_num).value
            if not valor_atual:
                sheet.update_cell(row_number, col_num, hora_agora)
                st.success(f"✅ {tipo_coluna} registrado com sucesso às {hora_agora}!")
            else:
                st.warning(f"⚠️ Você já registrou {tipo_coluna} hoje às {valor_atual}")

# --- Interface ---
st.title("⏰ Sistema de Ponto")

# Chama a função do relógio aqui no topo
exibir_relogio_real()

tab1, tab2 = st.tabs(["Registrar", "Espelho de Ponto"])

with tab1:
    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶️ 1. Entrada", use_container_width=True):
            registrar_ponto("Entrada")
        if st.button("🍽️ 2. Saída Almoço", use_container_width=True):
            registrar_ponto("Almoco_Inicio")
            
    with col2:
        if st.button("🔙 3. Volta Almoço", use_container_width=True):
            registrar_ponto("Almoco_Fim")
        if st.button("🛑 4. Saída Geral", use_container_width=True):
            registrar_ponto("Saida")

with tab2:
    st.write("Dados lidos diretamente da sua planilha:")
    if st.button("🔄 Atualizar Tabela"):
        st.rerun()
        
    sheet = conectar_gsheets()
    if sheet:
        dados = sheet.get_all_records()
        df = pd.DataFrame(dados)
        if not df.empty:
            st.dataframe(df)
            st.link_button("Abrir Planilha no Google", "https://docs.google.com/spreadsheets/")
        else:
            st.info("A planilha está vazia.")