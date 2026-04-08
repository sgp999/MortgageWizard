from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse

app = FastAPI(title="MORTGAGE-WIZARD")


STATE_RATES = {
    "OH": {"30": 6.55, "15": 5.96},
    "PA": {"30": 6.50, "15": 5.90},
    "NY": {"30": 6.60, "15": 6.00},
    "CA": {"30": 6.62, "15": 5.99},
    "FL": {"30": 6.58, "15": 5.95},
    "TX": {"30": 6.57, "15": 5.94},
    "HI": {"30": 6.40, "15": 5.80},
}

STATE_TAX_RATES = {
    "OH": 0.015,
    "PA": 0.014,
    "NY": 0.017,
    "CA": 0.012,
    "FL": 0.011,
    "TX": 0.018,
    "HI": 0.003,
}

STATE_INSURANCE_RATES = {
    "OH": 0.0040,
    "PA": 0.0042,
    "NY": 0.0045,
    "CA": 0.0048,
    "FL": 0.0075,
    "TX": 0.0060,
    "HI": 0.0035,
}


def zip_to_state(zip_code: str) -> str:
    zip_code = zip_code.strip()

    if len(zip_code) != 5 or not zip_code.isdigit():
        raise HTTPException(status_code=400, detail="Invalid ZIP code")

    first_three = int(zip_code[:3])
    first_two = int(zip_code[:2])

    if 967 <= first_three <= 968:
        return "HI"
    if 43 <= first_two <= 45:
        return "OH"
    if 15 <= first_two <= 19:
        return "PA"
    if 10 <= first_two <= 14:
        return "NY"
    if 90 <= first_two <= 96:
        return "CA"
    if 32 <= first_two <= 34:
        return "FL"
    if 75 <= first_two <= 79:
        return "TX"

    return "OH"


def calculate_monthly_payment(loan_amount: float, annual_rate: float, years: int) -> float:
    monthly_rate = annual_rate / 100 / 12
    total_payments = years * 12

    if monthly_rate == 0:
        return loan_amount / total_payments

    return loan_amount * (
        monthly_rate * (1 + monthly_rate) ** total_payments
    ) / (
        (1 + monthly_rate) ** total_payments - 1
    )


@app.get("/", response_class=HTMLResponse)
def home(
    zip_code: str = "",
    home_price: float = 0,
    down_payment: float = 0,
    mortgage_rate: float = 0,
    loan_term: int = 30,
):
    home_price_value = "" if home_price == 0 else str(home_price)
    down_payment_value = "" if down_payment == 0 else str(down_payment)
    mortgage_rate_value = "" if mortgage_rate == 0 else str(mortgage_rate)

    return f"""
    <html>
        <head>
            <title>MORTGAGE-WIZARD</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    max-width: 900px;
                    margin: 40px auto;
                    padding: 20px;
                    background: #f4f7fb;
                    color: #1f2937;
                }}
                .card {{
                    background: white;
                    border-radius: 14px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.08);
                    padding: 28px;
                }}
                h1 {{
                    margin-top: 0;
                    color: #1d4ed8;
                }}
                label {{
                    font-weight: 600;
                    display: block;
                    margin-bottom: 6px;
                }}
                input, select {{
                    width: 100%;
                    padding: 10px 12px;
                    border: 1px solid #d1d5db;
                    border-radius: 8px;
                    box-sizing: border-box;
                    margin-bottom: 18px;
                }}
                .row {{
                    display: flex;
                    gap: 20px;
                }}
                .col {{
                    flex: 1;
                }}
                button {{
                    background: #2563eb;
                    color: white;
                    border: none;
                    padding: 12px 18px;
                    border-radius: 8px;
                    font-size: 16px;
                    cursor: pointer;
                }}
                button:hover {{
                    background: #1d4ed8;
                }}
                .small {{
                    color: #6b7280;
                    font-size: 14px;
                }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1>MORTGAGE-WIZARD</h1>
                <p class="small">Enter your ZIP code and compare estimated 15-year and 30-year mortgage costs.</p>

                <form action="/calculate" method="post">
                    <label>ZIP Code</label>
                    <input id="zip_code" name="zip_code" value="{zip_code}" required onblur="fetchRate()">

                    <div class="row">
                        <div class="col">
                            <label>Home Price</label>
                            <input name="home_price" type="number" value="{home_price_value}" required>
                        </div>
                        <div class="col">
                            <label>Down Payment</label>
                            <input name="down_payment" type="number" value="{down_payment_value}" required>
                        </div>
                    </div>

                    <label>Mortgage Rate (%)</label>
                    <input id="mortgage_rate" name="mortgage_rate" type="number" step="0.01" value="{mortgage_rate_value}" required>

                    <label>Loan Term</label>
                    <select id="loan_term" name="loan_term" onchange="fetchRate()">
                        <option value="30" {"selected" if loan_term == 30 else ""}>30 Year</option>
                        <option value="15" {"selected" if loan_term == 15 else ""}>15 Year</option>
                    </select>

                    <button type="submit">Calculate</button>
                </form>
            </div>

            <script>
            async function fetchRate() {{
                const zip = document.getElementById("zip_code").value;
                const term = document.getElementById("loan_term").value;

                if (zip.length !== 5) return;

                const res = await fetch(`/rate?zip_code=${{zip}}&loan_term=${{term}}`);
                const data = await res.json();

                if (data.rate) {{
                    document.getElementById("mortgage_rate").value = data.rate;
                }}
            }}
            </script>
        </body>
    </html>
    """


@app.get("/rate")
def get_rate(zip_code: str, loan_term: int = 30):
    state = zip_to_state(zip_code)
    rate = STATE_RATES.get(state, {}).get(str(loan_term))
    return {"state": state, "rate": rate}


@app.post("/calculate", response_class=HTMLResponse)
async def calculate(
    zip_code: str = Form(...),
    home_price: float = Form(...),
    down_payment: float = Form(...),
    mortgage_rate: float = Form(...),
    loan_term: int = Form(...),
):
    state = zip_to_state(zip_code)

    rate_30 = STATE_RATES.get(state, {}).get("30", "N/A")
    rate_15 = STATE_RATES.get(state, {}).get("15", "N/A")

    tax_rate = STATE_TAX_RATES.get(state, 0.015)
    insurance_rate = STATE_INSURANCE_RATES.get(state, 0.004)

    annual_tax = home_price * tax_rate
    monthly_tax = annual_tax / 12

    annual_insurance = home_price * insurance_rate
    monthly_insurance = annual_insurance / 12

    loan_amount = home_price - down_payment

    monthly_30 = calculate_monthly_payment(loan_amount, mortgage_rate, 30)
    monthly_15 = calculate_monthly_payment(loan_amount, mortgage_rate, 15)

    pmi = 0
    if (down_payment / home_price) < 0.20:
        pmi = loan_amount * 0.005 / 12

    total_30 = monthly_30 + monthly_tax + monthly_insurance + pmi
    total_15 = monthly_15 + monthly_tax + monthly_insurance + pmi

    interest_30 = (monthly_30 * 360) - loan_amount
    interest_15 = (monthly_15 * 180) - loan_amount
    interest_saved = interest_30 - interest_15

    return f"""
    <html>
        <head>
            <title>MORTGAGE-WIZARD Results</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    max-width: 1100px;
                    margin: 40px auto;
                    padding: 20px;
                    background: #f4f7fb;
                    color: #1f2937;
                }}
                .header-card, .summary-card {{
                    background: white;
                    border-radius: 14px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.08);
                    padding: 24px;
                    margin-bottom: 20px;
                }}
                .loan-grid {{
                    display: flex;
                    gap: 20px;
                    margin-bottom: 20px;
                }}
                .loan-card {{
                    flex: 1;
                    background: white;
                    border-radius: 14px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.08);
                    padding: 24px;
                }}
                .loan-card h2 {{
                    margin-top: 0;
                    color: #1d4ed8;
                }}
                .big-number {{
                    font-size: 32px;
                    font-weight: 700;
                    margin: 14px 0;
                }}
                .button {{
                    display: inline-block;
                    background: #2563eb;
                    color: white;
                    text-decoration: none;
                    padding: 12px 18px;
                    border-radius: 8px;
                    margin-top: 16px;
                }}
                .button:hover {{
                    background: #1d4ed8;
                }}
                .muted {{
                    color: #6b7280;
                }}
            </style>
        </head>
        <body>
            <div class="header-card">
                <h1 style="margin-top:0; color:#1d4ed8;">MORTGAGE-WIZARD Results</h1>
                <p><b>ZIP Code:</b> {zip_code}</p>
                <p><b>State:</b> {state}</p>
                <p><b>30-Year Rate:</b> {rate_30}% &nbsp;&nbsp;&nbsp; <b>15-Year Rate:</b> {rate_15}%</p>
                <p><b>Home Price:</b> ${home_price:,.0f} &nbsp;&nbsp;&nbsp; <b>Down Payment:</b> ${down_payment:,.0f} &nbsp;&nbsp;&nbsp; <b>Loan Amount:</b> ${loan_amount:,.0f}</p>
            </div>

            <div class="loan-grid">
                <div class="loan-card">
                    <h2>30-Year Loan</h2>
                    <div class="big-number">${total_30:,.2f}</div>
                    <p><b>Mortgage:</b> ${monthly_30:,.2f}</p>
                    <p><b>Estimated Property Tax:</b> ${monthly_tax:,.2f}</p>
                    <p><b>Estimated Insurance:</b> ${monthly_insurance:,.2f}</p>
                    <p><b>Private Mortgage Insurance:</b> ${pmi:,.2f}</p>
                    <p><b>Total Interest:</b> ${interest_30:,.0f}</p>
                </div>

                <div class="loan-card">
                    <h2>15-Year Loan</h2>
                    <div class="big-number">${total_15:,.2f}</div>
                    <p><b>Mortgage:</b> ${monthly_15:,.2f}</p>
                    <p><b>Estimated Property Tax:</b> ${monthly_tax:,.2f}</p>
                    <p><b>Estimated Insurance:</b> ${monthly_insurance:,.2f}</p>
                    <p><b>Private Mortgage Insurance:</b> ${pmi:,.2f}</p>
                    <p><b>Total Interest:</b> ${interest_15:,.0f}</p>
                </div>
            </div>

            <div class="summary-card">
                <p><b>Interest saved with 15-year loan:</b> ${interest_saved:,.0f}</p>
                <p class="muted">Property tax and insurance are estimates based on state averages.</p>
                <a class="button" href="/?zip_code={zip_code}&home_price={home_price}&down_payment={down_payment}&mortgage_rate={mortgage_rate}&loan_term={loan_term}">
                    New Calc
                </a>
            </div>
        </body>
    </html>
    """