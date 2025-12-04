import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import streamlit.components.v1 as components
import time

# --- Configurações ---
NOME_PLANILHA = "Controle de Ponto"
FUSO_BRASIL = timezone(timedelta(hours=-3))

st.set_page_config(page_title="Ponto Multi-Usuário", page_icon="👥", layout="wide")

# --- HTML/JS para Relógio ---
def exibir_relogio_real():
    relogio_html = """
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        body { font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 80px; margin: 0; background-color: transparent; }
        .container { background-color: #f0f2f6; padding: 10px 20px; border-radius: 10px; text-align: center; border: 1px solid #dcdcdc; }
        .clock { font-size: 24px; font-weight: bold; color: #0068c9; font-family: 'Courier New', monospace; }
    </style>
    </head>
    <body>
        <div class="container">
            <div class="clock" id="clock">Carregando...</div>
        </div>
        <script>
            function updateClock() {
                var now = new Date();
                var utc = now.getTime() + (now.getTimezoneOffset() * 60000);
                var brasiliaTime = new Date(utc + (3600000 * -3));
                var timeString = brasiliaTime.toLocaleTimeString('pt-BR', { hour12: false });
                document.getElementById('clock').innerHTML = "🕒 " + timeString;
            }
            setInterval(updateClock, 1000);
            updateClock();
        </script>
    </body>
    </html>
    """
    components.html(relogio_html, height=100)

# --- Conexão Google Sheets ---
def conectar_gsheets(aba_nome):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    try:
        # Tenta abrir a aba específica (0 = primeira aba, 1 = segunda aba, ou pelo nome)
        sheet = client.open(NOME_PLANILHA)
        return sheet.worksheet(aba_nome)
    except Exception as e:
        st.error(f"Erro ao conectar na aba '{aba_nome}': {e}")
        return None

# --- Funções de Autenticação ---
def verificar_login(username, senha):
    sheet = conectar_gsheets("Usuarios")
    if not sheet: return False, None
    
    registros = sheet.get_all_records()
    df = pd.DataFrame(registros)
    
    # Converte tudo para string para evitar erro
    df['Username'] = df['Username'].astype(str)
    df['Senha'] = df['Senha'].astype(str)
    
    usuario_encontrado = df[(df['Username'] == username) & (df['Senha'] == senha)]
    
    if not usuario_encontrado.empty:
        return True, usuario_encontrado.iloc[0]['Nome']
    return False, None

def cadastrar_usuario(username, senha, nome):
    sheet = conectar_gsheets("Usuarios")
    if not sheet: return False
    
    registros = sheet.get_all_records()
    df = pd.DataFrame(registros)
    
    if not df.empty and username in df['Username'].astype(str).values:
        return False # Usuário já existe
    
    sheet.append_row([username, senha, nome])
    return True

# --- Lógica de Ponto (Agora Filtrada por Usuário) ---
def registrar_ponto(tipo_coluna, usuario_atual):
    sheet = conectar_gsheets("Página1") # Ou o nome da sua aba de pontos (Página1 é o padrão)
    if not sheet: return

    agora = datetime.now(FUSO_BRASIL)
    data_hoje = agora.strftime("%Y-%m-%d")
    hora_agora = agora.strftime("%H:%M:%S")
    
    dados = sheet.get_all_records()
    df = pd.DataFrame(dados)
    
    # Colunas agora: Usuario(1), Data(2), Entrada(3), Alm_Ini(4), Alm_Fim(5), Saida(6)
    # Mapeamento ajustado (+1 devido à coluna nova de Usuário)
    colunas_map = {"Entrada": 3, "Almoco_Inicio": 4, "Almoco_Fim": 5, "Saida": 6}
    col_num = colunas_map[tipo_coluna]

    with st.spinner('Registrando...'):
        # Procura linha que tenha a DATA DE HOJE E O USUÁRIO ATUAL
        if not df.empty:
            df['Data'] = df['Data'].astype(str)
            df['Usuario'] = df['Usuario'].astype(str)
            filtro = (df['Data'] == data_hoje) & (df['Usuario'] == usuario_atual)
            linha_index = df.index[filtro].tolist()
        else:
            linha_index = []

        if not linha_index:
            # Cria nova linha com o nome do usuário
            nova_linha = [usuario_atual, data_hoje, "", "", "", ""]
            nova_linha[col_num - 1] = hora_agora
            sheet.append_row(nova_linha)
            st.success(f"✅ Dia iniciado para {usuario_atual}!")
        else:
            # Atualiza linha existente
            row_number = linha_index[0] + 2
            valor_atual = sheet.cell(row_number, col_num).value
            if not valor_atual:
                sheet.update_cell(row_number, col_num, hora_agora)
                st.success(f"✅ {tipo_coluna} registrado!")
            else:
                st.warning(f"⚠️ Já registrado às {valor_atual}")
    time.sleep(1)
    st.rerun()

def calcular_espelho(usuario_atual):
    sheet = conectar_gsheets("Página1")
    if not sheet: return pd.DataFrame()
    
    dados = sheet.get_all_records()
    df = pd.DataFrame(dados)
    
    if df.empty: return df
    
    # FILTRAR APENAS DADOS DO USUÁRIO LOGADO
    df['Usuario'] = df['Usuario'].astype(str)
    df_usuario = df[df['Usuario'] == usuario_atual].copy()
    
    if df_usuario.empty: return pd.DataFrame()

    def processar_linha(row):
        # Lógica de Sábado/Semana
        fmt = "%H:%M:%S"
        try:
            data_obj = datetime.strptime(str(row['Data']), "%Y-%m-%d")
            dia_semana = data_obj.weekday()
            nome_dia = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"][dia_semana]
            
            meta_horas = 4 if dia_semana == 5 else (0 if dia_semana == 6 else 8)
            
            ent, sai = str(row['Entrada']), str(row['Saida'])
            alm_i, alm_f = str(row['Almoco_Inicio']), str(row['Almoco_Fim'])
            
            t_trabalhado = timedelta(0)
            
            if ent and sai:
                t1, t4 = datetime.strptime(ent, fmt), datetime.strptime(sai, fmt)
                if alm_i and alm_f:
                    t2, t3 = datetime.strptime(alm_i, fmt), datetime.strptime(alm_f, fmt)
                    t_trabalhado = (t2 - t1) + (t4 - t3)
                elif not alm_i and not alm_f:
                    t_trabalhado = t4 - t1
            
            saldo = t_trabalhado - timedelta(hours=meta_horas)
            
            # Formatação bonita
            sinal = "+" if saldo.total_seconds() >= 0 else "-"
            total_sec = abs(int(saldo.total_seconds()))
            str_saldo = f"{sinal}{total_sec//3600:02d}:{(total_sec%3600)//60:02d}"
            
            trab_sec = int(t_trabalhado.total_seconds())
            str_trab = f"{trab_sec//3600:02d}:{(trab_sec%3600)//60:02d}"
            
            return f"{nome_dia} ({meta_horas}h)", str_trab, str_saldo
        except:
            return "Erro", "---", "---"

    resultados = df_usuario.apply(processar_linha, axis=1, result_type='expand')
    if not results_vazios(resultados):
        df_usuario[['Dia', 'Horas', 'Saldo']] = resultados
        return df_usuario[['Data', 'Dia', 'Entrada', 'Almoco_Inicio', 'Almoco_Fim', 'Saida', 'Horas', 'Saldo']].sort_values(by='Data', ascending=False)
    return df_usuario

def results_vazios(res):
    return res.empty

# --- GESTÃO DE SESSÃO (LOGIN) ---
if 'logado' not in st.session_state:
    st.session_state['logado'] = False
    st.session_state['usuario'] = ""
    st.session_state['nome'] = ""

# --- INTERFACE PRINCIPAL ---

if not st.session_state['logado']:
    # TELA DE LOGIN / CADASTRO
    st.title("🔐 Acesso ao Ponto")
    tab_login, tab_cadastro = st.tabs(["Entrar", "Criar Conta"])
    
    with tab_login:
        user_input = st.text_input("Usuário")
        pass_input = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            sucesso, nome_real = verificar_login(user_input, pass_input)
            if sucesso:
                st.session_state['logado'] = True
                st.session_state['usuario'] = user_input
                st.session_state['nome'] = nome_real
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos.")

    with tab_cadastro:
        st.warning("Crie um usuário único.")
        novo_user = st.text_input("Novo Usuário (Login)")
        nova_senha = st.text_input("Nova Senha", type="password")
        novo_nome = st.text_input("Seu Nome Completo")
        if st.button("Cadastrar"):
            if novo_user and nova_senha and novo_nome:
                if cadastrar_usuario(novo_user, nova_senha, novo_nome):
                    st.success("Cadastrado com sucesso! Faça login na aba ao lado.")
                else:
                    st.error("Erro: Usuário já existe.")
            else:
                st.error("Preencha todos os campos.")

else:
    # SISTEMA LOGADO
    col_logout, _ = st.columns([1, 5])
    if col_logout.button("🚪 Sair"):
        st.session_state['logado'] = False
        st.rerun()

    st.title(f"Olá, {st.session_state['nome']}! 👋")
    exibir_relogio_real()

    tab1, tab2 = st.tabs(["📝 Bater Ponto", "📊 Meu Espelho"])

    with tab1:
        st.write("---")
        c1, c2 = st.columns(2)
        usuario_atual = st.session_state['usuario']
        
        with c1:
            if st.button("▶️ 1. Entrada", use_container_width=True): registrar_ponto("Entrada", usuario_atual)
            if st.button("🍽️ 2. Saída Almoço", use_container_width=True): registrar_ponto("Almoco_Inicio", usuario_atual)
        with c2:
            if st.button("🔙 3. Volta Almoço", use_container_width=True): registrar_ponto("Almoco_Fim", usuario_atual)
            if st.button("🛑 4. Saída Geral", use_container_width=True): registrar_ponto("Saida", usuario_atual)

    with tab2:
        st.write("### Seus registros:")
        if st.button("🔄 Atualizar"): st.rerun()
        
        df_espelho = calcular_espelho(st.session_state['usuario'])
        
        if not df_espelho.empty:
            def highlight_saldo(val):
                color = 'green' if '+' in str(val) else ('red' if '-' in str(val) else 'black')
                return f'color: {color}; font-weight: bold'
            
            st.dataframe(df_espelho.style.map(highlight_saldo, subset=['Saldo']), use_container_width=True)
        else:
            st.info("Nenhum registro encontrado para você.")