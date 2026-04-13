from fastapi import FastAPI, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse
from pypdf import PdfReader
from openai import OpenAI
import io
import os

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

ZIP_SCHOOLS = {
    "44313": [
        {"name": "Revere High School", "rating": 8},
        {"name": "Bath Elementary School", "rating": 9},
        {"name": "Revere Middle School", "rating": 8},
    ],
    "44333": [
        {"name": "Revere High School", "rating": 8},
        {"name": "Bath Elementary School", "rating": 9},
        {"name": "Revere Middle School", "rating": 8},
    ],
    "15237": [
        {"name": "North Allegheny High School", "rating": 9},
        {"name": "McKnight Elementary School", "rating": 8},
        {"name": "Carson Middle School", "rating": 8},
    ],
    "32804": [
        {"name": "Edgewater High School", "rating": 7},
        {"name": "College Park Middle School", "rating": 8},
        {"name": "Princeton Elementary School", "rating": 8},
    ],
    "90210": [
        {"name": "Beverly Hills High School", "rating": 9},
        {"name": "Hawthorne Elementary School", "rating": 8},
        {"name": "Beverly Vista Middle School", "rating": 8},
    ],
}

DEFAULT_SCHOOLS = [
    {"name": "Sample Area High School", "rating": 7},
    {"name": "Sample Area Middle School", "rating": 7},
    {"name": "Sample Area Elementary School", "rating": 7},
]


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


def get_schools(zip_code: str):
    return ZIP_SCHOOLS.get(zip_code, DEFAULT_SCHOOLS)


def extract_pdf_text(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    text = ""

    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"

    return text.strip()


def extract_relevant_closing_lines(text: str) -> str:
    keywords = [
        "origination", "underwriting", "appraisal", "credit",
        "title", "settlement", "recording", "transfer",
        "prepaid", "escrow", "insurance", "tax",
        "cash to close", "loan costs", "other costs",
        "services borrower", "services you can shop",
        "initial escrow", "total closing costs",
        "lender fees", "title fees", "closing costs"
    ]

    lines = text.splitlines()
    matched = []

    for line in lines:
        lower = line.lower()
        if any(keyword in lower for keyword in keywords):
            cleaned = line.strip()
            if cleaned:
                matched.append(cleaned)

    return "\n".join(matched[:200])


def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def analyze_closing_cost_text(text: str) -> str:
    client = get_openai_client()

    if not client:
        return "OpenAI API key not found. Add OPENAI_API_KEY to your environment to enable AI analysis."

    if not text.strip():
        return "No readable fee text was found in the uploaded PDF."

    prompt = f"""
You are an expert at reviewing real estate closing disclosures for home buyers.

Read the closing disclosure fee lines below and provide:

1. A short plain-English summary
2. A breakdown of the main fee categories:
   - Loan Costs
   - Other Costs
   - Prepaids
   - Initial Escrow Payment at Closing
   - Cash to Close
3. Possible red flags or inflated costs
4. Which fees are common and which may be negotiable
5. A short list of questions the buyer should ask the lender, broker, or title company

Keep the output easy to read with headings and bullet points.

Closing disclosure fee lines:
{text[:12000]}
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
    )

    return response.output_text


@app.get("/", response_class=HTMLResponse)
def home(
    zip_code: str = "",
    home_price: float = 0,
    down_payment: float = 0,
    monthly_budget: float = 0,
    mortgage_rate: float = 0,
    loan_term: int = 30,
):
    home_price_value = "" if home_price == 0 else str(home_price)
    down_payment_value = "" if down_payment == 0 else str(down_payment)
    monthly_budget_value = "" if monthly_budget == 0 else str(monthly_budget)
    mortgage_rate_value = "" if mortgage_rate == 0 else str(mortgage_rate)

    return f"""
    <html>
        <head>
            <title>MORTGAGE-WIZARD</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    background: #eef3f8;
                    margin: 0;
                    padding: 32px;
                    color: #1f2937;
                }}
                .page {{
                    max-width: 1280px;
                    margin: 0 auto;
                }}
                .grid {{
                    display: grid;
                    grid-template-columns: 2fr 1fr;
                    gap: 24px;
                }}
                .card {{
                    background: white;
                    border-radius: 18px;
                    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
                    padding: 28px;
                }}
                h1 {{
                    margin: 0 0 10px 0;
                    font-size: 52px;
                    color: #2450d3;
                    letter-spacing: -1px;
                }}
                h2, h3 {{
                    color: #2450d3;
                    margin-top: 0;
                }}
                .subtitle {{
                    color: #6b7280;
                    margin-bottom: 24px;
                }}
                label {{
                    display: block;
                    font-weight: 700;
                    margin-bottom: 8px;
                    font-size: 18px;
                }}
                input, select {{
                    width: 100%;
                    padding: 14px 16px;
                    border: 1px solid #d1d5db;
                    border-radius: 12px;
                    box-sizing: border-box;
                    margin-bottom: 18px;
                    font-size: 16px;
                    background: #fff;
                }}
                input:focus, select:focus {{
                    outline: none;
                    border-color: #2450d3;
                    box-shadow: 0 0 0 3px rgba(36, 80, 211, 0.12);
                }}
                .row {{
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 18px;
                }}
                button {{
                    background: #2563eb;
                    color: white;
                    border: none;
                    padding: 14px 18px;
                    border-radius: 12px;
                    font-size: 16px;
                    font-weight: 700;
                    cursor: pointer;
                }}
                button:hover {{
                    background: #1d4ed8;
                }}
                .placeholder {{
                    color: #6b7280;
                }}
                .school-item {{
                    padding: 14px 0;
                    border-bottom: 1px solid #e5e7eb;
                }}
                .school-item:last-child {{
                    border-bottom: none;
                }}
                .school-name {{
                    font-weight: 700;
                    margin-bottom: 4px;
                }}
                .school-rating {{
                    color: #4b5563;
                }}
                .sidebar-section {{
                    margin-top: 28px;
                    padding-top: 24px;
                    border-top: 1px solid #e5e7eb;
                }}
                .upload-note {{
                    color: #6b7280;
                    margin-bottom: 16px;
                }}
                @media (max-width: 900px) {{
                    .grid, .row {{
                        grid-template-columns: 1fr;
                    }}
                    h1 {{
                        font-size: 40px;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="page">
                <div class="grid">
                    <div class="card">
                        <h1>MORTGAGE-WIZARD</h1>
                        <div class="subtitle">Compare payments, check affordability, and review local schools.</div>

                        <form action="/calculate" method="post">
                            <div class="row">
                                <div>
                                    <label>ZIP Code</label>
                                    <input id="zip_code" name="zip_code" value="{zip_code}" oninput="fetchRateAndSchools()" required>
                                </div>
                                <div>
                                    <label>Loan Term</label>
                                    <select id="loan_term" name="loan_term" onchange="fetchRateAndSchools()">
                                        <option value="30" {"selected" if loan_term == 30 else ""}>30 Year</option>
                                        <option value="15" {"selected" if loan_term == 15 else ""}>15 Year</option>
                                    </select>
                                </div>
                            </div>

                            <div class="row">
                                <div>
                                    <label>Home Price</label>
                                    <input name="home_price" type="number" step="0.01" value="{home_price_value}" required>
                                </div>
                                <div>
                                    <label>Down Payment</label>
                                    <input name="down_payment" type="number" step="0.01" value="{down_payment_value}" required>
                                </div>
                            </div>

                            <div class="row">
                                <div>
                                    <label>Monthly Budget</label>
                                    <input name="monthly_budget" type="number" step="0.01" value="{monthly_budget_value}">
                                </div>
                                <div>
                                    <label>Mortgage Rate (%)</label>
                                    <input id="mortgage_rate" name="mortgage_rate" type="number" step="0.01" value="{mortgage_rate_value}" required>
                                </div>
                            </div>

                            <button type="submit">Calculate</button>
                        </form>
                    </div>

                    <div class="card">
                        <h2>Area Schools</h2>
                        <div id="schools_list" class="placeholder">Enter a 5-digit ZIP code to see area schools.</div>

                        <div class="sidebar-section">
                            <h3>Closing Cost Tool</h3>
                            <div class="upload-note">Upload a closing disclosure PDF for a faster fee review.</div>

                            <form action="/closing-costs" method="post" enctype="multipart/form-data">
                                <input type="file" name="closing_file" accept=".pdf" required>
                                <button type="submit">Analyze</button>
                            </form>
                        </div>
                    </div>
                </div>
            </div>

            <script>
            async function fetchRateAndSchools() {{
                const zip = document.getElementById("zip_code").value.trim();
                const loanTerm = document.getElementById("loan_term").value;
                const rateInput = document.getElementById("mortgage_rate");
                const schoolsList = document.getElementById("schools_list");

                if (zip.length !== 5) {{
                    if (schoolsList) {{
                        schoolsList.innerHTML = "<p class='placeholder'>Enter a 5-digit ZIP code to see area schools.</p>";
                    }}
                    return;
                }}

                try {{
                    const rateRes = await fetch(`/rate?zip_code=${{zip}}&loan_term=${{loanTerm}}`);
                    const rateData = await rateRes.json();

                    if (rateData.rate !== null && rateData.rate !== undefined) {{
                        rateInput.value = rateData.rate;
                    }}

                    if (schoolsList) {{
                        const schoolsRes = await fetch(`/schools?zip_code=${{zip}}`);
                        const schoolsData = await schoolsRes.json();

                        if (schoolsData.schools && schoolsData.schools.length > 0) {{
                            schoolsList.innerHTML = schoolsData.schools.map(
                                s => `
                                    <div class="school-item">
                                        <div class="school-name">${{s.name}}</div>
                                        <div class="school-rating">Rating: ${{s.rating}}/10</div>
                                    </div>
                                `
                            ).join("");
                        }} else {{
                            schoolsList.innerHTML = "<p class='placeholder'>No schools found for that ZIP code.</p>";
                        }}
                    }}
                }} catch (err) {{
                    console.error(err);
                }}
            }}

            window.onload = function() {{
                const zip = document.getElementById("zip_code").value.trim();
                if (zip.length === 5) {{
                    fetchRateAndSchools();
                }}
            }};
            </script>
        </body>
    </html>
    """


@app.get("/rate")
def get_rate(zip_code: str, loan_term: int = 30):
    state = zip_to_state(zip_code)
    rate = STATE_RATES.get(state, {}).get(str(loan_term))
    return {"state": state, "rate": rate}


@app.get("/schools")
def schools(zip_code: str):
    if len(zip_code.strip()) != 5 or not zip_code.strip().isdigit():
        return {"schools": []}
    return {"schools": get_schools(zip_code.strip())}


@app.post("/closing-costs", response_class=HTMLResponse)
async def closing_costs(closing_file: UploadFile = File(...)):
    file_bytes = await closing_file.read()
    text = extract_pdf_text(file_bytes)
    filtered_text = extract_relevant_closing_lines(text)
    analysis = analyze_closing_cost_text(filtered_text)

    return f"""
    <html>
        <head>
            <title>Closing Cost Breakdown</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    max-width: 1000px;
                    margin: 40px auto;
                    padding: 20px;
                    background: #f4f7fb;
                    color: #1f2937;
                }}
                .card {{
                    background: white;
                    border-radius: 14px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.08);
                    padding: 24px;
                    margin-bottom: 20px;
                }}
                h1, h2 {{
                    margin-top: 0;
                    color: #1d4ed8;
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
                .analysis-box {{
                    white-space: pre-wrap;
                    line-height: 1.6;
                    background: #f9fafb;
                    padding: 16px;
                    border-radius: 10px;
                    border: 1px solid #e5e7eb;
                }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1>Closing Cost Breakdown</h1>
                <p><b>File:</b> {closing_file.filename}</p>
            </div>

            <div class="card">
                <h2>AI Analysis</h2>
                <div class="analysis-box">{analysis}</div>
                <a class="button" href="/">Back to Mortgage Wizard</a>
            </div>
        </body>
    </html>
    """


@app.post("/calculate", response_class=HTMLResponse)
async def calculate(
    zip_code: str = Form(...),
    home_price: float = Form(...),
    down_payment: float = Form(...),
    mortgage_rate: float = Form(...),
    loan_term: int = Form(30),
    monthly_budget: float = Form(0),
):
    if home_price <= 0:
        raise HTTPException(status_code=400, detail="Home price must be greater than 0")

    if down_payment < 0:
        raise HTTPException(status_code=400, detail="Down payment cannot be negative")

    if down_payment >= home_price:
        raise HTTPException(status_code=400, detail="Down payment must be less than home price")

    state = zip_to_state(zip_code)
    schools = get_schools(zip_code)

    rate_30 = float(STATE_RATES.get(state, {}).get("30", mortgage_rate))
    rate_15 = float(STATE_RATES.get(state, {}).get("15", mortgage_rate))

    tax_rate = STATE_TAX_RATES.get(state, 0.015)
    insurance_rate = STATE_INSURANCE_RATES.get(state, 0.004)

    annual_tax = home_price * tax_rate
    monthly_tax = annual_tax / 12

    annual_insurance = home_price * insurance_rate
    monthly_insurance = annual_insurance / 12

    loan_amount = home_price - down_payment

    monthly_30 = calculate_monthly_payment(loan_amount, rate_30, 30)
    monthly_15 = calculate_monthly_payment(loan_amount, rate_15, 15)

    pmi = 0
    if home_price > 0 and (down_payment / home_price) < 0.20:
        pmi = loan_amount * 0.005 / 12

    total_30 = monthly_30 + monthly_tax + monthly_insurance + pmi
    total_15 = monthly_15 + monthly_tax + monthly_insurance + pmi

    interest_30 = (monthly_30 * 360) - loan_amount
    interest_15 = (monthly_15 * 180) - loan_amount
    interest_saved = interest_30 - interest_15

    affordable_price = None
    base_budget = None

    if monthly_budget and monthly_budget > 0:
        base_budget = monthly_budget - (monthly_tax + monthly_insurance + pmi)
        if base_budget > 0:
            r = (rate_30 / 100) / 12
            n = 30 * 12
            if r > 0:
                affordable_loan = base_budget * (((1 + r) ** n - 1) / (r * (1 + r) ** n))
                affordable_price = affordable_loan + down_payment

    difference = None
    budget_color = "black"
    budget_label = ""

    if monthly_budget and monthly_budget > 0:
        difference = monthly_budget - total_30
        if difference >= 0:
            budget_color = "green"
            budget_label = "Under Budget"
        else:
            budget_color = "red"
            budget_label = "Over Budget"

    schools_html = "".join(
        [
            f"<p><b>{school['name']}</b> - Rating: {school['rating']}/10</p>"
            for school in schools
        ]
    )

    affordability_html = (
        f"<p><b>Estimated Affordable Home Price:</b> ${affordable_price:,.0f}</p>"
        if affordable_price
        else "<p><b>Estimated Affordable Home Price:</b> Enter a monthly budget to calculate.</p>"
    )

    budget_html = ""
    if monthly_budget and monthly_budget > 0 and difference is not None and base_budget is not None:
        budget_html = f"""
        <div class="summary-card">
            <h2>Budget vs Payment</h2>
            <p><b>Your Monthly Budget:</b> ${monthly_budget:,.2f}</p>
            <p><b>Base Budget After Tax, Insurance, and PMI:</b> ${base_budget:,.2f}</p>
            <p><b>Estimated Monthly Mortgage Payment:</b> ${monthly_30:,.2f}</p>
            <p><b>Estimated Total Monthly Payment:</b> ${total_30:,.2f}</p>
            <p style="color:{budget_color}; font-weight:700;">
                {budget_label}: ${abs(difference):,.2f}
            </p>
        </div>
        """

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
                .header-card, .summary-card, .schools-card, .afford-card {{
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
                .loan-card h2, .schools-card h2, .afford-card h2 {{
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
                @media (max-width: 700px) {{
                    .loan-grid {{
                        flex-direction: column;
                    }}
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

            {budget_html}

            <div class="afford-card">
                <h2>Affordability Summary</h2>
                {affordability_html}
                <p class="muted">This estimate uses the 30-year rate and includes estimated tax, insurance, and PMI.</p>
            </div>

            <div class="schools-card">
                <h2>Area Schools</h2>
                {schools_html}
            </div>

            <div class="summary-card">
                <p><b>Interest saved with 15-year loan:</b> ${interest_saved:,.0f}</p>
                <p class="muted">Property tax and insurance are estimates. School list is ZIP-based sample data.</p>
                <a class="button" href="/?zip_code={zip_code}&home_price={home_price}&down_payment={down_payment}&monthly_budget={monthly_budget}&mortgage_rate={mortgage_rate}&loan_term={loan_term}">
                    New Calc
                </a>
            </div>
        </body>
    </html>
    """