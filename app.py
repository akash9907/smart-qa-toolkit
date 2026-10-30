import io
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# ReportLab Imports for PDF Generation
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# ==========================================
# 1. PAGE CONFIGURATION & CONSTANTS
# ==========================================
st.set_page_config(page_title="Smart QA Toolkit", page_icon="🛡️", layout="wide")

REQUIRED_COLUMNS = ["Date", "Machine", "Model", "Shift", "Production", "Defective Cells", "Defect", "Count"]
OPTIONAL_COLUMNS = ["Action plan"]


# ==========================================
# 2. HELPER FUNCTIONS (Data Processing)
# ==========================================

def clean_and_validate_data(df: pd.DataFrame) -> pd.DataFrame:
    """Cleans, standardizes, and validates the uploaded CSV data."""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    # Keep only required columns + optional if they exist
    cols_to_keep = REQUIRED_COLUMNS + [c for c in OPTIONAL_COLUMNS if c in df.columns]
    out = df[cols_to_keep].copy().drop_duplicates()

    # Formatting Data Types and Strings
    out["Date"] = pd.to_datetime(out["Date"], errors="coerce", dayfirst=True)
    out["Machine"] = out["Machine"].astype("string").str.strip().str.upper()
    out["Shift"] = out["Shift"].astype("string").str.strip().str.upper()
    out["Model"] = out["Model"].astype("string").str.strip().str.upper()
    out["Defect"] = out["Defect"].astype("string").str.strip().str.title()

    if "Action plan" in out.columns:
        out["Action plan"] = out["Action plan"].astype("string").str.strip().fillna("Pending")
    else:
        out["Action plan"] = "Pending"

    # Handle Numbers
    for col in ["Production", "Defective Cells", "Count"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out = out.dropna(subset=["Date", "Machine", "Model", "Production", "Defective Cells", "Defect", "Count"])
    out = out[(out["Machine"] != "") & (out["Model"] != "") & (out["Shift"] != "") & (out["Defect"] != "")]
    out = out[(out["Production"] > 0) & (out["Defective Cells"] >= 0) & (out["Count"] >= 0)]

    for col in ["Production", "Defective Cells", "Count"]:
        if not (out[col] % 1 == 0).all():
            raise ValueError(f"'{col}' must contain whole numbers only.")
        out[col] = out[col].astype("int64")

    # Business Logic Validations
    if (out["Defective Cells"] > out["Production"]).any():
        raise ValueError("Defective Cells cannot be greater than Production.")

    group_keys = ["Date", "Machine", "Model", "Shift"]

    # Ensure production numbers are consistent per group
    grouped = out.groupby(group_keys)[["Production", "Defective Cells"]].nunique()
    if (grouped > 1).any().any():
        raise ValueError(
            "Production and Defective Cells must have the same values for each Date + Machine + Model + Shift.")

    # Ensure total defect counts don't exceed total defective cells
    defect_totals = out.groupby(group_keys)["Count"].sum().rename("Total Count")
    cell_totals = out.groupby(group_keys)["Defective Cells"].first().rename("Defective Cells")
    check = pd.concat([defect_totals, cell_totals], axis=1)
    bad = check[check["Total Count"] > check["Defective Cells"]]

    if not bad.empty:
        raise ValueError(f"Sum of defect Count exceeds Defective Cells for: {', '.join(bad.index.tolist()[:5])}...")

    return out


def calculate_kpis(df: pd.DataFrame) -> dict:
    """Calculates high-level QA KPIs to avoid double-counting."""
    # Group by identifiers to get unique Production per Machine/Model/Shift
    prod_data = df.groupby(["Date", "Machine", "Model", "Shift"]).agg({
        "Production": "max", "Defective Cells": "max"
    }).reset_index()

    total_production = int(prod_data["Production"].sum())
    total_defective = int(prod_data["Defective Cells"].sum())

    return {
        "production": total_production,
        "defective": total_defective,
        "good": total_production - total_defective,
        "defect_rate": (total_defective / total_production * 100) if total_production > 0 else 0
    }


def build_pareto_table(df: pd.DataFrame) -> pd.DataFrame:
    """Creates the Pareto (80/20) ranking table."""
    p = df.groupby("Defect", as_index=False)["Count"].sum().sort_values("Count", ascending=False).reset_index(drop=True)
    total = int(p["Count"].sum())

    if total > 0:
        p["Cumulative Count"] = p["Count"].cumsum()
        p["Cumulative %"] = (p["Cumulative Count"] / total * 100).round(2)
        p["Defect %"] = (p["Count"] / total * 100).round(2)
    else:
        p["Cumulative Count"] = 0
        p["Cumulative %"] = 0.0
        p["Defect %"] = 0.0

    p.insert(0, "Rank", range(1, len(p) + 1))
    return p


def generate_pdf_report(kpi, pareto_df, date_range, filtered_df):
    """Generates a 1-page PDF Executive Summary."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    styles = getSampleStyleSheet()

    # 1. Title
    title_style = ParagraphStyle(name='TitleStyle', parent=styles['Heading1'], alignment=1,
                                 textColor=colors.HexColor("#1f77b4"))
    elements.append(Paragraph("Smart QA Toolkit - Executive Report", title_style))
    elements.append(Paragraph(f"Date Range: {date_range[0]} to {date_range[1]}", styles['Normal']))
    elements.append(Spacer(1, 15))

    # 2. KPI Table
    kpi_data = [
        ["Inspected Cells", "Defective Cells", "Good Cells", "Defect Rate"],
        [f"{kpi['production']:,}", f"{kpi['defective']:,}", f"{kpi['good']:,}", f"{kpi['defect_rate']:.2f}%"]
    ]
    kpi_table = Table(kpi_data, colWidths=[120, 120, 120, 120])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f0f2f6")),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('FONTSIZE', (0, 1), (-1, 1), 14),
        ('TOPPADDING', (0, 1), (-1, 1), 10), ('BOTTOMPADDING', (0, 1), (-1, 1), 10)
    ]))
    elements.append(kpi_table)
    elements.append(Spacer(1, 20))

    # 3. Top 10 Defect Summary Table
    elements.append(Paragraph("<b>Defect Summary Table</b>", styles['Heading2']))
    summary_data = [["Rank", "Defect Name", "Total Count"]]
    for _, row in pareto_df.head(10).iterrows():
        summary_data.append([str(row["Rank"]), row["Defect"], str(row["Count"])])

    summary_table = Table(summary_data, colWidths=[60, 200, 100])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f0f2f6")),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9f9f9")])
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))

    # 4. Top 5 Defects & Action Plan
    elements.append(Paragraph("<b>Top 5 Defects & Action Plan</b>", styles['Heading2']))
    action_plans = filtered_df[["Defect", "Action plan"]].drop_duplicates().groupby("Defect")[
        "Action plan"].first().to_dict()

    action_data = [["Rank", "Defect Category", "Count", "Cum. %", "Action Plan"]]
    for _, row in pareto_df.head(5).iterrows():
        action = action_plans.get(row['Defect'], "Pending")
        action_para = Paragraph(str(action), styles['Normal'])
        action_data.append([str(row['Rank']), row['Defect'], str(row['Count']), f"{row['Cumulative %']}%", action_para])

    action_table = Table(action_data, colWidths=[40, 120, 50, 60, 250])
    action_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1f77b4")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (3, -1), 'CENTER'), ('ALIGN', (4, 0), (4, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9f9f9")])
    ]))
    elements.append(action_table)

    doc.build(elements)
    buffer.seek(0)
    return buffer


# ==========================================
# 3. APP LAYOUT & DATA LOADING
# ==========================================

st.title("🛡️ Smart QA Toolkit")
st.caption("Quality Analysis & Defect Summary • V1.0")
st.info("Developed By Akash")

# Sidebar Data Source
with st.sidebar:
    st.header("Data source")
    source = st.radio("Choose data source", ["Use demo data", "Upload CSV / Excel"])
    st.divider()

# Load Data based on selection
if source == "Upload CSV / Excel":
    uploaded = st.file_uploader("Upload a CSV or Excel file", type=["csv", "xlsx"])
    if uploaded is None:
        st.warning("Upload a file to continue, or select 'Use demo data'.")
        st.stop()
    try:
        raw_df = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)
        df = clean_and_validate_data(raw_df)
    except Exception as e:
        st.error(f"Data Error: {e}")
        st.stop()
else:
    # Fallback Demo Data
    demo_data = pd.DataFrame([
        {"Date": "2026-10-01", "Machine": "AWIN1", "Model": "M001", "Shift": "A", "Production": 1000,
         "Defective Cells": 40, "Defect": "Dent", "Count": 15, "Action plan": "Update cooling"},
        {"Date": "2026-10-01", "Machine": "AWIN2", "Model": "M002", "Shift": "A", "Production": 1000,
         "Defective Cells": 40, "Defect": "Bubble", "Count": 25, "Action plan": "Calibrate dispenser"},
        {"Date": "2026-10-02", "Machine": "AWIN3", "Model": "M001", "Shift": "B", "Production": 800,
         "Defective Cells": 20, "Defect": "Wrinkle", "Count": 20, "Action plan": "Adjust tension"},
    ])
    df = clean_and_validate_data(demo_data)

# ==========================================
# 4. FILTERS (Sidebar & Date)
# ==========================================

with st.sidebar:
    st.subheader("Filters")
    selected_machines = st.multiselect("Select Machines", options=sorted(df["Machine"].unique()),
                                       default=sorted(df["Machine"].unique()))
    selected_shifts = st.multiselect("Select Shifts", options=sorted(df["Shift"].unique()),
                                     default=sorted(df["Shift"].unique()))
    selected_models = st.multiselect("Select Models", options=sorted(df["Model"].unique()),
                                     default=sorted(df["Model"].unique()))

if not selected_machines or not selected_shifts or not selected_models:
    st.warning("Please select at least one Machine, Shift, and Model from the sidebar.")
    st.stop()

# Date Filter
st.subheader("Date filter")
c1, c2 = st.columns(2)
with c1:
    start_date = st.date_input("From date", value=df["Date"].min().date(), min_value=df["Date"].min().date(),
                               max_value=df["Date"].max().date())
with c2:
    end_date = st.date_input("To date", value=df["Date"].max().date(), min_value=df["Date"].min().date(),
                             max_value=df["Date"].max().date())

if start_date > end_date:
    st.error("'From date' must be earlier than or equal to 'To date'.")
    st.stop()

# Apply All Filters
filtered_df = df[
    (df["Date"].dt.date >= start_date) &
    (df["Date"].dt.date <= end_date) &
    (df["Machine"].isin(selected_machines)) &
    (df["Shift"].isin(selected_shifts)) &
    (df["Model"].isin(selected_models))
    ].copy()

if filtered_df.empty:
    st.warning("No records found for the selected filters.")
    st.stop()

# ==========================================
# 5. KPIs & COMPARISON CHARTS
# ==========================================

kpi = calculate_kpis(filtered_df)

st.subheader("Production & Quality Overview")
st.caption("KPIs below reflect the **selected filters**.")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Inspected Cells", f'{kpi["production"]:,}')
col2.metric("Defective Cells", f'{kpi["defective"]:,}')
col3.metric("Good Cells", f'{kpi["good"]:,}')
col4.metric("Defect Rate", f'{kpi["defect_rate"]:.2f}%')

st.divider()
st.subheader("Comparison Dashboard")

# Group data to avoid double-counting production numbers
grouped_prod = filtered_df.groupby(["Date", "Machine", "Model", "Shift"]).agg(
    {"Production": "max", "Defective Cells": "max"}).reset_index()

# Prepare Summaries
shift_wise_data = grouped_prod.groupby("Shift", as_index=False).agg(Production=("Production", "sum"),
                                                                    Defective_Cells=("Defective Cells", "sum"))
shift_wise_data["Defect Rate (%)"] = (shift_wise_data["Defective_Cells"] / shift_wise_data["Production"] * 100).round(2)

model_wise_data = grouped_prod.groupby("Model", as_index=False).agg(Production=("Production", "sum"),
                                                                    Defective_Cells=("Defective Cells", "sum"))
model_wise_data["Defect Rate (%)"] = (model_wise_data["Defective_Cells"] / model_wise_data["Production"] * 100).round(2)

machine_wise_data = grouped_prod.groupby("Machine", as_index=False).agg(Production=("Production", "sum"),
                                                                        Defective_Cells=("Defective Cells", "sum"))
machine_wise_data["Defect Rate (%)"] = (
            machine_wise_data["Defective_Cells"] / machine_wise_data["Production"] * 100).round(2)

# --- Section: Shift Performance ---
st.markdown("### Shift Performance")
st.dataframe(shift_wise_data, width="stretch", hide_index=True)

sc1, sc2 = st.columns(2)
with sc1:
    st.plotly_chart(px.bar(shift_wise_data, x="Shift", y=["Production", "Defective_Cells"], barmode="group",
                           title="Production vs Defective (by Shift)"), width="stretch")
with sc2:
    st.plotly_chart(px.bar(shift_wise_data, x="Shift", y="Defect Rate (%)", text="Defect Rate (%)",
                           title="Defect Rate % (by Shift)"), width="stretch")

# --- Section: Model Performance ---
st.markdown("### Model Performance")
st.dataframe(model_wise_data, width="stretch", hide_index=True)

mc1, mc2 = st.columns(2)
with mc1:
    st.plotly_chart(px.bar(model_wise_data, x="Model", y=["Production", "Defective_Cells"], barmode="group",
                           title="Production vs Defective (by Model)"), width="stretch")
with mc2:
    st.plotly_chart(px.bar(model_wise_data, x="Model", y="Defect Rate (%)", text="Defect Rate (%)",
                           title="Defect Rate % (by Model)"), width="stretch")

# --- Section: Machine Performance ---
st.markdown("### Machine Performance")
st.dataframe(machine_wise_data, width="stretch", hide_index=True)

mch1, mch2 = st.columns(2)
with mch1:
    st.plotly_chart(px.bar(machine_wise_data, x="Machine", y=["Production", "Defective_Cells"], barmode="group",
                           title="Production vs Defective (by Machine)"), width="stretch")
with mch2:
    st.plotly_chart(px.bar(machine_wise_data, x="Machine", y="Defect Rate (%)", text="Defect Rate (%)",
                           title="Defect Rate % (by Machine)"), width="stretch")

# --- Section: Defect Breakdown Analysis ---
st.divider()
st.markdown("### Defect Breakdown Analysis")

tab1, tab2 = st.tabs(["By Model", "By Machine"])

with tab1:
    chart_type_model = st.radio("Select chart view:", ["Defect by Model", "Model by Defect"], horizontal=True,
                                key="radio_model")
    model_defects = filtered_df.groupby(["Model", "Defect"], as_index=False)["Count"].sum()

    if chart_type_model == "Defect by Model":
        fig = px.bar(model_defects, x="Model", y="Count", color="Defect", barmode="stack",
                     title="Defect Categories per Model")
    else:
        fig = px.bar(model_defects, x="Defect", y="Count", color="Model", barmode="group",
                     title="Models per Defect Category")
    st.plotly_chart(fig.update_layout(xaxis_tickangle=-45), width="stretch")

with tab2:
    chart_type_machine = st.radio("Select chart view:", ["Defect by Machine", "Machine by Defect"], horizontal=True,
                                  key="radio_machine")
    machine_defects = filtered_df.groupby(["Machine", "Defect"], as_index=False)["Count"].sum()

    if chart_type_machine == "Defect by Machine":
        fig = px.bar(machine_defects, x="Machine", y="Count", color="Defect", barmode="stack",
                     title="Defect Categories per Machine")
    else:
        fig = px.bar(machine_defects, x="Defect", y="Count", color="Machine", barmode="group",
                     title="Machines per Defect Category")
    st.plotly_chart(fig.update_layout(xaxis_tickangle=-45), width="stretch")

# ==========================================
# 6. DEFECT SUMMARY & PARETO ANALYSIS
# ==========================================

st.divider()
st.subheader("Defect Summary")
total_defects = int(filtered_df["Count"].sum())
top_defect = filtered_df.groupby("Defect")["Count"].sum().idxmax() if total_defects > 0 else "None"

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Defect Occurrences", f"{total_defects:,}")
m2.metric("Defect Categories", f'{filtered_df["Defect"].nunique():,}')
m3.metric("Records", f"{len(filtered_df):,}")
with m4:
    st.metric("Top Defect", top_defect if len(top_defect) < 15 else top_defect[:15] + "...")
    st.caption(top_defect)

# Pareto Calculation & Chart
st.subheader("Pareto Analysis (80/20)")
pareto_df = build_pareto_table(filtered_df)
p_left, p_right = st.columns([1.35, 1])

with p_left:
    fig_pareto = make_subplots(specs=[[{"secondary_y": True}]])
    fig_pareto.add_bar(x=pareto_df["Defect"], y=pareto_df["Count"], name="Occurrences", marker_color="#4C78A8")
    fig_pareto.add_scatter(x=pareto_df["Defect"], y=pareto_df["Cumulative %"], name="Cumulative %",
                           mode="lines+markers", line=dict(color="#E45756", width=2), secondary_y=True)
    fig_pareto.add_hline(y=80, line_dash="dash", line_color="gray", secondary_y=True, annotation_text="80%",
                         annotation_position="top right")

    fig_pareto.update_layout(title="Defects ranked (Pareto)", xaxis_tickangle=-45, margin=dict(b=120),
                             hovermode="x unified")
    fig_pareto.update_yaxes(title_text="Count", secondary_y=False)
    fig_pareto.update_yaxes(title_text="Cumulative %", range=[0, 105], ticksuffix="%", secondary_y=True)
    st.plotly_chart(fig_pareto, width="stretch")

with p_right:
    st.markdown("**Defect Trend**")
    trend_df = filtered_df.groupby(filtered_df["Date"].dt.date)["Count"].sum().reset_index()
    trend_df.columns = ["Date", "Count"]
    st.plotly_chart(px.line(trend_df, x="Date", y="Count", markers=True, title="Daily defect occurrences"),
                    width="stretch")

# 80/20 Insight
if not pareto_df.empty and pareto_df["Cumulative %"].max() >= 80:
    vital_few = pareto_df[pareto_df["Cumulative %"] <= 80]
    vital_count = len(vital_few) + 1 if len(vital_few) < len(pareto_df) else len(vital_few)
    # st.info(
    #     f"💡 **80/20 Insight:** Just **{vital_count} out of {len(pareto_df)} defect categories** are responsible for **80% of all defects**.")
else:
    st.info("💡 All defect categories are required to reach 80% of occurrences.")

st.dataframe(pareto_df, width="stretch", hide_index=True)

# ==========================================
# 7. DEFECT RECORDS & EXPORT
# ==========================================

st.divider()
st.subheader("Defect Records")
# st.caption("💡 **Tip:** Kisi bhi row par click karein aur us defect ka poora Action Plan neeche dekhein.")

cols_order = ["Date", "Machine", "Model", "Shift", "Production", "Defective Cells", "Defect", "Count", "Action plan"]
display_df = filtered_df[[c for c in cols_order if c in filtered_df.columns]].sort_values("Date", ascending=False)

# Reset index taaki click karne par sahi row ka data mile
display_df = display_df.reset_index(drop=True)

# Dataframe with row selection enabled
event = st.dataframe(
    display_df,
    width="stretch",
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "Action plan": st.column_config.TextColumn(
            "Action Plan",
            help="Click on the row to view full text below",
            width="medium"  # Chhota kar diya taaki table screen par fit ho jaye
        )
    }
)

# Agar user ne koi row select ki hai, toh uska poora Action Plan dikhao
if event.selection and event.selection.rows:
    selected_idx = event.selection.rows[0]
    selected_row = display_df.iloc[selected_idx]

    st.info(
        f"**Selected Defect Details:**\n\n"
        f"**Date:** {selected_row['Date'].strftime('%Y-%m-%d')} | "
        f"**Machine:** {selected_row['Machine']} | "
        f"**Model:** {selected_row['Model']} | "
        f"**Defect:** {selected_row['Defect']}\n\n"
        f"**Full Action Plan:**\n\n"
        f"{selected_row['Action plan']}"
    )

st.subheader("Export Data")
c_exp1, c_exp2, c_exp3 = st.columns(3)
with c_exp1:
    st.download_button("⬇️ Pareto Report (CSV)", data=pareto_df.to_csv(index=False).encode("utf-8-sig"),
                       file_name="Pareto_Report.csv", mime="text/csv", width="stretch")
with c_exp2:
    st.download_button("⬇️ Filtered Records (CSV)", data=display_df.to_csv(index=False).encode("utf-8-sig"),
                       file_name="Filtered_Records.csv", mime="text/csv", width="stretch")
with c_exp3:
    st.download_button("⬇️ Shift Summary (CSV)", data=shift_wise_data.to_csv(index=False).encode("utf-8-sig"),
                       file_name="Shift_Summary.csv", mime="text/csv", width="stretch")

pdf_bytes = generate_pdf_report(kpi, pareto_df, (start_date, end_date), filtered_df)
st.download_button(
    label="🖨️ Download Executive PDF Report",
    data=pdf_bytes,
    file_name="Smart_QA_Report.pdf",
    mime="application/pdf",
    type="primary",
    width="stretch"
)
