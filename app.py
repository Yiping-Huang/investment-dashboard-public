"""Read-only Streamlit dashboard for public deployment exports."""

from __future__ import annotations

import os
from html import escape
from datetime import date, timedelta
from typing import Any

import altair as alt
import pandas as pd
import requests
import streamlit as st


DEFAULT_PRICE_SCHEMA = "market"
DEFAULT_PORTFOLIO_SCHEMA = "portfolio"
DEFAULT_SYMBOL = "VFV.TO"
DEFAULT_TARGET_CAGR = 0.10
COMFORT_ZONE_MULTIPLIER = 0.10
PREFERRED_HOLDING_SYMBOLS = [DEFAULT_SYMBOL, "CASH.TO", "QQQ"]
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


def sidebar() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] div.stButton > button {
            justify-content: flex-start;
            text-align: left;
        }
        [data-testid="stSidebar"] div.stButton > button:disabled {
            opacity: 1;
        }
        .st-key-sidebar_auth_footer {
            position: fixed;
            bottom: 1rem;
            left: 1rem;
            width: 16rem;
            max-width: calc(100vw - 2rem);
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
        st.header("Dashboard")
        st.button("Holdings", disabled=True, width="stretch", type="primary")
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


def load_transactions(portfolio_schema: str, symbol: str) -> pd.DataFrame:
    access_token = supabase_auth_token()
    if not access_token:
        raise RuntimeError("Sign in before reading portfolio data.")

    rows = fetch_table(
        portfolio_schema,
        "transactions",
        (
            ("select", "id,symbol,account_id,transaction_date,transaction_type,quantity,price,fees,currency,notes,created_at"),
            ("symbol", f"eq.{symbol}"),
            ("order", "transaction_date.desc"),
        ),
        access_token,
    )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    for column in ["quantity", "price", "fees"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["transaction_date"] = pd.to_datetime(frame["transaction_date"])
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


def chart_palette() -> dict[str, str]:
    try:
        theme_type = st.context.theme.get("type")
    except Exception:
        theme_type = None
    is_dark = (theme_type or st.get_option("theme.base")) != "light"
    if is_dark:
        return {
            "actual": "#60a5fa",
            "average_cost": "#f87171",
            "target_growth": "#22c55e",
            "comfort_area": "#64748b",
            "comfort_label": "#cbd5e1",
        }
    return {
        "actual": "#2563eb",
        "average_cost": "#dc2626",
        "target_growth": "#16a34a",
        "comfort_area": "#64748b",
        "comfort_label": "#111827",
    }


def chart_label_dates(prices: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    end_date = prices["price_date"].max()
    label_offset_days = max(
        1,
        int((prices["price_date"].max() - prices["price_date"].min()).days * 0.02),
    )
    return end_date, end_date + pd.Timedelta(days=label_offset_days)


def render_position_value_chart(
    prices: pd.DataFrame,
    transactions: pd.DataFrame,
    target_cagr: float,
) -> None:
    position_data = position_value_data(prices, transactions, target_cagr)
    if position_data.empty:
        return

    palette = chart_palette()
    _, label_date = chart_label_dates(prices)
    latest = position_data.iloc[-1]
    target_growth_label = f"Target Growth ({target_cagr:.1%} CAGR)"
    labels = pd.DataFrame(
        [
            {
                "Date": label_date,
                "Value": latest["Actual Growth"],
                "Label": "Actual Growth",
            },
            {
                "Date": label_date,
                "Value": latest["Target Growth"],
                "Label": target_growth_label,
            },
            {
                "Date": label_date,
                "Value": latest["Comfort Zone High Growth"],
                "Label": "Comfort Zone +10%",
            },
            {
                "Date": label_date,
                "Value": latest["Comfort Zone Low Growth"],
                "Label": "Comfort Zone -10%",
            },
        ]
    )
    chart = alt.layer(
        alt.Chart(position_data)
        .mark_area(color=palette["comfort_area"], opacity=0.13)
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
        alt.Chart(labels)
        .mark_text(align="left", baseline="middle", dx=6, fontSize=12)
        .encode(
            x=alt.X("Date:T", title="Date"),
            y=alt.Y("Value:Q", title="Growth (CAD)", scale=alt.Scale(zero=False)),
            text="Label:N",
            color=alt.Color(
                "Label:N",
                scale=alt.Scale(
                    domain=[
                        "Actual Growth",
                        target_growth_label,
                        "Comfort Zone +10%",
                        "Comfort Zone -10%",
                    ],
                    range=[
                        palette["actual"],
                        palette["target_growth"],
                        palette["comfort_label"],
                        palette["comfort_label"],
                    ],
                ),
                legend=None,
            ),
        ),
    ).resolve_scale(y="shared").properties(height=420)

    st.subheader("My VFV Growth")
    st.altair_chart(chart, width="stretch")


def render_price_vs_cost_chart(
    prices: pd.DataFrame,
    average_cost: float | None,
    transactions: pd.DataFrame,
) -> None:
    palette = chart_palette()
    chart_data = prices[["price_date", "close"]].rename(
        columns={"price_date": "Date", "close": "Price"}
    )
    _, label_date = chart_label_dates(prices)
    latest_price = chart_data.iloc[-1]["Price"]
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
    price_label = pd.DataFrame(
        {
            "Date": [label_date],
            "Price": [latest_price],
            "Label": ["Market Price"],
        }
    )
    layers.append(
        alt.Chart(price_label)
        .mark_text(
            align="left",
            baseline="middle",
            dx=6,
            fontSize=12,
            color=palette["actual"],
        )
        .encode(
            x=alt.X("Date:T", title="Date"),
            y=alt.Y("Price:Q", title="Price (CAD)", scale=alt.Scale(zero=False)),
            text="Label:N",
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
                "Date": [label_date],
                "Average Cost Basis": [average_cost],
                "Label": ["Average Cost Basis"],
            }
        )
        layers.append(
            alt.Chart(cost_label)
            .mark_text(
                align="left",
                baseline="middle",
                dx=6,
                fontSize=12,
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

    st.subheader("VFV Price vs Cost Basis")
    st.altair_chart(
        alt.layer(*layers).resolve_scale(y="shared").properties(height=420),
        width="stretch",
    )


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
    start_date = (
        date(1900, 1, 1)
        if lookback_days is None
        else date.today() - timedelta(days=lookback_days)
    )

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

    render_position_value_chart(prices, transactions, target_cagr)
    render_price_vs_cost_chart(prices, average_cost, transactions)

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
        st.dataframe(prices, width="stretch", hide_index=True)


def main() -> None:
    st.set_page_config(
        page_title="Investment Dashboard",
        page_icon="",
        layout="wide",
    )
    require_supabase_auth()
    sidebar()

    st.title("Investment Dashboard")
    price_schema = get_setting("SUPABASE_PRICE_SCHEMA", DEFAULT_PRICE_SCHEMA)
    portfolio_schema = get_setting(
        "SUPABASE_PORTFOLIO_SCHEMA", DEFAULT_PORTFOLIO_SCHEMA
    )

    try:
        assets = load_assets(price_schema)
    except RuntimeError as error:
        st.error(str(error))
        st.stop()

    if assets.empty:
        st.warning("No assets found in Supabase.")
        st.stop()

    st.subheader("Holdings")
    holding_symbols = holding_symbol_options(assets)
    if not holding_symbols:
        st.warning("No assets found in Supabase.")
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
        target_cagr_pct = st.number_input(
            "Target CAGR",
            min_value=-50.0,
            max_value=50.0,
            value=DEFAULT_TARGET_CAGR * 100,
            step=0.5,
            format="%.1f",
        )
        show_rows = st.checkbox("Show raw rows", value=False)

    render_asset_page(
        price_schema,
        portfolio_schema,
        assets,
        HISTORY_WINDOW_OPTIONS[history_window_label],
        target_cagr_pct / 100,
        show_rows,
        selected_symbol,
    )


if __name__ == "__main__":
    main()
