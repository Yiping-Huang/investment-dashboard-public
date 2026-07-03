"""Read-only Streamlit dashboard for public deployment exports."""

from __future__ import annotations

import os
from html import escape
from datetime import date, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import requests
import streamlit as st


DEFAULT_PRICE_SCHEMA = "market"
DEFAULT_PORTFOLIO_SCHEMA = "portfolio"
DEFAULT_SYMBOL = "VFV.TO"
DEFAULT_TARGET_CAGR = 0.10
COMFORT_ZONE_MULTIPLIER = 0.10
EMA_PERIODS = [8, 20, 50, 100, 200]
EMA_HISTORY_DAYS = 420
VANCOUVER_TZ = ZoneInfo("America/Vancouver")
SECTION_OVERVIEW = "Overview"
SECTION_ACCOUNTS_TAX = "Accounts and Tax"
SECTION_GOALS = "Goals"
SECTION_ALLOCATION = "Allocation"
SECTION_PERFORMANCE_INCOME = "Performance and Income"
SECTION_RISK_LIQUIDITY = "Risk and Liquidity"
SECTION_HOLDINGS = "Holdings"
SECTION_RESEARCH = "Research"
PREFERRED_HOLDING_SYMBOLS = [DEFAULT_SYMBOL, "XEQT.TO", "QQC.TO", "CASH.TO", "QQQ"]
HISTORY_WINDOW_OPTIONS = {
    "All Time": None,
    "1 Week": 7,
    "2 Weeks": 14,
    "30 Days": 30,
    "45 Days": 45,
    "60 Days": 60,
    "90 Days": 90,
    "120 Days": 120,
    "180 Days": 180,
    "270 Days": 270,
    "1 Year": 365,
    "18 Months": 545,
    "2 Years": 730,
}
SECTION_SUBPAGES = {
    SECTION_OVERVIEW: [
        "Net Worth",
        "Monthly Trend",
        "Emergency Fund Progress",
        "Asset Allocation",
        "Tax Sheltered Allocation",
    ],
    SECTION_ACCOUNTS_TAX: [
        "Account Allocation",
        "Account Balances",
        "TFSA Room",
        "RRSP Room",
        "Tax Advantaged Coverage",
    ],
    SECTION_GOALS: [
        "Short-Term Goals",
        "Mid-Term Goals",
        "Long-Term Goals",
    ],
    SECTION_ALLOCATION: [
        "Asset Class Allocation",
        "Target vs Actual Allocation",
        "Purpose Allocation",
    ],
    SECTION_PERFORMANCE_INCOME: [
        "Income Summary",
        "Principal vs Growth",
        "Return vs Inflation",
        "Yield Table",
    ],
    SECTION_RISK_LIQUIDITY: [
        "Portfolio Characteristics",
        "Liquidity Ladder",
        "Risk Allocation",
    ],
    SECTION_RESEARCH: [
        "Watchlist",
        "Comparison",
    ],
}
DASHBOARD_SECTIONS = [
    SECTION_OVERVIEW,
    SECTION_ACCOUNTS_TAX,
    SECTION_GOALS,
    SECTION_ALLOCATION,
    SECTION_PERFORMANCE_INCOME,
    SECTION_RISK_LIQUIDITY,
    SECTION_HOLDINGS,
    SECTION_RESEARCH,
]


def get_setting(name: str, default: str | None = None) -> str | None:
    try:
        value = st.secrets.get(name)
    except Exception:
        value = None
    return value or os.getenv(name) or default


def supabase_url() -> str:
    url = get_setting("SUPABASE_URL")
    if not url:
        raise RuntimeError("Missing SUPABASE_URL.")
    return url.rstrip("/")


def supabase_anon_key() -> str:
    anon_key = get_setting("SUPABASE_ANON_KEY") or get_setting("SUPABASE_READ_KEY")
    if not anon_key:
        raise RuntimeError("Missing Supabase anon key. Set SUPABASE_ANON_KEY.")
    return anon_key


def supabase_auth_token() -> str | None:
    return st.session_state.get("supabase_access_token")


def supabase_headers(schema: str, access_token: str | None = None) -> dict[str, str]:
    anon_key = supabase_anon_key()
    bearer_token = access_token or anon_key
    return {
        "apikey": anon_key,
        "Authorization": f"Bearer {bearer_token}",
        "Accept-Profile": schema,
        "Content-Profile": schema,
    }


def sign_in_with_password(email: str, password: str) -> dict[str, Any]:
    anon_key = supabase_anon_key()
    response = requests.post(
        f"{supabase_url()}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": anon_key, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError("Email or password is incorrect.")

    payload = response.json()
    if not payload.get("access_token"):
        raise RuntimeError("Supabase Auth did not return an access token.")
    return payload


def require_supabase_auth() -> None:
    if supabase_auth_token():
        return

    st.subheader("Sign In")
    with st.form("supabase_auth"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")

    if submitted:
        if not email.strip() or not password:
            st.error("Email and password are required.")
        else:
            try:
                payload = sign_in_with_password(email.strip(), password)
            except RuntimeError as error:
                st.error(str(error))
            else:
                user = payload.get("user") or {}
                st.session_state["supabase_access_token"] = payload["access_token"]
                st.session_state["supabase_user_email"] = user.get("email") or email.strip()
                fetch_table.clear()
                st.rerun()

    st.stop()


def sidebar() -> str:
    if st.session_state.get("dashboard_page") not in DASHBOARD_SECTIONS:
        st.session_state["dashboard_page"] = SECTION_HOLDINGS

    st.markdown(
        """
        <style>
        section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            padding-top: 0.15rem !important;
        }
        section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
            padding-top: 0 !important;
        }
        .sidebar-title {
            margin: -2.2rem 0 0.9rem 0;
            padding: 0;
            font-size: 1.35rem;
            font-weight: 700;
            line-height: 1.15;
        }
        [data-testid="stSidebar"] div.stButton > button {
            justify-content: flex-start;
            text-align: left;
        }
        [data-testid="stSidebar"] div.stButton > button:disabled {
            opacity: 1;
        }
        .st-key-sidebar_auth_footer {
            margin-top: 1.25rem;
            width: 100%;
            padding: 0.75rem 0.85rem;
            border: 1px solid rgba(128, 128, 128, 0.22);
            border-radius: 0.5rem;
            background: rgba(255, 255, 255, 0.04);
        }
        .sidebar-account-label {
            font-size: 0.72rem;
            color: rgba(128, 128, 128, 0.95);
            margin-bottom: 0.1rem;
        }
        .sidebar-account-email {
            font-size: 0.86rem;
            font-weight: 500;
            line-height: 1.25;
            overflow-wrap: anywhere;
            margin-bottom: 0.45rem;
        }
        .st-key-sidebar_auth_footer div.stButton > button {
            width: auto;
            min-height: 2rem;
            padding: 0.2rem 0.6rem;
            font-size: 0.85rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown('<div class="sidebar-title">Dashboard</div>', unsafe_allow_html=True)
        for section in DASHBOARD_SECTIONS:
            is_active = st.session_state["dashboard_page"] == section
            if st.button(
                section,
                key=f"nav_{section}",
                disabled=is_active,
                width="stretch",
                type="primary" if is_active else "secondary",
            ):
                st.session_state["dashboard_page"] = section
                st.rerun()
        with st.container(key="sidebar_auth_footer"):
            user_email = st.session_state.get("supabase_user_email")
            if user_email:
                st.markdown(
                    (
                        '<div class="sidebar-account-label">Signed in as</div>'
                        f'<div class="sidebar-account-email">{escape(user_email)}</div>'
                    ),
                    unsafe_allow_html=True,
                )
                if st.button("Sign out", key="sign_out"):
                    st.session_state.pop("supabase_access_token", None)
                    st.session_state.pop("supabase_user_email", None)
                    fetch_table.clear()
                    st.rerun()

    return st.session_state["dashboard_page"]


@st.cache_data(ttl=300)
def fetch_table(
    schema: str,
    table: str,
    params: tuple[tuple[str, str], ...],
    access_token: str | None = None,
) -> list[dict[str, Any]]:
    response = requests.get(
        f"{supabase_url()}/rest/v1/{table}",
        params=dict(params),
        headers=supabase_headers(schema, access_token),
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Supabase read failed for {schema}.{table}: "
            f"{response.status_code} {response.text}"
        )
    return response.json()


def load_assets(price_schema: str) -> pd.DataFrame:
    rows = fetch_table(
        price_schema,
        "assets",
        (
            ("select", "symbol,name,asset_type,exchange,currency"),
            ("order", "symbol.asc"),
        ),
        supabase_auth_token(),
    )
    return pd.DataFrame(rows)


@st.cache_data(ttl=3600)
def load_tracked_market_symbols(price_schema: str) -> pd.DataFrame:
    rows = fetch_table(
        price_schema,
        "watchlist_symbols",
        (
            ("select", "symbol,name,asset_type,exchange,currency,yahoo_chart_symbol,twelve_data_symbol,manual_pe_ratio,manual_pe_updated_on,manual_pe_source,manual_pe_notes,manual_beta,manual_beta_updated_on,manual_beta_source,manual_beta_notes,active,notes,added_at,updated_at"),
            ("active", "eq.true"),
            ("order", "symbol.asc"),
        ),
        supabase_auth_token(),
    )
    return pd.DataFrame(rows)


def load_latest_quote_snapshots(price_schema: str) -> pd.DataFrame:
    rows = fetch_table(
        price_schema,
        "latest_asset_quote_snapshots",
        (
            ("select", "symbol,snapshot_date,latest_close,volume,average_volume,pe_ratio,beta,expense_ratio,nav,market_cap,source,fetched_at"),
            ("source", "eq.daily_prices_derived"),
            ("order", "symbol.asc"),
        ),
        supabase_auth_token(),
    )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    for column in [
        "latest_close",
        "volume",
        "average_volume",
        "pe_ratio",
        "beta",
        "expense_ratio",
        "nav",
        "market_cap",
    ]:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["snapshot_date"] = pd.to_datetime(frame["snapshot_date"])
    return frame


def load_prices(price_schema: str, symbol: str, start_date: date) -> pd.DataFrame:
    rows = fetch_table(
        price_schema,
        "daily_prices",
        (
            ("select", "symbol,price_date,open,high,low,close,adjusted_close,volume,source,fetched_at"),
            ("symbol", f"eq.{symbol}"),
            ("price_date", f"gte.{start_date.isoformat()}"),
            ("order", "price_date.asc"),
        ),
        supabase_auth_token(),
    )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    frame["price_date"] = pd.to_datetime(frame["price_date"])
    for column in ["open", "high", "low", "close", "adjusted_close", "volume"]:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def load_positions(portfolio_schema: str, symbol: str) -> pd.DataFrame:
    access_token = supabase_auth_token()
    if not access_token:
        raise RuntimeError("Sign in before reading portfolio data.")

    try:
        rows = fetch_table(
            portfolio_schema,
            "latest_positions",
            (
                ("select", "symbol,account_name,quantity,average_cost,currency,as_of_date,notes"),
                ("symbol", f"eq.{symbol}"),
                ("order", "as_of_date.desc"),
            ),
            access_token,
        )
    except RuntimeError:
        rows = fetch_table(
            portfolio_schema,
            "positions",
            (
                ("select", "symbol,account_name,quantity,average_cost,currency,as_of_date,notes"),
                ("symbol", f"eq.{symbol}"),
                ("order", "as_of_date.desc"),
            ),
            access_token,
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    frame["quantity"] = pd.to_numeric(frame["quantity"], errors="coerce")
    frame["average_cost"] = pd.to_numeric(frame["average_cost"], errors="coerce")
    frame["as_of_date"] = pd.to_datetime(frame["as_of_date"])
    return frame


def load_transactions(portfolio_schema: str, symbol: str | None = None) -> pd.DataFrame:
    access_token = supabase_auth_token()
    if not access_token:
        raise RuntimeError("Sign in before reading portfolio data.")

    params: list[tuple[str, str]] = [
        ("select", "id,symbol,account_id,transaction_date,transaction_type,quantity,price,fees,currency,notes,created_at"),
        ("order", "transaction_date.desc"),
    ]
    if symbol:
        params.append(("symbol", f"eq.{symbol}"))

    rows = fetch_table(portfolio_schema, "transactions", tuple(params), access_token)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    for column in ["quantity", "price", "fees"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["transaction_date"] = pd.to_datetime(frame["transaction_date"])
    return frame


def load_fund_yields(price_schema: str, symbol: str, start_date: date) -> pd.DataFrame:
    rows = fetch_table(
        price_schema,
        "fund_yields",
        (
            ("select", "symbol,metric_date,twelve_month_trailing_yield,annualized_distribution_yield,gross_yield,source,fetched_at"),
            ("symbol", f"eq.{symbol}"),
            ("metric_date", f"gte.{start_date.isoformat()}"),
            ("order", "metric_date.asc"),
        ),
        supabase_auth_token(),
    )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    frame["metric_date"] = pd.to_datetime(frame["metric_date"])
    for column in [
        "twelve_month_trailing_yield",
        "annualized_distribution_yield",
        "gross_yield",
    ]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def load_fund_distributions(price_schema: str, symbol: str) -> pd.DataFrame:
    rows = fetch_table(
        price_schema,
        "fund_distributions",
        (
            ("select", "symbol,ex_dividend_date,record_date,payment_date,payment_amount,distribution_period,source,fetched_at"),
            ("symbol", f"eq.{symbol}"),
            ("order", "ex_dividend_date.desc"),
        ),
        supabase_auth_token(),
    )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    for column in ["ex_dividend_date", "record_date", "payment_date"]:
        frame[column] = pd.to_datetime(frame[column])
    frame["payment_amount"] = pd.to_numeric(frame["payment_amount"], errors="coerce")
    return frame


def holding_symbol_options(assets: pd.DataFrame) -> list[str]:
    symbols = [str(symbol) for symbol in assets["symbol"].dropna().tolist()]
    available_symbols = set(symbols)
    preferred_symbols = [
        symbol for symbol in PREFERRED_HOLDING_SYMBOLS if symbol in available_symbols
    ]
    remaining_symbols = sorted(
        symbol for symbol in symbols if symbol not in set(preferred_symbols)
    )
    return preferred_symbols + remaining_symbols


def transaction_symbol_options(transactions: pd.DataFrame) -> list[str]:
    if transactions.empty or "symbol" not in transactions:
        return []

    symbols = [str(symbol) for symbol in transactions["symbol"].dropna().tolist()]
    available_symbols = set(symbols)
    preferred_symbols = [
        symbol for symbol in PREFERRED_HOLDING_SYMBOLS if symbol in available_symbols
    ]
    remaining_symbols = sorted(
        symbol for symbol in available_symbols if symbol not in set(preferred_symbols)
    )
    return preferred_symbols + remaining_symbols


def weighted_average_cost(positions: pd.DataFrame) -> float | None:
    if positions.empty:
        return None
    total_quantity = positions["quantity"].sum()
    if not total_quantity:
        return None
    return float((positions["quantity"] * positions["average_cost"]).sum() / total_quantity)


def weighted_average_cost_from_transactions(
    transactions: pd.DataFrame,
) -> tuple[float | None, float | None]:
    if transactions.empty:
        return None, None

    buys = transactions[transactions["transaction_type"] == "buy"].copy()
    if buys.empty:
        return None, None

    buy_quantity = buys["quantity"].sum()
    if not buy_quantity:
        return None, None

    weighted_cost = ((buys["quantity"] * buys["price"]) + buys["fees"].fillna(0)).sum()
    sold_quantity = transactions.loc[
        transactions["transaction_type"] == "sell", "quantity"
    ].sum()
    return float(weighted_cost / buy_quantity), float(buy_quantity - sold_quantity)


def position_value_data(
    prices: pd.DataFrame,
    transactions: pd.DataFrame,
    target_cagr: float,
) -> pd.DataFrame:
    if prices.empty or transactions.empty:
        return pd.DataFrame()

    share_flows = transactions[
        transactions["transaction_type"].isin(["buy", "sell"])
        & transactions["transaction_date"].notna()
        & transactions["quantity"].notna()
    ].copy()
    contributions = transactions[
        (transactions["transaction_type"] == "buy")
        & transactions["transaction_date"].notna()
        & transactions["quantity"].notna()
        & transactions["price"].notna()
    ].copy()
    if share_flows.empty or contributions.empty:
        return pd.DataFrame()

    first_transaction_date = contributions["transaction_date"].min().normalize()
    value_prices = prices[prices["price_date"] >= first_transaction_date].copy()
    if value_prices.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for price_row in value_prices.itertuples():
        price_date = price_row.price_date.normalize()
        active_share_flows = share_flows[share_flows["transaction_date"] <= price_date]
        active_contributions = contributions[
            contributions["transaction_date"] <= price_date
        ]
        if active_share_flows.empty or active_contributions.empty:
            continue

        signed_quantities = active_share_flows["quantity"].where(
            active_share_flows["transaction_type"] == "buy",
            -active_share_flows["quantity"],
        )
        quantity = signed_quantities.sum()
        market_value = float(price_row.close) * float(quantity)

        cost_basis = 0.0
        target_value = 0.0
        for flow in active_contributions.itertuples():
            fees = 0 if pd.isna(flow.fees) else float(flow.fees)
            contribution = float(flow.quantity) * float(flow.price) + fees
            cost_basis += contribution
            elapsed_days = (price_date - flow.transaction_date.normalize()).days
            target_value += contribution * ((1 + target_cagr) ** (elapsed_days / 365))

        rows.append(
            {
                "Date": price_date,
                "Market Value": market_value,
                "Cost Basis": cost_basis,
                "Target Value": target_value,
                "Comfort Zone Low": target_value * (1 - COMFORT_ZONE_MULTIPLIER),
                "Comfort Zone High": target_value * (1 + COMFORT_ZONE_MULTIPLIER),
                "Target Growth": target_value - cost_basis,
                "Actual Growth": market_value - cost_basis,
                "Comfort Zone Low Growth": target_value
                * (1 - COMFORT_ZONE_MULTIPLIER)
                - cost_basis,
                "Comfort Zone High Growth": target_value
                * (1 + COMFORT_ZONE_MULTIPLIER)
                - cost_basis,
            }
        )

    return pd.DataFrame(rows)


def latest_ema_data(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame()

    close_prices = prices[["price_date", "close"]].dropna().sort_values("price_date")
    rows: list[dict[str, Any]] = []
    latest_date = close_prices["price_date"].max()
    for period in EMA_PERIODS:
        if len(close_prices) < period:
            continue
        ema_value = float(
            close_prices["close"].ewm(span=period, adjust=False).mean().iloc[-1]
        )
        rows.append(
            {
                "Date": latest_date,
                "Indicator": f"EMA{period}",
                "Value": ema_value,
                "Label": f"EMA{period} {ema_value:,.2f}",
            }
        )

    return pd.DataFrame(rows)


def is_dark_theme() -> bool:
    try:
        theme_type = st.context.theme.get("type")
    except Exception:
        theme_type = None
    return (theme_type or st.get_option("theme.base")) != "light"


def chart_palette() -> dict[str, str]:
    if is_dark_theme():
        return {
            "actual": "#60a5fa",
            "average_cost": "#f87171",
            "cost_basis": "#fbbf24",
            "target_growth": "#22c55e",
            "comfort_area": "#64748b",
            "comfort_label": "#cbd5e1",
            "ema8": "#a78bfa",
            "ema20": "#2dd4bf",
            "ema50": "#facc15",
            "ema100": "#fb923c",
            "ema200": "#e879f9",
        }
    return {
        "actual": "#2563eb",
        "average_cost": "#dc2626",
        "cost_basis": "#d97706",
        "target_growth": "#16a34a",
        "comfort_area": "#64748b",
        "comfort_label": "#111827",
        "ema8": "#7c3aed",
        "ema20": "#0f766e",
        "ema50": "#ca8a04",
        "ema100": "#ea580c",
        "ema200": "#c026d3",
    }


def chart_legend(items: list[tuple[str, str]]) -> None:
    text_color = "#f9fafb" if is_dark_theme() else "#111827"
    legend_items = "".join(
        f"""
        <div style="
            display: flex;
            align-items: center;
            gap: 0.4rem;
            min-height: 1.25rem;
            margin: 0;
            color: {text_color};
            font-size: 0.85rem;
            line-height: 1.2;
            white-space: nowrap;
        ">
            <div style="
                flex: 0 0 auto;
                width: 1.4rem;
                height: 0.2rem;
                border-radius: 999px;
                background: {escape(color)};
            "></div>
            <div style="line-height: 1.2;">{escape(label)}</div>
        </div>
        """
        for label, color in items
    )
    st.markdown(
        f"""
        <div style="
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: center;
            gap: 0.45rem 1rem;
            line-height: 1.2;
            margin: -0.35rem 0 0.75rem 0;
        ">{legend_items}</div>
        """,
        unsafe_allow_html=True,
    )


def render_position_total_value_chart(
    prices: pd.DataFrame,
    transactions: pd.DataFrame,
    target_cagr: float,
) -> None:
    position_data = position_value_data(prices, transactions, target_cagr)
    if position_data.empty:
        return

    palette = chart_palette()
    target_value_label = f"Target Value ({target_cagr:.1%} CAGR)"

    chart = alt.layer(
        alt.Chart(position_data)
        .mark_area(color=palette["comfort_area"], opacity=0.22)
        .encode(
            x=alt.X("Date:T", title="Date"),
            y=alt.Y(
                "Comfort Zone Low:Q",
                title="Value (CAD)",
                scale=alt.Scale(zero=False),
            ),
            y2="Comfort Zone High:Q",
            tooltip=[
                alt.Tooltip("Date:T", title="Date"),
                alt.Tooltip(
                    "Comfort Zone Low:Q",
                    title="Comfort Zone -10%",
                    format=",.2f",
                ),
                alt.Tooltip(
                    "Comfort Zone High:Q",
                    title="Comfort Zone +10%",
                    format=",.2f",
                ),
            ],
        ),
        alt.Chart(position_data)
        .mark_line(color=palette["target_growth"], strokeDash=[7, 5], strokeWidth=2.5)
        .encode(
            x=alt.X("Date:T", title="Date"),
            y=alt.Y(
                "Target Value:Q",
                title="Value (CAD)",
                scale=alt.Scale(zero=False),
            ),
            tooltip=[
                alt.Tooltip("Date:T", title="Date"),
                alt.Tooltip("Target Value:Q", title=target_value_label, format=",.2f"),
            ],
        ),
        alt.Chart(position_data)
        .mark_line(
            color=palette["cost_basis"],
            interpolate="step-after",
            strokeWidth=2,
        )
        .encode(
            x=alt.X("Date:T", title="Date"),
            y=alt.Y(
                "Cost Basis:Q",
                title="Value (CAD)",
                scale=alt.Scale(zero=False),
            ),
            tooltip=[
                alt.Tooltip("Date:T", title="Date"),
                alt.Tooltip("Cost Basis:Q", title="Principal Value", format=",.2f"),
            ],
        ),
        alt.Chart(position_data)
        .mark_line(color=palette["actual"], strokeWidth=2.5)
        .encode(
            x=alt.X("Date:T", title="Date"),
            y=alt.Y(
                "Market Value:Q",
                title="Value (CAD)",
                scale=alt.Scale(zero=False),
            ),
            tooltip=[
                alt.Tooltip("Date:T", title="Date"),
                alt.Tooltip("Market Value:Q", title="Market Value", format=",.2f"),
            ],
        ),
    ).resolve_scale(y="shared").properties(height=420)

    st.subheader("My VFV Position Value")
    st.altair_chart(chart, width="stretch")
    chart_legend(
        [
            ("Market Value", palette["actual"]),
            (target_value_label, palette["target_growth"]),
            ("Principal Value", palette["cost_basis"]),
            ("Comfort Zone (+/-10%)", palette["comfort_label"]),
        ]
    )


def render_position_value_chart(
    prices: pd.DataFrame,
    transactions: pd.DataFrame,
    target_cagr: float,
) -> None:
    position_data = position_value_data(prices, transactions, target_cagr)
    if position_data.empty:
        return

    palette = chart_palette()
    target_growth_label = f"Target Growth ({target_cagr:.1%} CAGR)"
    chart = alt.layer(
        alt.Chart(position_data)
        .mark_area(color=palette["comfort_area"], opacity=0.22)
        .encode(
            x=alt.X("Date:T", title="Date"),
            y=alt.Y(
                "Comfort Zone Low Growth:Q",
                title="Growth (CAD)",
                scale=alt.Scale(zero=False),
            ),
            y2="Comfort Zone High Growth:Q",
            tooltip=[
                alt.Tooltip("Date:T", title="Date"),
                alt.Tooltip(
                    "Comfort Zone Low Growth:Q",
                    title="Comfort Zone -10%",
                    format=",.2f",
                ),
                alt.Tooltip(
                    "Comfort Zone High Growth:Q",
                    title="Comfort Zone +10%",
                    format=",.2f",
                ),
            ],
        ),
        alt.Chart(position_data)
        .mark_line(color=palette["target_growth"], strokeDash=[7, 5], strokeWidth=2.5)
        .encode(
            x=alt.X("Date:T", title="Date"),
            y=alt.Y("Target Growth:Q", title="Growth (CAD)", scale=alt.Scale(zero=False)),
            tooltip=[
                alt.Tooltip("Date:T", title="Date"),
                alt.Tooltip("Target Growth:Q", title=target_growth_label, format=",.2f"),
            ],
        ),
        alt.Chart(position_data)
        .mark_line(color=palette["actual"], strokeWidth=2.5)
        .encode(
            x=alt.X("Date:T", title="Date"),
            y=alt.Y("Actual Growth:Q", title="Growth (CAD)", scale=alt.Scale(zero=False)),
            tooltip=[
                alt.Tooltip("Date:T", title="Date"),
                alt.Tooltip("Actual Growth:Q", title="Actual Growth", format=",.2f"),
            ],
        ),
    ).resolve_scale(y="shared").properties(height=420)

    st.subheader("My VFV Growth")
    st.altair_chart(chart, width="stretch")
    chart_legend(
        [
            ("Actual Growth", palette["actual"]),
            (target_growth_label, palette["target_growth"]),
            ("Comfort Zone (+/-10%)", palette["comfort_label"]),
        ]
    )


def render_price_vs_cost_chart(
    prices: pd.DataFrame,
    average_cost: float | None,
    transactions: pd.DataFrame,
    ema_prices: pd.DataFrame | None = None,
) -> None:
    palette = chart_palette()
    chart_data = prices[["price_date", "close"]].rename(
        columns={"price_date": "Date", "close": "Price"}
    )
    layers = []
    layers.append(
        alt.Chart(chart_data)
        .mark_line(color=palette["actual"], strokeWidth=2.5)
        .encode(
            x=alt.X("Date:T", title="Date"),
            y=alt.Y("Price:Q", title="Price (CAD)", scale=alt.Scale(zero=False)),
            tooltip=[
                alt.Tooltip("Date:T", title="Date"),
                alt.Tooltip("Price:Q", title="Market Price", format=",.2f"),
            ],
        )
    )

    ema_data = latest_ema_data(ema_prices if ema_prices is not None else prices)
    ema_color = alt.Color(
        "Indicator:N",
        scale=alt.Scale(
            domain=[f"EMA{period}" for period in EMA_PERIODS],
            range=[palette[f"ema{period}"] for period in EMA_PERIODS],
        ),
        legend=None,
    )
    if not ema_data.empty:
        layers.append(
            alt.Chart(ema_data)
            .mark_rule(strokeWidth=1.8, strokeDash=[5, 4])
            .encode(
                y=alt.Y("Value:Q", scale=alt.Scale(zero=False)),
                color=ema_color,
                tooltip=[
                    alt.Tooltip("Indicator:N", title="Indicator"),
                    alt.Tooltip("Value:Q", title="Latest EMA", format=",.2f"),
                    alt.Tooltip("Date:T", title="As of"),
                ],
            )
        )
        layers.append(
            alt.Chart(ema_data)
            .mark_text(
                align="right",
                baseline="bottom",
                dx=-6,
                dy=-5,
                fontSize=11,
                fontWeight="bold",
            )
            .encode(
                x=alt.X("Date:T", title="Date"),
                y=alt.Y("Value:Q", scale=alt.Scale(zero=False)),
                text="Label:N",
                color=ema_color,
            )
        )

    if average_cost is not None:
        layers.append(
            alt.Chart(pd.DataFrame({"Average Cost Basis": [average_cost]}))
            .mark_rule(color=palette["average_cost"], strokeWidth=2)
            .encode(
                y=alt.Y("Average Cost Basis:Q", scale=alt.Scale(zero=False)),
                tooltip=[
                    alt.Tooltip(
                        "Average Cost Basis:Q",
                        title="Average Cost Basis",
                        format=",.2f",
                    )
                ],
            )
        )
        cost_label = pd.DataFrame(
            {
                "Date": [chart_data["Date"].max()],
                "Average Cost Basis": [average_cost],
                "Label": [f"{average_cost:,.2f}"],
            }
        )
        layers.append(
            alt.Chart(cost_label)
            .mark_text(
                align="right",
                baseline="bottom",
                dx=-6,
                dy=-4,
                fontSize=12,
                fontWeight="bold",
                color=palette["average_cost"],
            )
            .encode(
                x=alt.X("Date:T", title="Date"),
                y=alt.Y("Average Cost Basis:Q", scale=alt.Scale(zero=False)),
                text="Label:N",
            )
        )

    buys = transactions[
        (transactions["transaction_type"] == "buy")
        & transactions["transaction_date"].notna()
        & transactions["price"].notna()
    ].copy()
    if not buys.empty:
        buys = buys.rename(
            columns={
                "transaction_date": "Date",
                "price": "Purchase price",
                "quantity": "Quantity",
            }
        )
        buys["Price Label"] = buys["Purchase price"].map(lambda value: f"{value:,.2f}")
        layers.append(
            alt.Chart(buys)
            .mark_circle(size=95, color="#f97316", opacity=0.9)
            .encode(
                x=alt.X("Date:T", title=None),
                y=alt.Y("Purchase price:Q", scale=alt.Scale(zero=False)),
                tooltip=[
                    alt.Tooltip("Date:T", title="Purchase date"),
                    alt.Tooltip("Purchase price:Q", title="Purchase price", format=",.2f"),
                    alt.Tooltip("Quantity:Q", title="Quantity", format=",.4f"),
                    alt.Tooltip("currency:N", title="Currency"),
                    alt.Tooltip("notes:N", title="Notes"),
                ],
            )
        )
        layers.append(
            alt.Chart(buys)
            .mark_text(
                align="center",
                baseline="bottom",
                dy=-10,
                fontSize=11,
                fontWeight="bold",
                color="#f97316",
            )
            .encode(
                x=alt.X("Date:T", title=None),
                y=alt.Y("Purchase price:Q", scale=alt.Scale(zero=False)),
                text="Price Label:N",
            )
        )

    st.subheader("VFV Price vs My Average Cost Basis")
    st.altair_chart(
        alt.layer(*layers).resolve_scale(y="shared").properties(height=420),
        width="stretch",
    )
    legend_items = [("Market Price", palette["actual"])]
    ema_indicators = set(ema_data["Indicator"]) if not ema_data.empty else set()
    for period in EMA_PERIODS:
        if f"EMA{period}" in ema_indicators:
            legend_items.append((f"EMA{period}", palette[f"ema{period}"]))
    if average_cost is not None:
        legend_items.append(("Average Cost Basis", palette["average_cost"]))
    if not transactions.empty:
        legend_items.append(("Purchases", "#f97316"))
    chart_legend(legend_items)


def format_optional_int(value: Any) -> str:
    if value is None or pd.isna(value):
        return "Not available"
    return f"{float(value):,.0f}"


def format_optional_number(value: Any, decimals: int = 2) -> str:
    if value is None or pd.isna(value):
        return "Not available"
    return f"{float(value):,.{decimals}f}"


def format_optional_date(value: Any) -> str:
    if value is None or pd.isna(value):
        return "date not recorded"
    return pd.to_datetime(value).date().isoformat()


def has_optional_date(value: Any) -> bool:
    return value is not None and not pd.isna(value)


def render_metric_with_update_date(
    container: Any,
    label: str,
    raw_value: Any,
    updated_on: Any,
) -> None:
    if raw_value is None or pd.isna(raw_value):
        container.metric(label, "N/A")
        return

    value = format_optional_number(raw_value)
    if has_optional_date(updated_on):
        container.metric(label, value, format_optional_date(updated_on))
        return

    container.metric(label, value)


def render_market_price_chart(symbol: str, prices: pd.DataFrame) -> None:
    if prices.empty:
        st.info(f"No price history found for {symbol}.")
        return

    palette = chart_palette()
    chart_data = prices[["price_date", "close"]].rename(
        columns={"price_date": "Date", "close": "Price"}
    )
    layers = [
        alt.Chart(chart_data)
        .mark_line(color=palette["actual"], strokeWidth=2.5)
        .encode(
            x=alt.X("Date:T", title="Date"),
            y=alt.Y("Price:Q", title="Price (CAD)", scale=alt.Scale(zero=False)),
            tooltip=[
                alt.Tooltip("Date:T", title="Date"),
                alt.Tooltip("Price:Q", title="Market Price", format=",.2f"),
            ],
        )
    ]

    ema_data = latest_ema_data(prices)
    ema_color = alt.Color(
        "Indicator:N",
        scale=alt.Scale(
            domain=[f"EMA{period}" for period in EMA_PERIODS],
            range=[palette[f"ema{period}"] for period in EMA_PERIODS],
        ),
        legend=None,
    )
    if not ema_data.empty:
        layers.append(
            alt.Chart(ema_data)
            .mark_rule(strokeWidth=1.8, strokeDash=[5, 4])
            .encode(
                y=alt.Y("Value:Q", scale=alt.Scale(zero=False)),
                color=ema_color,
                tooltip=[
                    alt.Tooltip("Indicator:N", title="Indicator"),
                    alt.Tooltip("Value:Q", title="Latest EMA", format=",.2f"),
                    alt.Tooltip("Date:T", title="As of"),
                ],
            )
        )
        layers.append(
            alt.Chart(ema_data)
            .mark_text(
                align="right",
                baseline="bottom",
                dx=-6,
                dy=-5,
                fontSize=11,
                fontWeight="bold",
            )
            .encode(
                x=alt.X("Date:T", title="Date"),
                y=alt.Y("Value:Q", scale=alt.Scale(zero=False)),
                text="Label:N",
                color=ema_color,
            )
        )

    st.subheader(f"{symbol} Price")
    st.altair_chart(
        alt.layer(*layers).resolve_scale(y="shared").properties(height=420),
        width="stretch",
    )
    legend_items = [("Market Price", palette["actual"])]
    ema_indicators = set(ema_data["Indicator"]) if not ema_data.empty else set()
    for period in EMA_PERIODS:
        if f"EMA{period}" in ema_indicators:
            legend_items.append((f"EMA{period}", palette[f"ema{period}"]))
    chart_legend(legend_items)


def comparison_price_data(
    price_schema: str,
    symbols: list[str],
    start_date: date,
    mode: str,
    rolling_window: int,
) -> pd.DataFrame:
    frames = []
    for symbol in symbols:
        prices = load_prices(price_schema, symbol, start_date)
        if prices.empty:
            continue
        prices = prices[["price_date", "close"]].dropna().sort_values("price_date")
        if prices.empty:
            continue

        prices = prices.rename(columns={"price_date": "Date", "close": "Close"})
        prices["Symbol"] = symbol
        if mode == "Normalized":
            base_price = float(prices.iloc[0]["Close"])
            if not base_price:
                continue
            prices["Value"] = prices["Close"] / base_price * 100
        elif mode == "Price":
            prices["Value"] = prices["Close"]
        elif mode == "Drawdown":
            prices["Value"] = (prices["Close"] / prices["Close"].cummax() - 1) * 100
        elif mode == "Rolling Return":
            prices["Value"] = prices["Close"].pct_change(periods=rolling_window) * 100
        elif mode == "Rolling Volatility":
            prices["Value"] = (
                prices["Close"].pct_change().rolling(rolling_window).std()
                * (252**0.5)
                * 100
            )
        prices = prices.dropna(subset=["Value"])
        if prices.empty:
            continue
        frames.append(prices)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def comparison_volume_data(
    price_schema: str,
    symbols: list[str],
    start_date: date,
    mode: str,
) -> pd.DataFrame:
    frames = []
    for symbol in symbols:
        prices = load_prices(price_schema, symbol, start_date)
        if prices.empty or "volume" not in prices:
            continue
        prices = prices[["price_date", "volume"]].dropna().sort_values("price_date")
        if prices.empty:
            continue

        prices = prices.rename(columns={"price_date": "Date", "volume": "Volume"})
        prices["Symbol"] = symbol
        prices["Value"] = (
            prices["Volume"].rolling(20, min_periods=1).mean()
            if mode == "Average Volume"
            else prices["Volume"]
        )
        frames.append(prices)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def latest_comparison_metrics(
    tracked: pd.DataFrame,
    quote_snapshots: pd.DataFrame,
    symbols: list[str],
    mode: str,
) -> pd.DataFrame:
    rows = []
    for symbol in symbols:
        metadata_match = tracked[tracked["symbol"] == symbol]
        quote_match = quote_snapshots[quote_snapshots["symbol"] == symbol]
        metadata = metadata_match.iloc[0] if not metadata_match.empty else None
        quote_row = quote_match.iloc[0] if not quote_match.empty else None

        if mode == "PE":
            manual_value = metadata.get("manual_pe_ratio") if metadata is not None else None
            fallback_value = quote_row["pe_ratio"] if quote_row is not None else None
        elif mode == "Beta":
            manual_value = metadata.get("manual_beta") if metadata is not None else None
            fallback_value = quote_row["beta"] if quote_row is not None else None
        else:
            manual_value = None
            fallback_value = quote_row["average_volume"] if quote_row is not None else None

        value = manual_value if manual_value is not None and not pd.isna(manual_value) else fallback_value
        if value is None or pd.isna(value):
            continue
        rows.append({"Symbol": symbol, "Value": float(value)})

    return pd.DataFrame(rows)


def comparison_axis_title(mode: str, rolling_window: int) -> str:
    if mode == "Normalized":
        return "Indexed Growth (Start = 100)"
    if mode == "Price":
        return "Price (CAD)"
    if mode == "Volume":
        return "Volume (units)"
    if mode == "Average Volume":
        return "20-Day Average Volume (units)"
    if mode == "PE":
        return "PE"
    if mode == "Beta":
        return "Beta"
    if mode == "Drawdown":
        return "Drawdown (%)"
    if mode == "Rolling Return":
        return f"{rolling_window}-Day Rolling Return (%)"
    return f"{rolling_window}-Day Annualized Volatility (%)"


def render_research_comparison_page(price_schema: str) -> None:
    try:
        tracked = load_tracked_market_symbols(price_schema)
        quote_snapshots = load_latest_quote_snapshots(price_schema)
    except RuntimeError as error:
        st.error(str(error))
        return

    if tracked.empty:
        st.warning("No tracked market symbols found.")
        return

    tracked = tracked.sort_values("symbol")
    symbols = tracked["symbol"].dropna().astype(str).tolist()
    default_symbols = [
        symbol
        for symbol in ["QQC.TO", "XEQT.TO", "VFV.TO"]
        if symbol in set(symbols)
    ]

    controls_col1, controls_col2, controls_col3 = st.columns([2, 1, 1])
    with controls_col1:
        selected_symbols = st.multiselect(
            "Compare",
            symbols,
            default=default_symbols,
        )
    with controls_col2:
        history_window_label = st.selectbox(
            "History window",
            list(HISTORY_WINDOW_OPTIONS.keys()),
            index=list(HISTORY_WINDOW_OPTIONS.keys()).index("1 Year"),
            key="research_comparison_history",
        )
    with controls_col3:
        mode = st.selectbox(
            "Mode",
            [
                "Normalized",
                "Price",
                "Volume",
                "Average Volume",
                "PE",
                "Beta",
                "Drawdown",
                "Rolling Return",
                "Rolling Volatility",
            ],
            key="research_comparison_mode",
        )

    if len(selected_symbols) < 2:
        st.info("Select at least two symbols to compare.")
        return

    rolling_window = 20
    if mode in {"Rolling Return", "Rolling Volatility"}:
        rolling_window = st.number_input(
            "Rolling window",
            min_value=5,
            max_value=252,
            value=20,
            step=5,
            key="research_comparison_rolling_window",
        )

    lookback_days = HISTORY_WINDOW_OPTIONS[history_window_label]
    start_date = (
        date(1900, 1, 1)
        if lookback_days is None
        else date.today() - timedelta(days=lookback_days)
    )

    try:
        if mode in {"Volume", "Average Volume"}:
            chart_data = comparison_volume_data(
                price_schema,
                selected_symbols,
                start_date,
                mode,
            )
        elif mode in {"PE", "Beta"}:
            chart_data = latest_comparison_metrics(
                tracked,
                quote_snapshots,
                selected_symbols,
                mode,
            )
        else:
            chart_data = comparison_price_data(
                price_schema,
                selected_symbols,
                start_date,
                mode,
                int(rolling_window),
            )
    except RuntimeError as error:
        st.error(str(error))
        return

    if chart_data.empty:
        st.info("No comparable price history found for the selected symbols.")
        return

    y_title = comparison_axis_title(mode, int(rolling_window))
    st.subheader(f"{mode} Comparison")
    if mode in {"PE", "Beta"}:
        chart = (
            alt.Chart(chart_data)
            .mark_bar(size=38)
            .encode(
                x=alt.X("Symbol:N", title=None, sort="-y"),
                y=alt.Y("Value:Q", title=y_title),
                color=alt.Color("Symbol:N", title=None, legend=None),
                tooltip=[
                    alt.Tooltip("Symbol:N", title="Symbol"),
                    alt.Tooltip("Value:Q", title=y_title, format=",.2f"),
                ],
            )
            .properties(height=420)
        )
    else:
        tooltip = [
            alt.Tooltip("Date:T", title="Date"),
            alt.Tooltip("Symbol:N", title="Symbol"),
            alt.Tooltip("Value:Q", title=y_title, format=",.2f"),
        ]
        if "Close" in chart_data:
            tooltip.insert(2, alt.Tooltip("Close:Q", title="Close", format=",.2f"))
        if "Volume" in chart_data:
            tooltip.insert(2, alt.Tooltip("Volume:Q", title="Volume", format=",.0f"))
        chart = (
            alt.Chart(chart_data)
            .mark_line(strokeWidth=2.4)
            .encode(
                x=alt.X("Date:T", title="Date"),
                y=alt.Y(
                    "Value:Q",
                    title=y_title,
                    scale=alt.Scale(zero=False),
                ),
                color=alt.Color("Symbol:N", title=None),
                tooltip=tooltip,
            )
            .properties(height=460)
        )
    st.altair_chart(chart, width="stretch")
    if mode == "Normalized":
        st.caption(
            "Each selected symbol starts at 100 on its first available close in the "
            "selected window, so the lines show relative growth rather than raw price."
        )
    elif mode in {"Volume", "Average Volume"}:
        st.caption("Volume is reported in traded units, not CAD market value.")
    elif mode == "Rolling Volatility":
        st.caption("Rolling volatility is annualized from daily close-to-close returns.")


def transaction_cash_amount(row: Any) -> float:
    quantity = 0 if pd.isna(row.quantity) else float(row.quantity or 0)
    price = 0 if pd.isna(row.price) else float(row.price or 0)
    if quantity and price:
        return quantity * price
    if price:
        return price
    return quantity


def cash_position_summary(
    transactions: pd.DataFrame,
    prices: pd.DataFrame,
) -> dict[str, float | None]:
    if transactions.empty:
        return {
            "principal": None,
            "quantity": None,
            "latest_close": None,
            "market_value": None,
            "dividends": None,
            "total_value": None,
            "gain_rate": None,
        }

    principal = 0.0
    quantity = 0.0
    dividends = 0.0
    for row in transactions.itertuples():
        amount = transaction_cash_amount(row)
        fees = 0 if pd.isna(row.fees) else float(row.fees or 0)
        row_quantity = 0 if pd.isna(row.quantity) else float(row.quantity or 0)
        if row.transaction_type == "buy":
            principal += amount + fees
            quantity += row_quantity
        elif row.transaction_type == "sell":
            principal -= amount - fees
            quantity -= row_quantity
        elif row.transaction_type == "dividend":
            dividends += amount

    latest_close = None
    market_value = None
    if not prices.empty and quantity:
        latest_close = float(prices.iloc[-1]["close"])
        market_value = latest_close * quantity

    total_value = market_value + dividends if market_value is not None else None
    total_gain = total_value - principal if total_value is not None else None
    gain_rate = total_gain / principal if total_gain is not None and principal else None
    return {
        "principal": principal,
        "quantity": quantity,
        "latest_close": latest_close,
        "market_value": market_value,
        "dividends": dividends,
        "total_value": total_value,
        "gain_rate": gain_rate,
    }


def last_business_day_next_month(value: date) -> date:
    year = value.year + (1 if value.month == 12 else 0)
    month = 1 if value.month == 12 else value.month + 1
    next_month = 1 if month == 12 else month + 1
    next_year = year + (1 if month == 12 else 0)
    current = date(next_year, next_month, 1) - timedelta(days=1)
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def expected_distribution_dates(distributions: pd.DataFrame) -> tuple[str, str]:
    if distributions.empty:
        return "Not available", "Not available"

    today = pd.Timestamp(pd.Timestamp.now(tz=VANCOUVER_TZ).date())
    future_ex = distributions[distributions["ex_dividend_date"] >= today]
    future_payment = distributions[distributions["payment_date"] >= today]

    if not future_ex.empty:
        ex_date = future_ex.sort_values("ex_dividend_date").iloc[0]["ex_dividend_date"]
        ex_label = ex_date.date().isoformat()
    else:
        latest_ex = distributions["ex_dividend_date"].max().date()
        ex_label = last_business_day_next_month(latest_ex).isoformat()

    if not future_payment.empty:
        payment_date = future_payment.sort_values("payment_date").iloc[0]["payment_date"]
        payment_label = payment_date.date().isoformat()
    else:
        latest_payment = distributions["payment_date"].max().date()
        payment_label = (
            last_business_day_next_month(latest_payment) + timedelta(days=7)
        ).isoformat()

    return ex_label, payment_label


def latest_metric_row(frame: pd.DataFrame) -> pd.Series | None:
    if frame.empty:
        return None
    preferred = frame[frame["source"] == "globalx_product_page"]
    if not preferred.empty:
        return preferred.sort_values("metric_date").iloc[-1]
    return frame.sort_values("metric_date").iloc[-1]


def metric_percent_label(row: pd.Series | None, column: str) -> str:
    if row is None or pd.isna(row[column]):
        return "Not set"
    return f"{row[column]:.2%}"


def metric_date_label(row: pd.Series | None) -> str:
    if row is None:
        return "Not set"
    return row["metric_date"].date().isoformat()


def highlighted_metric(label: str, value: str, detail: str | None = None) -> None:
    detail_markup = (
        f"""
            <span style="
                color: #92400e;
                font-size: 0.95rem;
                font-weight: 700;
                margin-left: 0.5rem;
                white-space: nowrap;
            ">({escape(detail)})</span>
        """
        if detail
        else ""
    )
    st.markdown(
        f"""
        <div style="
            display: inline-block;
            width: auto;
            max-width: 100%;
            border: 1px solid #f59e0b;
            border-left: 6px solid #f59e0b;
            background: #fffbeb;
            border-radius: 8px;
            padding: 0.75rem 1rem;
            min-height: 5.25rem;
            margin-bottom: 0.75rem;
        ">
            <div style="
                color: #92400e;
                font-size: 0.875rem;
                font-weight: 700;
                margin-bottom: 0.35rem;
            ">{escape(label)}</div>
            <div style="
                color: #7c2d12;
                font-size: 2rem;
                font-weight: 800;
                line-height: 1.1;
                overflow-wrap: anywhere;
            ">{escape(value)}{detail_markup}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def yield_chart_data(yields: pd.DataFrame) -> pd.DataFrame:
    if yields.empty:
        return yields

    source_rank = {"derived_distribution_ttm": 0, "globalx_product_page": 1}
    chart_data = yields.copy()
    chart_data["source_rank"] = chart_data["source"].map(source_rank).fillna(0)
    chart_data = chart_data.sort_values(["metric_date", "source_rank"])
    chart_data = chart_data.drop_duplicates("metric_date", keep="last")
    chart_data["12-Month Trailing Yield"] = (
        chart_data["twelve_month_trailing_yield"] * 100
    )
    return chart_data


def render_cash_yield_chart(yields: pd.DataFrame) -> None:
    chart_data = yield_chart_data(yields)
    if chart_data.empty:
        st.info("No CASH.TO yield history found yet.")
        return

    palette = chart_palette()
    chart = alt.layer(
        alt.Chart(chart_data)
        .mark_line(color=palette["actual"], strokeWidth=2.5, interpolate="step-after")
        .encode(
            x=alt.X("metric_date:T", title="Date"),
            y=alt.Y(
                "12-Month Trailing Yield:Q",
                title="Yield (%)",
                scale=alt.Scale(zero=False),
            ),
            tooltip=[
                alt.Tooltip("metric_date:T", title="Date"),
                alt.Tooltip(
                    "12-Month Trailing Yield:Q",
                    title="Derived 12-Month Distribution Yield",
                    format=".2f",
                ),
                alt.Tooltip("source:N", title="Source"),
            ],
        ),
    ).resolve_scale(y="shared").properties(height=380)

    st.subheader("CASH.TO Derived 12-Month Distribution Yield")
    st.altair_chart(chart, width="stretch")
    chart_legend([("Derived 12-Month Distribution Yield", palette["actual"])])


def cash_dividend_data(transactions: pd.DataFrame) -> pd.DataFrame:
    if transactions.empty:
        return pd.DataFrame()

    dividends = transactions[transactions["transaction_type"] == "dividend"].copy()
    if dividends.empty:
        return pd.DataFrame()

    dividends["Amount"] = [
        transaction_cash_amount(row) for row in dividends.itertuples()
    ]
    dividends = dividends[dividends["Amount"] > 0]
    if dividends.empty:
        return pd.DataFrame()

    dividends["Payment Month"] = dividends["transaction_date"].dt.to_period("M").dt.to_timestamp()
    return (
        dividends.groupby("Payment Month", as_index=False)["Amount"]
        .sum()
        .sort_values("Payment Month")
    )


def render_cash_dividend_chart(transactions: pd.DataFrame) -> None:
    chart_data = cash_dividend_data(transactions)
    if chart_data.empty:
        return

    st.subheader("CASH.TO Distributions Received")
    chart = (
        alt.Chart(chart_data)
        .mark_bar(color=chart_palette()["target_growth"], opacity=0.82)
        .encode(
            x=alt.X("Payment Month:T", title="Payment month"),
            y=alt.Y("Amount:Q", title="Distribution received (CAD)"),
            tooltip=[
                alt.Tooltip("Payment Month:T", title="Payment month"),
                alt.Tooltip("Amount:Q", title="Distribution received", format=",.2f"),
            ],
        )
        .properties(height=320)
    )
    st.altair_chart(chart, width="stretch")


def render_cash_page(
    price_schema: str,
    portfolio_schema: str,
    lookback_days: int | None,
    show_rows: bool,
) -> None:
    start_date = (
        date(2026, 5, 22)
        if lookback_days is None
        else date.today() - timedelta(days=lookback_days)
    )

    try:
        transactions = load_transactions(portfolio_schema, "CASH.TO")
    except RuntimeError:
        transactions = pd.DataFrame()

    try:
        prices = load_prices(price_schema, "CASH.TO", start_date)
        yields = load_fund_yields(price_schema, "CASH.TO", start_date)
        distributions = load_fund_distributions(price_schema, "CASH.TO")
    except RuntimeError as error:
        st.error(str(error))
        st.stop()

    summary = cash_position_summary(transactions, prices)
    latest_yield = latest_metric_row(yields)
    expected_ex_date, expected_payment_date = expected_distribution_dates(distributions)

    st.subheader("CASH.TO - Global X High Interest Savings ETF")
    highlighted_metric(
        "Annualized distribution yield",
        metric_percent_label(latest_yield, "annualized_distribution_yield"),
        f"Updated {metric_date_label(latest_yield)}",
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "Principal value",
        f"{summary['principal']:,.2f}" if summary["principal"] is not None else "Not set",
    )
    col2.metric(
        "Distributions received",
        f"{summary['dividends']:,.2f}" if summary["dividends"] is not None else "Not set",
    )
    col3.metric(
        "Total value + dividends",
        f"{summary['total_value']:,.2f}" if summary["total_value"] is not None else "Not set",
        (
            f"Market value {summary['market_value']:,.2f}"
            if summary["market_value"] is not None
            else None
        ),
    )
    col4.metric(
        "Total return",
        f"{summary['gain_rate']:.2%}" if summary["gain_rate"] is not None else "Not set",
    )

    col5, col6, col7, col8 = st.columns(4)
    col5.metric(
        "Gross yield",
        metric_percent_label(latest_yield, "gross_yield"),
    )
    col6.metric(
        "12-month trailing yield",
        metric_percent_label(latest_yield, "twelve_month_trailing_yield"),
    )
    col7.metric("Expected ex-dividend date", expected_ex_date)
    col8.metric("Expected payment date", expected_payment_date)

    st.caption(
        "Annualized distribution yield and gross yield are current official "
        "Global X metrics. The historical chart uses 12-month trailing yield, "
        "with older rows derived from distributions and market closes."
    )

    render_cash_yield_chart(yields)
    render_cash_dividend_chart(transactions)

    if transactions.empty:
        st.info("No transaction history found for CASH.TO.")
    else:
        st.subheader("Transaction History")
        st.dataframe(transactions, width="stretch", hide_index=True)

    if show_rows:
        st.subheader("Yield Rows")
        st.dataframe(yields, width="stretch", hide_index=True)
        st.subheader("Distribution Rows")
        st.dataframe(distributions, width="stretch", hide_index=True)


def render_asset_page(
    price_schema: str,
    portfolio_schema: str,
    assets: pd.DataFrame,
    lookback_days: int | None,
    target_cagr: float,
    show_rows: bool,
    symbol: str,
) -> None:
    matching_assets = assets[assets["symbol"] == symbol]
    if matching_assets.empty:
        st.warning(f"{symbol} is not registered in Supabase assets.")
        st.stop()

    selected_asset = matching_assets.iloc[0].to_dict()
    display_start_date = (
        date(1900, 1, 1)
        if lookback_days is None
        else date.today() - timedelta(days=lookback_days)
    )
    start_date = min(display_start_date, date.today() - timedelta(days=EMA_HISTORY_DAYS))

    try:
        prices = load_prices(price_schema, symbol, start_date)
        transactions = load_transactions(portfolio_schema, symbol)
    except RuntimeError as error:
        st.error(str(error))
        st.stop()

    try:
        positions = load_positions(portfolio_schema, symbol)
    except RuntimeError:
        positions = pd.DataFrame()

    if prices.empty:
        st.warning(f"No price rows found for {symbol}.")
        st.stop()

    display_prices = (
        prices
        if lookback_days is None
        else prices[prices["price_date"] >= pd.Timestamp(display_start_date)]
    )
    if display_prices.empty:
        display_prices = prices

    average_cost, total_quantity = weighted_average_cost_from_transactions(transactions)
    if average_cost is None:
        average_cost = weighted_average_cost(positions)
        total_quantity = float(positions["quantity"].sum()) if not positions.empty else None

    latest = prices.iloc[-1]
    latest_close = float(latest["close"])
    latest_date = latest["price_date"].date().isoformat()
    gain_per_unit = latest_close - average_cost if average_cost is not None else None
    gain_pct = gain_per_unit / average_cost if average_cost else None
    principal_value = (
        average_cost * total_quantity
        if average_cost is not None and total_quantity is not None
        else None
    )
    market_value = latest_close * total_quantity if total_quantity is not None else None
    total_gain = (
        gain_per_unit * total_quantity
        if gain_per_unit is not None and total_quantity is not None
        else None
    )
    total_return_pct = total_gain / principal_value if total_gain is not None and principal_value else None

    st.subheader(f"{symbol} - {selected_asset.get('name', symbol)}")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Latest close", f"{latest_close:,.2f}", latest_date)
    col2.metric(
        "Weighted average cost",
        f"{average_cost:,.2f}" if average_cost is not None else "Not set",
    )
    col3.metric(
        "Gain per unit",
        f"{gain_per_unit:,.2f}" if gain_per_unit is not None else "Not set",
        f"{gain_pct:.2%}" if gain_pct is not None else None,
    )
    col4.metric(
        "Quantity",
        f"{total_quantity:,.4f}" if total_quantity is not None else "Not set",
    )

    col5, col6, col7 = st.columns(3)
    col5.metric(
        "Principal value",
        f"{principal_value:,.2f}" if principal_value is not None else "Not set",
    )
    col6.metric(
        "Market value",
        f"{market_value:,.2f}" if market_value is not None else "Not set",
    )
    col7.metric(
        "Total gain",
        f"{total_gain:,.2f}" if total_gain is not None else "Not set",
        f"{total_return_pct:.2%}" if total_return_pct is not None else None,
    )

    render_price_vs_cost_chart(display_prices, average_cost, transactions, prices)
    render_position_value_chart(display_prices, transactions, target_cagr)
    render_position_total_value_chart(display_prices, transactions, target_cagr)

    if not transactions.empty:
        st.subheader("Transaction History")
        st.dataframe(transactions, width="stretch", hide_index=True)
    elif not positions.empty:
        st.subheader("Legacy Position Inputs")
        st.dataframe(positions, width="stretch", hide_index=True)
    else:
        st.info("No purchase history found.")

    if show_rows:
        st.subheader("Price Rows")
        st.dataframe(display_prices, width="stretch", hide_index=True)


def render_market_research_page(price_schema: str) -> None:
    try:
        tracked = load_tracked_market_symbols(price_schema)
        quote_snapshots = load_latest_quote_snapshots(price_schema)
    except RuntimeError as error:
        st.error(str(error))
        return

    if tracked.empty:
        st.warning("No tracked market symbols found.")
        return

    tracked = tracked.sort_values("symbol")
    symbols = tracked["symbol"].dropna().astype(str).tolist()
    symbol = st.selectbox("Symbol", symbols)
    metadata = tracked[tracked["symbol"] == symbol].iloc[0]

    controls_col, _ = st.columns([1, 2])
    with controls_col:
        history_window_label = st.selectbox(
            "History window",
            list(HISTORY_WINDOW_OPTIONS.keys()),
            index=list(HISTORY_WINDOW_OPTIONS.keys()).index("180 Days"),
            key="watchlist_history_window",
        )

    lookback_days = HISTORY_WINDOW_OPTIONS[history_window_label]
    display_start_date = (
        date(1900, 1, 1)
        if lookback_days is None
        else date.today() - timedelta(days=lookback_days)
    )
    start_date = min(display_start_date, date.today() - timedelta(days=EMA_HISTORY_DAYS))
    try:
        prices = load_prices(price_schema, symbol, start_date)
    except RuntimeError as error:
        st.error(str(error))
        return

    st.subheader(f"{symbol} - {metadata.get('name', symbol)}")
    if prices.empty:
        st.info(
            f"No price rows found for {symbol}. Run backfill_recent_prices.py for this symbol."
        )
        return

    display_prices = prices[prices["price_date"].dt.date >= display_start_date].copy()
    if display_prices.empty:
        st.info(f"No price rows found for {symbol} in the selected window.")
        return

    latest = prices.iloc[-1]
    quote_snapshot = quote_snapshots[quote_snapshots["symbol"] == symbol]
    quote_row = quote_snapshot.iloc[0] if not quote_snapshot.empty else None

    latest_close = (
        float(quote_row["latest_close"])
        if quote_row is not None and not pd.isna(quote_row["latest_close"])
        else float(latest["close"])
    )
    latest_date = latest["price_date"].date().isoformat()
    latest_volume = (
        quote_row["volume"]
        if quote_row is not None and "volume" in quote_row and not pd.isna(quote_row["volume"])
        else latest["volume"] if "volume" in latest else None
    )
    average_volume = (
        quote_row["average_volume"]
        if quote_row is not None
        and "average_volume" in quote_row
        and not pd.isna(quote_row["average_volume"])
        else prices["volume"].dropna().tail(20).mean()
    )
    manual_pe_ratio = metadata.get("manual_pe_ratio")
    pe_ratio = (
        manual_pe_ratio
        if manual_pe_ratio is not None and not pd.isna(manual_pe_ratio)
        else quote_row["pe_ratio"] if quote_row is not None else None
    )
    pe_updated_on = metadata.get("manual_pe_updated_on")
    manual_beta = metadata.get("manual_beta")
    beta = (
        manual_beta
        if manual_beta is not None and not pd.isna(manual_beta)
        else quote_row["beta"] if quote_row is not None else None
    )
    beta_updated_on = metadata.get("manual_beta_updated_on")

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Latest close", f"{latest_close:,.2f}", latest_date)
    col2.metric("Volume", format_optional_int(latest_volume))
    col3.metric("Avg volume", format_optional_int(average_volume))
    render_metric_with_update_date(col4, "PE", pe_ratio, pe_updated_on)
    render_metric_with_update_date(col5, "Beta", beta, beta_updated_on)
    st.caption(
        "Quote metrics come from the latest market.asset_quote_snapshots row when "
        "available. Daily price rows are used as fallback for close and volume. "
        "PE and beta are manually maintained on the watchlist."
    )

    render_market_price_chart(symbol, display_prices)


def render_placeholder_section(section: str, price_schema: str | None = None) -> None:
    subpages = SECTION_SUBPAGES[section]
    selected_subpage = st.segmented_control(
        "View",
        subpages,
        default=subpages[0],
        key=f"subpage_{section}",
    )
    if not selected_subpage:
        st.stop()

    if section == SECTION_RESEARCH and selected_subpage == "Comparison":
        if price_schema is None:
            st.stop()
        render_research_comparison_page(price_schema)
        return

    if section == SECTION_RESEARCH and selected_subpage == "Watchlist":
        if price_schema is None:
            st.stop()
        render_market_research_page(price_schema)
        return

    st.subheader(selected_subpage)
    st.info("Placeholder. This dashboard section is ready for future data and charts.")


def render_holdings_section(
    price_schema: str,
    portfolio_schema: str,
    assets: pd.DataFrame,
) -> None:
    st.subheader("Holdings")
    try:
        all_transactions = load_transactions(portfolio_schema)
    except RuntimeError as error:
        st.error(str(error))
        st.stop()

    holding_symbols = transaction_symbol_options(all_transactions)
    if not holding_symbols:
        st.info("No transaction history found yet.")
        st.stop()

    selected_symbol = st.segmented_control(
        "Holding",
        holding_symbols,
        default=DEFAULT_SYMBOL if DEFAULT_SYMBOL in holding_symbols else holding_symbols[0],
    )
    if not selected_symbol:
        st.stop()

    controls_col, _ = st.columns([1, 2])
    with controls_col:
        history_window_label = st.selectbox(
            "History window",
            list(HISTORY_WINDOW_OPTIONS.keys()),
            index=list(HISTORY_WINDOW_OPTIONS.keys()).index("180 Days"),
        )
        target_cagr_pct = DEFAULT_TARGET_CAGR * 100
        if selected_symbol != "CASH.TO":
            target_cagr_pct = st.number_input(
                "Target CAGR",
                min_value=-50.0,
                max_value=50.0,
                value=DEFAULT_TARGET_CAGR * 100,
                step=0.5,
                format="%.1f",
            )
        show_rows = st.checkbox("Show raw rows", value=False)

    lookback_days = HISTORY_WINDOW_OPTIONS[history_window_label]
    if selected_symbol == "CASH.TO":
        render_cash_page(price_schema, portfolio_schema, lookback_days, show_rows)
    else:
        render_asset_page(
            price_schema,
            portfolio_schema,
            assets,
            lookback_days,
            target_cagr_pct / 100,
            show_rows,
            selected_symbol,
        )


def main() -> None:
    st.set_page_config(
        page_title="Investment Dashboard",
        page_icon="",
        layout="wide",
    )
    require_supabase_auth()
    section = sidebar()

    st.title("Investment Dashboard")
    price_schema = get_setting("SUPABASE_PRICE_SCHEMA", DEFAULT_PRICE_SCHEMA)
    portfolio_schema = get_setting(
        "SUPABASE_PORTFOLIO_SCHEMA", DEFAULT_PORTFOLIO_SCHEMA
    )

    if section in SECTION_SUBPAGES:
        render_placeholder_section(section, price_schema)
        return

    if section != SECTION_HOLDINGS:
        st.stop()

    try:
        assets = load_assets(price_schema)
    except RuntimeError as error:
        st.error(str(error))
        st.stop()

    if assets.empty:
        st.warning("No assets found in Supabase.")
        st.stop()

    render_holdings_section(price_schema, portfolio_schema, assets)


if __name__ == "__main__":
    main()
