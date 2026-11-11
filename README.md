# BYOT Interiors

A Streamlit app for managing an interior design business.

## Features

- Owner login
- Client and project records
- Editable room and work headings
- Quotations and expense tracking
- Materials, purchasing stores, and deadlines
- Automatic project surplus and margin calculations
- Payments received and outstanding balance
- Internal Excel and client quotation downloads

## Run locally

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Keep the logo at assets/logo.jpg.

## Demo deployment

In Streamlit Cloud Secrets, set:

```toml
BYOT_DEMO_MODE = "true"
```

Use fictional data only. Demo records may disappear after
a reboot or redeployment. Download exports before finishing.

## Calculations

Project surplus = agreed project value − material purchases
− other recorded expenses.

Surplus is provisional until all costs are entered.
Tax liabilities and unrecorded overhead are not calculated.

## Before business use

Connect a persistent database and replace the shared test
credentials with private authentication settings.
