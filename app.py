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
import streamlit.components.v1 as components


DEFAULT_PRICE_SCHEMA = "market"
DEFAULT_PORTFOLIO_SCHEMA = "portfolio"
DEFAULT_SYMBOL = "VFV.TO"
DEFAULT_TARGET_CAGR = 0.10
COMFORT_ZONE_MULTIPLIER = 0.10
EMA_PERIODS = [8, 20, 50, 100, 200]
EMA_HISTORY_DAYS = 420
VANCOUVER_TZ = ZoneInfo("America/Vancouver")
PORTFOLIO_ASSET_TYPES = {
    "cash": "Cash",
    "savings_account": "Savings account",
    "money_market": "Money market",
    "gic": "GIC",
    "redeemable_gic": "Flexible / Redeemable GIC",
    "equity_index": "Equity index",
    "equity": "Equity",
    "bond": "Bond",
    "fixed_income": "Fixed income",
    "real_estate": "Real estate",
    "gold": "Gold",
    "commodity": "Commodity",
    "crypto": "Crypto",
    "alternative": "Alternative",
    "balanced_fund": "Balanced fund",
    "other": "Other",
}
ACCOUNT_TYPE_LABELS = {
    "tfsa": "TFSA",
    "rrsp": "RRSP",
    "fhsa": "FHSA",
    "taxable": "Taxable",
    "non_registered": "Non-registered",
    "chequing": "Chequing",
    "savings": "Savings",
    "brokerage": "Brokerage",
    "cash": "Cash",
    "other": "Other",
}
REGISTERED_ACCOUNT_TYPES = ["tfsa", "rrsp", "fhsa"]
SECTION_OVERVIEW = "Overview"
SECTION_ACCOUNTS_TAX = "Accounts and Tax"
SECTION_ASSETS = "Assets"
SECTION_PORTFOLIOS = "Portfolios"
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
PORTFOLIO_SUBPAGES = [
    "Asset Type Allocation",
    "Target vs Actual Allocation",
    "Investment Triangle",
]
PORTFOLIO_SELECT_COLUMNS = (
    "id,name,slug,start_year,target_horizon_years_min,target_horizon_years_max,"
    "description,active,archived,display_order,created_at,updated_at"
)
SECTION_SUBPAGES = {
    SECTION_OVERVIEW: [
        "Net Worth",
        "Return vs Inflation",
        "Investment Triangle",
        "Portfolio Overview",
    ],
    SECTION_ACCOUNTS_TAX: [
        "Account Details",
        "Tax Benefit Details",
    ],
    SECTION_RESEARCH: [
        "Watchlist",
        "Comparison",
    ],
}
DASHBOARD_SECTIONS = [
    SECTION_OVERVIEW,
    SECTION_HOLDINGS,
    SECTION_ACCOUNTS_TAX,
    SECTION_ASSETS,
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


def nav_options(portfolio_pages: list[str]) -> list[str]:
    return [*DASHBOARD_SECTIONS, *portfolio_pages]


def sidebar(portfolio_pages: list[str]) -> str:
    if st.session_state.get("dashboard_page") not in nav_options(portfolio_pages):
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
        .sidebar-section-title {
            margin: 1.25rem 0 0.5rem 0;
            padding: 0;
            font-size: 1.02rem;
            font-weight: 700;
            letter-spacing: 0;
            color: inherit;
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
        st.markdown(
            f'<div class="sidebar-section-title">{escape(SECTION_PORTFOLIOS)}</div>',
            unsafe_allow_html=True,
        )
        for section in portfolio_pages:
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


def load_portfolios(portfolio_schema: str) -> pd.DataFrame:
    access_token = supabase_auth_token()
    if not access_token:
        raise RuntimeError("Sign in before reading portfolio data.")

    rows = fetch_table(
        portfolio_schema,
        "portfolios",
        (
            ("select", PORTFOLIO_SELECT_COLUMNS),
            ("active", "eq.true"),
            ("archived", "eq.false"),
            ("order", "display_order.asc,name.asc"),
        ),
        access_token,
    )
    frame = pd.DataFrame(rows)
    for column in [
        "id",
        "start_year",
        "target_horizon_years_min",
        "target_horizon_years_max",
        "display_order",
    ]:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def portfolio_page_options(portfolios: pd.DataFrame) -> list[str]:
    if portfolios.empty or "name" not in portfolios:
        return []
    return [str(name) for name in portfolios["name"].dropna()]


def portfolio_metadata_by_name(portfolios: pd.DataFrame, name: str) -> pd.Series | None:
    if portfolios.empty or "name" not in portfolios:
        return None
    matching = portfolios[portfolios["name"] == name]
    if matching.empty:
        return None
    return matching.iloc[0]


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


def load_holdings(portfolio_schema: str, symbol: str | None = None) -> pd.DataFrame:
    access_token = supabase_auth_token()
    if not access_token:
        raise RuntimeError("Sign in before reading portfolio data.")

    params: list[tuple[str, str]] = [
        ("select", "symbol,account_id,account_name,bought_quantity,sold_quantity,net_quantity,weighted_average_cost,currency"),
        ("order", "symbol.asc"),
    ]
    if symbol:
        params.append(("symbol", f"eq.{symbol}"))

    rows = fetch_table(portfolio_schema, "holdings", tuple(params), access_token)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    for column in [
        "bought_quantity",
        "sold_quantity",
        "net_quantity",
        "weighted_average_cost",
    ]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def load_accounts(portfolio_schema: str) -> pd.DataFrame:
    access_token = supabase_auth_token()
    if not access_token:
        raise RuntimeError("Sign in before reading portfolio data.")

    rows = fetch_table(
        portfolio_schema,
        "account_current_balances",
        (
            (
                "select",
                "id,account_name,institution,account_type,currency,current_interest_rate,"
                "cash_balance,holdings_market_value,current_balance,notes,created_at",
            ),
            ("order", "account_name.asc"),
        ),
        access_token,
    )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    for column in [
        "id",
        "current_interest_rate",
        "cash_balance",
        "holdings_market_value",
        "current_balance",
    ]:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "created_at" in frame:
        frame["created_at"] = pd.to_datetime(frame["created_at"], errors="coerce")
    return frame


def load_registered_account_room_status(portfolio_schema: str) -> pd.DataFrame:
    access_token = supabase_auth_token()
    if not access_token:
        raise RuntimeError("Sign in before reading portfolio data.")

    rows = fetch_table(
        portfolio_schema,
        "registered_account_room_status",
        (
            (
                "select",
                "wrapper_type,total_room,used_room,remaining_room,overused_room,"
                "used_pct,remaining_pct,account_count,protected_balance,notes,"
                "created_at,updated_at",
            ),
            ("order", "wrapper_type.asc"),
        ),
        access_token,
    )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    for column in [
        "total_room",
        "used_room",
        "remaining_room",
        "overused_room",
        "used_pct",
        "remaining_pct",
        "account_count",
        "protected_balance",
    ]:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in ["created_at", "updated_at"]:
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return frame


def load_holding_current_values(portfolio_schema: str) -> pd.DataFrame:
    access_token = supabase_auth_token()
    if not access_token:
        raise RuntimeError("Sign in before reading portfolio data.")

    rows = fetch_table(
        portfolio_schema,
        "holding_current_values",
        (
            (
                "select",
                "id,portfolio_id,portfolio_name,asset_id,asset_name,ticker,asset_type,"
                "valuation_method,market_symbol,holding_name,net_quantity,book_value,"
                "weighted_average_cost,market_price,current_value,currency,start_date,"
                "maturity_date,interest_rate,interest_rate_type,compounding_frequency,"
                "principal_amount,maturity_value,closed_on,auto_accrue_interest,"
                "risk_score,liquidity_score,return_score,expected_return_rate,"
                "volatility_rate,matured_principal,accrued_interest,"
                "expected_maturity_value,notes,active,archived,display_order,"
                "created_at,updated_at",
            ),
            ("order", "portfolio_name.asc,asset_name.asc"),
        ),
        access_token,
    )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    for column in [
        "id",
        "portfolio_id",
        "asset_id",
        "net_quantity",
        "book_value",
        "principal_value",
        "weighted_average_cost",
        "market_price",
        "current_value",
        "interest_rate",
        "principal_amount",
        "maturity_value",
        "risk_score",
        "liquidity_score",
        "return_score",
        "expected_return_rate",
        "volatility_rate",
        "matured_principal",
        "accrued_interest",
        "expected_maturity_value",
        "display_order",
    ]:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in [
        "start_date",
        "maturity_date",
        "closed_on",
        "created_at",
        "updated_at",
    ]:
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
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


@st.cache_data(ttl=3600)
def load_canada_inflation(price_schema: str) -> pd.DataFrame:
    rows = fetch_table(
        price_schema,
        "canada_inflation",
        (
            (
                "select",
                "observation_month,inflation_rate,source,notes,created_at,updated_at",
            ),
            ("order", "observation_month.desc"),
        ),
        supabase_auth_token(),
    )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    if "observation_month" in frame:
        frame["observation_month"] = pd.to_datetime(
            frame["observation_month"],
            errors="coerce",
        )
    if "inflation_rate" in frame:
        frame["inflation_rate"] = pd.to_numeric(
            frame["inflation_rate"],
            errors="coerce",
        )
    for column in ["created_at", "updated_at"]:
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return frame


def load_holding_transactions_current(portfolio_schema: str) -> pd.DataFrame:
    access_token = supabase_auth_token()
    if not access_token:
        raise RuntimeError("Sign in before reading portfolio data.")

    rows = fetch_table(
        portfolio_schema,
        "transactions",
        (
            (
                "select",
                "id,holding_id,transaction_type,quantity,price,fees,cash_amount,"
                "principal_amount,interest_amount,income_amount",
            ),
            ("order", "transaction_date.desc,id.desc"),
        ),
        access_token,
    )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    for column in [
        "id",
        "holding_id",
        "quantity",
        "price",
        "fees",
        "cash_amount",
        "principal_amount",
        "interest_amount",
        "income_amount",
    ]:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def active_detail_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame

    active_rows = frame.copy()
    if "active" in active_rows:
        active_rows = active_rows[active_rows["active"].fillna(False)]
    if "archived" in active_rows:
        active_rows = active_rows[~active_rows["archived"].fillna(False)]

    value_columns = [
        column
        for column in [
            "net_quantity",
            "current_value",
            "expected_maturity_value",
            "maturity_value",
            "principal_amount",
            "principal_value",
            "book_value",
            "accrued_interest",
        ]
        if column in active_rows
    ]
    if value_columns:
        numeric_values = active_rows[value_columns].apply(
            pd.to_numeric,
            errors="coerce",
        ).fillna(0)
        active_rows = active_rows[numeric_values.abs().sum(axis=1) != 0]
    return active_rows


def ensure_principal_value_column(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()

    normalized = frame.copy()
    book_values = (
        pd.to_numeric(normalized.get("book_value"), errors="coerce")
        if "book_value" in normalized
        else pd.Series([pd.NA] * len(normalized), index=normalized.index, dtype="object")
    )
    if "principal_value" not in normalized:
        normalized["principal_value"] = book_values
    else:
        normalized["principal_value"] = pd.to_numeric(
            normalized["principal_value"],
            errors="coerce",
        ).where(
            pd.to_numeric(normalized["principal_value"], errors="coerce").notna(),
            book_values,
        )
    return normalized


def holdings_overview_label(row: pd.Series | dict[str, Any]) -> str:
    portfolio_name = row.get("portfolio_name")
    asset_name = row.get("asset_name")
    portfolio_label = (
        str(portfolio_name).strip()
        if portfolio_name is not None and not pd.isna(portfolio_name) and str(portfolio_name).strip()
        else "Unknown portfolio"
    )
    asset_label = (
        str(asset_name).strip()
        if asset_name is not None and not pd.isna(asset_name) and str(asset_name).strip()
        else f"Holding {int(row.get('id', 0))}"
    )
    holding_name = row.get("holding_name")
    if holding_name is None or pd.isna(holding_name) or not str(holding_name).strip():
        return f"{portfolio_label} - {asset_label}"
    return f"{portfolio_label} - {asset_label} ({str(holding_name).strip()})"


def asset_type_label(asset_type: Any) -> str:
    if asset_type is None or pd.isna(asset_type):
        return "Unknown"
    return PORTFOLIO_ASSET_TYPES.get(str(asset_type), str(asset_type))


def holdings_display_name(row: pd.Series | dict[str, Any]) -> str:
    holding_name = row.get("holding_name")
    if holding_name is not None and not pd.isna(holding_name) and str(holding_name).strip():
        return str(holding_name).strip()
    asset_name = row.get("asset_name")
    if asset_name is not None and not pd.isna(asset_name) and str(asset_name).strip():
        return str(asset_name).strip()
    return f"Holding {int(row.get('id', 0))}"


def portfolio_initials(name: Any) -> str:
    if name is None or pd.isna(name) or not str(name).strip():
        return "UP"
    parts = [part for part in str(name).strip().split() if part]
    if not parts:
        return "UP"
    return "".join(part[0].upper() for part in parts)


def principal_growth_axis_name(row: pd.Series | dict[str, Any], view_mode: str) -> str:
    holding_name = holdings_display_name(row)
    if view_mode == "View by Portfolio":
        ticker = row.get("ticker")
        if ticker is not None and not pd.isna(ticker) and str(ticker).strip():
            return f"{str(ticker).strip()} {holding_name}"
        return holding_name
    return f"{portfolio_initials(row.get('portfolio_name'))} {holding_name}"


def holding_principal_adjustments(
    transactions: pd.DataFrame,
) -> pd.Series:
    if transactions.empty:
        return pd.Series(dtype="float64")

    normalized = transactions.copy()
    for column in [
        "holding_id",
        "quantity",
        "price",
        "fees",
        "cash_amount",
        "principal_amount",
        "interest_amount",
    ]:
        if column not in normalized:
            normalized[column] = pd.Series(dtype="float64")
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    normalized["fees"] = normalized["fees"].fillna(0)
    normalized["transaction_amount"] = normalized["cash_amount"]
    no_cash_mask = normalized["transaction_amount"].isna()
    normalized.loc[no_cash_mask, "transaction_amount"] = (
        normalized.loc[no_cash_mask, "quantity"].fillna(0)
        * normalized.loc[no_cash_mask, "price"].fillna(0)
    )
    remaining_mask = normalized["transaction_amount"].isna() | (
        normalized["transaction_amount"] == 0
    )
    normalized.loc[remaining_mask, "transaction_amount"] = normalized.loc[
        remaining_mask, "price"
    ]
    remaining_mask = normalized["transaction_amount"].isna() | (
        normalized["transaction_amount"] == 0
    )
    normalized.loc[remaining_mask, "transaction_amount"] = normalized.loc[
        remaining_mask, "quantity"
    ]
    remaining_mask = normalized["transaction_amount"].isna() | (
        normalized["transaction_amount"] == 0
    )
    normalized.loc[remaining_mask, "transaction_amount"] = (
        normalized.loc[remaining_mask, "principal_amount"].fillna(0)
        + normalized.loc[remaining_mask, "interest_amount"].fillna(0)
    )
    normalized["transaction_amount"] = normalized["transaction_amount"].fillna(0)

    normalized["principal_component"] = 0.0
    buy_mask = normalized["transaction_type"] == "buy"
    sell_mask = normalized["transaction_type"] == "sell"
    deposit_mask = normalized["transaction_type"].isin(["deposit", "transfer_in"])
    withdrawal_mask = normalized["transaction_type"].isin(["withdrawal", "transfer_out"])
    maturity_mask = normalized["transaction_type"] == "maturity"

    normalized.loc[buy_mask, "principal_component"] = (
        normalized.loc[buy_mask, "transaction_amount"] + normalized.loc[buy_mask, "fees"]
    )
    normalized.loc[sell_mask, "principal_component"] = -(
        normalized.loc[sell_mask, "transaction_amount"] + normalized.loc[sell_mask, "fees"]
    )
    normalized.loc[deposit_mask, "principal_component"] = normalized.loc[
        deposit_mask, "transaction_amount"
    ]
    normalized.loc[withdrawal_mask, "principal_component"] = -normalized.loc[
        withdrawal_mask, "transaction_amount"
    ]
    normalized.loc[maturity_mask, "principal_component"] = -normalized.loc[
        maturity_mask, "principal_amount"
    ].fillna(
        normalized.loc[maturity_mask, "transaction_amount"]
        - normalized.loc[maturity_mask, "interest_amount"].fillna(0)
    )

    return normalized.groupby("holding_id")["principal_component"].sum()


def holding_income_adjustments(
    transactions: pd.DataFrame,
) -> pd.Series:
    if transactions.empty:
        return pd.Series(dtype="float64")

    normalized = transactions.copy()
    for column in [
        "holding_id",
        "cash_amount",
        "interest_amount",
        "income_amount",
    ]:
        if column not in normalized:
            normalized[column] = pd.Series(dtype="float64")
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    normalized["income_component"] = normalized["income_amount"]

    dividend_interest_mask = normalized["transaction_type"].isin(["dividend", "interest"])
    normalized.loc[
        dividend_interest_mask & normalized["income_component"].isna(),
        "income_component",
    ] = normalized.loc[
        dividend_interest_mask & normalized["income_component"].isna(),
        "cash_amount",
    ]

    maturity_mask = normalized["transaction_type"] == "maturity"
    normalized.loc[
        maturity_mask & normalized["income_component"].isna(),
        "income_component",
    ] = normalized.loc[
        maturity_mask & normalized["income_component"].isna(),
        "interest_amount",
    ]

    normalized["income_component"] = normalized["income_component"].fillna(0)
    return normalized.groupby("holding_id")["income_component"].sum()


def active_holdings_overview_rows(
    holding_values: pd.DataFrame,
    transactions: pd.DataFrame | None = None,
) -> pd.DataFrame:
    active_holdings = ensure_principal_value_column(active_detail_rows(holding_values))
    if active_holdings.empty:
        return active_holdings

    for column in ["principal_value", "current_value", "expected_return_rate"]:
        if column not in active_holdings:
            active_holdings[column] = 0
        active_holdings[column] = pd.to_numeric(
            active_holdings[column],
            errors="coerce",
        )
    active_holdings["principal_value"] = active_holdings["principal_value"].fillna(0)
    active_holdings["accumulated_income_amount"] = 0.0
    if transactions is not None and not transactions.empty:
        adjusted_principal = holding_principal_adjustments(transactions)
        adjusted_income = holding_income_adjustments(transactions)
        active_holdings["principal_value"] = (
            active_holdings["id"]
            .map(adjusted_principal)
            .fillna(active_holdings["principal_value"])
        )
        active_holdings["accumulated_income_amount"] = (
            active_holdings["id"].map(adjusted_income).fillna(0)
        )
    active_holdings["current_value"] = active_holdings["current_value"].fillna(0)
    active_holdings["growth_value"] = (
        active_holdings["current_value"]
        - active_holdings["principal_value"]
        + active_holdings["accumulated_income_amount"]
    )
    active_holdings["holding_label"] = active_holdings.apply(
        holdings_overview_label,
        axis=1,
    )
    return active_holdings.sort_values("holding_label").reset_index(drop=True)


def add_allocation_value(holdings: pd.DataFrame) -> pd.DataFrame:
    frame = ensure_principal_value_column(holdings)
    value_columns = [
        "current_value",
        "expected_maturity_value",
        "maturity_value",
        "principal_amount",
        "principal_value",
        "book_value",
    ]
    for column in value_columns:
        if column not in frame:
            frame[column] = 0
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)

    frame["allocation_value"] = 0.0
    for column in value_columns:
        frame["allocation_value"] = frame["allocation_value"].where(
            frame["allocation_value"] > 0,
            frame[column],
        )
    return frame


def investment_triangle_weighted_scores(holdings: pd.DataFrame) -> pd.DataFrame:
    metrics = [
        ("risk_score", "Risk"),
        ("liquidity_score", "Liquidity"),
        ("return_score", "Return"),
    ]
    rows: list[dict[str, float | str | int]] = []
    for index, (column, label) in enumerate(metrics):
        scored = holdings[
            holdings["allocation_value"].gt(0) & holdings[column].notna()
        ].copy()
        total_weight = float(scored["allocation_value"].sum()) if not scored.empty else 0.0
        weighted_score = (
            float((scored["allocation_value"] * scored[column]).sum()) / total_weight
            if total_weight > 0
            else 0.0
        )
        coverage_weight = total_weight
        coverage_pct = (
            total_weight / float(holdings["allocation_value"].sum())
            if not holdings.empty and float(holdings["allocation_value"].sum()) > 0
            else 0.0
        )
        rows.append(
            {
                "axis": label,
                "score": weighted_score,
                "sort_order": index,
                "coverage_weight": coverage_weight,
                "coverage_pct": coverage_pct,
            }
        )
    return pd.DataFrame(rows)


def investment_triangle_distribution(
    holdings: pd.DataFrame,
    score_column: str,
    label: str,
) -> pd.DataFrame:
    frame = holdings[
        holdings["allocation_value"].gt(0) & holdings[score_column].notna()
    ].copy()
    if frame.empty:
        return pd.DataFrame(
            {
                "bucket": list(range(11)),
                "allocation_value": [0.0] * 11,
                "score_type": [label] * 11,
            }
        )

    frame["bucket"] = frame[score_column].round().clip(0, 10).astype(int)
    distribution = (
        frame.groupby("bucket", as_index=False)["allocation_value"]
        .sum()
        .sort_values("bucket")
    )
    distribution = distribution.set_index("bucket").reindex(range(11), fill_value=0.0).reset_index()
    distribution["score_type"] = label
    return distribution


def holding_symbol_options(holdings: pd.DataFrame) -> list[str]:
    if holdings.empty or "symbol" not in holdings:
        return []

    active_holdings = holdings
    if "net_quantity" in holdings:
        active_holdings = holdings[holdings["net_quantity"].fillna(0) != 0]

    symbols = [str(symbol) for symbol in active_holdings["symbol"].dropna().tolist()]
    available_symbols = set(symbols)
    preferred_symbols = [
        symbol for symbol in PREFERRED_HOLDING_SYMBOLS if symbol in available_symbols
    ]
    remaining_symbols = sorted(
        symbol for symbol in available_symbols if symbol not in set(preferred_symbols)
    )
    return preferred_symbols + remaining_symbols


def holding_summary(holdings: pd.DataFrame) -> tuple[float | None, float | None]:
    if holdings.empty:
        return None, None

    active_holdings = holdings[holdings["net_quantity"].fillna(0) != 0].copy()
    if active_holdings.empty:
        return None, None

    total_quantity = active_holdings["net_quantity"].sum()
    if not total_quantity:
        return None, None

    cost_rows = active_holdings.dropna(subset=["weighted_average_cost"])
    if cost_rows.empty:
        return None, float(total_quantity)

    weighted_cost = (
        cost_rows["weighted_average_cost"] * cost_rows["net_quantity"]
    ).sum()
    cost_quantity = cost_rows["net_quantity"].sum()
    if not cost_quantity:
        return None, float(total_quantity)

    return float(weighted_cost / cost_quantity), float(total_quantity)


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


def render_total_gain_rate_donut(gain_rate: float | None) -> None:
    st.subheader("Total Gain Rate")
    if gain_rate is None:
        st.info("Total gain rate is not available yet.")
        return

    palette = chart_palette()
    gain_color = palette["target_growth"] if gain_rate >= 0 else palette["average_cost"]
    remainder_color = "rgba(148, 163, 184, 0.28)"
    ring_fill = min(abs(gain_rate), 1.0)
    chart_data = pd.DataFrame(
        [
            {"Segment": "Total Gain Rate", "Value": ring_fill},
            {"Segment": "Remaining", "Value": max(1.0 - ring_fill, 0.0)},
        ]
    )
    text_color = "#f9fafb" if is_dark_theme() else "#111827"
    chart = (
        alt.Chart(chart_data)
        .mark_arc(innerRadius=58, outerRadius=82)
        .encode(
            theta=alt.Theta("Value:Q", stack=True),
            color=alt.Color(
                "Segment:N",
                scale=alt.Scale(
                    domain=["Total Gain Rate", "Remaining"],
                    range=[gain_color, remainder_color],
                ),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("Segment:N", title="Metric"),
                alt.Tooltip("Value:Q", title="Ring share", format=".0%"),
            ],
        )
    )
    label = (
        alt.Chart(pd.DataFrame([{"label": f"{gain_rate:.2%}"}]))
        .mark_text(size=24, fontWeight="bold", color=text_color)
        .encode(text="label:N")
    )
    st.altair_chart((chart + label).properties(height=210), width="stretch")


def svg_triangle_radar(weighted_scores: pd.DataFrame) -> str:
    axis_order = ["Risk", "Liquidity", "Return"]
    values = {
        row["axis"]: float(row["score"])
        for row in weighted_scores.to_dict("records")
    }
    width = 420
    height = 380
    cx = width / 2
    cy = height / 2 + 8
    radius = 130
    angles = {
        "Risk": -90,
        "Liquidity": 30,
        "Return": 150,
    }

    def point(axis: str, scale: float) -> tuple[float, float]:
        angle = angles[axis] * 3.141592653589793 / 180.0
        return (
            cx + radius * scale * __import__("math").cos(angle),
            cy + radius * scale * __import__("math").sin(angle),
        )

    grid_levels = [0.25, 0.5, 0.75, 1.0]
    grid_polygons = []
    for level in grid_levels:
        coords = [point(axis, level) for axis in axis_order]
        grid_polygons.append(
            " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
        )

    data_coords = [
        point(axis, max(0.0, min(10.0, values.get(axis, 0.0))) / 10.0)
        for axis in axis_order
    ]
    data_polygon = " ".join(f"{x:.1f},{y:.1f}" for x, y in data_coords)

    axis_lines = []
    axis_labels = []
    tick_labels = []
    for axis in axis_order:
        x, y = point(axis, 1.0)
        axis_lines.append(
            f'<line class="triangle-axis" x1="{cx:.1f}" y1="{cy:.1f}" x2="{x:.1f}" y2="{y:.1f}" stroke-width="1.5" />'
        )
        lx, ly = point(axis, 1.16)
        axis_labels.append(
            f'<text class="triangle-axis-label" x="{lx:.1f}" y="{ly:.1f}" font-size="15" font-weight="600" text-anchor="middle">{axis}</text>'
        )

    for level, label in zip(grid_levels, ["2.5", "5", "7.5", "10"]):
        tx, ty = point("Risk", level)
        tick_labels.append(
            f'<text class="triangle-tick-label" x="{tx + 10:.1f}" y="{ty + 4:.1f}" font-size="11">{label}</text>'
        )

    value_badges = []
    for axis in axis_order:
        vx, vy = point(axis, max(0.0, min(10.0, values.get(axis, 0.0))) / 10.0)
        value_badges.append(
            f'<circle class="triangle-point" cx="{vx:.1f}" cy="{vy:.1f}" r="4.5" />'
            f'<text class="triangle-value-label" x="{vx:.1f}" y="{vy - 10:.1f}" font-size="12" text-anchor="middle">{values.get(axis, 0.0):.1f}</text>'
        )

    return f"""
    <style>
      .triangle-radar {{
        --triangle-bg: var(--background-color, #ffffff);
        --triangle-grid: color-mix(in srgb, var(--text-color, #0f172a) 18%, transparent);
        --triangle-axis: color-mix(in srgb, var(--text-color, #0f172a) 55%, transparent);
        --triangle-axis-text: var(--text-color, #0f172a);
        --triangle-tick-text: color-mix(in srgb, var(--text-color, #0f172a) 72%, transparent);
        --triangle-fill: rgba(59, 130, 246, 0.22);
        --triangle-stroke: #2563eb;
        --triangle-point: #1d4ed8;
        --triangle-value-text: #1e3a8a;
      }}
      @media (prefers-color-scheme: dark) {{
        .triangle-radar {{
          --triangle-fill: rgba(125, 183, 255, 0.28);
          --triangle-stroke: #ffffff;
          --triangle-point: #ffffff;
          --triangle-value-text: #ffffff;
        }}
      }}
      [data-theme-base="dark"] .triangle-radar,
      [data-base-theme="dark"] .triangle-radar,
      [data-testid="stAppViewContainer"][data-theme="dark"] .triangle-radar,
      .stApp[data-theme="dark"] .triangle-radar,
      .stApp[class*="dark"] .triangle-radar {{
        --triangle-bg: #000000;
        --triangle-fill: rgba(125, 183, 255, 0.28);
        --triangle-stroke: #ffffff;
        --triangle-point: #ffffff;
        --triangle-value-text: #ffffff;
      }}
      .triangle-radar .triangle-bg {{ fill: var(--triangle-bg); }}
      .triangle-radar .triangle-grid {{ fill: none; stroke: var(--triangle-grid); stroke-width: 1; }}
      .triangle-radar .triangle-axis {{ stroke: var(--triangle-axis); }}
      .triangle-radar .triangle-shape {{ fill: var(--triangle-fill); stroke: var(--triangle-stroke); stroke-width: 3; }}
      .triangle-radar .triangle-point {{ fill: var(--triangle-point); }}
      .triangle-radar .triangle-axis-label {{ fill: var(--triangle-axis-text); }}
      .triangle-radar .triangle-tick-label {{ fill: var(--triangle-tick-text); }}
      .triangle-radar .triangle-value-label {{ fill: var(--triangle-value-text); }}
    </style>
    <div class="triangle-radar" style="display:flex; justify-content:center; padding: 8px 0 22px 0;">
      <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Investment triangle radar chart">
        <rect class="triangle-bg" x="0" y="0" width="{width}" height="{height}" rx="14" ry="14" />
        {' '.join(f'<polygon class="triangle-grid" points="{poly}" />' for poly in grid_polygons)}
        {''.join(axis_lines)}
        <polygon class="triangle-shape" points="{data_polygon}" />
        {''.join(value_badges)}
        {''.join(axis_labels)}
        {''.join(tick_labels)}
      </svg>
    </div>
    """


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


def format_year(value: Any) -> str:
    if value is None or pd.isna(value):
        return "Not available"
    return f"{int(value)}"


def compact_horizon_label(min_years: Any, max_years: Any) -> str:
    if min_years is None or pd.isna(min_years):
        return "Not set"
    min_value = float(min_years)
    if max_years is None or pd.isna(max_years) or float(max_years) == min_value:
        return f"{min_value:g} yr"
    return f"{min_value:g}-{float(max_years):g} yrs"


def portfolio_status_label(portfolio: pd.Series) -> str:
    labels = []
    if bool(portfolio.get("active", False)):
        labels.append("Active")
    else:
        labels.append("Inactive")
    if bool(portfolio.get("archived", False)):
        labels.append("Archived")
    return " / ".join(labels)


def render_portfolio_metadata_summary(portfolio: pd.Series) -> None:
    description = portfolio.get("description")
    if isinstance(description, str) and description.strip():
        st.caption(description.strip())

    col1, col2, col3 = st.columns(3)
    col1.metric("Start", format_year(portfolio.get("start_year")))
    col2.metric(
        "Horizon",
        compact_horizon_label(
            portfolio.get("target_horizon_years_min"),
            portfolio.get("target_horizon_years_max"),
        ),
    )
    col3.metric("Status", portfolio_status_label(portfolio))


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


def render_average_volume_chart(
    symbol: str,
    prices: pd.DataFrame,
    window: int = 20,
) -> None:
    if prices.empty or "volume" not in prices:
        return

    chart_data = (
        prices[["price_date", "volume"]]
        .dropna()
        .sort_values("price_date")
        .rename(columns={"price_date": "Date", "volume": "Volume"})
    )
    if chart_data.empty:
        return

    chart_data["Average Volume"] = (
        chart_data["Volume"].rolling(window, min_periods=1).mean()
    )
    base = alt.Chart(chart_data).encode(
        x=alt.X("Date:T", title="Date"),
        tooltip=[
            alt.Tooltip("Date:T", title="Date"),
            alt.Tooltip("Volume:Q", title="Daily Volume", format=",.0f"),
            alt.Tooltip(
                "Average Volume:Q",
                title=f"{window}-Day Avg Volume",
                format=",.0f",
            ),
        ],
    )
    daily_bars = (
        base.mark_bar(color="#93c5fd", opacity=0.45)
        .encode(
            y=alt.Y("Volume:Q", title="Volume (units)", scale=alt.Scale(zero=False))
        )
    )
    average_line = (
        base.mark_line(color="#0f766e", strokeWidth=2.6)
        .encode(y=alt.Y("Average Volume:Q", title="Volume (units)"))
    )
    st.subheader(f"{symbol} Volume")
    st.altair_chart(
        alt.layer(daily_bars, average_line).resolve_scale(y="shared").properties(height=300),
        width="stretch",
    )
    chart_legend(
        [
            ("Daily Volume", "#93c5fd"),
            (f"{window}-Day Avg Volume", "#0f766e"),
        ]
    )


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
    tracked: pd.DataFrame,
    symbols: list[str],
    start_date: date,
    mode: str,
) -> pd.DataFrame:
    frames = []
    for symbol in symbols:
        prices = load_prices(price_schema, symbol, start_date)
        if prices.empty or "volume" not in prices:
            continue
        required_columns = ["price_date", "open", "high", "low", "close", "volume"]
        prices = prices[[column for column in required_columns if column in prices]]
        prices = prices.dropna(subset=["price_date", "volume"]).sort_values("price_date")
        if prices.empty:
            continue

        prices = prices.rename(columns={"price_date": "Date", "volume": "Volume"})
        prices["Symbol"] = symbol
        if mode == "Average USD Volume":
            metadata_match = tracked[tracked["symbol"] == symbol]
            currency = (
                metadata_match.iloc[0].get("currency")
                if not metadata_match.empty
                else "USD"
            )
            fx_rate = fetch_fx_rate_to_usd(currency)
            if fx_rate is None:
                continue
            ohlc_columns = [
                column for column in ["open", "high", "low", "close"] if column in prices
            ]
            prices["Average Price"] = prices[ohlc_columns].mean(axis=1, skipna=True)
            prices["USD Dollar Volume"] = prices["Average Price"] * prices["Volume"] * fx_rate
            prices["Value"] = prices["USD Dollar Volume"].rolling(20, min_periods=1).mean()
        else:
            prices["Value"] = (
                prices["Volume"].rolling(20, min_periods=1).mean()
                if mode == "Average Volume"
                else prices["Volume"]
            )
        frames.append(prices)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


@st.cache_data(ttl=3600)
def fetch_fx_rate_to_usd(currency: str | None) -> float | None:
    currency_code = (currency or "USD").strip().upper()
    if currency_code == "USD":
        return 1.0

    response = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{currency_code}USD=X",
        params={"range": "5d", "interval": "1d"},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=10,
    )
    if response.status_code >= 400:
        return None

    payload = response.json()
    results = (payload.get("chart") or {}).get("result") or []
    if not results:
        return None

    close_values = (
        ((results[0].get("indicators") or {}).get("quote") or [{}])[0].get("close")
        or []
    )
    rates = pd.to_numeric(pd.Series(close_values), errors="coerce").dropna()
    if rates.empty:
        return None
    return float(rates.iloc[-1])


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
    if mode == "Average USD Volume":
        return "20-Day Average USD Volume"
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
                "Average USD Volume",
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
        if mode in {"Volume", "Average Volume", "Average USD Volume"}:
            chart_data = comparison_volume_data(
                price_schema,
                tracked,
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
        if "Average Price" in chart_data:
            tooltip.insert(3, alt.Tooltip("Average Price:Q", title="Average Price", format=",.2f"))
        if "USD Dollar Volume" in chart_data:
            tooltip.insert(4, alt.Tooltip("USD Dollar Volume:Q", title="USD Volume", format=",.0f"))
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
    elif mode == "Average USD Volume":
        st.caption(
            "Average USD volume uses a 20-day rolling average of estimated dollar "
            "volume: mean(open, high, low, close) x volume x latest FX rate to USD."
        )
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
            "total_gain": None,
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
        "total_gain": total_gain,
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


def account_type_label(account_type: Any) -> str:
    if account_type is None or pd.isna(account_type):
        return "Unknown"
    return ACCOUNT_TYPE_LABELS.get(str(account_type), str(account_type))


def render_account_allocation(accounts: pd.DataFrame) -> None:
    if accounts.empty:
        st.info("No account balance data is available yet.")
        return

    allocation = accounts.copy()
    allocation["current_balance"] = pd.to_numeric(
        allocation.get("current_balance"),
        errors="coerce",
    ).fillna(0)
    allocation = allocation[allocation["current_balance"] > 0].copy()
    if allocation.empty:
        st.info("No positive account balances found.")
        return

    total_balance = float(allocation["current_balance"].sum())
    if total_balance <= 0:
        st.info("No positive account balances found.")
        return

    allocation["account_type_label"] = allocation["account_type"].apply(account_type_label)
    allocation["allocation_pct"] = allocation["current_balance"] / total_balance
    allocation["allocation_pct_display"] = allocation["allocation_pct"] * 100
    allocation["account_label"] = allocation.apply(
        lambda row: (
            str(row["account_name"]).strip()
            if not row.get("institution")
            else f"{str(row['account_name']).strip()} ({str(row['institution']).strip()})"
        ),
        axis=1,
    )
    allocation = allocation.sort_values("current_balance", ascending=False).reset_index(
        drop=True
    )

    chart = (
        alt.Chart(allocation)
        .mark_arc(innerRadius=58, outerRadius=130)
        .encode(
            theta=alt.Theta("current_balance:Q", stack=True),
            color=alt.Color("account_label:N", title="Account"),
            tooltip=[
                alt.Tooltip("account_name:N", title="Account"),
                alt.Tooltip("institution:N", title="Institution"),
                alt.Tooltip("account_type_label:N", title="Account type"),
                alt.Tooltip("current_balance:Q", title="Balance", format=",.2f"),
                alt.Tooltip("allocation_pct:Q", title="Allocation", format=".2%"),
                alt.Tooltip("cash_balance:Q", title="Cash balance", format=",.2f"),
                alt.Tooltip(
                    "holdings_market_value:Q",
                    title="Holdings value",
                    format=",.2f",
                ),
            ],
        )
        .properties(height=380)
    )
    st.altair_chart(chart, width="stretch")
    st.caption(f"Total account balance: {total_balance:,.2f}")
    st.dataframe(
        allocation,
        width="stretch",
        hide_index=True,
        column_config={
            "account_name": "Account",
            "institution": "Institution",
            "account_type_label": "Account type",
            "current_balance": st.column_config.NumberColumn("Balance", format="%.2f"),
            "allocation_pct_display": st.column_config.NumberColumn(
                "Allocation",
                format="%.2f%%",
            ),
            "cash_balance": st.column_config.NumberColumn(
                "Cash",
                format="%.2f",
            ),
            "holdings_market_value": st.column_config.NumberColumn(
                "Holdings",
                format="%.2f",
            ),
        },
        column_order=[
            "account_name",
            "institution",
            "account_type_label",
            "current_balance",
            "allocation_pct_display",
            "cash_balance",
            "holdings_market_value",
        ],
    )


def render_account_balance_chart(accounts: pd.DataFrame) -> None:
    if accounts.empty:
        st.info("No account balance data is available yet.")
        return

    chart_data = accounts.copy()
    chart_data["current_balance"] = pd.to_numeric(
        chart_data.get("current_balance"),
        errors="coerce",
    ).fillna(0)
    chart_data = chart_data[chart_data["current_balance"] != 0].copy()
    if chart_data.empty:
        st.info("No non-zero account balances found.")
        return

    chart_data["account_type_label"] = chart_data["account_type"].apply(account_type_label)
    chart_data["account_label"] = chart_data.apply(
        lambda row: (
            str(row["account_name"]).strip()
            if not row.get("institution")
            else f"{str(row['account_name']).strip()} ({str(row['institution']).strip()})"
        ),
        axis=1,
    )
    chart_data["balance_label"] = chart_data["current_balance"].map(lambda value: f"{value:,.2f}")
    chart_data = chart_data.sort_values("current_balance", ascending=False).reset_index(
        drop=True
    )

    text_align = "left" if (chart_data["current_balance"] >= 0).all() else "center"
    text_dx = 6 if (chart_data["current_balance"] >= 0).all() else 0
    chart = alt.layer(
        alt.Chart(chart_data)
        .mark_bar(color=chart_palette()["actual"], cornerRadiusEnd=4, opacity=0.88)
        .encode(
            x=alt.X("current_balance:Q", title="Balance"),
            y=alt.Y(
                "account_label:N",
                title=None,
                sort=chart_data["account_label"].tolist(),
            ),
            tooltip=[
                alt.Tooltip("account_name:N", title="Account"),
                alt.Tooltip("institution:N", title="Institution"),
                alt.Tooltip("account_type_label:N", title="Account type"),
                alt.Tooltip("current_balance:Q", title="Balance", format=",.2f"),
                alt.Tooltip("cash_balance:Q", title="Cash balance", format=",.2f"),
                alt.Tooltip(
                    "holdings_market_value:Q",
                    title="Holdings value",
                    format=",.2f",
                ),
            ],
        ),
        alt.Chart(chart_data)
        .mark_text(
            align=text_align,
            baseline="middle",
            dx=text_dx,
            color="#f9fafb" if is_dark_theme() else "#111827",
            fontWeight="bold",
        )
        .encode(
            x=alt.X("current_balance:Q"),
            y=alt.Y("account_label:N", sort=chart_data["account_label"].tolist()),
            text="balance_label:N",
        ),
    ).properties(height=max(260, 56 * len(chart_data)))
    st.altair_chart(chart, width="stretch")


def render_labeled_donut_chart(
    *,
    values: pd.DataFrame,
    category_field: str,
    value_field: str,
    label_text: str,
    color_range: list[str],
    tooltip: list[Any],
    height: int = 250,
) -> None:
    text_color = "#f9fafb" if is_dark_theme() else "#111827"
    chart = (
        alt.Chart(values)
        .mark_arc(innerRadius=60, outerRadius=96)
        .encode(
            theta=alt.Theta(f"{value_field}:Q", stack=True),
            color=alt.Color(
                f"{category_field}:N",
                scale=alt.Scale(
                    domain=values[category_field].tolist(),
                    range=color_range,
                ),
                legend=None,
            ),
            tooltip=tooltip,
        )
    )
    label = (
        alt.Chart(pd.DataFrame([{"label": label_text}]))
        .mark_text(
            size=19,
            fontWeight="bold",
            align="center",
            baseline="middle",
            color=text_color,
        )
        .encode(text="label:N")
    )
    st.altair_chart((chart + label).properties(height=height), width="stretch")


def portfolio_horizon_bucket(midpoint_years: Any) -> str:
    midpoint = pd.to_numeric(midpoint_years, errors="coerce")
    if pd.isna(midpoint):
        return "Unspecified"
    if float(midpoint) <= 3:
        return "Short term"
    if float(midpoint) <= 10:
        return "Medium term"
    return "Long term"


def build_global_portfolio_overview(
    portfolios: pd.DataFrame,
    holding_values: pd.DataFrame,
) -> pd.DataFrame:
    if portfolios.empty:
        return pd.DataFrame()

    active_holdings = active_detail_rows(holding_values)
    if active_holdings.empty:
        grouped_values = pd.DataFrame(columns=["portfolio_id", "market_value"])
    else:
        active_holdings = active_holdings.copy()
        active_holdings["current_value"] = pd.to_numeric(
            active_holdings.get("current_value"),
            errors="coerce",
        ).fillna(0)
        grouped_values = (
            active_holdings.groupby("portfolio_id", dropna=False, as_index=False)[
                "current_value"
            ]
            .sum()
            .rename(columns={"current_value": "market_value"})
        )

    overview = portfolios.copy()
    overview = overview.merge(
        grouped_values,
        how="left",
        left_on="id",
        right_on="portfolio_id",
    )
    overview["market_value"] = pd.to_numeric(
        overview.get("market_value"),
        errors="coerce",
    ).fillna(0)
    overview["target_horizon_years_min"] = pd.to_numeric(
        overview.get("target_horizon_years_min"),
        errors="coerce",
    )
    overview["target_horizon_years_max"] = pd.to_numeric(
        overview.get("target_horizon_years_max"),
        errors="coerce",
    )
    overview["horizon_midpoint_years"] = (
        overview["target_horizon_years_min"].fillna(overview["target_horizon_years_max"])
        + overview["target_horizon_years_max"].fillna(overview["target_horizon_years_min"])
    ) / 2
    overview["horizon_bucket"] = overview["horizon_midpoint_years"].apply(
        portfolio_horizon_bucket
    )
    overview["horizon_range_label"] = overview.apply(
        lambda row: compact_horizon_label(
            row.get("target_horizon_years_min"),
            row.get("target_horizon_years_max"),
        ),
        axis=1,
    )
    total_market_value = float(overview["market_value"].sum())
    overview["allocation_pct"] = (
        overview["market_value"] / total_market_value if total_market_value > 0 else 0.0
    )
    return overview.sort_values(
        ["market_value", "display_order", "name"],
        ascending=[False, True, True],
        na_position="last",
    ).reset_index(drop=True)


def render_global_portfolio_overview(portfolio_schema: str) -> None:
    try:
        portfolios = load_portfolios(portfolio_schema)
        holding_values = load_holding_current_values(portfolio_schema)
    except RuntimeError as error:
        st.error(str(error))
        return

    overview = build_global_portfolio_overview(portfolios, holding_values)
    if overview.empty:
        st.info("No active portfolios are available yet.")
        return

    portfolio_allocation = overview[overview["market_value"] > 0].copy()
    st.subheader("Portfolio Allocation")
    if portfolio_allocation.empty:
        st.info("No portfolio market values are available yet.")
    else:
        donut_colors = [
            "#60a5fa",
            "#22c55e",
            "#f59e0b",
            "#f87171",
            "#a78bfa",
            "#2dd4bf",
            "#fb7185",
            "#c084fc",
        ]
        total_market_value = float(portfolio_allocation["market_value"].sum())
        render_labeled_donut_chart(
            values=portfolio_allocation,
            category_field="name",
            value_field="market_value",
            label_text=f"{total_market_value:,.0f}",
            color_range=donut_colors[: len(portfolio_allocation)],
            tooltip=[
                alt.Tooltip("name:N", title="Portfolio"),
                alt.Tooltip("market_value:Q", title="Market value", format=",.2f"),
                alt.Tooltip("allocation_pct:Q", title="Allocation", format=".2%"),
            ],
            height=300,
        )
        chart_legend(
            list(
                zip(
                    portfolio_allocation["name"].tolist(),
                    donut_colors[: len(portfolio_allocation)],
                )
            )
        )
        st.caption(f"Total portfolio market value: {total_market_value:,.2f}")

    st.dataframe(
        overview[["name", "market_value", "allocation_pct", "horizon_range_label", "horizon_midpoint_years"]],
        width="stretch",
        hide_index=True,
        column_config={
            "name": "Portfolio",
            "market_value": st.column_config.NumberColumn("Market Value", format="%.2f"),
            "allocation_pct": st.column_config.NumberColumn("Allocation", format="%.2f%%"),
            "horizon_range_label": "Time Horizon",
            "horizon_midpoint_years": st.column_config.NumberColumn(
                "Midpoint (Years)",
                format="%.1f",
            ),
        },
        column_order=[
            "name",
            "market_value",
            "allocation_pct",
            "horizon_range_label",
            "horizon_midpoint_years",
        ],
    )

    st.subheader("Time Horizon Allocation")
    horizon_order = ["Short term", "Medium term", "Long term", "Unspecified"]
    horizon_labels = {
        "Short term": "Short term (<= 3y)",
        "Medium term": "Medium term (3-10y)",
        "Long term": "Long term (> 10y)",
        "Unspecified": "Unspecified",
    }
    horizon_overview = overview.copy()
    horizon_overview["bucket_label"] = horizon_overview["horizon_bucket"].map(horizon_labels)
    bucket_totals = (
        horizon_overview.groupby(["horizon_bucket", "bucket_label"], as_index=False)
        .agg(
            market_value=("market_value", "sum"),
            portfolio_count=("id", "count"),
        )
    )
    bucket_totals["bucket_order"] = bucket_totals["horizon_bucket"].map(
        {bucket: index for index, bucket in enumerate(horizon_order)}
    )
    bucket_totals = bucket_totals.sort_values("bucket_order").reset_index(drop=True)
    bucket_totals["value_label"] = bucket_totals["market_value"].map(lambda value: f"{value:,.2f}")

    if bucket_totals.empty or float(bucket_totals["market_value"].sum()) <= 0:
        st.info("No time horizon allocation data is available yet.")
    else:
        palette = {
            "Short term (<= 3y)": "#60a5fa",
            "Medium term (3-10y)": "#f59e0b",
            "Long term (> 10y)": "#22c55e",
            "Unspecified": "#94a3b8",
        }
        chart = alt.layer(
            alt.Chart(bucket_totals)
            .mark_bar(cornerRadiusEnd=6)
            .encode(
                y=alt.Y(
                    "bucket_label:N",
                    title="Time horizon bucket",
                    sort=bucket_totals["bucket_label"].tolist(),
                ),
                x=alt.X("market_value:Q", title="Market value"),
                color=alt.Color(
                    "bucket_label:N",
                    scale=alt.Scale(
                        domain=list(palette.keys()),
                        range=list(palette.values()),
                    ),
                    legend=None,
                ),
                tooltip=[
                    alt.Tooltip("bucket_label:N", title="Bucket"),
                    alt.Tooltip("market_value:Q", title="Market value", format=",.2f"),
                    alt.Tooltip("portfolio_count:Q", title="Portfolios"),
                ],
            ),
            alt.Chart(bucket_totals)
            .mark_text(
                dx=8,
                align="left",
                baseline="middle",
                fontWeight="bold",
                color="#f9fafb" if is_dark_theme() else "#111827",
            )
            .encode(
                y=alt.Y("bucket_label:N", sort=bucket_totals["bucket_label"].tolist()),
                x=alt.X("market_value:Q"),
                text="value_label:N",
            ),
        ).properties(height=320)
        st.altair_chart(chart, width="stretch")
        chart_legend(list(palette.items()))

    st.caption(
        "Time horizon buckets use each portfolio's horizon midpoint: (min years + max years) / 2."
    )
    st.dataframe(
        overview[
            [
                "name",
                "horizon_range_label",
                "horizon_midpoint_years",
                "horizon_bucket",
                "market_value",
            ]
        ],
        width="stretch",
        hide_index=True,
        column_config={
            "name": "Portfolio",
            "horizon_range_label": "Time Horizon",
            "horizon_midpoint_years": st.column_config.NumberColumn(
                "Midpoint (Years)",
                format="%.1f",
            ),
            "horizon_bucket": "Bucket",
            "market_value": st.column_config.NumberColumn("Market Value", format="%.2f"),
        },
        column_order=[
            "name",
            "horizon_range_label",
            "horizon_midpoint_years",
            "horizon_bucket",
            "market_value",
        ],
    )


def render_tax_advantaged_coverage(accounts: pd.DataFrame) -> None:
    if accounts.empty:
        st.info("No account balance data is available yet.")
        return

    balances = accounts.copy()
    balances["current_balance"] = pd.to_numeric(
        balances.get("current_balance"),
        errors="coerce",
    ).fillna(0)
    total_balance = float(balances["current_balance"].sum())
    if total_balance <= 0:
        st.info("No positive account balances found.")
        return

    protected_balance = float(
        balances[
            balances["account_type"].isin(REGISTERED_ACCOUNT_TYPES)
        ]["current_balance"].sum()
    )
    unprotected_balance = max(total_balance - protected_balance, 0.0)
    coverage_pct = protected_balance / total_balance if total_balance > 0 else 0.0
    chart_data = pd.DataFrame(
        [
            {"segment": "Protected", "value": protected_balance},
            {"segment": "Unprotected", "value": unprotected_balance},
        ]
    )
    palette = chart_palette()
    render_labeled_donut_chart(
        values=chart_data,
        category_field="segment",
        value_field="value",
        label_text=f"{coverage_pct:.0%}",
        color_range=[palette["target_growth"], "rgba(148, 163, 184, 0.28)"],
        tooltip=[
            alt.Tooltip("segment:N", title="Segment"),
            alt.Tooltip("value:Q", title="Balance", format=",.2f"),
        ],
        height=260,
    )
    col1, col2, col3 = st.columns(3)
    col1.metric("Protected balance", format_optional_number(protected_balance))
    col2.metric("Total account balance", format_optional_number(total_balance))
    col3.metric("Coverage", f"{coverage_pct:.2%}")

    by_wrapper = (
        balances[balances["account_type"].isin(REGISTERED_ACCOUNT_TYPES)]
        .groupby("account_type", as_index=False)["current_balance"]
        .sum()
    )
    if not by_wrapper.empty:
        by_wrapper["wrapper_label"] = by_wrapper["account_type"].apply(account_type_label)
        st.dataframe(
            by_wrapper,
            width="stretch",
            hide_index=True,
            column_config={
                "wrapper_label": "Registered account",
                "current_balance": st.column_config.NumberColumn(
                    "Protected balance",
                    format="%.2f",
                ),
            },
            column_order=["wrapper_label", "current_balance"],
        )


def render_return_vs_inflation_page(price_schema: str) -> None:
    try:
        inflation = load_canada_inflation(price_schema)
    except RuntimeError as error:
        st.error(str(error))
        return

    st.subheader("Canada Inflation")
    st.caption(
        "The chart itself is not implemented yet. Public mode stays read-only and displays the saved Canada inflation rows that will feed the future return-vs-inflation view."
    )

    latest_row = inflation.iloc[0] if not inflation.empty else None
    metric_cols = st.columns(3)
    metric_cols[0].metric(
        "Latest inflation rate",
        (
            f"{float(latest_row['inflation_rate']):.2f}%"
            if latest_row is not None and pd.notna(latest_row.get("inflation_rate"))
            else "Not set"
        ),
    )
    metric_cols[1].metric(
        "Latest observation month",
        (
            pd.to_datetime(latest_row["observation_month"]).strftime("%Y-%m")
            if latest_row is not None and pd.notna(latest_row.get("observation_month"))
            else "Not set"
        ),
    )
    metric_cols[2].metric("Rows stored", f"{len(inflation):,}")

    if inflation.empty:
        st.info("No Canada inflation rows have been entered yet.")
        return

    st.info("Return-vs-inflation chart is not implemented yet. The inflation data layer is ready.")
    display = inflation.copy()
    display["observation_month_label"] = display["observation_month"].dt.strftime("%Y-%m")
    st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        column_config={
            "observation_month_label": "Observation Month",
            "inflation_rate": st.column_config.NumberColumn(
                "Inflation Rate",
                format="%.2f%%",
            ),
            "source": "Source",
            "notes": "Notes",
            "updated_at": st.column_config.DatetimeColumn("Updated At"),
        },
        column_order=[
            "observation_month_label",
            "inflation_rate",
            "source",
            "notes",
            "updated_at",
        ],
    )


def render_registered_room_card(status_row: pd.Series) -> None:
    wrapper_label = account_type_label(status_row.get("wrapper_type"))
    total_room_raw = pd.to_numeric(status_row.get("total_room"), errors="coerce")
    used_room_raw = pd.to_numeric(status_row.get("used_room"), errors="coerce")
    total_room = 0.0 if pd.isna(total_room_raw) else float(total_room_raw)
    used_room = 0.0 if pd.isna(used_room_raw) else float(used_room_raw)
    remaining_room = max(total_room - used_room, 0.0)
    overused_room = max(used_room - total_room, 0.0)
    chart_used = min(used_room, total_room) if total_room > 0 else 0.0
    chart_remaining = max(total_room - chart_used, 0.0)
    palette = chart_palette()

    st.subheader(f"{wrapper_label} Room")
    if total_room > 0:
        render_labeled_donut_chart(
            values=pd.DataFrame(
                [
                    {"segment": "Used", "value": chart_used},
                    {"segment": "Remaining", "value": chart_remaining},
                ]
            ),
            category_field="segment",
            value_field="value",
            label_text=f"{(used_room / total_room):.0%}",
            color_range=[palette["actual"], "rgba(148, 163, 184, 0.28)"],
            tooltip=[
                alt.Tooltip("segment:N", title="Segment"),
                alt.Tooltip("value:Q", title="Room", format=",.2f"),
            ],
            height=240,
        )
    else:
        st.info("No total room value has been set yet.")

    col1, col2 = st.columns(2)
    col1.metric("Used room", format_optional_number(used_room))
    col2.metric("Remaining room", format_optional_number(remaining_room))
    col3, col4 = st.columns(2)
    col3.metric("Total room", format_optional_number(total_room))
    col4.metric("Protected balance", format_optional_number(status_row.get("protected_balance")))
    if overused_room > 0:
        st.warning(f"{wrapper_label} is over room by {overused_room:,.2f}.")
    notes = status_row.get("notes")
    if notes is not None and not pd.isna(notes) and str(notes).strip():
        st.caption(str(notes).strip())


def render_tax_benefit_details(
    accounts: pd.DataFrame,
    room_status: pd.DataFrame,
) -> None:
    st.subheader("Tax Advantaged Coverage")
    render_tax_advantaged_coverage(accounts)

    status_by_wrapper = {
        str(row["wrapper_type"]): row for _, row in room_status.iterrows()
    } if not room_status.empty else {}

    wrapper_cols = st.columns(len(REGISTERED_ACCOUNT_TYPES))
    for column, wrapper_type in zip(wrapper_cols, REGISTERED_ACCOUNT_TYPES):
        with column:
            row = status_by_wrapper.get(wrapper_type)
            if row is None:
                row = pd.Series(
                    {
                        "wrapper_type": wrapper_type,
                        "total_room": 0,
                        "used_room": 0,
                        "remaining_room": 0,
                        "protected_balance": 0,
                    }
                )
            render_registered_room_card(row)


def render_holdings_principal_vs_growth(
    holding_values: pd.DataFrame,
    transactions: pd.DataFrame | None = None,
) -> None:
    overview = active_holdings_overview_rows(holding_values, transactions)
    if overview.empty:
        st.info("No active holdings found for principal vs growth.")
        return

    palette = chart_palette()

    view_mode = st.radio(
        "View Mode",
        ["View by Portfolio", "View by Asset Type"],
        horizontal=True,
        key="holdings_principal_growth_view_mode",
    )

    overview["portfolio_filter_label"] = overview["portfolio_name"].fillna(
        "Unknown portfolio"
    ).astype(str)
    overview["asset_type_filter_label"] = overview["asset_type"].apply(asset_type_label)
    overview["display_name"] = overview.apply(holdings_display_name, axis=1)

    filter_col, _ = st.columns([1, 2.2])
    if view_mode == "View by Portfolio":
        selected_portfolio = filter_col.selectbox(
            "Filter",
            sorted(overview["portfolio_filter_label"].unique().tolist()),
            key="holdings_principal_growth_portfolio",
        )
        overview = overview[
            overview["portfolio_filter_label"] == selected_portfolio
        ].copy()
    else:
        selected_asset_type = filter_col.selectbox(
            "Filter",
            sorted(overview["asset_type_filter_label"].unique().tolist()),
            key="holdings_principal_growth_asset_type",
        )
        overview = overview[
            overview["asset_type_filter_label"] == selected_asset_type
        ].copy()

    if overview.empty:
        st.info("No holdings matched the selected filter.")
        return

    overview["holding_axis_label"] = overview.apply(
        lambda row: principal_growth_axis_name(row, view_mode),
        axis=1,
    )

    chart_rows = pd.DataFrame(
        [
            {
                "holding_axis_label": row["holding_axis_label"],
                "holding_label": row["holding_label"],
                "portfolio_name": row["portfolio_filter_label"],
                "asset_type_label": row["asset_type_filter_label"],
                "component": "Principal Value",
                "value": row["principal_value"],
                "value_label": f"{row['principal_value']:,.2f}",
            }
            for _, row in overview.iterrows()
        ]
        + [
            {
                "holding_axis_label": row["holding_axis_label"],
                "holding_label": row["holding_label"],
                "portfolio_name": row["portfolio_filter_label"],
                "asset_type_label": row["asset_type_filter_label"],
                "component": "Growth Value",
                "value": row["growth_value"],
                "value_label": f"{row['growth_value']:,.2f}",
            }
            for _, row in overview.iterrows()
        ]
    )
    chart_rows = chart_rows[chart_rows["value"] != 0].copy()
    if chart_rows.empty:
        st.info("No principal or growth values found for active holdings.")
        return

    label_threshold = max(float(overview["current_value"].abs().max()) * 0.08, 250.0)
    principal_inside_rows: list[dict[str, Any]] = []
    principal_outside_rows: list[dict[str, Any]] = []
    growth_inside_rows: list[dict[str, Any]] = []
    growth_outside_rows: list[dict[str, Any]] = []
    for _, row in overview.iterrows():
        axis_label = row["holding_axis_label"]
        principal_value = float(row["principal_value"])
        growth_value = float(row["growth_value"])

        if principal_value != 0:
            principal_inside = abs(principal_value) >= label_threshold
            target_rows = principal_inside_rows if principal_inside else principal_outside_rows
            target_rows.append(
                {
                    "holding_axis_label": axis_label,
                    "text": f"{principal_value:,.2f}",
                    "x": principal_value / 2 if principal_inside else principal_value,
                }
            )

        if growth_value != 0 and round(growth_value, 2) != 0:
            if growth_value > 0:
                growth_inside = abs(growth_value) >= label_threshold
                growth_end = principal_value + growth_value
                (growth_inside_rows if growth_inside else growth_outside_rows).append(
                    {
                        "holding_axis_label": axis_label,
                        "text": f"{growth_value:,.2f}",
                        "x": principal_value + (growth_value / 2) if growth_inside else growth_end,
                        "is_negative": False,
                    }
                )
            else:
                growth_inside = abs(growth_value) >= label_threshold
                (growth_inside_rows if growth_inside else growth_outside_rows).append(
                    {
                        "holding_axis_label": axis_label,
                        "text": f"{growth_value:,.2f}",
                        "x": growth_value / 2 if growth_inside else growth_value,
                        "is_negative": True,
                    }
                )

    bar_chart = (
        alt.Chart(chart_rows)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            y=alt.Y(
                "holding_axis_label:N",
                title="Holding",
                sort=overview["holding_axis_label"].tolist(),
            ),
            x=alt.X("value:Q", title="Amount"),
            color=alt.Color(
                "component:N",
                scale=alt.Scale(
                    domain=["Principal Value", "Growth Value"],
                    range=[palette["actual"], palette["target_growth"]],
                ),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("holding_axis_label:N", title="Name"),
                alt.Tooltip("portfolio_name:N", title="Portfolio"),
                alt.Tooltip("asset_type_label:N", title="Asset type"),
                alt.Tooltip("holding_label:N", title="Holding detail"),
                alt.Tooltip("component:N", title="Component"),
                alt.Tooltip("value:Q", title="Amount", format=",.2f"),
            ],
        )
    )
    label_layers: list[Any] = []
    if principal_inside_rows:
        label_layers.append(
            alt.Chart(pd.DataFrame(principal_inside_rows))
            .mark_text(fontSize=11, fontWeight="bold", color="#f9fafb", align="center")
            .encode(
                y=alt.Y("holding_axis_label:N", sort=overview["holding_axis_label"].tolist()),
                x=alt.X("x:Q"),
                text="text:N",
            )
        )
    if principal_outside_rows:
        label_layers.append(
            alt.Chart(pd.DataFrame(principal_outside_rows))
            .mark_text(fontSize=11, fontWeight="bold", color="#f9fafb", align="left", dx=8)
            .encode(
                y=alt.Y("holding_axis_label:N", sort=overview["holding_axis_label"].tolist()),
                x=alt.X("x:Q"),
                text="text:N",
            )
        )
    if growth_inside_rows:
        label_layers.append(
            alt.Chart(pd.DataFrame(growth_inside_rows))
            .mark_text(fontSize=11, fontWeight="bold", color="#f9fafb", align="center")
            .encode(
                y=alt.Y("holding_axis_label:N", sort=overview["holding_axis_label"].tolist()),
                x=alt.X("x:Q"),
                text="text:N",
            )
        )
    if growth_outside_rows:
        outside_growth = pd.DataFrame(growth_outside_rows)
        positive_growth = outside_growth[~outside_growth["is_negative"]]
        negative_growth = outside_growth[outside_growth["is_negative"]]
        if not positive_growth.empty:
            label_layers.append(
                alt.Chart(positive_growth)
                .mark_text(
                    fontSize=11,
                    fontWeight="bold",
                    color=palette["target_growth"],
                    align="left",
                    dx=8,
                )
                .encode(
                    y=alt.Y("holding_axis_label:N", sort=overview["holding_axis_label"].tolist()),
                    x=alt.X("x:Q"),
                    text="text:N",
                )
            )
        if not negative_growth.empty:
            label_layers.append(
                alt.Chart(negative_growth)
                .mark_text(
                    fontSize=11,
                    fontWeight="bold",
                    color=palette["target_growth"],
                    align="right",
                    dx=-8,
                )
                .encode(
                    y=alt.Y("holding_axis_label:N", sort=overview["holding_axis_label"].tolist()),
                    x=alt.X("x:Q"),
                    text="text:N",
                )
            )
    chart = bar_chart
    for layer in label_layers:
        chart = chart + layer
    st.altair_chart(
        chart.properties(height=max(320, 44 * len(overview))),
        width="stretch",
    )
    chart_legend(
        [
            ("Principal Value", palette["actual"]),
            ("Growth Value", palette["target_growth"]),
        ]
    )


def render_holdings_expected_return_rate(holding_values: pd.DataFrame) -> None:
    overview = active_holdings_overview_rows(holding_values)
    if overview.empty:
        st.info("No active holdings found for expected return rate.")
        return

    comparison = overview[["holding_label", "expected_return_rate"]].copy()
    comparison = comparison.dropna(subset=["expected_return_rate"])
    if comparison.empty:
        st.info("No expected return rates have been set for active holdings.")
        return

    comparison = comparison.sort_values(
        "expected_return_rate",
        ascending=False,
        na_position="last",
    ).reset_index(drop=True)
    st.dataframe(
        comparison,
        width="stretch",
        hide_index=True,
        column_config={
            "holding_label": "Holding",
            "expected_return_rate": st.column_config.NumberColumn(
                "Expected Return Rate",
                format="%.2f%%",
            ),
        },
        column_order=["holding_label", "expected_return_rate"],
    )


def render_global_investment_triangle(portfolio_schema: str) -> None:
    try:
        holding_values = load_holding_current_values(portfolio_schema)
    except RuntimeError as error:
        st.error(str(error))
        return

    active_holdings = active_detail_rows(holding_values)
    if active_holdings.empty:
        st.info("No active holdings found for investment triangle.")
        return

    active_holdings = add_allocation_value(active_holdings)
    active_holdings = active_holdings[active_holdings["allocation_value"] > 0].copy()
    if active_holdings.empty:
        st.info("No positive holding allocation values found across portfolios.")
        return

    score_columns = ["risk_score", "liquidity_score", "return_score"]
    for column in [*score_columns, "allocation_value", "current_value"]:
        if column not in active_holdings:
            active_holdings[column] = pd.NA
        active_holdings[column] = pd.to_numeric(
            active_holdings[column],
            errors="coerce",
        )

    weighted_scores = investment_triangle_weighted_scores(active_holdings)
    total_value = float(active_holdings["allocation_value"].sum())
    scored_value = float(
        active_holdings[
            active_holdings[score_columns].notna().any(axis=1)
        ]["allocation_value"].sum()
    )

    metric_cols = st.columns(4)
    metric_cols[0].metric("Current total value", f"{total_value:,.2f}")
    metric_cols[1].metric(
        "Weighted risk",
        f"{float(weighted_scores.loc[weighted_scores['axis'] == 'Risk', 'score'].iloc[0]):.1f}",
    )
    metric_cols[2].metric(
        "Weighted liquidity",
        f"{float(weighted_scores.loc[weighted_scores['axis'] == 'Liquidity', 'score'].iloc[0]):.1f}",
    )
    metric_cols[3].metric(
        "Weighted return",
        f"{float(weighted_scores.loc[weighted_scores['axis'] == 'Return', 'score'].iloc[0]):.1f}",
    )

    components.html(svg_triangle_radar(weighted_scores), height=430, scrolling=False)
    st.caption(
        "Scores are weighted by current holding value across all active holdings. Missing scores are excluded from that dimension's weighted average."
    )
    st.caption(
        f"Scored current value coverage: {scored_value:,.2f} of {total_value:,.2f} current value."
    )

    distribution_specs = [
        ("return_score", "Return"),
        ("liquidity_score", "Liquidity"),
        ("risk_score", "Risk"),
    ]
    for score_column, label in distribution_specs:
        st.subheader(f"{label} Allocation")
        distribution = investment_triangle_distribution(
            active_holdings,
            score_column,
            label,
        )
        chart = (
            alt.Chart(distribution)
            .mark_bar()
            .encode(
                x=alt.X("bucket:O", title=f"{label} score bucket"),
                y=alt.Y("allocation_value:Q", title="Current value"),
                tooltip=[
                    alt.Tooltip("bucket:O", title="Score bucket"),
                    alt.Tooltip("allocation_value:Q", title="Current value", format=",.2f"),
                ],
            )
            .properties(height=260)
        )
        st.altair_chart(chart, width="stretch")

        detail_rows = active_holdings[active_holdings[score_column].notna()].copy()
        if detail_rows.empty:
            st.info(f"No holdings have a {label.lower()} score yet.")
            continue

        detail_rows["bucket"] = detail_rows[score_column].round().clip(0, 10).astype(int)
        detail_rows["holding_label"] = detail_rows.apply(
            lambda row: (
                str(row.get("portfolio_name")).strip()
                if pd.notna(row.get("portfolio_name")) and str(row.get("portfolio_name")).strip()
                else "Unknown portfolio"
            )
            + " - "
            + (
                str(row.get("asset_name")).strip()
                if pd.notna(row.get("asset_name")) and str(row.get("asset_name")).strip()
                else f"Holding {int(row['id'])}"
            )
            + (
                f" - {str(row.get('holding_name')).strip()}"
                if pd.notna(row.get("holding_name")) and str(row.get("holding_name")).strip()
                else ""
            ),
            axis=1,
        )
        st.dataframe(
            detail_rows[
                [
                    "holding_label",
                    "asset_type",
                    score_column,
                    "bucket",
                    "allocation_value",
                ]
            ].sort_values(["bucket", "allocation_value"], ascending=[False, False]),
            width="stretch",
            hide_index=True,
            column_config={
                "holding_label": "Holding",
                "asset_type": "Asset type",
                score_column: st.column_config.NumberColumn(
                    f"{label} score",
                    format="%.1f",
                ),
                "bucket": st.column_config.NumberColumn("Score bucket", format="%d"),
                "allocation_value": st.column_config.NumberColumn(
                    "Current value",
                    format="%.2f",
                ),
            },
        )


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
        "Total gain",
        f"{summary['total_gain']:,.2f}" if summary["total_gain"] is not None else "Not set",
        f"{summary['gain_rate']:.2%}" if summary["gain_rate"] is not None else None,
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

    render_total_gain_rate_donut(summary["gain_rate"])
    render_cash_yield_chart(yields)
    render_average_volume_chart("CASH.TO", prices)
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
        holdings = load_holdings(portfolio_schema, symbol)
        transactions = load_transactions(portfolio_schema, symbol)
    except RuntimeError as error:
        st.error(str(error))
        st.stop()

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

    average_cost, total_quantity = holding_summary(holdings)

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

    render_total_gain_rate_donut(total_return_pct)
    render_price_vs_cost_chart(display_prices, average_cost, transactions, prices)
    render_average_volume_chart(symbol, display_prices)
    render_position_value_chart(display_prices, transactions, target_cagr)
    render_position_total_value_chart(display_prices, transactions, target_cagr)

    if not transactions.empty:
        st.subheader("Transaction History")
        st.dataframe(transactions, width="stretch", hide_index=True)
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

    controls_col, _ = st.columns([1, 2])
    with controls_col:
        symbol = st.selectbox("Symbol", symbols)
        history_window_label = st.selectbox(
            "History window",
            list(HISTORY_WINDOW_OPTIONS.keys()),
            index=list(HISTORY_WINDOW_OPTIONS.keys()).index("180 Days"),
            key="watchlist_history_window",
        )
    metadata = tracked[tracked["symbol"] == symbol].iloc[0]

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
    render_average_volume_chart(symbol, display_prices)


def render_placeholder_section(
    section: str,
    price_schema: str | None = None,
    portfolio_schema: str | None = None,
) -> None:
    subpages = SECTION_SUBPAGES[section]
    for tab, subpage in zip(st.tabs(subpages), subpages):
        with tab:
            render_section_subpage(section, subpage, price_schema, portfolio_schema)


def render_section_subpage(
    section: str,
    subpage: str,
    price_schema: str | None = None,
    portfolio_schema: str | None = None,
) -> None:
    if section == SECTION_RESEARCH and subpage == "Comparison":
        if price_schema is None:
            st.info("Price schema is not configured.")
            return
        render_research_comparison_page(price_schema)
        return

    if section == SECTION_RESEARCH and subpage == "Watchlist":
        if price_schema is None:
            st.info("Price schema is not configured.")
            return
        render_market_research_page(price_schema)
        return

    if section == SECTION_OVERVIEW and subpage == "Investment Triangle":
        if portfolio_schema is None:
            st.info("Portfolio schema is not configured.")
            return
        st.subheader(f"{section} - Investment Triangle")
        render_global_investment_triangle(portfolio_schema)
        return

    if section == SECTION_OVERVIEW and subpage == "Return vs Inflation":
        if price_schema is None:
            st.info("Price schema is not configured.")
            return
        st.subheader(f"{section} - Return vs Inflation")
        render_return_vs_inflation_page(price_schema)
        return

    if subpage == "Investment Triangle":
        render_investment_triangle_placeholder(section)
        return

    if section == SECTION_OVERVIEW and subpage == "Portfolio Overview":
        if portfolio_schema is None:
            st.info("Portfolio schema is not configured.")
            return
        st.subheader(f"{section} - Portfolio Overview")
        render_global_portfolio_overview(portfolio_schema)
        return

    if section == SECTION_ACCOUNTS_TAX and subpage == "Account Details":
        if portfolio_schema is None:
            st.info("Portfolio schema is not configured.")
            return
        try:
            accounts = load_accounts(portfolio_schema)
        except RuntimeError as error:
            st.error(str(error))
            return

        st.subheader("Account Allocation")
        render_account_allocation(accounts)

        st.subheader("Account Balances")
        render_account_balance_chart(accounts)
        return

    if section == SECTION_ACCOUNTS_TAX and subpage == "Tax Benefit Details":
        if portfolio_schema is None:
            st.info("Portfolio schema is not configured.")
            return
        try:
            accounts = load_accounts(portfolio_schema)
            room_status = load_registered_account_room_status(portfolio_schema)
        except RuntimeError as error:
            st.error(str(error))
            return

        render_tax_benefit_details(accounts, room_status)
        return

    st.subheader(subpage)
    st.info("Placeholder. This dashboard section is ready for future data and charts.")


def render_investment_triangle_placeholder(context: str) -> None:
    st.subheader(f"{context} - Investment Triangle")
    st.info("Placeholder. Radar chart for return, liquidity, and risk.")

    st.subheader("Yield Rate / Return Rate Allocation")
    st.info("Placeholder. This section is ready for return and yield allocation data.")

    st.subheader("Liquidity Allocation")
    st.info("Placeholder. This section is ready for liquidity allocation data.")

    st.subheader("Risk Allocation")
    st.info("Placeholder. This section is ready for risk allocation data.")


def render_simple_placeholder_page(page: str) -> None:
    if page == SECTION_ASSETS:
        details_tab = st.tabs(["Details"])[0]
        with details_tab:
            st.subheader("Asset Type Allocation")
            st.info("Placeholder. This section is ready for asset type allocation data.")

            st.subheader("Asset Details")
            st.info("Placeholder. This section is ready for asset detail data.")
        return

    st.subheader(page)
    st.info("Placeholder. This dashboard page is ready for future data and charts.")


def render_portfolio_placeholder_page(portfolio: pd.Series) -> None:
    portfolio_page = str(portfolio["name"])
    render_portfolio_metadata_summary(portfolio)

    for tab, subpage in zip(st.tabs(PORTFOLIO_SUBPAGES), PORTFOLIO_SUBPAGES):
        with tab:
            if subpage == "Investment Triangle":
                render_investment_triangle_placeholder(portfolio_page)
                continue

            st.subheader(f"{portfolio_page} - {subpage}")
            st.info("Placeholder. This portfolio page is ready for future data and charts.")


def render_holdings_section(
    price_schema: str,
    portfolio_schema: str,
    assets: pd.DataFrame,
) -> None:
    try:
        holding_values = load_holding_current_values(portfolio_schema)
        holding_transactions = load_holding_transactions_current(portfolio_schema)
    except RuntimeError as error:
        st.error(str(error))
        st.stop()

    principal_growth_tab, yield_rate_tab, details_tab = st.tabs(
        ["Principal vs Growth", "Expected Return Rate", "Details"]
    )

    with principal_growth_tab:
        st.subheader("Principal vs Growth")
        render_holdings_principal_vs_growth(holding_values, holding_transactions)

    with yield_rate_tab:
        st.subheader("Expected Return Rate")
        render_holdings_expected_return_rate(holding_values)

    try:
        all_holdings = load_holdings(portfolio_schema)
    except RuntimeError as error:
        st.error(str(error))
        st.stop()

    holding_symbols = holding_symbol_options(all_holdings)
    if not holding_symbols:
        st.info("No transaction history found yet.")
        st.stop()

    with details_tab:
        controls_col, _ = st.columns([1, 2])
        with controls_col:
            selected_symbol = st.selectbox(
                "Holding",
                holding_symbols,
                index=(
                    holding_symbols.index(DEFAULT_SYMBOL)
                    if DEFAULT_SYMBOL in holding_symbols
                    else 0
                ),
                key="holdings_detail_symbol",
            )
            if not selected_symbol:
                st.stop()

            history_window_label = st.selectbox(
                "History window",
                list(HISTORY_WINDOW_OPTIONS.keys()),
                index=list(HISTORY_WINDOW_OPTIONS.keys()).index("180 Days"),
                key="holdings_detail_history_window",
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
                    key="holdings_detail_target_cagr",
                )
            show_rows = st.checkbox(
                "Show raw rows",
                value=False,
                key="holdings_detail_show_rows",
            )

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
    price_schema = get_setting("SUPABASE_PRICE_SCHEMA", DEFAULT_PRICE_SCHEMA)
    portfolio_schema = get_setting(
        "SUPABASE_PORTFOLIO_SCHEMA", DEFAULT_PORTFOLIO_SCHEMA
    )

    try:
        visible_portfolios = load_portfolios(portfolio_schema)
        portfolio_pages = portfolio_page_options(visible_portfolios)
    except RuntimeError as error:
        st.error(str(error))
        st.stop()

    section = sidebar(portfolio_pages)
    st.title(section)

    if section in SECTION_SUBPAGES:
        render_placeholder_section(section, price_schema, portfolio_schema)
        return

    if section in portfolio_pages:
        selected_portfolio = portfolio_metadata_by_name(visible_portfolios, section)
        if selected_portfolio is None:
            st.warning("Portfolio is no longer available.")
            st.stop()
        render_portfolio_placeholder_page(selected_portfolio)
        return

    if section == SECTION_ASSETS:
        render_simple_placeholder_page(section)
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
