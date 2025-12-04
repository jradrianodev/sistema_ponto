import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

# --- Configurações ---
NOME_PLANILHA = "Controle de Ponto"  # Tem que ser IDÊNTICO ao nome no Google Sheets
HORAS_DIARIAS = timedelta(hours=6)

st.set_page_config(page_title="Ponto G-Sheets", page_icon="📝")

# --- Conexão com Google Sheets ---
def conectar_gsheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Pega as credenciais dos segredos do Streamlit
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    
    try:
        sheet = client.open(NOME_PLANILHA).sheet1
        return sheet
    except Exception as e:
        st.error(f"Erro ao abrir planilha: {e}")
        return None

# --- Lógica de Registro ---
def registrar_ponto(tipo_coluna):
    sheet = conectar_gsheets()
    if not sheet: return

    agora = datetime.now()
    data_hoje = agora.strftime("%Y-%m-%d")
    hora_agora = agora.strftime("%H:%M:%S")
    
    # Busca todos os dados
    dados = sheet.get_all_records()
    df = pd.DataFrame(dados)
    
    # Converte a coluna Data para string para garantir a busca
    if not df.empty:
        df['Data'] = df['Data'].astype(str)
        # Procura se hoje já existe
        linha_index = df.index[df['Data'] == data_hoje].tolist()
    else:
        linha_index = []

    # Mapeamento de colunas (Gspread usa índice 1-based. A=1, B=2...)
    colunas_map = {
        "Entrada": 2,
        "Almoco_Inicio": 3,
        "Almoco_Fim": 4,
        "Saida": 5
    }
    col_num = colunas_map[tipo_coluna]

    with st.spinner('Salvando no Google Sheets...'):
        if not linha_index:
            # Se não existe hoje, cria nova linha
            nova_linha = [data_hoje, "", "", "", ""]
            # Preenche a posição correta
            nova_linha[col_num - 1] = hora_agora
            sheet.append_row(nova_linha)
            st.success(f"Dia iniciado! {tipo_coluna} registrado às {hora_agora}")
        else:
            # Se já existe, atualiza a célula
            # +2 porque: +1 pelo index do pandas começar em 0, +1 pelo cabeçalho da planilha
            row_number = linha_index[0] + 2 
            
            # Verifica se já não tem valor
            valor_atual = sheet.cell(row_number, col_num).value
            if not valor_atual:
                sheet.update_cell(row_number, col_num, hora_agora)
                st.success(f"{tipo_coluna} registrado com sucesso às {hora_agora}!")
            else:
                st.warning(f"Você já registrou {tipo_coluna} hoje às {valor_atual}")

# --- Interface ---
st.title("📝 Ponto Integrado ao Google Sheets")

# Abas
tab1, tab2 = st.tabs(["Registrar", "Espelho de Ponto"])

with tab1:
    st.write(f"**Data:** {datetime.now().strftime('%d/%m/%Y')}")
    
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
    sheet = conectar_gsheets()
    if sheet:
        dados = sheet.get_all_records()
        df = pd.DataFrame(dados)
        if not df.empty:
            st.dataframe(df)
            st.caption("Para editar ou corrigir erros, abra diretamente o Google Sheets.")
            st.link_button("Abrir Planilha no Google", f"https://docs.google.com/spreadsheets/")
        else:
            st.info("A planilha está vazia.")
            