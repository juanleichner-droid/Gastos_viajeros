import streamlit as st
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# --- CONFIGURACIÓN DE PÁGINA ADAPTABLE A CELULAR Y PC ---
st.set_page_config(page_title="Gastos de Viaje", page_icon="🚗", layout="wide")

# --- CONEXIÓN A BASE DE DATOS EN LA NUBE (NEON POSTGRESQL) ---
DATABASE_URL = "postgresql://neondb_owner:npg_qIJk93MutBlR@ep-lucky-poetry-b5t0p12u-pooler.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- MODELOS ORM ---
class Expense(Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, default=1)
    description = Column(String)
    payer = Column(String)
    amount_ars = Column(Float)
    currency = Column(String, default="ARS")
    original_amount = Column(Float)
    exchange_rate = Column(Float, default=1.0)
    category = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    splits = relationship("ExpenseSplit", back_populates="expense", cascade="all, delete-orphan")

class ExpenseSplit(Base):
    __tablename__ = "expense_splits"
    id = Column(Integer, primary_key=True, index=True)
    expense_id = Column(Integer, ForeignKey("expenses.id"))
    person = Column(String)
    assigned_amount = Column(Float)
    expense = relationship("Expense", back_populates="splits")

class SettlementPayment(Base):
    __tablename__ = "settlement_payments"
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, default=1)
    payer = Column(String)
    receiver = Column(String)
    amount = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# --- VIAJEROS DEFINIDOS ---
VIAJEROS = ["Juan", "Lucas", "Agustin", "Marcos"]
CATEGORIAS = ["Comida / Restaurante", "Combustible / Peajes", "Alojamiento", "Supermercado", "Excursiones / Entradas", "Varios"]

# --- FUNCIONES DE BASE DE DATOS ---
def get_db():
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise

def guardar_gasto(descripcion, pagador, monto_pesificado, moneda, monto_orig, tc, categoria, beneficiarios):
    db = get_db()
    monto_por_cabeza = monto_pesificado / len(beneficiarios)
    
    desc_final = descripcion
    if moneda == "USD":
        desc_final = f"{descripcion} (US$ {monto_orig:.2f} @ ${tc:,.2f})"
        
    nuevo_gasto = Expense(
        description=desc_final,
        payer=pagador,
        amount_ars=monto_pesificado,
        currency=moneda,
        original_amount=monto_orig,
        exchange_rate=tc,
        category=categoria
    )
    db.add(nuevo_gasto)
    db.flush()
    
    for persona in beneficiarios:
        split = ExpenseSplit(
            expense_id=nuevo_gasto.id,
            person=persona,
            assigned_amount=monto_por_cabeza
        )
        db.add(split)
        
    db.commit()
    db.close()

def guardar_pago(pagador, receptor, monto):
    db = get_db()
    pago = SettlementPayment(payer=pagador, receiver=receptor, amount=monto)
    db.add(pago)
    db.commit()
    db.close()

# --- ENCABEZADO ---
st.title("🚗 Gastos de Viaje")
st.caption("Gestor de gastos compartidos en pesos y dólares — Persistencia en Neon Cloud")

# --- PESTAÑAS PRINCIPALES ---
tab_cargar, tab_balance, tab_historial, tab_pagos = st.tabs([
    "➕ Cargar Gasto", 
    "⚖️ Balance y Deudas", 
    "📋 Historial de Gastos", 
    "💸 Registrar Transferencia"
])

# ==========================================
# 1. CARGAR GASTO (CON CONVERSOR A DÓLAR)
# ==========================================
with tab_cargar:
    st.subheader("Nuevo Gasto Compartido")
    
    # 1. Selector de moneda interactivo (fuera del form para reaccionar al instante)
    col_m1, col_m2 = st.columns([1, 2])
    with col_m1:
        moneda_sel = st.radio("Moneda", ["ARS ($)", "USD (US$)"], horizontal=True)
        es_dolar = "USD" in moneda_sel

    with st.form("form_nuevo_gasto", clear_on_submit=True):
        descripcion = st.text_input("Descripción del gasto", placeholder="Ej: Cena en restaurante, Nafta")
        
        col_pag, col_cat = st.columns(2)
        with col_pag:
            pagador = st.selectbox("¿Quién pagó?", VIAJEROS)
        with col_cat:
            categoria = st.selectbox("Categoría", CATEGORIAS)
            
        st.markdown("---")
        
        if es_dolar:
            col_u1, col_u2 = st.columns(2)
            with col_u1:
                monto_input = st.number_input("Monto en Dólares (US$)", min_value=0.0, step=1.0, format="%.2f")
            with col_u2:
                tipo_cambio = st.number_input(
                    "Tipo de cambio (1 USD = X ARS)", 
                    min_value=1.0, 
                    value=1350.0, 
                    step=10.0, 
                    format="%.2f",
                    help="Cotización para convertir el gasto a pesos"
                )
            monto_pesificado = monto_input * tipo_cambio
            st.info(f"💵 **Total convertido a pesos:** ${monto_pesificado:,.2f} ARS *(US$ {monto_input:,.2f} × ${tipo_cambio:,.2f})*")
        else:
            monto_input = st.number_input("Monto en Pesos ($ ARS)", min_value=0.0, step=100.0, format="%.2f")
            tipo_cambio = 1.0
            monto_pesificado = monto_input
            
        st.markdown("---")
        st.write("**¿Entre quiénes se divide el gasto?**")
        participantes = []
        col_part = st.columns(len(VIAJEROS))
        for i, v in enumerate(VIAJEROS):
            with col_part[i]:
                if st.checkbox(v, value=True, key=f"part_{v}"):
                    participantes.append(v)
                    
        submitted = st.form_submit_button("Guardar Gasto", use_container_width=True, type="primary")
        
        if submitted:
            if not descripcion.strip():
                st.error("Por favor, ingresa una descripción para el gasto.")
            elif monto_input <= 0:
                st.error("El monto debe ser mayor a 0.")
            elif not participantes:
                st.error("Debes seleccionar al menos un participante para dividir el gasto.")
            else:
                guardar_gasto(
                    descripcion=descripcion.strip(),
                    pagador=pagador,
                    monto_pesificado=monto_pesificado,
                    moneda="USD" if es_dolar else "ARS",
                    monto_orig=monto_input,
                    tc=tipo_cambio,
                    categoria=categoria,
                    beneficiarios=participantes
                )
                st.success(f"¡Gasto registrado! Total: ${monto_pesificado:,.2f} ARS")
                st.rerun()

# ==========================================
# 2. BALANCE Y LIQUIDACIÓN DE DEUDAS
# ==========================================
with tab_balance:
    st.subheader("Estado de Cuentas y Saldos")
    db = get_db()
    
    # Calcular saldos netos
    netos = {v: 0.0 for v in VIAJEROS}
    total_gastado = 0.0
    
    # Gastos pagados
    gastos = db.query(Expense).all()
    for g in gastos:
        if g.payer in netos:
            netos[g.payer] += g.amount_ars
            total_gastado += g.amount_ars
            
    # Partes consumidas
    splits = db.query(ExpenseSplit).all()
    for s in splits:
        if s.person in netos:
            netos[s.person] -= s.assigned_amount
            
    # Transferencias realizadas entre ellos
    pagos = db.query(SettlementPayment).all()
    for p in pagos:
        if p.payer in netos:
            netos[p.payer] += p.amount
        if p.receiver in netos:
            netos[p.receiver] -= p.amount
            
    db.close()
    
    st.metric("Total General Gastado (Pesificado)", f"${total_gastado:,.2f} ARS")
    
    col_bal1, col_bal2 = st.columns(2)
    with col_bal1:
        st.markdown("#### Saldos individuales")
        df_netos = pd.DataFrame([
            {
                "Viajero": v, 
                "Saldo Neto (ARS)": f"${s:,.2f}", 
                "Condición": "Le deben cobrar 🟢" if s > 0.01 else ("Debe pagar 🔴" if s < -0.01 else "Al día ⚪")
            }
            for v, s in netos.items()
        ])
        st.dataframe(df_netos, hide_index=True, use_container_width=True)
        
    with col_bal2:
        st.markdown("#### ¿Cómo saldar las deudas?")
        deudores = [(v, -s) for v, s in netos.items() if s < -0.01]
        acreedores = [(v, s) for v, s in netos.items() if s > 0.01]
        
        deudores.sort(key=lambda x: x[1], reverse=True)
        acreedores.sort(key=lambda x: x[1], reverse=True)
        
        deudas = []
        i, j = 0, 0
        deudores_calc = [list(x) for x in deudores]
        acreedores_calc = [list(x) for x in acreedores]
        
        while i < len(deudores_calc) and j < len(acreedores_calc):
            deudor, d_monto = deudores_calc[i]
            acreedor, a_monto = acreedores_calc[j]
            monto_pago = min(d_monto, a_monto)
            
            if monto_pago > 0.01:
                deudas.append((deudor, acreedor, monto_pago))
                
            deudores_calc[i][1] -= monto_pago
            acreedores_calc[j][1] -= monto_pago
            
            if deudores_calc[i][1] <= 0.01:
                i += 1
            if acreedores_calc[j][1] <= 0.01:
                j += 1
                
        if not deudas:
            st.success("🎉 ¡Todos están al día! No hay transferencias pendientes.")
        else:
            for d, a, m in deudas:
                st.warning(f"👉 **{d}** le debe transferir **${m:,.2f} ARS** a **{a}**")

# ==========================================
# 3. HISTORIAL DE GASTOS
# ==========================================
with tab_historial:
    st.subheader("Historial Detallado de Gastos")
    db = get_db()
    gastos_list = db.query(Expense).order_by(Expense.created_at.desc()).all()
    
    if not gastos_list:
        st.info("No hay gastos registrados todavía.")
    else:
        filas = []
        for g in gastos_list:
            filas.append({
                "Fecha": g.created_at.strftime("%d/%m/%Y %H:%M"),
                "Descripción": g.description,
                "Categoría": g.category,
                "Pagó": g.payer,
                "Moneda Orig.": g.currency,
                "Monto Orig.": f"{'US$ ' if g.currency == 'USD' else '$ '}{g.original_amount:,.2f}",
                "Total Pesificado": f"${g.amount_ars:,.2f} ARS"
            })
        st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
    db.close()

# ==========================================
# 4. REGISTRAR TRANSFERENCIA ENTRE VIAJEROS
# ==========================================
with tab_pagos:
    st.subheader("Asentar Transferencia Realizada")
    st.caption("Utiliza esta opción cuando un integrante le transfiera plata a otro para saldar deudas.")
    
    with st.form("form_pago", clear_on_submit=True):
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            deudor_pago = st.selectbox("Quién transfirió (pagó)", VIAJEROS, key="pago_deudor")
        with col_p2:
            acreedor_pago = st.selectbox("Quién recibió la plata", [v for v in VIAJEROS if v != deudor_pago], key="pago_acreedor")
            
        monto_transferido = st.number_input("Monto transferido en Pesos ($ ARS)", min_value=0.0, step=100.0, format="%.2f")
        submit_pago = st.form_submit_button("Registrar Transferencia", type="primary", use_container_width=True)
        
        if submit_pago:
            if monto_transferido <= 0:
                st.error("El monto de la transferencia debe ser mayor a 0.")
            else:
                guardar_pago(deudor_pago, acreedor_pago, monto_transferido)
                st.success(f"Transferencia de ${monto_transferido:,.2f} ARS registrada correctamente.")
                st.rerun()
