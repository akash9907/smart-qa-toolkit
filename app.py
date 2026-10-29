import io
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import pandas as pd
import plotly.express as px
from plotly.subplots import make_subplots
import streamlit as st

st.set_page_config(
    page_title="Smart QA Toolkit",
    page_icon="🛡️",
    layout="wide"
)

# UPDATED: "Line" is now "Machine"
REQUIRED_COLUMNS = [
    "Date", "Machine", "Model", "Shift", "Production", "Defective Cells", "Defect", "Count"
]
OPTIONAL_COLUMNS = ["Action plan"]


# ---------------- PDF GENERATION ----------------

def generate_pdf_report(kpi, pareto_df, shift_df, date_range, filtered_df):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(name='TitleStyle', parent=styles['Heading1'], alignment=1,
                                 textColor=colors.HexColor("#1f77b4"))
    elements.append(Paragraph("Smart QA Toolkit - Executive Report", title_style))
    elements.append(Paragraph(f"Date Range: {date_range[0]} to {date_range[1]}", styles['Normal']))
    elements.append(Spacer(1, 15))

    kpi_data = [
        ["Inspected Cells", "Defective Cells", "Good Cells", "Defect Rate"],
        [f"{kpi['production']:,}", f"{kpi['defective']:,}", f"{kpi['good']:,}", f"{kpi['defect_rate']:.2f}%"]
    ]
    kpi_table = Table(kpi_data, colWidths=[120, 120, 120, 120])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f0f2f6")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, 1), colors.white),
        ('FONTSIZE', (0, 1), (-1, 1), 14),
        ('TOPPADDING', (0, 1), (-1, 1), 10),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey)
    ]))
    elements.append(kpi_table)
    elements.append(Spacer(1, 20))

    elements.append(Paragraph("<b>Defect Summary Table</b>", styles['Heading2']))

    summary_data = [["Rank", "Defect Name", "Total Count"]]
    for _, row in pareto_df.head(10).iterrows():  # Top 10 defects PDF mein
        summary_data.append([str(row["Rank"]), row["Defect"], str(row["Count"])])

    summary_table = Table(summary_data, colWidths=[60, 200, 100])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f0f2f6")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9f9f9")])
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))

    elements.append(Paragraph("<b>Top 5 Defects & Action Plan</b>", styles['Heading2']))
    action_plans = filtered_df[["Defect", "Action plan"]].drop_duplicates().groupby("Defect")[
        "Action plan"].first().to_dict()

    table_data = [["Rank", "Defect Category", "Count", "Cum. %", "Action Plan"]]
    for index, row in pareto_df.head(5).iterrows():
        action = action_plans.get(row['Defect'], "Pending")
        action_para = Paragraph(str(action), styles['Normal'])
        table_data.append([str(row['Rank']), row['Defect'], str(row['Count']), f"{row['Cumulative %']}%", action_para])

    defect_table = Table(table_data, colWidths=[40, 120, 50, 60, 250])
    defect_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1f77b4")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (3, -1), 'CENTER'),
        ('ALIGN', (4, 0), (4, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9f9f9")])
    ]))
    elements.append(defect_table)

    doc.build(elements)
    buffer.seek(0)
    return buffer


# ---------------- DATA CLEANING ----------------

def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    cols_to_keep = REQUIRED_COLUMNS + [c for c in OPTIONAL_COLUMNS if c in df.columns]
    out = df[cols_to_keep].copy()
    out = out.drop_duplicates()

    out["Date"] = pd.to_datetime(out["Date"], errors="coerce", dayfirst=True)

    out["Machine"] = out["Machine"].astype("string").str.strip().str.upper()
    out["Shift"] = out["Shift"].astype("string").str.strip().str.upper()
    out["Model"] = out["Model"].astype("string").str.strip().str.upper()
    out["Defect"] = out["Defect"].astype("string").str.strip().str.title()

    if "Action plan" in out.columns:
        out["Action plan"] = out["Action plan"].astype("string").str.strip().fillna("Pending")
    else:
        out["Action plan"] = "Pending"

    numeric_columns = ["Production", "Defective Cells", "Count"]
    for column in numeric_columns:
        out[column] = pd.to_numeric(out[column], errors="coerce")

    out = out.dropna(subset=["Date", "Machine", "Model", "Production", "Defective Cells", "Defect", "Count"])

    out = out[
        (out["Machine"] != "") & (out["Model"] != "") & (out["Shift"] != "")
        & (out["Defect"] != "") & (out["Production"] > 0)
        & (out["Defective Cells"] >= 0) & (out["Count"] >= 0)
        ].copy()

    for column in numeric_columns:
        if not (out[column] % 1 == 0).all():
            raise ValueError(f"'{column}' must contain whole numbers only.")
        out[column] = out[column].astype("int64")

    if (out["Defective Cells"] > out["Production"]).any():
        raise ValueError("Defective Cells cannot be greater than Production.")

    group_keys = ["Date", "Machine", "Model", "Shift"]

    grouped = out.groupby(group_keys)[["Production", "Defective Cells"]].nunique()
    if (grouped > 1).any().any():
        raise ValueError(
            "Production and Defective Cells must have the same values for every Date + Machine + Model + Shift combination.")

    defect_totals = out.groupby(group_keys)["Count"].sum().rename("Total Count")
    cell_totals = out.groupby(group_keys)["Defective Cells"].first().rename("Defective Cells")
    check = pd.concat([defect_totals, cell_totals], axis=1)

    bad = check[check["Total Count"] > check["Defective Cells"]]
    if not bad.empty:
        raise ValueError("Sum of defect Count exceeds Defective Cells for: " + ", ".join(
            f"{d} / {m} / {s}" for d, m, s in bad.index.tolist()[:5]) + (" ..." if len(bad) > 5 else ""))

    return out


# ---------------- PARETO & KPI ----------------

def pareto_table(df: pd.DataFrame) -> pd.DataFrame:
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


def calculate_kpis(df: pd.DataFrame) -> dict:
    prod_data = df.groupby(["Date", "Machine", "Model", "Shift"]).agg({
        "Production": "max",
        "Defective Cells": "max"
    }).reset_index()

    total_production = int(prod_data["Production"].sum())
    total_defective = int(prod_data["Defective Cells"].sum())
    total_good = total_production - total_defective
    defect_rate = (total_defective / total_production * 100) if total_production > 0 else 0

    return {"production": total_production, "defective": total_defective, "good": total_good,
            "defect_rate": defect_rate}


# ---------------- APP HEADER ----------------

st.title("🛡️ Smart QA Toolkit")
st.caption("Quality Analysis & Defect Summary • V1.7")
st.info("Developed By Akash")

# ---------------- SIDEBAR ----------------

with st.sidebar:
    st.header("Data source")
    source = st.radio("Choose data source", ["Use demo data", "Upload CSV / Excel"])
    st.caption("Required: Date, Machine, Model, Shift, Production, Defective Cells, Defect, Count")
    st.divider()

# ---------------- DEMO DATA ----------------

demo = pd.DataFrame([
    {"Date": "2026-10-01", "Machine": "MCH-01", "Model": "M001", "Shift": "A", "Production": 1000,
     "Defective Cells": 40,
     "Defect": "Dent", "Count": 15, "Action plan": "Update cooling"},
    {"Date": "2026-10-01", "Machine": "MCH-02", "Model": "M002", "Shift": "A", "Production": 1000,
     "Defective Cells": 40,
     "Defect": "Bubble", "Count": 25, "Action plan": "Calibrate dispenser"},
    {"Date": "2026-10-02", "Machine": "MCH-01", "Model": "M001", "Shift": "B", "Production": 800, "Defective Cells": 20,
     "Defect": "Wrinkle", "Count": 20, "Action plan": "Adjust tension"},
])

# ---------------- LOAD DATA ----------------

if source == "Upload CSV / Excel":
    uploaded = st.file_uploader("Upload a CSV or Excel file", type=["csv", "xlsx"])
    if uploaded is None:
        st.warning("Upload a file to continue, or select 'Use demo data'.")
        st.stop()

    try:
        if uploaded.name.lower().endswith(".csv"):
            raw_df = pd.read_csv(uploaded)
        else:
            raw_df = pd.read_excel(uploaded)
        data = clean_data(raw_df)
    except Exception as e:
        st.error(f"Could not read or validate the file: {e}")
        st.stop()
else:
    data = clean_data(demo)

if data.empty:
    st.warning("No valid records found. Please check your data.")
    st.stop()

# ---------------- FILTERS ----------------

with st.sidebar:
    st.subheader("Filters")

    # NEW: Machine Filter
    available_machines = sorted(data["Machine"].dropna().unique().tolist())
    selected_machines = st.multiselect("Select Machines", options=available_machines, default=available_machines)

    available_shifts = sorted(data["Shift"].dropna().unique().tolist())
    selected_shifts = st.multiselect("Select Shifts", options=available_shifts, default=available_shifts)

    available_models = sorted(data["Model"].dropna().unique().tolist())
    selected_models = st.multiselect("Select Models", options=available_models, default=available_models)

if not selected_machines or not selected_shifts or not selected_models:
    st.warning("Please select at least one machine, shift, and model.")
    st.stop()

st.subheader("Date filter")
min_date = data["Date"].min().date()
max_date = data["Date"].max().date()

c1, c2 = st.columns(2)
with c1:
    start_date = st.date_input("From date", value=min_date, min_value=min_date, max_value=max_date)
with c2:
    end_date = st.date_input("To date", value=max_date, min_value=min_date, max_value=max_date)

if start_date > end_date:
    st.error("'From date' must be earlier than or equal to 'To date'.")
    st.stop()

date_filtered = data[(data["Date"].dt.date >= start_date) & (data["Date"].dt.date <= end_date)].copy()

if date_filtered.empty:
    st.warning("No records in the selected date range.")
    st.stop()

# Apply Machine, Shift, and Model filters for the main dashboard
filtered = date_filtered[
    (date_filtered["Machine"].isin(selected_machines)) &
    (date_filtered["Shift"].isin(selected_shifts)) &
    (date_filtered["Model"].isin(selected_models))
    ].copy()

if filtered.empty:
    st.warning("No records found for the selected filters.")
    st.stop()

# ---------------- KPIs ----------------

kpi = calculate_kpis(filtered)

st.subheader("Production & Quality Overview")
st.caption("KPIs below reflect the **selected filters**.")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Inspected Cells", f'{kpi["production"]:,}')
col2.metric("Defective Cells", f'{kpi["defective"]:,}')
col3.metric("Good Cells", f'{kpi["good"]:,}')
col4.metric("Defect Rate", f'{kpi["defect_rate"]:.2f}%')

# ---------------- COMPARISON DASHBOARD ----------------

st.divider()
st.subheader("Comparison Dashboard")
st.caption("Charts below reflect the **selected filters**.")

# Grouping logic
group_production = filtered.groupby(["Date", "Machine", "Model", "Shift"]).agg(
    {"Production": "max", "Defective Cells": "max"}).reset_index()

shift_summary = group_production.groupby("Shift", as_index=False).agg(Production=("Production", "sum"),
                                                                      Defective_Cells=("Defective Cells", "sum"))
shift_summary["Good Cells"] = shift_summary["Production"] - shift_summary["Defective_Cells"]
shift_summary["Defect Rate (%)"] = (
        shift_summary["Defective_Cells"].div(shift_summary["Production"].replace(0, pd.NA)) * 100).round(2).fillna(
    0.0)

model_summary = group_production.groupby("Model", as_index=False).agg(Production=("Production", "sum"),
                                                                      Defective_Cells=("Defective Cells", "sum"))
model_summary["Good Cells"] = model_summary["Production"] - model_summary["Defective_Cells"]
model_summary["Defect Rate (%)"] = (
        model_summary["Defective_Cells"].div(model_summary["Production"].replace(0, pd.NA)) * 100).round(2).fillna(
    0.0)

# Shift Charts
st.markdown("### Shift Performance")
st.dataframe(shift_summary.rename(columns={"Defective_Cells": "Defective Cells"}), width="stretch", hide_index=True)

col_s1, col_s2 = st.columns(2)
with col_s1:
    fig1 = px.bar(shift_summary, x="Shift", y=["Production", "Defective_Cells"], barmode="group",
                  title="Production vs Defective (by Shift)")
    st.plotly_chart(fig1, width="stretch")
with col_s2:
    fig2 = px.bar(shift_summary, x="Shift", y="Defect Rate (%)", text="Defect Rate (%)",
                  title="Defect Rate % (by Shift)")
    st.plotly_chart(fig2, width="stretch")

# Model Charts
st.markdown("### Model Performance")
st.dataframe(model_summary.rename(columns={"Defective_Cells": "Defective Cells"}), width="stretch", hide_index=True)

col_m1, col_m2 = st.columns(2)
with col_m1:
    fig_m1 = px.bar(model_summary, x="Model", y=["Production", "Defective_Cells"], barmode="group",
                    title="Production vs Defective (by Model)")
    st.plotly_chart(fig_m1, width="stretch")
with col_m2:
    fig_m2 = px.bar(model_summary, x="Model", y="Defect Rate (%)", text="Defect Rate (%)",
                    title="Defect Rate % (by Model)")
    st.plotly_chart(fig_m2, width="stretch")

# Defect Breakdown Chart
st.markdown("### Defect Breakdown")
model_defects = filtered.groupby(["Model", "Defect"], as_index=False)["Count"].sum()

chart_type = st.radio("Select chart view:", ["Defect by Model", "Model by Defect"], horizontal=True)

if chart_type == "Defect by Model":
    fig_model_defect = px.bar(model_defects, x="Model", y="Count", color="Defect", barmode="stack",
                              title="Defect Categories per Model")
else:
    fig_model_defect = px.bar(model_defects, x="Defect", y="Count", color="Model", barmode="group",
                              title="Models per Defect Category")

fig_model_defect.update_layout(xaxis_tickangle=-45, margin=dict(b=100))
st.plotly_chart(fig_model_defect, width="stretch")

# Defect Breakdown Chart (Machine-wise)
st.markdown("### Machine-wise Defect Breakdown")
machine_defects = filtered.groupby(["Machine", "Defect"], as_index=False)["Count"].sum()

machine_chart_type = st.radio("Select machine chart view:", ["Defect by Machine", "Machine by Defect"], horizontal=True, key="machine_radio")

if machine_chart_type == "Defect by Machine":
    fig_machine_defect = px.bar(machine_defects, x="Machine", y="Count", color="Defect", barmode="stack",
                              title="Defect Categories per Machine")
else:
    fig_machine_defect = px.bar(machine_defects, x="Defect", y="Count", color="Machine", barmode="group",
                              title="Machines per Defect Category")

fig_machine_defect.update_layout(xaxis_tickangle=-45, margin=dict(b=100))
st.plotly_chart(fig_machine_defect, width="stretch")

# ---------------- DEFECT SUMMARY ----------------

total_defects = int(filtered["Count"].sum())
unique_defects = int(filtered["Defect"].nunique())
total_records = int(len(filtered))
top_row = filtered.groupby("Defect")["Count"].sum().sort_values(ascending=False)
top_defect = top_row.index[0] if len(top_row) and top_row.iloc[0] > 0 else "None"

st.subheader("Defect Summary")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Defect Occurrences", f"{total_defects:,}")
m2.metric("Defect Categories", f"{unique_defects:,}")
m3.metric("Records", f"{total_records:,}")

with m4:
    st.metric("Top Defect", top_defect if len(top_defect) < 15 else top_defect[:15] + "...")
    st.caption(top_defect)

# ---------------- CHARTS & PARETO ----------------

st.divider()
st.subheader("Pareto Analysis (80/20)")
st.caption("Reflects the **selected filters**.")

p = pareto_table(filtered)
left, right = st.columns([1.35, 1])

with left:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_bar(
        x=p["Defect"], y=p["Count"], name="Occurrences", marker_color="#4C78A8",
        customdata=p[["Rank", "Defect %", "Cumulative %"]],
        hovertemplate="<b>%{x}</b><br>Count: %{y}<br>Rank: %{customdata[0]}<br>Defect %: %{customdata[1]}<br>Cumulative %: %{customdata[2]}<extra></extra>",
    )
    fig.add_scatter(
        x=p["Defect"], y=p["Cumulative %"], name="Cumulative %", mode="lines+markers",
        line=dict(color="#E45756", width=2), marker=dict(size=7), secondary_y=True,
        hovertemplate="Cumulative: %{y:.2f}%<extra></extra>",
    )
    fig.add_hline(y=80, line_dash="dash", line_color="gray", secondary_y=True, annotation_text="80%",
                  annotation_position="top right")
    fig.update_layout(
        title="Defects ranked — bars = count, line = cumulative %",
        xaxis_title="Defect category", legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        hovermode="x unified", bargap=0.15, margin=dict(b=120)
    )
    fig.update_yaxes(title_text="Defect occurrences", secondary_y=False)
    fig.update_yaxes(title_text="Cumulative %", range=[0, 105], ticksuffix="%", secondary_y=True)
    fig.update_xaxes(tickangle=-45)
    st.plotly_chart(fig, width="stretch")

with right:
    st.markdown("**Defect Trend**")
    trend = filtered.groupby(filtered["Date"].dt.date)["Count"].sum().reset_index()
    trend.columns = ["Date", "Count"]
    trend["Date"] = pd.to_datetime(trend["Date"])
    trend_fig = px.line(trend, x="Date", y="Count", markers=True, title="Daily defect occurrences")
    trend_fig.update_layout(margin=dict(b=50))
    st.plotly_chart(trend_fig, width="stretch")

st.subheader("Pareto Table & 80/20 Insight")
if not p.empty and p["Cumulative %"].max() >= 80:
    vital_few = p[p["Cumulative %"] <= 80]
    vital_few_count = len(vital_few) + 1 if len(vital_few) < len(p) else len(vital_few)
    vital_few_pct = (vital_few_count / len(p)) * 100
    st.info(
        f"💡 **80/20 Insight:** Just **{vital_few_count} out of {len(p)} defect categories** ({vital_few_pct:.1f}%) are responsible for **80% of all defects**.")
elif not p.empty:
    st.info("💡 All defect categories are required to reach 80% of occurrences.")

st.dataframe(p, width="stretch", hide_index=True)

# ---------------- DEFECT RECORDS & EXPORT ----------------

st.subheader("Defect Records")
cols_order = ["Date", "Machine", "Model", "Shift", "Production", "Defective Cells", "Defect", "Count", "Action plan"]
display_df = filtered[[c for c in cols_order if c in filtered.columns]].sort_values("Date", ascending=False)

st.dataframe(
    display_df, width="stretch", hide_index=True,
    column_config={"Action plan": st.column_config.TextColumn("Action Plan", help="Corrective action", width="large")}
)

st.divider()
st.subheader("Export Data")

col_exp1, col_exp2, col_exp3 = st.columns(3)
with col_exp1:
    st.download_button("⬇️ Pareto Report (CSV)", data=p.to_csv(index=False).encode("utf-8-sig"),
                       file_name="smart_qa_pareto_report.csv", mime="text/csv", width="stretch")
with col_exp2:
    st.download_button("⬇️ Filtered Records (CSV)",
                       data=filtered.sort_values("Date", ascending=False).to_csv(index=False).encode("utf-8-sig"),
                       file_name="smart_qa_filtered_records.csv", mime="text/csv", width="stretch")
with col_exp3:
    st.download_button("⬇️ Shift Summary (CSV)", data=shift_summary.to_csv(index=False).encode("utf-8-sig"),
                       file_name="smart_qa_shift_summary.csv", mime="text/csv", width="stretch")

st.markdown("<br>", unsafe_allow_html=True)
pdf_bytes = generate_pdf_report(kpi, p, shift_summary, (start_date, end_date), filtered)
st.download_button(
    label="🖨️ Download Executive PDF Report", data=pdf_bytes, file_name="Smart_QA_Report.pdf",
    mime="application/pdf", type="primary", width="stretch"
)
