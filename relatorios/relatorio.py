import re
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import plotly.express as px
from io import BytesIO

# Função para detectar dispositivos móveis
def is_mobile():
    """Detecta se o dispositivo é móvel baseado no User-Agent"""
    import re
    # Como não temos acesso direto ao User-Agent no Streamlit Cloud,
    # usamos uma abordagem simplificada baseada na session_state
    if 'is_mobile' in st.session_state:
        return st.session_state['is_mobile']
    # Valor padrão - assumir desktop
    return False

# Configuração da página - modo wide
st.set_page_config(
    page_title="Relatório de Produção",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed" if is_mobile() else "expanded"
)

# Caminho do arquivo compartilhado no ambiente do deploy
SHARED_UPLOAD_PATH = "shared_buffer_data.xlsx"

# Inicializar o buffer no session_state
if "buffer" not in st.session_state:
    st.session_state["buffer"] = None

# ===== Inicializar session_state flags =====
if "centro_sel" not in st.session_state:
    st.session_state["centro_sel"] = None

# ----------------- Funções auxiliares -----------------
def t(hhmm):
    return datetime.strptime(hhmm, "%H:%M").time()

def data_produtiva(dt):
    if pd.isna(dt):
        return pd.NaT
    return pd.Timestamp(dt.date()) if dt.time() >= t("06:00") else pd.Timestamp((dt - timedelta(days=1)).date())

def atribuir_turno(datahora, centro_trabalho, prod_date):
    if pd.isna(datahora) or pd.isna(prod_date):
        return "Indefinido"
    hora = datahora.time()
    sab = prod_date.weekday() == 5
    if str(centro_trabalho).startswith("GR"):
        return "Turno Dia (GR)" if t("06:00") <= hora < t("18:00") else "Turno Noite (GR)"
    if t("06:00") <= hora < t("14:20"):
        return "Turno 1"
    if t("14:20") <= hora < (t("22:13") if sab else t("22:40")):
        return "Turno 2"
    return "Turno 3"

def intervalo_turno(prod_date, turno, centro_trabalho):
    sab = prod_date.weekday() == 5
    if str(centro_trabalho).startswith("GR"):
        if "Dia" in turno:
            return (datetime.combine(prod_date.date(), t("06:00")),
                    datetime.combine(prod_date.date(), t("18:00")))
        else:
            return (datetime.combine(prod_date.date(), t("18:00")),
                    datetime.combine((prod_date + timedelta(days=1)).date(), t("06:00")))
    if turno == "Turno 1":
        return (datetime.combine(prod_date.date(), t("06:00")),
                datetime.combine(prod_date.date(), t("14:20")))
    if turno == "Turno 2":
        fim_hora = "22:13" if sab else "22:40"
        return (datetime.combine(prod_date.date(), t("14:20")),
                datetime.combine(prod_date.date(), t(fim_hora)))
    ini_hora = "22:13" if sab else "22:40"
    return (datetime.combine(prod_date.date(), t(ini_hora)),
            datetime.combine((prod_date + timedelta(days=1)).date(), t("06:00")))

def horas_para_hhmm(horas):
    if pd.isna(horas):
        return ""
    total_min = int(round(horas * 60))
    return f"{total_min // 60:02d}:{total_min % 60:02d}"

def cor_eficiencia(val):
    if pd.isna(val): return ''
    if val >= 90:
        return 'background-color: #d4edda;'  # verde claro
    elif val >= 80:
        return 'background-color: #fff3cd;'  # amarelo claro
    else:
        return 'background-color: #f8d7da;'  # vermelho claro

# ----------------- Entrada -----------------
st.title("📊 Relatório de Produção")

source = st.sidebar.selectbox("Fonte de dados", ["Upload (Excel)", "Banco de Dados (SQL)", "Arquivos locais"], index=0)

df = None
vel = None
vel_path = os.path.join("relatorios", "static", "Velocidade.xlsx")

# Caminho para salvar o arquivo enviado pela conta do deploy
deploy_file_path = os.path.join("static", "registros.xlsx")

# Caminho para salvar o arquivo enviado localmente
local_file_path = "registros_local.xlsx"

# Upload de arquivo pelo usuário

# No início do app, após as importações
upload_option = st.sidebar.radio("Selecione a ação:", ["Ver dados existentes", "Fazer upload de novo arquivo"])

if upload_option == "Fazer upload de novo arquivo":
    reg_file = st.sidebar.file_uploader("Upload: arquivo de registros (Excel)", type=["xls", "xlsx"], key="new_upload")
    if reg_file is not None:

        try:
            # 1. Salvar o arquivo enviado no local compartilhado
            with open(SHARED_UPLOAD_PATH, "wb") as f:
                f.write(reg_file.getbuffer())
            
            # 2. Carregar o arquivo no DataFrame atual
            df_user = pd.read_excel(SHARED_UPLOAD_PATH, engine="openpyxl")
            st.success("✅ Arquivo carregado e disponível para todos os usuários.")
            
            # 3. Armazenar na sessão atual também
            st.session_state["buffer"] = BytesIO(reg_file.read())
            
            # Atribuir ao DataFrame principal
            df = df_user
        except Exception as e:
            st.error(f"Falha ao processar arquivo: {str(e)}")
# Verificar se existe arquivo compartilhado
elif os.path.exists(SHARED_UPLOAD_PATH):
    try:
        # Carregar dados do arquivo compartilhado
        df = pd.read_excel(SHARED_UPLOAD_PATH, engine="openpyxl")
        st.sidebar.info("📄 Usando dados compartilhados do último upload.")
    except Exception as e:
        st.sidebar.error(f"Erro ao carregar arquivo compartilhado: {str(e)}")
else:
    st.sidebar.warning("⚠️ Nenhum arquivo de dados compartilhado disponível. Faça o upload.")

if os.path.exists(vel_path):
    try:
        vel = pd.read_excel(vel_path)
        if vel.empty:
            st.sidebar.warning("A planilha de velocidades está vazia — velocidades serão tratadas como faltantes.")
        else:
            st.sidebar.success(f"Arquivo de velocidades carregado de static/: {vel_path}")
    except Exception as e:
        vel = pd.DataFrame()
        st.sidebar.error(f"Falha ao ler velocidade em static/: {e}")
else:
    vel = pd.DataFrame()
    st.sidebar.error(f"Arquivo de velocidades não encontrado em: {vel_path}")

if df is None:
    df = pd.DataFrame()
if vel is None:
    vel = pd.DataFrame()

# ----------------- Processamento (quando há registros) -----------------
if not df.empty:
    if vel.empty:
        st.sidebar.warning("A planilha de velocidades (static) não foi encontrada ou está vazia — velocidades serão tratadas como faltantes.")
    df.columns = df.columns.str.strip()
    vel.columns = vel.columns.str.strip()

    def parse_dt(data_col, hora_col):
        return pd.to_datetime(
            df[data_col].astype(str).str.strip() + " " +
            df[hora_col].astype(str).str.strip(),
            format="%d/%m/%Y %H:%M:%S", errors="coerce"
        )

    df["DataHoraInicio"] = parse_dt("Data Início", "Hora Início")
    df["DataHoraFim"] = parse_dt("Data Término", "Hora Fim")
    df["DataProd"] = df["DataHoraInicio"].apply(data_produtiva)
    df["Turno"] = df.apply(lambda r: atribuir_turno(r["DataHoraInicio"], r["Centro Trabalho"], r["DataProd"]), axis=1)

    df["Conc"] = df["Centro Trabalho"].astype(str).str.strip() + "-" + df["Roteiro"].astype(str).str.strip()
    vel = vel.rename(columns={"Vel Padrão/Ideal": "Velocidade Padrão"})

    def atribuir_roteiros(df, vel):
        """
        Atribui roteiros genéricos para diversos centros de trabalho baseado em regras específicas:
        - CA05: Baseado na quantidade aprovada (≤18000: 50000, >18000: 70000)
        - CA04: Operação "Pre Vincagem" - velocidade 60000
        - CA16: Operação "Pre Vincagem" - velocidade 100000 (50000*2)
        - CA15: Operação "Aplic Ink-Jet / Colagem" - velocidade 10000
        - CA09: Qualquer operação diferente de "Colagem" - velocidade 12000
        - CA01: Qualquer operação com roteiro vazio - velocidade 9000
        
        Args:
            df: DataFrame principal com registros de produção
            vel: DataFrame de velocidades
        
        Returns:
            DataFrame com roteiros atualizados e tabela de velocidades atualizada
        """
        # Trabalhar com uma cópia para não afetar o original durante o processamento
        df = df.copy()
        
        # Contador para roteiros atribuídos
        roteiros_atribuidos = 0
        
        # ----- Regra 1: CA05 (baseada em Qtd Aprovada) -----
        registros_ca05_sem_roteiro = df[
            (df["Centro Trabalho"] == "CA05") & 
            (df["Roteiro"].isna() | (df["Roteiro"] == ""))
        ]

        if not registros_ca05_sem_roteiro.empty:
            itens_unicos = {}
            for _, row in registros_ca05_sem_roteiro.iterrows():
                item = row["Descrição Item"]
    
                # Converte o valor de Qtd Aprovada para número, com segurança
                try:
                    qtd_aprovada = float(row["Qtd Aprovada"])
                except (ValueError, TypeError):
                    continue  # pula se não for possível converter
        
                if item not in itens_unicos:
                    itens_unicos[item] = {
                        "qtd": qtd_aprovada,
                        "roteiro": "RAPIDO" if qtd_aprovada <= 18000 else "LENTO",
                        "velocidade": 50000 if qtd_aprovada <= 18000 else 70000
                    }
            # Atribuir roteiros e atualizar o DataFrame
            for item, info in itens_unicos.items():
                mask = (
                    (df["Centro Trabalho"] == "CA05") & 
                    (df["Descrição Item"] == item) & 
                    (df["Roteiro"].isna() | (df["Roteiro"] == ""))
                )
                
                df.loc[mask, "Roteiro"] = info["roteiro"]
                df.loc[mask, "Conc"] = df.loc[mask, "Centro Trabalho"].astype(str) + "-" + df.loc[mask, "Roteiro"].astype(str)
                
            # Atualizar velocidades
            for item, info in itens_unicos.items():
                conc = f"CA05-{info['roteiro']}"
                if conc not in vel["Conc"].values:
                    nova_vel = pd.DataFrame({
                        "Conc": [conc],
                        "Velocidade Padrão": [info["velocidade"]]
                    })
                    vel = pd.concat([vel, nova_vel], ignore_index=True)
                    
            roteiros_atribuidos += len(itens_unicos)
            
        # ----- Regra 2: CA04 e CA16 (Pre Vincagem) -----
        # CA04 - Pre Vincagem - 60000
        mask_ca04 = (
            (df["Centro Trabalho"] == "CA04") & 
            (df["Descrição Operação"] == "Pre Vincagem") &
            (df["Roteiro"].isna() | (df["Roteiro"] == ""))
        )
        if mask_ca04.any():
            df.loc[mask_ca04, "Roteiro"] = "PREVINCAGEM"
            df.loc[mask_ca04, "Conc"] = "CA04-PREVINCAGEM"
            if "CA04-PREVINCAGEM" not in vel["Conc"].values:
                nova_vel = pd.DataFrame({
                    "Conc": ["CA04-PREVINCAGEM"],
                    "Velocidade Padrão": [120000]
                })
                vel = pd.concat([vel, nova_vel], ignore_index=True)
            roteiros_atribuidos += mask_ca04.sum()
        
        # CA16 - Pre Vincagem - 50000*2 = 100000
        mask_ca16 = (
            (df["Centro Trabalho"] == "CA16") & 
            (df["Descrição Operação"] == "Pre Vincagem") &
            (df["Roteiro"].isna() | (df["Roteiro"] == ""))
        )
        if mask_ca16.any():
            df.loc[mask_ca16, "Roteiro"] = "PREVINCAGEM"
            df.loc[mask_ca16, "Conc"] = "CA16-PREVINCAGEM"
            if "CA16-PREVINCAGEM" not in vel["Conc"].values:
                nova_vel = pd.DataFrame({
                    "Conc": ["CA16-PREVINCAGEM"],
                    "Velocidade Padrão": [100000]
                })
                vel = pd.concat([vel, nova_vel], ignore_index=True)
            roteiros_atribuidos += mask_ca16.sum()
        
        # ----- Regra 3: CA15 (Aplic Ink-Jet / Colagem) -----
        mask_ca15 = (
            (df["Centro Trabalho"] == "CA15") & 
            (df["Descrição Operação"] == "Aplic Ink-Jet / Colagem") &
            (df["Roteiro"].isna() | (df["Roteiro"] == ""))
        )
        if mask_ca15.any():
            df.loc[mask_ca15, "Roteiro"] = "INKJET"
            df.loc[mask_ca15, "Conc"] = "CA15-INKJET"
            if "CA15-INKJET" not in vel["Conc"].values:
                nova_vel = pd.DataFrame({
                    "Conc": ["CA15-INKJET"],
                    "Velocidade Padrão": [10000]
                })
                vel = pd.concat([vel, nova_vel], ignore_index=True)
            roteiros_atribuidos += mask_ca15.sum()
        
        # ----- Regra 4: CA09 (Qualquer operação diferente de Colagem) -----
        mask_ca09 = (
            (df["Centro Trabalho"] == "CA09") & 
            (df["Descrição Operação"] != "Colagem") &
            (df["Roteiro"].isna() | (df["Roteiro"] == ""))
        )
        if mask_ca09.any():
            df.loc[mask_ca09, "Roteiro"] = "GERAL"
            df.loc[mask_ca09, "Conc"] = "CA09-GERAL"
            if "CA09-GERAL" not in vel["Conc"].values:
                nova_vel = pd.DataFrame({
                    "Conc": ["CA09-GERAL"],
                    "Velocidade Padrão": [12000]
                })
                vel = pd.concat([vel, nova_vel], ignore_index=True)
            roteiros_atribuidos += mask_ca09.sum()
            
         mask_ca01 = (
            (df["Centro Trabalho"] == "CA01") & 
            (df["Roteiro"].isna() | (df["Roteiro"] == ""))
        )
        mask_ca01 = (
            (df["Centro Trabalho"] == "CA01") & 
            (df["Roteiro"].isna() | (df["Roteiro"] == ""))
        )
        if mask_ca01.any():
            df.loc[mask_ca01, "Roteiro"] = "GERAL"
            df.loc[mask_ca01, "Conc"] = "CA01-GERAL"
            if "CA01-GERAL" not in vel["Conc"].values:
                nova_vel = pd.DataFrame({
                    "Conc": ["CA01-GERAL"],
                    "Velocidade Padrão": [9000]
                })
                vel = pd.concat([vel, nova_vel], ignore_index=True)
            roteiros_atribuidos += mask_ca01.sum()
            
        if roteiros_atribuidos > 0:
            st.success(f"Roteiros atribuídos para {roteiros_atribuidos} registros sem roteiro definido")
        
        return df, vel    
    # Aplicar regra para CA05
    df, vel = atribuir_roteiros(df, vel)

    df = df[df["Centro Trabalho"].str.startswith("CA", na=False)].copy()

    data_sugerida = df["DataProd"].min().date() if pd.notna(df["DataProd"].min()) else datetime.today().date()
    data_base = st.date_input("📆 Data produtiva (06→06)", value=data_sugerida)
    janela_ini = datetime.combine(data_base, t("06:00"))
    janela_fim = janela_ini + timedelta(days=1)
    st.caption(f"Janela ativa: {janela_ini:%d/%m/%Y %H:%M} → {janela_fim:%d/%m/%Y %H:%M}")

    df = df[df["DataProd"] == pd.Timestamp(data_base)].copy()

    df["MinEvento"] = (df["DataHoraFim"] - df["DataHoraInicio"]).dt.total_seconds().div(60).fillna(0)

    df["Parada Real Útil"] = pd.to_numeric(
        df.get("Parada Real Útil", 0).astype(str).str.replace(",", "."),
        errors="coerce"
    ).fillna(0)

    sample = df.loc[df["Tipo Registro"] == "Reporte de Parada", "Parada Real Útil"]
    max_val = float(sample.max()) if not sample.empty else 0.0
    med_val = float(sample.median()) if not sample.empty else 0.0
    assume_minutes = (med_val > 24) or (max_val > 48)

    if assume_minutes:
        df["Parada_min"] = df["Parada Real Útil"]
        df["Parada_h"] = df["Parada_min"] / 60.0
    else:
        df["Parada_h"] = df["Parada Real Útil"]
        df["Parada_min"] = df["Parada_h"] * 60.0

    paradas_globais = (
        df[df["Tipo Registro"] == "Reporte de Parada"]
        .groupby(["Centro Trabalho", "Turno", "DataProd"])["MinEvento"]
        .sum()
        .reset_index(name="Paradas_min")
    )

    paradas_detalhe = (
        df[df["Tipo Registro"] == "Reporte de Parada"]
        .groupby(["Centro Trabalho", "Turno", "DataProd", "Descrição Parada"])["Parada_min"]
        .sum()
        .reset_index()
        .sort_values("Parada_min", ascending=False)
    )

    paradas_detalhe["Parada_h"] = paradas_detalhe["Parada_min"] / 60.0
    paradas_detalhe["Parada_fmt"] = paradas_detalhe["Parada_h"].apply(horas_para_hhmm)

    # Atualizar criação do DataFrame `prod` para incluir `DataHoraFim`
    prod = (
        df[df["Tipo Registro"] == "Reporte de Produção"]
        .groupby(["Centro Trabalho", "Turno", "DataProd", "Conc", "Descrição Item", "DataHoraInicio", "DataHoraFim"])["Qtd Aprovada"]
        .sum()
        .reset_index()
    )
    # Antes do merge
    # Garantir que os valores de Conc são strings e bem formatados
    vel.columns = vel.columns.str.strip()
    prod["Conc"] = prod["Conc"].astype(str).str.strip()
    vel["Conc"] = vel["Conc"].astype(str).str.strip()
    
    # Debug: verificar valores de Conc em cada DataFrame
    print("Conc em prod:", prod["Conc"].unique())
    print("Conc em vel:", vel["Conc"].unique())
    
    # Verificar se a coluna Velocidade Padrão existe
    if "Velocidade Padrão" not in vel.columns:
        st.warning("Coluna 'Velocidade Padrão' não encontrada na planilha. Disponíveis: " + ", ".join(vel.columns))
        # Criar coluna padrão para evitar erro
        vel["Velocidade Padrão"] = 0
    
    # Realizar o merge com logs
    prod = prod.merge(vel[["Conc", "Velocidade Padrão"]], on="Conc", how="left")
    
    # Verificar se houve valores nulos após o merge
    missing_vel = prod["Velocidade Padrão"].isna().sum()
    if missing_vel > 0:
        st.warning(f"Atenção: {missing_vel} registros ficaram sem velocidade padrão após o merge.")
        # Mostrar quais Conc não encontraram correspondência
        missing_concs = prod[prod["Velocidade Padrão"].isna()]["Conc"].unique()
        if len(missing_concs) <= 10:  # Limite para não sobrecarregar a UI
            st.info(f"Conc sem correspondência: {', '.join(missing_concs)}")
        else:
            st.info(f"Há {len(missing_concs)} valores de Conc sem correspondência.")
    
    # Garantir tipo numérico para Velocidade Padrão
    prod["Velocidade Padrão"] = pd.to_numeric(prod["Velocidade Padrão"], errors="coerce").fillna(0)

    # Criar DataFrame com os itens produzidos por centro e turno
    if not prod.empty and "Descrição Item" in prod.columns:
        itens_por_centro_turno = (
            prod[["Centro Trabalho", "Turno", "DataProd", "Descrição Item"]]
            .drop_duplicates()
            .groupby(["Centro Trabalho", "Turno", "DataProd"])
            ["Descrição Item"]
            .apply(list)
            .reset_index()
        )
    else:
        itens_por_centro_turno = pd.DataFrame(columns=["Centro Trabalho", "Turno", "Descrição Item"])

    # Antes de agrupar, garantir tipos numéricos
    prod["Qtd Aprovada"] = pd.to_numeric(prod["Qtd Aprovada"], errors="coerce").fillna(0)
    prod["Velocidade Padrão"] = pd.to_numeric(prod["Velocidade Padrão"], errors="coerce").fillna(0)
    
    # Debug: verificar se a coluna existe e tem valores
    print("Coluna Velocidade Padrão existe:", "Velocidade Padrão" in prod.columns)
    print("Valores em Velocidade Padrão:", prod["Velocidade Padrão"].describe())

    # Agrupamento com verificação de erros
    try:
        resumo_turno = prod.groupby(["Centro Trabalho", "Turno", "DataProd"]).agg(
            Produzido=("Qtd Aprovada", "sum"),
            Vel_padrao_media=("Velocidade Padrão", "mean")
        ).reset_index()
    
        # Verificar se o resultado contém NaN
        if resumo_turno["Vel_padrao_media"].isna().any():
            st.warning("Alguns centros/turnos ficaram sem velocidade padrão média")
    except Exception as e:
        st.error(f"Erro ao agrupar por centro e turno: {str(e)}")
        # Criar um resumo_turno vazio para evitar erros posteriores
        resumo_turno = pd.DataFrame(columns=["Centro Trabalho", "Turno", "DataProd", 
                                            "Produzido", "Vel_padrao_media"])

    resumo_turno = resumo_turno.merge(paradas_globais, on=["Centro Trabalho", "Turno", "DataProd"], how="left")
    resumo_turno["Paradas_min"] = resumo_turno["Paradas_min"].fillna(0)
    resumo_turno["Paradas_h"] = resumo_turno["Paradas_min"] / 60.0
    
    # ADICIONE ESTE AJUSTE AQUI - Dobrar a velocidade padrão para CA12
    resumo_turno.loc[resumo_turno["Centro Trabalho"] == "CA12", "Vel_padrao_media"] *= 2
    
    # ADICIONE ESTA VERIFICAÇÃO - Garantir que não há velocidades zero
    if (resumo_turno["Vel_padrao_media"] <= 0).any():
        print("⚠️ ATENÇÃO: Encontradas velocidades padrão zeradas ou negativas!")
        # Substituir por um valor padrão conservador (20000) para evitar divisões por zero
        resumo_turno.loc[resumo_turno["Vel_padrao_media"] <= 0, "Vel_padrao_media"] = 20000
        
    
    resumo_turno["Duracao_turno_h"] = resumo_turno.apply(
        lambda r: (intervalo_turno(r["DataProd"], r["Turno"], r["Centro Trabalho"])[1] -
                   intervalo_turno(r["DataProd"], r["Turno"], r["Centro Trabalho"])[0]).total_seconds() / 3600,
        axis=1
    )
    
    resumo_turno["Tempo_liquido_h"] = (resumo_turno["Duracao_turno_h"] - resumo_turno["Paradas_h"]).clip(lower=0)
    resumo_turno["Prod_prevista"] = resumo_turno["Vel_padrao_media"] * resumo_turno["Tempo_liquido_h"]
    resumo_turno["Prod_deveria"] = resumo_turno["Prod_prevista"]
    
    # CORRIGIDO - Proteger contra divisão por zero
    resumo_turno["Tempo_liquido_h_safe"] = resumo_turno["Tempo_liquido_h"].replace(0, np.nan)
    resumo_turno["Vel_real"] = resumo_turno["Produzido"] / resumo_turno["Tempo_liquido_h_safe"]
    
    # CORRIGIDO - Proteger cálculo de eficiência
    resumo_turno["Eficiencia_%"] = np.where(
        (resumo_turno["Vel_padrao_media"] > 0) & (resumo_turno["Vel_real"].notna()),
        (resumo_turno["Vel_real"] / resumo_turno["Vel_padrao_media"]) * 100,
        np.nan
    )
    
    # Limitação de valores extremos
    resumo_turno["Eficiencia_%"] = resumo_turno["Eficiencia_%"].clip(lower=0, upper=999.99)
    
    # ===== Cálculo de Eficiência e Produção Prevista =====
    
    # Filtrar paradas obrigatórias
    paradas_obrigatorias = ["REFEIÇÕES", "ACERTO", "TESTE", "PRODUÇÃO INTERROMPIDA"]
    paradas_obrigatorias_df = (
        paradas_detalhe[paradas_detalhe["Descrição Parada"].isin(paradas_obrigatorias)]
        .groupby(["Centro Trabalho", "Turno", "DataProd"])["Parada_h"]
        .sum()
        .reset_index(name="Paradas_obrigatorias_h")
    )
    
    # Mesclar paradas obrigatórias ao resumo_turno
    resumo_turno = resumo_turno.merge(paradas_obrigatorias_df, on=["Centro Trabalho", "Turno", "DataProd"], how="left")
    resumo_turno["Paradas_obrigatorias_h"] = resumo_turno["Paradas_obrigatorias_h"].fillna(0)
    
    # Recalcular tempo disponível máximo para produção
    resumo_turno["Tempo_disponivel_h"] = (resumo_turno["Duracao_turno_h"] - resumo_turno["Paradas_obrigatorias_h"]).clip(lower=0)
    
    # Produção prevista ajustada (descontando apenas paradas obrigatórias)
    resumo_turno["Prod_prevista_ajustada"] = resumo_turno["Vel_padrao_media"] * resumo_turno["Tempo_disponivel_h"]
    
    # ===== Cálculo de Eficiência Geral e Ajustada =====
    
    # CORRIGIDO - Eficiência geral com proteção contra divisão por zero
    resumo_turno["Eficiencia_geral_%"] = np.where(
        resumo_turno["Prod_prevista"] > 0,
        (resumo_turno["Produzido"] / resumo_turno["Prod_prevista"]) * 100,
        np.nan
    )
    
    # CORRIGIDO - Eficiência ajustada com proteção contra divisão por zero
    resumo_turno["Eficiencia_ajustada_%"] = np.where(
        resumo_turno["Prod_prevista_ajustada"] > 0,
        (resumo_turno["Produzido"] / resumo_turno["Prod_prevista_ajustada"]) * 100,
        np.nan
    )
    
    # Limitação de valores extremos
    resumo_turno["Eficiencia_geral_%"] = resumo_turno["Eficiencia_geral_%"].clip(lower=0, upper=999.99)
    resumo_turno["Eficiencia_ajustada_%"] = resumo_turno["Eficiencia_ajustada_%"].clip(lower=0, upper=999.99)
    
    # Produção prevista geral (considerando todas as paradas)
    resumo_turno["Prod_prevista_geral"] = resumo_turno["Vel_padrao_media"] * resumo_turno["Tempo_liquido_h"]

    # ----------------- Renomear colunas para exibição (helper) -----------------
    COL_RENAMES = {
        "Centro Trabalho": "Centro",
        "Produzido": "Produzido",
        "Produzido_total": "Produção Total",
        "Vel_padrao_media": "Velocidade Padrão",
        "Prod_deveria": "Produção Prevista",
        "Prod_deveria_total": "Produção Prevista Total",
        "Vel_real": "Velocidade Real",
        "Vel_real_media": "Velocidade Real Média",
        "Eficiencia_%": "Eficiência (%)",
        "Ef_ponderada": "Eficiência Ponderada",
        "Ef_media": "Eficiência Média",
        "Ef_media_simples": "Eficiência Média",
        "Ef_ajustada_media": "Eficiência Ajustada Média",
        "Tempo_liquido_h": "Tempo Líquido (h)",
        "Tempo_liquido_h_total": "Tempo Líquido Total (h)",
        "Paradas_min": "Paradas (min)",
        "Paradas_min_total": "Paradas Totais (min)",
        "Paradas_h": "Paradas (h)",
        "Paradas_total_h": "Paradas Totais (h)",
        "Paradas_obrigatorias_h": "Paradas Obrigatórias (h)",
        "Duracao_turno_h": "Duração Turno (h)",
        "Turno": "Turno",
        "Turnos_ativos": "Turnos Ativos",
        "Conc": "Combinação",
        "Prod_prevista_geral": "Produção Prevista Geral",
        "Prod_prevista_ajustada": "Produção Prevista Ajustada",
        "Eficiencia_geral_%": "Eficiência Geral (%)",
        "Eficiencia_ajustada_%": "Eficiência Ajustada (%)",
        "Tempo_disponivel_h": "Tempo Disponível (h)",
        "Eficiencia_media": "Eficiência Média"
    }

    def pretty_cols(df_in):
        # Retorna cópia com colunas renomeadas para exibição (não altera df original)
        return df_in.rename(columns={k: v for k, v in COL_RENAMES.items() if k in df_in.columns})

    # NÃO sobrescrever `resumo_turno` — manter colunas originais para cálculos.
    # Criar uma cópia com nomes "bonitos" apenas para exibição quando necessário.
    resumo_turno_display = pretty_cols(resumo_turno)

# ----------------- Helpers de visualização -----------------
def medalha_html(posicao, centro, turno, produzido, eficiencia):
    estilos = {
        1: {"hex": "#FFD700", "bg": "rgba(255,215,0,0.12)", "emoji": "🥇"},
        2: {"hex": "#C0C0C0", "bg": "rgba(192,192,192,0.12)", "emoji": "🥈"},
        3: {"hex": "#CD7F32", "bg": "rgba(205,127,50,0.12)", "emoji": "🥉"},
    }
    s = estilos.get(posicao, {"hex": "#f8f9fa", "bg": "rgba(248,249,250,0.06)", "emoji": ""})
    try:
        prod_val = 0 if pd.isna(produzido) else int(round(float(produzido)))
    except Exception:
        prod_val = 0
    try:
        ef_val = 0 if pd.isna(eficiencia) else int(round(float(eficiencia)))
    except Exception:
        ef_val = 0
    return f"""
    <div style="display:flex; align-items:center; background-color:{s['bg']};
                border:2px solid {s['hex']}; border-radius:10px; padding:10px; margin-bottom:8px">
        <div style="font-size:26px; margin-right:12px">{s['emoji']}</div>
        <div style="font-size:14px; line-height:1.3">
            <strong>{posicao}º</strong> — {centro} ({turno})<br>
            Produzido: <b>{f"{prod_val:,}".replace(",", ".")}</b> | Eficiência: <b>{ef_val}%</b>
        </div>
    </div>
    """

def medalha_pior_html(posicao, centro, turno, produzido, eficiencia):
    estilos = {
        1: {"hex": "#b22222", "bg": "rgba(178,34,34,0.06)", "emoji": "🔻"},
        2: {"hex": "#ff4500", "bg": "rgba(255,69,0,0.06)", "emoji": "🔻"},
        3: {"hex": "#ff8c00", "bg": "rgba(255,140,0,0.06)", "emoji": "🔻"},
    }
    s = estilos.get(posicao, {"hex": "#6c757d", "bg": "rgba(108,117,125,0.06)", "emoji": "🔻"})
    try:
        prod_val = 0 if pd.isna(produzido) else int(round(float(produzido)))
    except Exception:
        prod_val = 0
    try:
        ef_val = 0 if pd.isna(eficiencia) else int(round(float(eficiencia)))
    except Exception:
        ef_val = 0
    return f"""
    <div style="display:flex; align-items:center; background-color:{s['bg']};
                border:2px solid {s['hex']}; border-radius:10px; padding:10px; margin-bottom:8px; opacity:0.95">
        <div style="font-size:22px; margin-right:12px">{s['emoji']}</div>
        <div style="font-size:14px; line-height:1.3">
            <strong>{posicao}º pior</strong> — {centro} ({turno})<br>
            Produzido: <b>{f"{prod_val:,}".replace(",", ".")}</b> | Eficiência: <b>{ef_val}%</b>
        </div>
    </div>
    """

# ===== Ranking Geral - Eficiência =====
st.subheader("🏆 Ranking Geral - Eficiência")
if "resumo_turno" in locals() and not resumo_turno.empty:
    top_efic = resumo_turno.dropna(subset=["Eficiencia_%"]).sort_values("Eficiencia_%", ascending=False).reset_index(drop=True)

    cols = st.columns(3)
    for i in range(3):
        with cols[i]:
            if i < len(top_efic):
                row = top_efic.iloc[i]
                st.markdown(
                    medalha_html(i+1, row.get('Centro Trabalho', '—'), row.get('Turno', '—'),
                                 row.get('Produzido', 0), row.get('Eficiencia_%', 0)),
                    unsafe_allow_html=True
                )

    def medalha_pior_html(posicao, centro, turno, produzido, eficiencia):
        estilos = {
            1: {"hex": "#b22222", "bg": "rgba(178,34,34,0.06)", "emoji": "🔻"},
            2: {"hex": "#ff4500", "bg": "rgba(255,69,0,0.06)", "emoji": "🔻"},
            3: {"hex": "#ff8c00", "bg": "rgba(255,140,0,0.06)", "emoji": "🔻"},
        }
        s = estilos.get(posicao, {"hex": "#6c757d", "bg": "rgba(108,117,125,0.06)", "emoji": "🔻"})
        try:
            prod_val = 0 if pd.isna(produzido) else int(round(float(produzido)))
        except Exception:
            prod_val = 0
        try:
            ef_val = 0 if pd.isna(eficiencia) else int(round(float(eficiencia)))
        except Exception:
            ef_val = 0
        return f"""
        <div style="display:flex; align-items:center; background-color:{s['bg']};
                    border:2px solid {s['hex']}; border-radius:10px; padding:10px; margin-bottom:8px; opacity:0.95">
            <div style="font-size:22px; margin-right:12px">{s['emoji']}</div>
            <div style="font-size:14px; line-height:1.3">
                <strong>{posicao}º pior</strong> — {centro} ({turno})<br>
                Produzido: <b>{f"{prod_val:,}".replace(",", ".")}</b> | Eficiência: <b>{ef_val}%</b>
            </div>
        </div>
        """

    bottom_efic = resumo_turno.dropna(subset=["Eficiencia_%"]).sort_values("Eficiencia_%", ascending=True).reset_index(drop=True)
    if not bottom_efic.empty:
        st.markdown("### ⤵️ 3 Piores - Eficiência")
        cols = st.columns(3)
        for i in range(3):
            with cols[i]:
                if i < len(bottom_efic):
                    row = bottom_efic.iloc[i]
                    st.markdown(
                        medalha_pior_html(i+1, row.get('Centro Trabalho', '—'), row.get('Turno', '—'),
                                          row.get('Produzido', 0), row.get('Eficiencia_%', 0)),
                        unsafe_allow_html=True
                    )
else:
    st.info("Nenhum dado para ranking de eficiência.")


# ===== Ranking Geral - Produção (Top 3 lado a lado + Piores 3) =====
st.subheader("📦 Ranking Geral - Produção")
if "resumo_turno" in locals() and not resumo_turno.empty:
    top_prod = resumo_turno.dropna(subset=["Produzido"]).sort_values("Produzido", ascending=False).reset_index(drop=True)

    cols = st.columns(3)
    for i in range(3):
        with cols[i]:
            if i < len(top_prod):
                row = top_prod.iloc[i]
                st.markdown(
                    medalha_html(i+1, row.get('Centro Trabalho', '—'), row.get('Turno', '—'),
                                 row.get('Produzido', 0), row.get('Eficiencia_%', 0)),
                    unsafe_allow_html=True
                )

    bottom_prod = resumo_turno.dropna(subset=["Produzido"]).sort_values("Produzido", ascending=True).reset_index(drop=True)
    if not bottom_prod.empty:
        st.markdown("### ⤵️ 3 Piores - Produção")
        cols = st.columns(3)
        for i in range(3):
            with cols[i]:
                if i < len(bottom_prod):
                    row = bottom_prod.iloc[i]
                    st.markdown(
                        medalha_pior_html(i+1, row.get('Centro Trabalho', '—'), row.get('Turno', '—'),
                                          row.get('Produzido', 0), row.get('Eficiencia_%', 0)),
                        unsafe_allow_html=True
                    )
else:
    st.info("Nenhum dado para ranking de produção.")

# ===== Resumo Geral =====

st.title("🏭 Resumo Geral")

with st.expander("📊 Resumo Geral", expanded=True):
    if "resumo_turno" in locals() and not resumo_turno.empty:
        total_produzido = int(resumo_turno["Produzido"].sum())
        tempo_total_h = float(resumo_turno["Tempo_liquido_h"].sum())
        avg_ef = resumo_turno["Eficiencia_%"].dropna().mean()
        avg_ef_ajustada = resumo_turno["Eficiencia_ajustada_%"].dropna().mean()
        total_paradas_h = resumo_turno["Paradas_h"].sum()
        prod_prevista_geral = int(resumo_turno["Prod_prevista"].sum())
        prod_prevista_ajustada = int(resumo_turno["Prod_prevista_ajustada"].sum())

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("📦 Produção Total", f"{total_produzido:,}".replace(",", "."))
        c2.metric("📦 Produção Prevista", f"{prod_prevista_geral:,}".replace(",", "."))
        c3.metric("📦 Produção Prevista Ajustada", f"{prod_prevista_ajustada:,}".replace(",", "."))
        c4.metric("⚙️ Eficiência Média", f"{avg_ef:.2f} %")
        c5.metric("⚙️ Eficiência Ajustada", f"{avg_ef_ajustada:.2f} %")
        c6.metric("⏱️ Tempo Total de Paradas (h)", f"{total_paradas_h:.2f}")
    else:
        st.info("Nenhum dado disponível para o resumo geral.")

# ===== Sumário dos Centros =====
st.title("📋 Sumário dos Centros")

if "resumo_turno" in locals() and not resumo_turno.empty:
    # Agrupar por Centro para calcular os totais e médias
    sumario_centros = resumo_turno.groupby("Centro Trabalho").agg(
        Produzido_total=("Produzido", "sum"),
        Paradas_total_h=("Paradas_h", "sum"),
        Ef_media=("Eficiencia_%", "mean"),
        Ef_ajustada_media=("Eficiencia_ajustada_%", "mean")
    ).reset_index()

    # Renomear a coluna "Centro Trabalho" para "Centro"
    sumario_centros = sumario_centros.rename(columns={"Centro Trabalho": "Centro"})

    # Classificar eficiência ajustada
    def classificar_eficiencia(ef):
        if pd.isna(ef):
            return "❓ Indefinido"
        if ef >= 95:
            return "✅ Excelente"
        elif ef >= 85:
            return "🟡 Bom"
        else:
            return "❌ Ruim"

    sumario_centros["Classificação"] = sumario_centros["Ef_ajustada_media"].apply(classificar_eficiencia)

    # Formatar os valores para exibição
    sumario_centros["Produzido_total"] = sumario_centros["Produzido_total"].apply(lambda v: f"{int(round(v))}".replace(",", "."))
    sumario_centros["Paradas_total_h"] = sumario_centros["Paradas_total_h"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—")
    sumario_centros["Ef_media"] = sumario_centros["Ef_media"].apply(lambda v: f"{v:.2f}%" if pd.notna(v) else "—")
    sumario_centros["Ef_ajustada_media"] = sumario_centros["Ef_ajustada_media"].apply(lambda v: f"{v:.2f}%" if pd.notna(v) else "—")

    # Adicionar as 4 maiores paradas por centro
    if "paradas_detalhe" in locals() and not paradas_detalhe.empty:
        # Verificar se a coluna "Centro Trabalho" existe no DataFrame
        if "Centro Trabalho" in paradas_detalhe.columns:
            # Primeiro agregar paradas do mesmo tipo para cada centro
            paradas_agrupadas = (
                paradas_detalhe
                .groupby(["Centro Trabalho", "Descrição Parada"])["Parada_min"]
                .sum()
                .reset_index()
            )
            
            # Converter minutos para horas
            paradas_agrupadas["Parada_h"] = paradas_agrupadas["Parada_min"] / 60.0
            paradas_agrupadas["Parada_fmt"] = paradas_agrupadas["Parada_h"].apply(horas_para_hhmm)
            
            # Agora selecionar as top 4 paradas por centro
            paradas_top4 = (
                paradas_agrupadas
                .groupby("Centro Trabalho")  # Corrigir chamada do groupby
                .apply(lambda x: x.nlargest(8, "Parada_min"))
                .reset_index(level=0, drop=True)
                .reset_index()
            )
            
            # Agrupar novamente para gerar o texto consolidado das paradas
            paradas_consolidadas = (
                paradas_top4
                .groupby("Centro Trabalho")
                .apply(lambda x: " | ".join(f"{row['Descrição Parada']} ({row['Parada_fmt']})" for _, row in x.iterrows()))
                .reset_index(name="Maiores Paradas")
            )
            
            # Mesclar com sumario_centros
            sumario_centros = sumario_centros.merge(paradas_consolidadas, left_on="Centro", right_on="Centro Trabalho", how="left")
            
            # Remover coluna duplicada se presente
            if "Centro Trabalho" in sumario_centros.columns:
                sumario_centros = sumario_centros.drop(columns=["Centro Trabalho"])
        else:
            st.error("A coluna 'Centro Trabalho' não está presente no DataFrame 'paradas_detalhe'.")
    else:
        sumario_centros["Maiores Paradas"] = "—"

    # Reorganizar colunas para mover "Classificação" após "Centro"
    colunas_ordenadas = [
        "Centro", "Classificação", "Produzido_total", "Paradas_total_h",
        "Ef_media", "Ef_ajustada_media", "Maiores Paradas"
    ]
    sumario_centros = sumario_centros[colunas_ordenadas]

    # Renomear colunas para melhor leitura
    sumario_centros = pretty_cols(sumario_centros)

    # Exibir tabela com largura ajustada usando st.dataframe
    st.dataframe(sumario_centros, use_container_width=True)
else:
    st.info("Nenhum dado disponível para o sumário dos centros.")

# Fim do arquivo


# ===== Detalhes por Centro =====
st.subheader("🔍 Detalhes por Centro")

if "resumo_turno" in locals() and not resumo_turno.empty:
    # Remover esta linha que está duplicando a multiplicação
    # resumo_turno.loc[resumo_turno["Centro Trabalho"] == "CA12", "Vel_padrao_media"] *= 2

    centros_unicos = sorted(resumo_turno["Centro Trabalho"].astype(str).unique().tolist())

    if centros_unicos:
        # Criar abas para cada centro
        tabs = st.tabs(centros_unicos)

        for tab, centro in zip(tabs, centros_unicos):
            with tab:
                df_centro = resumo_turno[resumo_turno["Centro Trabalho"].astype(str).str.strip() == centro].copy()

                if df_centro.empty:
                    st.warning(f"Nenhum dado encontrado para o Centro {centro}.")
                else:
                    st.markdown(f"## 🏭 Centro: `{centro}`")
                    total_produzido = int(df_centro["Produzido"].sum())
                    tempo_total_h = float(df_centro["Tempo_liquido_h"].sum())
                    avg_ef_geral = df_centro["Eficiencia_geral_%"].dropna().mean()
                    avg_ef_ajustada = df_centro["Eficiencia_ajustada_%"].dropna().mean()
                    prod_prevista_geral = int(df_centro["Prod_prevista_geral"].sum()) if "Prod_prevista_geral" in df_centro.columns else 0
                    prod_prevista_ajustada = int(df_centro["Prod_prevista_ajustada"].sum()) if "Prod_prevista_ajustada" in df_centro.columns else 0
                    
                    # Verificar valores válidos antes de calcular a média
                    vel_padrao_media = int(df_centro["Vel_padrao_media"].mean()) if not df_centro["Vel_padrao_media"].isna().all() else 0
                    vel_real_media = int(df_centro["Vel_real"].mean()) if not df_centro["Vel_real"].isna().all() else 0

                    # Exibir métricas gerais
                    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
                    c1.metric("📦 Produzido (total)", f"{total_produzido}".replace(",", "."))
                    c2.metric("📦 Previsto (geral)", f"{prod_prevista_geral}".replace(",", "."))
                    c3.metric("📦 Previsto (ajustado)", f"{prod_prevista_ajustada}".replace(",", "."))
                    c4.metric("⚙️ Eficiência Geral", f"{int(round(avg_ef_geral))} %" if "Eficiencia_geral_%" in df_centro.columns and not pd.isna(avg_ef_geral) else "—")
                    c5.metric("⚙️ Eficiência Ajustada", f"{int(round(avg_ef_ajustada))} %" if "Eficiencia_ajustada_%" in df_centro.columns and not pd.isna(avg_ef_ajustada) else "—")
                    c6.metric("🚀 Velocidade Padrão Média", f"{vel_padrao_media}" if vel_padrao_media > 0 else "—")
                    c7.metric("🚀 Velocidade Real Média", f"{vel_real_media}" if vel_real_media > 0 else "—")

                    st.divider()

                    # Detalhes por turno
                    for turno in sorted(df_centro["Turno"].unique().tolist()):
                        with st.expander(f"⏱️ Turno: {turno}", expanded=False):
                            df_turno = df_centro[df_centro["Turno"] == turno].copy()
                            cols_show = [
                                "Centro Trabalho", "Produzido", "Prod_prevista_geral", "Prod_prevista_ajustada",
                                "Eficiencia_geral_%", "Eficiencia_ajustada_%", "Paradas_min", "Vel_real"
                            ]
                            cols_show = [c for c in cols_show if c in df_turno.columns]
                            if df_turno.empty or not cols_show:
                                st.write("Sem dados para este turno.")
                                continue

                            # Exibir itens únicos produzidos neste turno
                            itens_filtrados = itens_por_centro_turno[
                                (itens_por_centro_turno["Centro Trabalho"] == centro) & 
                                (itens_por_centro_turno["Turno"] == turno) &
                                (itens_por_centro_turno["DataProd"] == df_turno["DataProd"].iloc[0])  # Adicione esta linha
                            ]
                            
                            if not itens_filtrados.empty:
                                st.markdown("**📦 Itens produzidos neste turno:**")
                                lista_itens = itens_filtrados["Descrição Item"].iloc[0]
                                if lista_itens:
                                    # Remover duplicatas e ordenar
                                    lista_unica = sorted(set(lista_itens))
                                    
                                    # Criar HTML com lista formatada adequadamente
                                    html_lista = "<ul style='margin-top:0; padding-left:20px'>\n"
                                    for item in lista_unica:
                                        html_lista += f"<li style='margin-bottom:4px'>{item}</li>\n"
                                    html_lista += "</ul>"
                                    
                                    # Exibir lista formatada
                                    st.markdown(html_lista, unsafe_allow_html=True)
                                else:
                                    st.write("Nenhum item produzido neste turno.")
                            else:
                                st.write("Nenhum item produzido neste turno.")

                            display = df_turno[cols_show].copy()
                            # Formatações simples
                            if "Produzido" in display.columns:
                                display["Produzido"] = display["Produzido"].apply(lambda v: f"{int(round(v))}" if pd.notna(v) else "")
                            if "Vel_real" in display.columns:
                                display["Vel_real"] = display["Vel_real"].apply(lambda v: f"{int(round(v))}" if pd.notna(v) else "")                            

                            if "Prod_prevista_geral" in display.columns:
                                display["Prod_prevista_geral"] = display["Prod_prevista_geral"].apply(lambda v: f"{int(round(v))}" if pd.notna(v) else "")
                            if "Prod_prevista_ajustada" in display.columns:
                                display["Prod_prevista_ajustada"] = display["Prod_prevista_ajustada"].apply(lambda v: f"{int(round(v))}" if pd.notna(v) else "")
                            if "Eficiencia_geral_%" in display.columns:
                                display["Eficiencia_geral_%"] = display["Eficiencia_geral_%"].apply(lambda v: f"{int(round(v))}%" if pd.notna(v) else "")
                            if "Eficiencia_ajustada_%" in display.columns:
                                display["Eficiencia_ajustada_%"] = display["Eficiencia_ajustada_%"].apply(lambda v: f"{int(round(v))}%" if pd.notna(v) else "")
                            if "Paradas_min" in display.columns:
                                display["Paradas_min"] = display["Paradas_min"].apply(lambda v: f"{int(round(v))}" if pd.notna(v) else "")

                            

                            display = pretty_cols(display)  # Aplicar nomes de colunas formatados

                            st.dataframe(display, use_container_width=True)

                            # Paradas detalhadas (se houver)
                            if "paradas_detalhe" in locals() and not paradas_detalhe.empty:
                                par_turno = paradas_detalhe[
                                    (paradas_detalhe["Centro Trabalho"].astype(str).str.strip() == centro) &
                                    (paradas_detalhe["Turno"] == turno)
                                ]
                                if not par_turno.empty:
                                    st.markdown("**📋 Paradas desse turno:**")
                                    st.dataframe(
                                        par_turno[["Descrição Parada", "Parada_fmt"]].rename(columns={"Parada_fmt": "Parada (HH:MM)"}),
                                        use_container_width=True
                                    )
    else:
        st.info("Nenhum centro disponível para exibição.")
else:
    st.info("Nenhum dado disponível para exibição.")

st.title("🏭 Plot Área")


# ===== Abas para Gráficos e Detalhes =====
tab1, tab2 = st.tabs(["📊 Gráficos", "Em desenvolvimento"])

# ===== Gráficos =====
with tab1:
    st.subheader("📊 Gráficos de Produção, Eficiência e Paradas")

    if "resumo_turno" in locals() and not resumo_turno.empty:
        # Gráfico: Produção por Turno
        st.markdown("### 📦 Produção por Turno")
        try:
            prod_por_turno = resumo_turno.groupby("Turno").agg(
                Produzido_total=("Produzido", "sum")
            ).reset_index()

            fig_prod_turno = px.bar(
                pretty_cols(prod_por_turno),
                x="Turno",
                y="Produção Total",  # Nome renomeado
                title="Produção Total por Turno",
                labels={"Produção Total": "Produção Total (unidades)", "Turno": "Turno"},
                text_auto=True
            )
            st.plotly_chart(fig_prod_turno, use_container_width=True, key="prod_turno")
        except Exception as e:
            st.error(f"Erro ao gerar gráfico de Produção por Turno: {e}")

        # Gráfico: Eficiência Média por Turno
        st.markdown("### 🏆 Eficiência Média por Turno")
        try:
            eficiencia_por_turno = resumo_turno.groupby("Turno").agg(
                Eficiencia_media=("Eficiencia_%", "mean")
            ).reset_index()

            fig_ef_turno = px.bar(
                eficiencia_por_turno,
                x="Turno",
                y="Eficiencia_media",
                title="Eficiência Média por Turno",
                labels={"Eficiencia_media": "Eficiência Média (%)", "Turno": "Turno"},
                text_auto=True
            )
            st.plotly_chart(fig_ef_turno, use_container_width=True, key="ef_turno")
        except Exception as e:
            st.error(f"Erro ao gerar gráfico de Eficiência Média por Turno: {e}")

        # Gráfico: Produção por Centro e Turno
        st.markdown("### 📦 Produção por Centro e Turno")
        try:
            fig_prod_centro_turno = px.bar(
                resumo_turno,
                x="Centro Trabalho",
                y="Produzido",
                color="Turno",
                title="Produção por Centro e Turno",
                labels={"Produzido": "Produção (unidades)", "Centro Trabalho": "Centro", "Turno": "Turno"},
                barmode="stack"
            )
            st.plotly_chart(fig_prod_centro_turno, use_container_width=True, key="prod_centro_turno")
        except Exception as e:
            st.error(f"Erro ao gerar gráfico de Produção por Centro e Turno: {e}")

        # Gráfico: Eficiência por Centro e Turno
        st.markdown("### 🏆 Eficiência por Centro e Turno")
        try:
            fig_ef_centro_turno = px.bar(
                resumo_turno,
                x="Centro Trabalho",
                y="Eficiencia_%",
                color="Turno",
                title="Eficiência por Centro e Turno",
                labels={"Eficiencia_%": "Eficiência (%)", "Centro Trabalho": "Centro", "Turno": "Turno"},
                barmode="stack"
            )
            st.plotly_chart(fig_ef_centro_turno, use_container_width=True, key="ef_centro_turno")
        except Exception as e:
            st.error(f"Erro ao gerar gráfico de Eficiência por Centro e Turno: {e}")

        # Gráfico: Paradas por Turno
        st.markdown("### ⏱️ Paradas por Turno")
        try:
            paradas_por_turno = resumo_turno.groupby("Turno").agg(
                Paradas_total_h=("Paradas_h", "sum")
            ).reset_index()

            fig_paradas_turno = px.bar(
                paradas_por_turno,
                x="Turno",
                y="Paradas_total_h",
                title="Tempo Total de Paradas por Turno",
                labels={"Paradas_total_h": "Paradas (horas)", "Turno": "Turno"},
                text_auto=True
            )
            st.plotly_chart(fig_paradas_turno, use_container_width=True, key="paradas_turno")
        except Exception as e:
            st.error(f"Erro ao gerar gráfico de Paradas por Turno: {e}")

        # Gráfico: Distribuição de Paradas por Tipo
        st.markdown("### 📋 Distribuição de Paradas por Tipo")
        if "paradas_detalhe" in locals() and not paradas_detalhe.empty:
            try:
                paradas_por_tipo = paradas_detalhe.groupby("Descrição Parada").agg(
                    Paradas_total_h=("Parada_h", "sum")
                ).reset_index()

                # Ordenar por tempo total de paradas
                paradas_por_tipo = paradas_por_tipo.sort_values("Paradas_total_h", ascending=False)

                # Gráfico de barras horizontais
                fig_paradas_tipo = px.bar(
                    paradas_por_tipo,
                    x="Paradas_total_h",
                    y="Descrição Parada",
                    orientation="h",
                    title="Distribuição de Paradas por Tipo",
                    labels={"Paradas_total_h": "Paradas (horas)", "Descrição Parada": "Tipo de Parada"},
                    text_auto=True
                )
                fig_paradas_tipo.update_layout(
                    yaxis=dict(title="Tipo de Parada", automargin=True),
                    xaxis=dict(title="Paradas (horas)"),
                    margin=dict(l=0, r=0, t=40, b=0),
                    height=600
                )
                st.plotly_chart(fig_paradas_tipo, use_container_width=True, key="paradas_tipo")
            except Exception as e:
                st.error(f"Erro ao gerar gráfico de Distribuição de Paradas por Tipo: {e}")
        else:
            st.info("Nenhum dado disponível para gerar gráfico de Distribuição de Paradas por Tipo.")
    else:
        st.info("Nenhum dado disponível para gráficos.")

with tab2:
    st.subheader("📊 Gráficos Detalhados por Centro")

    if "resumo_turno" in locals() and not resumo_turno.empty:
        centros_unicos = sorted(resumo_turno["Centro Trabalho"].astype(str).unique().tolist())

        if centros_unicos:
            # Criar abas para cada centro
            tabs = st.tabs(centros_unicos)

            for tab, centro in zip(tabs, centros_unicos):
                with tab:
                    df_centro = resumo_turno[resumo_turno["Centro Trabalho"].astype(str).str.strip() == centro].copy()

                    if df_centro.empty:
                        st.warning(f"Nenhum dado encontrado para o Centro {centro}.")
                    else:
                        st.markdown(f"## 🏭 Centro: `{centro}`")
                        # Gráfico: Produção ao longo do tempo
                        st.markdown("### 📈 Produção ao longo do tempo")
                        try:
                            prod_tempo = df_centro.groupby("DataProd").agg(
                                Produzido_total=("Produzido", "sum")
                            ).reset_index()

                            fig_prod_tempo = px.line(
                                prod_tempo,
                                x="DataProd",
                                y="Produzido_total",
                                title="Produção Total ao longo do tempo",
                                labels={"Produzido_total": "Produção Total (unidades)", "DataProd": "Data"},
                                markers=True
                            )
                            st.plotly_chart(fig_prod_tempo, use_container_width=True)
                        except Exception as e:
                            st.error(f"Erro ao gerar gráfico de Produção ao longo do tempo: {e}")

                        # Gráfico: Eficiência ao longo do tempo
                        st.markdown("### ⏱️ Eficiência ao longo do tempo")
                        try:
                            ef_tempo = df_centro.groupby("DataProd").agg(
                                Eficiencia_media=("Eficiencia_%", "mean")
                            ).reset_index()

                            fig_ef_tempo = px.line(
                                ef_tempo,
                                x="DataProd",
                                y="Eficiencia_media",
                                title="Eficiência Média ao longo do tempo",
                                labels={"Eficiencia_media": "Eficiência Média (%)", "DataProd": "Data"},
                                markers=True
                            )
                            st.plotly_chart(fig_ef_tempo, use_container_width=True)
                        except Exception as e:
                            st.error(f"Erro ao gerar gráfico de Eficiência ao longo do tempo: {e}")

                        # Gráfico: Produção e Eficiência em conjunto
                        st.markdown("### 📊 Produção e Eficiência em conjunto")
                        try:
                            prod_ef_tempo = df_centro.groupby("DataProd").agg(
                                Produzido_total=("Produzido", "sum"),
                                Eficiencia_media=("Eficiencia_%", "mean")
                            ).reset_index()

                            fig_prod_ef_tempo = px.line(
                                prod_ef_tempo,
                                x="DataProd",
                                y=["Produzido_total", "Eficiencia_media"],
                                title="Produção e Eficiência ao longo do tempo",
                                labels={"value": "Produção / Eficiência", "DataProd": "Data"},
                                markers=True
                            )
                            fig_prod_ef_tempo.update_traces(
                                hovertemplate=None,
                                mode="lines+markers"
                            )
                            st.plotly_chart(fig_prod_ef_tempo, use_container_width=True)
                        except Exception as e:
                            st.error(f"Erro ao gerar gráfico de Produção e Eficiência em conjunto: {e}")

                        # Gráfico: Paradas ao longo do tempo
                        st.markdown("### ⏱️ Paradas ao longo do tempo")
                        try:
                            paradas_tempo = df_centro.groupby("DataProd").agg(
                                Paradas_total_h=("Paradas_h", "sum")
                            ).reset_index()

                            fig_paradas_tempo = px.line(
                                paradas_tempo,
                                x="DataProd",
                                y="Paradas_total_h",
                                title="Tempo Total de Paradas ao longo do tempo",
                                labels={"Paradas_total_h": "Paradas (horas)", "DataProd": "Data"},
                                markers=True
                            )
                            st.plotly_chart(fig_paradas_tempo, use_container_width=True)
                        except Exception as e:
                            st.error(f"Erro ao gerar gráfico de Paradas ao longo do tempo: {e}")

                        # Gráfico: Distribuição de Paradas por Tipo (detalhado)
                        st.markdown("### 📋 Distribuição de Paradas por Tipo (detalhado)")
                        if "paradas_detalhe" in locals() and not paradas_detalhe.empty:
                            try:
                                paradas_por_tipo_centro = paradas_detalhe[
                                    paradas_detalhe["Centro Trabalho"].astype(str).str.strip() == centro
                                ].groupby("Descrição Parada").agg(
                                    Paradas_total_h=("Parada_h", "sum")
                                ).reset_index()

                                # Ordenar por tempo total de paradas
                                paradas_por_tipo_centro = paradas_por_tipo_centro.sort_values("Paradas_total_h", ascending=False)

                                # Gráfico de barras horizontais
                                fig_paradas_tipo_centro = px.bar(
                                    paradas_por_tipo_centro,
                                    x="Paradas_total_h",
                                    y="Descrição Parada",
                                    orientation="h",
                                    title="Distribuição de Paradas por Tipo",
                                    labels={"Paradas_total_h": "Paradas (horas)", "Descrição Parada": "Tipo de Parada"},
                                    text_auto=True
                                )
                                fig_paradas_tipo_centro.update_layout(
                                    yaxis=dict(title="Tipo de Parada", automargin=True),
                                    xaxis=dict(title="Paradas (horas)"),
                                    margin=dict(l=0, r=0, t=40, b=0),
                                    height=600
                                )
                                st.plotly_chart(fig_paradas_tipo_centro, use_container_width=True)
                            except Exception as e:
                                st.error(f"Erro ao gerar gráfico de Distribuição de Paradas por Tipo (detalhado): {e}")
                        else:
                            st.info("Nenhum dado disponível para gerar gráfico de Distribuição de Paradas por Tipo (detalhado).")
        else:
            st.info("Nenhum dado disponível para gráficos detalhados por centro.")
    else:

        st.info("Nenhum dado disponível para gráficos detalhados.")



















