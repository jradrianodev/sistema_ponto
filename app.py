import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import streamlit.components.v1 as components
import time

# --- BLOQUEIO DE CELULAR (CSS) ---
st.markdown("""
    <style>
    /* Se a tela for menor que 768px (tamanho comum de tablets/celulares) */
    @media (max-width: 768px) {
        
        /* Esconde todo o conteúdo do app */
        .stApp {
            display: none;
        }
        
        /* Mostra uma mensagem de aviso */
        body::before {
            content: '🚫 Acesso bloqueado via Celular. Por favor, acesse este sistema pelo Computador.';
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            width: 100vw;
            background-color: #0e1117; /* Cor de fundo escura */
            color: #ff4b4b; /* Cor do texto (vermelho do Streamlit) */
            font-size: 24px;
            font-weight: bold;
            text-align: center;
            position: fixed;
            top: 0;
            left: 0;
            z-index: 9999;
            padding: 20px;
        }
    }
    </style>
    """, unsafe_allow_html=True)

# --- Configurações ---
NOME_PLANILHA = "Controle de Ponto"
FUSO_BRASIL = timezone(timedelta(hours=-3))

st.set_page_config(page_title="Ponto Multi-Usuário", page_icon="👥", layout="wide")

# --- 🎨 GESTÃO DE TEMAS (NOVO) ---
def gerenciar_tema():
    # Se não existir no session_state, define padrão como 'Sistema'
    if 'tema_escolhido' not in st.session_state:
        st.session_state['tema_escolhido'] = 'Sistema'

    # Cria o seletor na barra lateral
    tema = st.sidebar.radio(
        "Tema da Interface",
        ["Sistema", "Claro", "Escuro"],
        index=["Sistema", "Claro", "Escuro"].index(st.session_state['tema_escolhido']),
        horizontal=True
    )
    st.session_state['tema_escolhido'] = tema

    # Definição das Cores (CSS Variables do Streamlit)
    css_claro = """
    <style>
        :root {
            --primary-color: #ff4b4b;
            --background-color: #ffffff;
            --secondary-background-color: #f0f2f6;
            --text-color: #31333F;
            --font: sans-serif;
        }
    </style>
    """
    
    css_escuro = """
    <style>
        :root {
            --primary-color: #ff4b4b;
            --background-color: #0e1117;
            --secondary-background-color: #262730;
            --text-color: #fafafa;
            --font: sans-serif;
        }
        /* Ajuste para inputs ficarem visíveis no escuro */
        .stTextInput input { color: #fafafa !important; }
    </style>
    """

    # Injeta o CSS baseado na escolha
    if tema == "Claro":
        st.markdown(css_claro, unsafe_allow_html=True)
    elif tema == "Escuro":
        st.markdown(css_escuro, unsafe_allow_html=True)
    # Se for "Sistema", não injetamos nada e deixamos o padrão do navegador.

# --- HTML/JS para Relógio ---
def exibir_relogio_real():
    # Detecta se o tema escolhido é escuro para ajustar a cor do texto do relógio
    cor_fundo = "#262730" if st.session_state.get('tema_escolhido') == 'Escuro' else "#f0f2f6"
    cor_texto = "#ffffff" if st.session_state.get('tema_escolhido') == 'Escuro' else "#333333"
    
    relogio_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        body {{ font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 80px; margin: 0; background-color: transparent; }}
        .container {{ background-color: {cor_fundo}; padding: 10px 20px; border-radius: 10px; text-align: center; border: 1px solid #dcdcdc; }}
        .clock {{ font-size: 24px; font-weight: bold; color: #0068c9; font-family: 'Courier New', monospace; }}
        .label {{ color: {cor_texto}; font-size: 12px; margin-bottom: 5px;}}
    </style>
    </head>
    <body>
        <div class="container">
            <div class="clock" id="clock">Carregando...</div>
        </div>
        <script>
            function updateClock() {{
                var now = new Date();
                var utc = now.getTime() + (now.getTimezoneOffset() * 60000);
                var brasiliaTime = new Date(utc + (3600000 * -3));
                var timeString = brasiliaTime.toLocaleTimeString('pt-BR', {{ hour12: false }});
                document.getElementById('clock').innerHTML = "🕒 " + timeString;
            }}
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
        return False
    sheet.append_row([username, senha, nome])
    return True

# --- Lógica de Ponto ---
def registrar_ponto(tipo_coluna, usuario_atual):
    sheet = conectar_gsheets("Página1")
    if not sheet: return

    agora = datetime.now(FUSO_BRASIL)
    data_hoje = agora.strftime("%Y-%m-%d")
    hora_agora = agora.strftime("%H:%M:%S")
    
    dados = sheet.get_all_records()
    df = pd.DataFrame(dados)
    colunas_map = {"Entrada": 3, "Almoco_Inicio": 4, "Almoco_Fim": 5, "Saida": 6}
    col_num = colunas_map[tipo_coluna]

    with st.spinner('Registrando...'):
        if not df.empty:
            df['Data'] = df['Data'].astype(str)
            df['Usuario'] = df['Usuario'].astype(str)
            filtro = (df['Data'] == data_hoje) & (df['Usuario'] == usuario_atual)
            linha_index = df.index[filtro].tolist()
        else:
            linha_index = []

        if not linha_index:
            nova_linha = [usuario_atual, data_hoje, "", "", "", ""]
            nova_linha[col_num - 1] = hora_agora
            sheet.append_row(nova_linha)
            st.success(f"✅ Dia iniciado para {usuario_atual}!")
        else:
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
    
    df['Usuario'] = df['Usuario'].astype(str)
    df_usuario = df[df['Usuario'] == usuario_atual].copy()
    if df_usuario.empty: return pd.DataFrame()

    def processar_linha(row):
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
            sinal = "+" if saldo.total_seconds() >= 0 else "-"
            total_sec = abs(int(saldo.total_seconds()))
            str_saldo = f"{sinal}{total_sec//3600:02d}:{(total_sec%3600)//60:02d}"
            trab_sec = int(t_trabalhado.total_seconds())
            str_trab = f"{trab_sec//3600:02d}:{(trab_sec%3600)//60:02d}"
            return f"{nome_dia} ({meta_horas}h)", str_trab, str_saldo
        except:
            return "Erro", "---", "---"

    resultados = df_usuario.apply(processar_linha, axis=1, result_type='expand')
    if not resultados.empty:
        df_usuario[['Dia', 'Horas', 'Saldo']] = resultados
        return df_usuario[['Data', 'Dia', 'Entrada', 'Almoco_Inicio', 'Almoco_Fim', 'Saida', 'Horas', 'Saldo']].sort_values(by='Data', ascending=False)
    return df_usuario

# --- SESSÃO E LOGIN ---
if 'logado' not in st.session_state:
    st.session_state['logado'] = False
    st.session_state['usuario'] = ""
    st.session_state['nome'] = ""

# --- APLICA O TEMA ANTES DE TUDO ---
gerenciar_tema()

if not st.session_state['logado']:
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
                st.error("Dados incorretos.")
    with tab_cadastro:
        st.warning("Crie um usuário único.")
        n_user = st.text_input("Novo Usuário")
        n_pass = st.text_input("Nova Senha", type="password")
        n_nome = st.text_input("Nome Completo")
        if st.button("Cadastrar"):
            if cadastrar_usuario(n_user, n_pass, n_nome):
                st.success("Sucesso! Faça login.")
            else:
                st.error("Usuário já existe.")
else:
    # BARRA LATERAL (Logout)
    st.sidebar.write(f"👤 **{st.session_state['nome']}**")
    if st.sidebar.button("🚪 Sair"):
        st.session_state['logado'] = False
        st.rerun()

    st.title("Sistema de Ponto")
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
                # Ajuste para ficar legível no modo escuro também
                if st.session_state['tema_escolhido'] == 'Escuro' and color == 'black':
                    color = 'white'
                return f'color: {color}; font-weight: bold'
            
            st.dataframe(df_espelho.style.map(highlight_saldo, subset=['Saldo']), use_container_width=True)
        else:
            st.info("Sem registros.")