import streamlit as st
import pandas as pd
import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, Date
from sqlalchemy.orm import declarative_base, sessionmaker

# Configuración de página adaptable a celular y PC
st.set_page_config(page_title="Gastos de Viaje", page_icon="✈️", layout="wide")

# --- CONEXIÓN A BASE DE DATOS EN LA NUBE (NEON POSTGRESQL) ---
DATABASE_URL = "postgresql://neondb_owner:npg_qIJk93MutBlR@ep-lucky-poetry-b5t0p12u-pooler.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require"
engine = create_engine(DATABASE_URL))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- MODELOS ORM ---
class Expense(Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer)
    paid_by = Column(String)
    amount = Column(Float)
    description = Column(String)
    expense_date = Column(Date, default=datetime.date.today)

class ExpenseSplit(Base):
    __tablename__ = "expense_splits"
    id = Column(Integer, primary_key=True, index=True)
    expense_id = Column(Integer, ForeignKey("expenses.id"))
    user_name = Column(String)
    split_amount = Column(Float)

class SettlementPayment(Base):
    """Registra pagos directos/transferencias entre pasajeros para saldar deudas"""
    __tablename__ = "settlement_payments"
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer)
    sender = Column(String)    # Quién transfiere
    receiver = Column(String)  # Quién recibe
    amount = Column(Float)
    payment_date = Column(Date, default=datetime.date.today)
    note = Column(String, default="")

Base.metadata.create_all(bind=engine)

# --- FORMATEO MONETARIO (Formato argentino: $ 15.000,00) ---
def format_pesos(valor: float) -> str:
    base = f"{valor:,.2f}"
    formateado = base.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"$ {formateado}"

# --- ALGORITMO GREEDY DE COMPENSACIÓN DE DEUDAS PENDIENTES ---
def calcular_liquidaciones(balances: dict):
    acreedores = [[u, monto] for u, monto in balances.items() if monto > 0.01]
    deudores = [[u, -monto] for u, monto in balances.items() if monto < -0.01]

    acreedores.sort(key=lambda x: x[1], reverse=True)
    deudores.sort(key=lambda x: x[1], reverse=True)

    transferencias = []
    i, j = 0, 0
    while i < len(deudores) and j < len(acreedores):
        deudor, monto_deuda = deudores[i]
        acreedor, monto_credito = acreedores[j]
        monto_pago = min(monto_deuda, monto_credito)

        transferencias.append({
            "de": deudor,
            "para": acreedor,
            "monto": round(monto_pago, 2)
        })

        deudores[i][1] -= monto_pago
        acreedores[j][1] -= monto_pago

        if abs(deudores[i][1]) < 0.01:
            i += 1
        if abs(acreedores[j][1]) < 0.01:
            j += 1

    return transferencias

# --- BARRA LATERAL: CONFIGURACIÓN ---
st.sidebar.header("⚙️ Configuración del Viaje")
grupo_id = st.sidebar.number_input("ID del Viaje", min_value=1, value=1, step=1)
viajeros_input = st.sidebar.text_input("Viajeros (separados por coma)", value="Gloria, Mario, Liliana, Luis, Orestes, Juan")
viajeros = [v.strip() for v in viajeros_input.split(",") if v.strip()]

st.title("✈️ GASTOS COMUNES DEL VIAJE")

# 4 PESTAÑAS
tab1, tab2, tab3, tab4 = st.tabs([
    "➕ Cargar Gasto compartido", 
    "💸 Pagos entre Pasajeros", 
    "📊 Situación Real y Balances", 
    "📋 Historial de pagos y Edición"
])

# ==========================================
# TAB 1: CARGA DE GASTOS COMUNES
# ==========================================
with tab1:
    st.subheader("Registrar nuevo gasto común")
    with st.form("form_nuevo_gasto", clear_on_submit=True):
        col_desc, col_date = st.columns([2, 1])
        with col_desc:
            descripcion = st.text_input("Descripción", placeholder="Ej: Combustible, Asado, Entradas")
        with col_date:
            fecha_gasto = st.date_input("Fecha", value=datetime.date.today())

        col_pago1, col_pago2 = st.columns(2)
        with col_pago1:
            pagador = st.selectbox("¿Quién pagó?", viajeros, key="pagador_nuevo_gasto")
        with col_pago2:
            monto = st.number_input("Monto total ($)", min_value=1.0, step=100.0, format="%.2f")

        st.markdown("**¿Entre quiénes se divide?**")
        participantes = st.multiselect("Participantes", viajeros, default=viajeros)

        guardar = st.form_submit_button("💾 Guardar Gasto", use_container_width=True)

        if guardar:
            if not descripcion:
                st.error("Por favor ingresa una descripción.")
            elif not participantes:
                st.error("Debes seleccionar al menos un participante.")
            else:
                monto_por_cabeza = round(monto / len(participantes), 2)
                db = SessionLocal()
                nuevo = Expense(
                    group_id=grupo_id,
                    paid_by=pagador,
                    amount=monto,
                    description=descripcion,
                    expense_date=fecha_gasto
                )
                db.add(nuevo)
                db.commit()
                db.refresh(nuevo)

                for part in participantes:
                    db.add(ExpenseSplit(
                        expense_id=nuevo.id,
                        user_name=part,
                        split_amount=monto_por_cabeza
                    ))
                db.commit()
                db.close()
                st.success(f"Gasto registrado: {format_pesos(monto)} ({format_pesos(monto_por_cabeza)} por persona)")
                st.rerun()

# ==========================================
# TAB 2: REGISTRO DE PAGOS / TRANSFERENCIAS ENTRE ELLOS
# ==========================================
with tab2:
    st.subheader("Registrar Pago / Transferencia entre Viajeros")
    st.caption("Usa este formulario cuando alguien le haya transferido dinero a otro para saldar o adelantar su parte.")

    with st.form("form_pago_directo", clear_on_submit=True):
        col_de, col_para = st.columns(2)
        with col_de:
            emisor = st.selectbox("¿Quién transfirió? (Deudor)", viajeros, key="emisor_pago")
        with col_para:
            # Filtramos para que no se elija a sí mismo
            posibles_receptores = [v for v in viajeros if v != emisor] if len(viajeros) > 1 else viajeros
            receptor = st.selectbox("¿Quién recibió el dinero? (Acreedor)", posibles_receptores, key="receptor_pago")

        col_monto, col_f_pago = st.columns(2)
        with col_monto:
            monto_transferido = st.number_input("Monto transferido ($)", min_value=1.0, step=100.0, format="%.2f")
        with col_f_pago:
            fecha_transferencia = st.date_input("Fecha del pago", value=datetime.date.today(), key="fecha_transf")

        nota_pago = st.text_input("Nota / Comprobante (opcional)", placeholder="Ej: Transferencia Banco / Alias / Efectivo")

        btn_guardar_pago = st.form_submit_button("💸 Confirmar Pago Directo", use_container_width=True)

        if btn_guardar_pago:
            if emisor == receptor:
                st.error("El pagador y el receptor deben ser personas distintas.")
            else:
                db = SessionLocal()
                nuevo_pago = SettlementPayment(
                    group_id=grupo_id,
                    sender=emisor,
                    receiver=receptor,
                    amount=monto_transferido,
                    payment_date=fecha_transferencia,
                    note=nota_pago
                )
                db.add(nuevo_pago)
                db.commit()
                db.close()
                st.success(f"¡Pago guardado! {emisor} le transfirió {format_pesos(monto_transferido)} a {receptor}.")
                st.rerun()

    st.write("---")
    st.markdown("### 📜 Historial de Transferencias Realizadas")
    db = SessionLocal()
    pagos_hechos = db.query(SettlementPayment).filter(SettlementPayment.group_id == grupo_id).all()
    if pagos_hechos:
        tabla_pagos = [
            {
                "ID": p.id,
                "Fecha": p.payment_date,
                "Quién pagó": p.sender,
                "Quién recibió": p.receiver,
                "Monto": format_pesos(p.amount),
                "Nota": p.note
            }
            for p in pagos_hechos
        ]
        st.dataframe(pd.DataFrame(tabla_pagos), use_container_width=True, hide_index=True)

        # Opción para anular/eliminar un pago mal cargado
        with st.expander("🗑️ Anular una transferencia errónea"):
            opciones_anular = {f"#{p.id}: {p.sender} ➔ {p.receiver} ({format_pesos(p.amount)})": p.id for p in pagos_hechos}
            pago_a_borrar_txt = st.selectbox("Selecciona la transferencia a borrar:", list(opciones_anular.keys()))
            if st.button("Eliminar esta transferencia", type="primary"):
                id_borrar = opciones_anular[pago_a_borrar_txt]
                db.query(SettlementPayment).filter(SettlementPayment.id == id_borrar).delete()
                db.commit()
                st.warning("Transferencia anulada.")
                st.rerun()
    else:
        st.info("No se han registrado transferencias directas entre pasajeros todavía.")
    db.close()

# ==========================================
# TAB 3: SITUACIÓN REAL, BALANCES Y PENDIENTES
# ==========================================
with tab3:
    db = SessionLocal()
    gastos = db.query(Expense).filter(Expense.group_id == grupo_id).all()
    pagos_directos = db.query(SettlementPayment).filter(SettlementPayment.group_id == grupo_id).all()

    if not gastos and not pagos_directos:
        st.info("No hay movimientos registrados en este viaje aún.")
    else:
        total_viaje = sum(g.amount for g in gastos)
        total_transferido = sum(p.amount for p in pagos_directos)

        # Inicializar contadores por pasajero
        aportes_bolsillo = {v: 0.0 for v in viajeros}
        consumo_total = {v: 0.0 for v in viajeros}
        pagado_a_otros = {v: 0.0 for v in viajeros}
        cobrado_de_otros = {v: 0.0 for v in viajeros}

        # 1. Sumar gastos comunes y consumos
        for g in gastos:
            aportes_bolsillo[g.paid_by] = aportes_bolsillo.get(g.paid_by, 0.0) + g.amount
            splits = db.query(ExpenseSplit).filter(ExpenseSplit.expense_id == g.id).all()
            for s in splits:
                consumo_total[s.user_name] = consumo_total.get(s.user_name, 0.0) + s.split_amount

        # 2. Sumar transferencias directas entre ellos
        for p in pagos_directos:
            pagado_a_otros[p.sender] = pagado_a_otros.get(p.sender, 0.0) + p.amount
            cobrado_de_otros[p.receiver] = cobrado_de_otros.get(p.receiver, 0.0) + p.amount

        # 3. BALANCE NETO REAL PENDIENTE:
        # Balance = (Aportes bolsillo + Pagado a otros) - (Consumido + Cobrado de otros)
        balances_reales = {}
        for v in viajeros:
            creditos = aportes_bolsillo.get(v, 0.0) + pagado_a_otros.get(v, 0.0)
            debitos = consumo_total.get(v, 0.0) + cobrado_de_otros.get(v, 0.0)
            balances_reales[v] = round(creditos - debitos, 2)

        # Métricas de cabecera
        c_m1, c_m2, c_m3 = st.columns(3)
        c_m1.metric("Gasto Total del Viaje", format_pesos(total_viaje))
        promedio = (total_viaje / len(viajeros)) if viajeros else 0
        c_m2.metric("Promedio Teórico p/ Persona", format_pesos(promedio))
        c_m3.metric("Transferencias Directas Ya Hechas", format_pesos(total_transferido))

        st.write("---")
        st.markdown("### 💳 Situación Real Pendiente (¿Quién debe transferir ahora?)")
        liquidaciones_pendientes = calcular_liquidaciones(balances_reales)

        if not liquidaciones_pendientes:
            st.success("🎉 ¡Las cuentas están totalmente al día y compensadas! Nadie le debe dinero a nadie.")
        else:
            for l in liquidaciones_pendientes:
                st.warning(f"👉 **{l['de']}** debe transferirle **{format_pesos(l['monto'])}** a **{l['para']}**")

        st.write("---")
        st.markdown("### 📊 Gráficos de Estado")

        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.markdown("**Saldo Neto Actual (Verde: le deben / Rojo o negativo: debe pagar)**")
            df_bar_bal = pd.DataFrame([{"Viajero": k, "Saldo Pendiente": v} for k, v in balances_reales.items()])
            st.bar_chart(df_bar_bal.set_index("Viajero")["Saldo Pendiente"])

        with col_g2:
            st.markdown("**Aportes directos en gastos comunes**")
            df_aportes = pd.DataFrame([{"Viajero": k, "Monto": v} for k, v in aportes_bolsillo.items() if v > 0])
            if not df_aportes.empty:
                st.bar_chart(df_aportes.set_index("Viajero")["Monto"])
            else:
                st.caption("Sin datos de compras aún.")

        st.write("---")
        st.markdown("### ⚖️ Detalle Contable Completo por Pasajero")
        
        datos_tabla_completa = []
        for u in viajeros:
            b_neto = balances_reales.get(u, 0.0)
            if b_neto > 0.01:
                estado = "🟢 Le deben dinero"
            elif b_neto < -0.01:
                estado = "🔴 Debe transferir"
            else:
                estado = "⚪ Saldado / Al día"

            datos_tabla_completa.append({
                "Viajero": u,
                "Gastado en Compras": format_pesos(aportes_bolsillo.get(u, 0.0)),
                "Total Consumido": format_pesos(consumo_total.get(u, 0.0)),
                "Transferido a Otros": format_pesos(pagado_a_otros.get(u, 0.0)),
                "Cobrado de Otros": format_pesos(cobrado_de_otros.get(u, 0.0)),
                "Saldo Neto Final": format_pesos(b_neto),
                "Estado": estado
            })

        st.dataframe(pd.DataFrame(datos_tabla_completa), use_container_width=True, hide_index=True)

    db.close()

# ==========================================
# TAB 4: HISTORIAL Y EDICIÓN COMPLETA DE GASTOS
# ==========================================
with tab4:
    st.subheader("Historial y Modificación de Gastos Comunes")
    
    db = SessionLocal()
    gastos = db.query(Expense).filter(Expense.group_id == grupo_id).all()

    if gastos:
        data_tabla = []
        for g in gastos:
            splits_g = db.query(ExpenseSplit).filter(ExpenseSplit.expense_id == g.id).all()
            quienes = ", ".join([s.user_name for s in splits_g])
            data_tabla.append({
                "ID": g.id,
                "Fecha": g.expense_date if g.expense_date else datetime.date.today(),
                "Descripción": g.description,
                "Pagado por": g.paid_by,
                "Monto": format_pesos(g.amount),
                "Dividido entre": quienes
            })
        
        st.dataframe(pd.DataFrame(data_tabla), use_container_width=True, hide_index=True)
        st.write("---")

        opciones_gastos = {
            f"#{g.id} | {g.expense_date} - {g.description} ({format_pesos(g.amount)}) pagado por {g.paid_by}": g.id 
            for g in gastos
        }
        gasto_elegido_txt = st.selectbox("Selecciona un gasto para modificar o eliminar:", list(opciones_gastos.keys()))
        gasto_id_sel = opciones_gastos[gasto_elegido_txt]
        gasto_actual = db.query(Expense).filter(Expense.id == gasto_id_sel).first()
        splits_actuales = db.query(ExpenseSplit).filter(ExpenseSplit.expense_id == gasto_id_sel).all()
        participantes_actuales = [s.user_name for s in splits_actuales]

        col_edit, col_del = st.columns([3, 1])

        # Formulario de modificación completa
        with col_edit:
            with st.expander("✏️ Editar datos de este gasto", expanded=True):
                with st.form("form_editar_gasto"):
                    c_desc, c_fecha = st.columns([2, 1])
                    with c_desc:
                        edit_desc = st.text_input("Descripción", value=gasto_actual.description)
                    with c_fecha:
                        edit_fecha = st.date_input("Fecha", value=gasto_actual.expense_date or datetime.date.today())

                    c_pagador, c_monto = st.columns(2)
                    with c_pagador:
                        idx_pagador = viajeros.index(gasto_actual.paid_by) if gasto_actual.paid_by in viajeros else 0
                        edit_pagador = st.selectbox("¿Quién pagó?", viajeros, index=idx_pagador, key="edit_pagador")
                    with c_monto:
                        edit_monto = st.number_input("Monto total ($)", min_value=1.0, value=float(gasto_actual.amount), step=100.0, format="%.2f")

                    edit_participantes = st.multiselect(
                        "Dividir entre:", 
                        viajeros, 
                        default=[p for p in participantes_actuales if p in viajeros]
                    )

                    btn_actualizar = st.form_submit_button("💾 Guardar Modificaciones", use_container_width=True)

                    if btn_actualizar:
                        if not edit_desc:
                            st.error("La descripción no puede quedar vacía.")
                        elif not edit_participantes:
                            st.error("Debes seleccionar al menos un participante.")
                        else:
                            gasto_actual.description = edit_desc
                            gasto_actual.expense_date = edit_fecha
                            gasto_actual.paid_by = edit_pagador
                            gasto_actual.amount = edit_monto

                            # Reasignar splits
                            db.query(ExpenseSplit).filter(ExpenseSplit.expense_id == gasto_actual.id).delete()
                            monto_cabeza = round(edit_monto / len(edit_participantes), 2)
                            for part in edit_participantes:
                                db.add(ExpenseSplit(
                                    expense_id=gasto_actual.id,
                                    user_name=part,
                                    split_amount=monto_cabeza
                                ))

                            db.commit()
                            st.success("¡Gasto actualizado con éxito!")
                            st.rerun()

        # Botón de eliminación
        with col_del:
            with st.expander("🗑️ Zona de peligro", expanded=True):
                st.write("¿Deseas eliminar este registro de gasto?")
                if st.button("Eliminar Gasto", type="primary", use_container_width=True):
                    db.query(ExpenseSplit).filter(ExpenseSplit.expense_id == gasto_id_sel).delete()
                    db.query(Expense).filter(Expense.id == gasto_id_sel).delete()
                    db.commit()
                    st.warning("Gasto eliminado.")
                    st.rerun()

    else:
        st.info("Aún no hay compras registradas en este viaje.")

    db.close()
