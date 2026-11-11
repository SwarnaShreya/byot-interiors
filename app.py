# BYOT INTERIORS — complete Streamlit app
# Save this file as app.py alongside the assets folder.
# Run: python -m streamlit run app.py



# -----------------------------------------------------------------
# domain.py
from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import math
import uuid

DEFAULT_SECTIONS = ['Parents Bedroom', 'Master Bedroom', 'Living room', 'Kitchen', 'Accessories', 'False ceiling']
QUOTE_COLUMNS = ['Section', 'Description', 'Core / finish', 'Carcass material', 'Shutter material', 'Unit', 'Nos', 'Height / depth (ft)', 'Width (ft)', 'Rate (INR)', 'Amount override (INR)', 'Deadline', 'Notes']
MATERIAL_COLUMNS = ['Section', 'Material', 'Store / supplier', 'Quantity', 'Unit', 'Purchase rate (INR)', 'Delivery / other (INR)', 'Deadline', 'Purchase date', 'Status', 'Notes']
EXPENSE_COLUMNS = ['Category', 'Description', 'Vendor / person', 'Amount (INR)', 'Deadline', 'Status', 'Notes']
PAYMENT_COLUMNS = ['Date', 'Reference', 'Amount received (INR)', 'Notes']

def number(value, label='Value'):
    if value is None or value == '':
        return 0.0
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{label} must be a number.')
    if not math.isfinite(result) or result < 0:
        raise ValueError(f'{label} must be a finite, non-negative number.')
    return result

def money(value):
    return float(Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))

def quote_line(row):
    unit = str(row.get('Unit') or 'sqft').lower().strip()
    nos = number(row.get('Nos'), 'Nos')
    rate = number(row.get('Rate (INR)'), 'Rate')
    if unit == 'sqft':
        quantity = nos * number(row.get('Height / depth (ft)')) * number(row.get('Width (ft)'))
    elif unit in ('nos', 'lumpsum'):
        quantity = nos
    else:
        raise ValueError('Quote unit must be sqft, nos or lumpsum.')
    override = row.get('Amount override (INR)')
    amount = money(number(override, 'Amount override') if override not in (None, '') else quantity * rate)
    return {'Quantity': round(quantity, 4), 'Quoted amount (INR)': amount}

def material_amount(row):
    return money(number(row.get('Quantity')) * number(row.get('Purchase rate (INR)')) + number(row.get('Delivery / other (INR)')))

def totals(project):
    quoted = money(sum(quote_line(r)['Quoted amount (INR)'] for r in project['quote']))
    purchases = money(sum(material_amount(r) for r in project['materials']))
    expenses = money(sum(number(r.get('Amount (INR)')) for r in project['expenses']))
    receipts = money(sum(number(r.get('Amount received (INR)')) for r in project['payments']))
    agreed = project.get('agreed_value')
    revenue = number(agreed) if agreed is not None else quoted
    cost = money(purchases + expenses)
    profit = money(revenue - cost)
    return dict(quoted=quoted, revenue=money(revenue), purchases=purchases, expenses=expenses, cost=cost,
                profit=profit, margin=profit / revenue * 100 if revenue else None,
                receipts=receipts, outstanding=money(revenue - receipts))

def apply_edits(base, changes, columns):
    rows = deepcopy(base)
    for idx, updates in changes.get('edited_rows', {}).items():
        idx = int(idx)
        if 0 <= idx < len(rows):
            rows[idx].update({k: v for k, v in updates.items() if k in columns})
    deleted = set(changes.get('deleted_rows', []))
    rows = [r for i, r in enumerate(rows) if i not in deleted]
    for added in changes.get('added_rows', []):
        rows.append({c: added.get(c) for c in columns})
    return rows

def validate_rows(kind, rows, sections):
    numeric = {
        'quote': ['Nos', 'Height / depth (ft)', 'Width (ft)', 'Rate (INR)', 'Amount override (INR)'],
        'materials': ['Quantity', 'Purchase rate (INR)', 'Delivery / other (INR)'],
        'expenses': ['Amount (INR)'], 'payments': ['Amount received (INR)'],
    }
    for row in rows:
        for col in numeric[kind]:
            number(row.get(col), col)
        if kind in ('quote', 'materials') and row.get('Section') and row['Section'] not in sections:
            raise ValueError('Choose one of the saved room / work headings.')
        if kind == 'quote':
            quote_line(row)

def new_project(name, template):
    rows = deepcopy(template)
    for row in rows:
        for key in ['Height / depth (ft)', 'Width (ft)', 'Rate (INR)']:
            row[key] = 0.0
        row['Nos'] = 1.0
        row['Amount override (INR)'] = None
        row['Deadline'] = ''
    return {'id': str(uuid.uuid4()), 'name': name.strip(), 'contact': '', 'site': '', 'deadline': '',
            'notes': '', 'agreed_value': None, 'costs_complete': False,
            'sections': DEFAULT_SECTIONS.copy(), 'quote': rows, 'materials': [], 'expenses': [], 'payments': [],
            'source': 'Blank template based on the supplied BYOT workbook'}

def completeness(project):
    issues = []
    for kind, name, qty, rate in [('quote', 'Description', 'Nos', 'Rate (INR)'), ('materials', 'Material', 'Quantity', 'Purchase rate (INR)')]:
        for i, row in enumerate(project[kind], 1):
            if not row.get(name):
                issues.append(f'{kind.title()} row {i}: add a description.')
            if kind == 'quote' and row.get('Amount override (INR)') not in (None, ''):
                continue
            if number(row.get(qty)) <= 0 or number(row.get(rate)) <= 0:
                issues.append(f'{kind.title()} row {i}: quantity or rate is zero / blank; check it.')
            if kind == 'quote' and (row.get('Unit') or 'sqft') == 'sqft' and (number(row.get('Height / depth (ft)')) <= 0 or number(row.get('Width (ft)')) <= 0):
                issues.append(f'Quote row {i}: add both dimensions.')
    return issues

def restore_backup(data):
    if not isinstance(data, dict) or not isinstance(data.get('name'), str) or not data['name'].strip():
        raise ValueError('This is not a valid BYOT project backup.')
    sections = data.get('sections')
    if not isinstance(sections, list) or not sections or len(sections) > 100 or not all(isinstance(s, str) and s.strip() for s in sections):
        raise ValueError('The backup needs a valid list of headings.')
    project = new_project(data['name'], [])
    project['sections'] = list(dict.fromkeys(sections))
    for kind, columns in [('quote', QUOTE_COLUMNS), ('materials', MATERIAL_COLUMNS), ('expenses', EXPENSE_COLUMNS), ('payments', PAYMENT_COLUMNS)]:
        rows = data.get(kind, [])
        if not isinstance(rows, list) or len(rows) > 5000 or not all(isinstance(r, dict) for r in rows):
            raise ValueError('Invalid or oversized backup table.')
        project[kind] = [{c: row.get(c) for c in columns} for row in rows]
        validate_rows(kind, project[kind], project['sections'])
    for key in ['contact', 'site', 'deadline', 'notes', 'source']:
        project[key] = str(data.get(key) or '')
    project['agreed_value'] = number(data['agreed_value']) if data.get('agreed_value') is not None else None
    project['costs_complete'] = bool(data.get('costs_complete', False))
    totals(project)
    return project


# -----------------------------------------------------------------
# auth.py
import hashlib
import hmac
import secrets

def make_hash(password):
    salt = secrets.token_hex(16)
    result = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000).hex()
    return f'pbkdf2_sha256$600000${salt}${result}'

def verify(password, encoded):
    try:
        algo, rounds, salt, expected = encoded.split('$')
        if algo != 'pbkdf2_sha256':
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), int(rounds)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False



# -----------------------------------------------------------------
# storage.py
import json
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone

class ConflictError(Exception):
    pass

class Store:
    def __init__(self, db_path, database_url=''):
        self.db_path = Path(db_path)
        self.database_url = database_url
        if not database_url:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS byot_projects (id TEXT PRIMARY KEY, name TEXT NOT NULL, payload TEXT NOT NULL, revision INTEGER NOT NULL, updated TEXT NOT NULL)')

    @contextmanager
    def connection(self):
        if self.database_url:
            import psycopg
            conn = psycopg.connect(self.database_url, connect_timeout=10, prepare_threshold=None)
        else:
            conn = sqlite3.connect(str(self.db_path), timeout=10)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def sql(self, query):
        return query.replace('?', '%s') if self.database_url else query

    def list(self):
        with self.connection() as conn:
            return conn.execute('SELECT id, name, revision, updated FROM byot_projects ORDER BY name, id').fetchall()

    def get(self, project_id):
        with self.connection() as conn:
            row = conn.execute(self.sql('SELECT payload, revision FROM byot_projects WHERE id=?'), (project_id,)).fetchone()
        if not row:
            raise KeyError('Client no longer exists.')
        return json.loads(row[0]), row[1]

    def create(self, project):
        now = datetime.now(timezone.utc).isoformat()
        with self.connection() as conn:
            conn.execute(self.sql('INSERT INTO byot_projects (id,name,payload,revision,updated) VALUES (?,?,?,?,?)'),
                         (project['id'], project['name'], json.dumps(project, allow_nan=False), 1, now))
        return 1

    def save(self, project, revision):
        now = datetime.now(timezone.utc).isoformat()
        with self.connection() as conn:
            result = conn.execute(self.sql('UPDATE byot_projects SET name=?,payload=?,revision=?,updated=? WHERE id=? AND revision=?'),
                                  (project['name'], json.dumps(project, allow_nan=False), revision+1, now, project['id'], revision))
            if result.rowcount != 1:
                raise ConflictError('This client changed in another window. Reload the saved client before continuing.')
        return revision+1


    def delete(self, project_id, revision):
        with self.connection() as conn:
            result = conn.execute(self.sql('DELETE FROM byot_projects WHERE id=? AND revision=?'),
                                  (project_id, revision))
            if result.rowcount != 1:
                raise ConflictError('This client changed or was deleted in another window. Reload the saved client before continuing.')


# -----------------------------------------------------------------
# excel_export.py
from io import BytesIO
from copy import deepcopy
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as ExcelImage

ORANGE = 'FF7300'

def export_project(project, logo_path, client_only=False):
    project = deepcopy(project)
    def safe(value):
        if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
            return "'" + value
        if isinstance(value, list):
            return [safe(v) for v in value]
        if isinstance(value, dict):
            return {k: safe(v) for k, v in value.items()}
        return value
    project = safe(project)
    wb = Workbook()
    summary = wb.active
    summary.title = 'Project summary'
    summary.append(['BYOT INTERIORS', 'YOUR SPACE, OUR DESIGN'])
    summary.append(['Client', project['name']])
    summary.append(['Site', project.get('site', '')])
    summary.append(['Deadline', project.get('deadline', '')])
    summary.append(['Currency', 'INR — amounts on the entered tax basis'])
    summary.append(['Notes', 'Review final scope and tax basis with BYOT.' if client_only else project.get('notes', '')])
    summary.append(['Source', 'BYOT client quotation' if client_only else project.get('source', '')])
    summary.append(['Scope', 'Quotation and payment milestones only'] if client_only else ['Cost status', 'Owner marked spending complete' if project.get('costs_complete') else 'Spending incomplete; surplus is provisional'])
    summary.append([])
    summary.append(['Measure', 'Amount (INR)'])
    quote = wb.create_sheet('Quotation')
    qheaders = ['Section', 'Description', 'Core / finish', 'Carcass material', 'Shutter material', 'Unit', 'Nos', 'Height / depth (ft)', 'Width (ft)', 'Calculated quantity', 'Unit price (INR)', 'Amount override (INR)', 'Quoted amount (INR)', 'Deadline', 'Notes']
    quote.append(qheaders)
    for idx, row in enumerate(project['quote'], 2):
        quote.append([row.get(c) for c in qheaders[:9]] + [f'=IF(F{idx}="sqft",G{idx}*H{idx}*I{idx},G{idx})', row.get('Rate (INR)', 0), row.get('Amount override (INR)'), f'=IF(L{idx}="",ROUND(J{idx}*K{idx},2),L{idx})', row.get('Deadline'), '' if client_only else row.get('Notes')])
    qend = max(2, quote.max_row)
    summary.append(['Quoted total', f"=SUM('Quotation'!M2:M{qend})"])
    summary.append(['Agreed project value', project.get('agreed_value') if project.get('agreed_value') is not None else '=B11'])
    if not client_only:
        purchases = wb.create_sheet('Material purchases')
        purchases.append(MATERIAL_COLUMNS + ['Purchase amount (INR)'])
        for idx, row in enumerate(project['materials'], 2):
            purchases.append([row.get(c) for c in MATERIAL_COLUMNS] + [f'=ROUND(D{idx}*F{idx}+G{idx},2)'])
        expenses = wb.create_sheet('Other expenses')
        expenses.append(EXPENSE_COLUMNS)
        for row in project['expenses']:
            expenses.append([row.get(c) for c in EXPENSE_COLUMNS])
        payments = wb.create_sheet('Payments received')
        payments.append(PAYMENT_COLUMNS)
        for row in project['payments']:
            payments.append([row.get(c) for c in PAYMENT_COLUMNS])
        summary.append(['Material purchases', f"=SUM('Material purchases'!L2:L{max(2,purchases.max_row)})"])
        summary.append(['Other expenses', f"=SUM('Other expenses'!D2:D{max(2,expenses.max_row)})"])
        summary.append(['Total recorded costs', '=SUM(B13:B14)'])
        summary.append(['Project surplus / (loss)', '=B12-B15'])
        summary.append(['Margin', '=IF(B12=0,"",B16/B12)'])
        summary.append(['Payments received', f"=SUM('Payments received'!C2:C{max(2,payments.max_row)})"])
        summary.append(['Balance to collect / (overpaid)', '=B12-B18'])
        summary['B17'].number_format = '0.0%'
        notes = wb.create_sheet('Notes and checks')
        notes.append(['Important notes'])
        for note in ['Profit is agreed value less material purchases and other recorded expenses; payments received are tracked separately.', 'Use the same tax basis for revenue and costs. Tax liabilities and unrecorded overhead are not calculated.', 'Do not repeat material purchases in Other expenses.', 'Blank / zero rates are drafts; complete them before relying on the totals.', 'The supplied quotation does not establish actual purchase costs or payments received.', 'Source fixed-amount overrides are retained; confirm whether they should remain.'] + completeness(project):
            notes.append([note])
    milestones = wb.create_sheet('Payment milestones')
    milestones.append(['Milestone', 'Share', 'Amount (INR)'])
    for idx, (label, percent) in enumerate([('Booking / sign-up', .1), ('Design approval', .4), ('Before material dispatch', .3), ('Carcass installation', .15), ('After handover', .05)], 2):
        milestones.append([label, percent, f"=ROUND('Project summary'!B12*B{idx},2)"])
        milestones.cell(idx, 2).number_format = '0%'
    for ws in wb:
        ws.freeze_panes = 'A2'
        ws.auto_filter.ref = ws.dimensions
        for cell in ws[1]:
            cell.fill = PatternFill('solid', fgColor=ORANGE)
            cell.font = Font(color='FFFFFF', bold=True)
        for col in ws.columns:
            letter = col[0].column_letter
            ws.column_dimensions[letter].width = min(48, max(16, max(len(str(c.value or '')) if c.data_type != 'f' else 18 for c in col) + 2))
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical='top', wrap_text=True)
                if isinstance(cell.value, (int, float)) or cell.data_type == 'f':
                    cell.number_format = '#,##0.00;[Red](#,##0.00)'
    if not client_only:
        summary['B17'].number_format = '0.0%'
    for i in range(2, 7):
        milestones.cell(i, 2).number_format = '0%'
    # Uploaded text stays text, including cells beginning with formula characters.
    for ws in wb:
        for row in ws:
            for cell in row:
                if isinstance(cell.value, str) and cell.data_type != 'f':
                    cell.data_type = 's'
    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True
    if logo_path and logo_path.exists():
        image = ExcelImage(str(logo_path))
        image.width, image.height = 120, 128
        summary.add_image(image, 'D1')
    result = BytesIO()
    wb.save(result)
    return result.getvalue()


# -----------------------------------------------------------------
# Streamlit screens
from pathlib import Path
from copy import deepcopy
from datetime import date, datetime
import base64
import json
import os
import time
import uuid

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parent
LOGO = next((ROOT / 'assets' / n for n in ['logo.jpg', 'logo.png', 'logo.jpeg'] if (ROOT / 'assets' / n).exists()), None)
st.set_page_config(page_title='BYOT Interiors | Project Studio', page_icon=str(LOGO) if LOGO else '🏠', layout='wide', initial_sidebar_state='expanded')

def setting(key, default=''):
    if key in os.environ:
        return os.environ[key]
    try:
        return st.secrets.get(key, default)
    except (FileNotFoundError, KeyError):
        return default

logo = base64.b64encode(LOGO.read_bytes()).decode() if LOGO else ''
logo_mime = 'image/png' if LOGO and LOGO.suffix.lower() == '.png' else 'image/jpeg'
st.markdown('''<style>
.stApp {background:#f7f5f2;color:#172128;}
[data-testid="stAppViewContainer"] input, [data-testid="stAppViewContainer"] textarea {background:#ffffff !important;color:#172128 !important;-webkit-text-fill-color:#172128 !important;}
[data-baseweb="select"] > div {background:#ffffff !important;color:#172128 !important;}
[data-baseweb="select"] span {color:#172128 !important;}
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {background:#ff7300 !important;color:white !important;}
[data-testid="stBaseButton-primary"] p, [data-testid="stBaseButton-primaryFormSubmit"] p {color:white !important;}

[data-testid="stMain"] h1,[data-testid="stMain"] h2,[data-testid="stMain"] h3,[data-testid="stMain"] p,[data-testid="stMain"] label {color:#172128;}
[data-testid="stMain"] [data-testid="stMetricValue"] {color:#172128;}
[data-testid="stMain"] .brand h1 {color:white !important;}
[data-testid="stMain"] .brand p {color:#d9cfc6 !important;}

[data-testid="stSidebar"] {background:#0c1115;}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] label,[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3 {color:#fafafa;}
h1,h2,h3 {font-family:Arial,sans-serif;letter-spacing:-.025em;}
[data-testid="stMetric"] {background:white;border:1px solid #e7e1da;border-top:3px solid #ff7300;padding:20px;border-radius:12px;}
.stButton>button[kind="primary"],.stFormSubmitButton>button[kind="primary"] {background:#ff7300;color:white;border:0;}
.brand {display:flex;align-items:center;gap:24px;background:#0c1115;padding:24px 30px;border-radius:18px;margin-bottom:24px;}
.brand img {width:95px;border-radius:50%;}
.brand h1 {color:white;margin:0;font-size:30px;}
.brand p {color:#d9cfc6;margin:4px 0 0;letter-spacing:.16em;font-size:11px;}
</style>''', unsafe_allow_html=True)

def brand():
    st.markdown(f'<div class="brand"><img src="data:{logo_mime};base64,{logo}"><div><h1>BYOT Interiors</h1><p>YOUR SPACE, OUR DESIGN</p></div></div>', unsafe_allow_html=True)

def clear_editors():
    st.session_state['editor_epoch'] = st.session_state.get('editor_epoch', 0) + 1
    st.session_state['editor_bases'] = {}

demo_hash = 'pbkdf2_sha256$600000$a2029a61e3a136b1b32edf2cb4bf0e4d$75d27d87422e4ec0ebce0668e436ac7ad3854e67288fd458e74cc36ecaad5cfd'
password_hash = setting('BYOT_PASSWORD_HASH', demo_hash)
username = setting('BYOT_USERNAME', 'BYOT')

if not st.session_state.get('authenticated'):
    left, center, right = st.columns([1, 1.3, 1])
    with center:
        brand()
        st.subheader('Welcome to your project studio')
        with st.form('login'):
            user = st.text_input('Username')
            password = st.text_input('Password', type='password')
            submitted = st.form_submit_button('Log in', type='primary', width='stretch')
        if submitted:
            if time.time() < st.session_state.get('locked_until', 0):
                st.error('Please wait a minute before trying again.')
            elif user == username and verify(password, password_hash):
                st.session_state.clear()
                st.session_state['authenticated'] = True
                st.session_state['page'] = 'Clients'
                st.rerun()
            else:
                failures = st.session_state.get('failures', 0) + 1
                st.session_state['failures'] = failures
                if failures % 5 == 0:
                    st.session_state['locked_until'] = time.time() + 60
                st.error('Username or password is incorrect.')
    st.stop()

database_url = setting('DATABASE_URL')
cloud = str(setting('BYOT_CLOUD', 'false')).lower() == 'true' or bool(os.environ.get('STREAMLIT_SHARING_MODE'))
if cloud and not database_url and str(setting("BYOT_DEMO_MODE", "false")).lower() != "true":
    st.error('Online saving needs a connected database. Add DATABASE_URL in Streamlit Secrets before using client records online. See SETUP.md.')
    st.stop()
try:
    store = Store(setting('BYOT_LOCAL_DB_PATH', str(ROOT / 'data/byot.sqlite3')), database_url)
    clients = store.list()
except Exception:
    st.error('The client database is unavailable. Records have not been changed. Check the database connection settings.')
    st.stop()

def current():
    return st.session_state['project']

def save_project(project):
    revision = store.save(project, st.session_state['revision'])
    st.session_state['project'] = deepcopy(project)
    st.session_state['revision'] = revision
    st.session_state['saved_at'] = datetime.now().strftime('%H:%M:%S')

def save_editor(kind, key, columns):
    project = deepcopy(current())
    try:
        rows = apply_edits(st.session_state['editor_bases'][key], st.session_state[key], columns)
        validate_rows(kind, rows, project['sections'])
        project[kind] = rows
        if kind in ('materials', 'expenses'):
            project['costs_complete'] = False
        save_project(project)
    except Exception as error:
        st.session_state['unsaved'] = project
        st.session_state['save_error'] = str(error) if isinstance(error, (ValueError, ConflictError)) else 'Saving failed. Check the database connection.'

def editor(kind, columns, config):
    project = current()
    epoch = st.session_state.get('editor_epoch', 0)
    key = f"edit_{project['id']}_{kind}_{epoch}"
    bases = st.session_state.setdefault('editor_bases', {})
    if key not in bases:
        bases[key] = deepcopy(project[kind])
    frame = pd.DataFrame(bases[key], columns=columns)
    for col, spec in config.items():
        if 'INR' in col or col in ('Nos', 'Height / depth (ft)', 'Width (ft)', 'Quantity'):
            frame[col] = pd.to_numeric(frame[col], errors='coerce').astype(float)
    st.data_editor(frame, num_rows='dynamic', hide_index=True, column_config=config,
                   key=key, on_change=save_editor, args=(kind, key, columns), width='stretch')
    st.caption('Click outside a cell or press Enter to save it. Select a row at the left to delete it. Draft rows can be completed later.')

with st.sidebar:
    if LOGO:
        st.image(str(LOGO), width=150)
    else:
        st.markdown('### BYOT Interiors')
    st.caption('PROJECT STUDIO')
    page = st.radio('Workspace', ['Clients', 'Costs', 'Materials', 'Profit', 'Logout'], key='page', on_change=clear_editors)
    with st.expander('Restore a downloaded project backup'):
        backup = st.file_uploader('BYOT JSON backup', type=['json'])
        st.caption('Restores as a new client record. Existing client records are never overwritten.')
        if st.button('Restore as new client', disabled=backup is None):
            try:
                if backup.size > 5 * 1024 * 1024:
                    raise ValueError('Choose a backup smaller than 5 MB.')
                restored = restore_backup(json.loads(backup.getvalue()))
                store.create(restored)
                st.session_state['pending_client'] = restored['id']
                st.rerun()
            except (ValueError, TypeError, KeyError) as error:
                st.error(str(error))
            except Exception:
                st.error('The backup could not be saved. Check the database connection.')
    if clients:
        ids = [r[0] for r in clients]
        labels = {r[0]: f'{r[1]} · {r[0][:4]}' for r in clients}
        if st.session_state.get('pending_client'):
            st.session_state['client_picker'] = st.session_state.pop('pending_client')
        if st.session_state.get('client_picker') not in ids:
            st.session_state['client_picker'] = ids[0]
        selected = st.selectbox('Choose client', ids, format_func=lambda x: labels[x], key='client_picker', on_change=clear_editors)
        if st.session_state.get('loaded_id') != selected:
            try:
                project, revision = store.get(selected)
                st.session_state.update(project=project, revision=revision, loaded_id=selected)
                clear_editors()
            except Exception:
                st.error('Could not load the saved client. Please reload.')
                st.stop()
    st.divider()
    st.caption('Connected database' if database_url else 'Saving on this computer')
    if st.session_state.get('saved_at'):
        st.caption('Last saved ' + st.session_state['saved_at'])
    if st.button('Reload saved client'):
        for key in ['loaded_id', 'save_error', 'unsaved']:
            st.session_state.pop(key, None)
        clear_editors()
        st.rerun()

brand()
if st.session_state.get('save_error'):
    st.error(st.session_state['save_error'])
    st.warning('The last change was not saved. Download the pending copy before reloading. Saved records are unchanged.')
    st.download_button('Download pending recovery copy', json.dumps(st.session_state.get('unsaved', current()), indent=2), 'byot_pending.json', mime='application/json', on_click='ignore')
    st.stop()

if page == 'Logout':
    st.header('Log out')
    st.write('Completed cell edits and saved client forms are stored. Logging out clears this browser session.')
    if st.button('Log out of BYOT', type='primary'):
        st.session_state.clear()
        st.rerun()
    st.stop()

variants = [{'name': 'Site revised', 'rows': [{'Section': 'Parents Bedroom', 'Description': 'Swing Wardrobe', 'Core / finish': 'Greenply/Laminate', 'Carcass material': 'MR PLY', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 7.0, 'Width (ft)': 5.0, 'Rate (INR)': 1600.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 7'}, {'Section': 'Parents Bedroom', 'Description': 'Frame type loft', 'Core / finish': 'Greenply/Laminate', 'Carcass material': '', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 2.0, 'Width (ft)': 5.0, 'Rate (INR)': 950.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 8'}, {'Section': 'Master Bedroom', 'Description': 'Swing Wardrobe', 'Core / finish': 'Greenply/Laminate', 'Carcass material': 'MR PLY', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 7.0, 'Width (ft)': 6.0, 'Rate (INR)': 1600.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 10'}, {'Section': 'Master Bedroom', 'Description': 'Frame loft-1', 'Core / finish': 'Greenply/Laminate', 'Carcass material': 'MR PLY', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 2.5, 'Width (ft)': 11.0, 'Rate (INR)': 950.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 11'}, {'Section': 'Master Bedroom', 'Description': 'Loft 2', 'Core / finish': 'Greenply/Laminate', 'Carcass material': 'MR PLY', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 2.5, 'Width (ft)': 11.0, 'Rate (INR)': 1050.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 12'}, {'Section': 'Master Bedroom', 'Description': 'Bottom panel', 'Core / finish': 'Greenply/Laminate', 'Carcass material': 'MR PLY', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 2.0, 'Width (ft)': 16.0, 'Rate (INR)': 800.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 13'}, {'Section': 'Living room', 'Description': 'Tv unit drawers', 'Core / finish': 'Greenply/Laminate', 'Carcass material': 'MR PLY', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 1.5, 'Width (ft)': 5.0, 'Rate (INR)': 1600.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 15'}, {'Section': 'Living room', 'Description': 'Pooja/Crockery', 'Core / finish': 'Greenply/Laminate', 'Carcass material': 'MR PLY', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 2.5, 'Width (ft)': 7.0, 'Rate (INR)': 1600.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 16'}, {'Section': 'Kitchen', 'Description': 'Base unit', 'Core / finish': 'Greenply/Laminate', 'Carcass material': 'BWP', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 2.5, 'Width (ft)': 9.5, 'Rate (INR)': 1750.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 18'}, {'Section': 'Kitchen', 'Description': 'Base O/S', 'Core / finish': 'Greenply/Laminate', 'Carcass material': 'BWP', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 2.5, 'Width (ft)': 6.0, 'Rate (INR)': 1050.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 19'}, {'Section': 'Kitchen', 'Description': 'Wall unit', 'Core / finish': 'Greenply/Laminate', 'Carcass material': 'BWP', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 2.4, 'Width (ft)': 10.0, 'Rate (INR)': 1750.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 20'}, {'Section': 'Kitchen', 'Description': 'Rolling shutter unit', 'Core / finish': 'Greenply/Laminate', 'Carcass material': 'BWP', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 4.4, 'Width (ft)': 2.0, 'Rate (INR)': 1750.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 21'}, {'Section': 'Kitchen', 'Description': 'Spice rack', 'Core / finish': 'Greenply/Laminate', 'Carcass material': 'BWP', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 6.0, 'Width (ft)': 1.0, 'Rate (INR)': 800.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 22'}, {'Section': 'Kitchen', 'Description': 'Loft', 'Core / finish': 'Greenply/Laminate', 'Carcass material': 'MR PLY', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 2.9, 'Width (ft)': 25.0, 'Rate (INR)': 1050.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 23'}, {'Section': 'Kitchen', 'Description': 'Bottom Panel', 'Core / finish': 'Greenply/Laminate', 'Carcass material': 'MR PLY', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 1.5, 'Width (ft)': 25.0, 'Rate (INR)': 800.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 24'}, {'Section': 'Accessories', 'Description': 'Plate basket', 'Core / finish': '', 'Carcass material': '', 'Shutter material': '', 'Unit': 'nos', 'Nos': 1.0, 'Height / depth (ft)': 1.0, 'Width (ft)': 1.0, 'Rate (INR)': 3500.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 29'}, {'Section': 'Accessories', 'Description': 'Plain Basket', 'Core / finish': '', 'Carcass material': '', 'Shutter material': '', 'Unit': 'nos', 'Nos': 1.0, 'Height / depth (ft)': 1.0, 'Width (ft)': 1.0, 'Rate (INR)': 3200.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 30'}, {'Section': 'Accessories', 'Description': 'Cutlery tray', 'Core / finish': '', 'Carcass material': '', 'Shutter material': '', 'Unit': 'nos', 'Nos': 1.0, 'Height / depth (ft)': 1.0, 'Width (ft)': 1.0, 'Rate (INR)': 4900.0, 'Amount override (INR)': 4900.0, 'Deadline': '', 'Notes': 'Source row 31 — original fixed amount preserved'}, {'Section': 'Accessories', 'Description': 'Oilpullout', 'Core / finish': '', 'Carcass material': '', 'Shutter material': '', 'Unit': 'nos', 'Nos': 1.0, 'Height / depth (ft)': 1.0, 'Width (ft)': 1.0, 'Rate (INR)': 4800.0, 'Amount override (INR)': 4800.0, 'Deadline': '', 'Notes': 'Source row 32 — original fixed amount preserved'}, {'Section': 'Accessories', 'Description': 'Bedroom 1 mirror', 'Core / finish': '', 'Carcass material': '', 'Shutter material': '', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 6.0, 'Width (ft)': 2.0, 'Rate (INR)': 400.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 33'}, {'Section': 'Accessories', 'Description': 'Bedroom 2 mirror', 'Core / finish': '', 'Carcass material': '', 'Shutter material': '', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 6.0, 'Width (ft)': 2.0, 'Rate (INR)': 400.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 34'}, {'Section': 'Accessories', 'Description': 'Rolling shutter', 'Core / finish': '', 'Carcass material': '', 'Shutter material': '', 'Unit': 'nos', 'Nos': 1.0, 'Height / depth (ft)': 1.0, 'Width (ft)': 1.0, 'Rate (INR)': 12000.0, 'Amount override (INR)': 12000.0, 'Deadline': '', 'Notes': 'Source row 35 — original fixed amount preserved'}, {'Section': 'Accessories', 'Description': 'Chimney', 'Core / finish': '', 'Carcass material': '', 'Shutter material': '', 'Unit': 'lumpsum', 'Nos': 1.0, 'Height / depth (ft)': 1.0, 'Width (ft)': 1.0, 'Rate (INR)': 15000.0, 'Amount override (INR)': 15000.0, 'Deadline': '', 'Notes': 'Source row 36 — original fixed amount preserved'}, {'Section': 'Accessories', 'Description': 'Electricals', 'Core / finish': '', 'Carcass material': '', 'Shutter material': '', 'Unit': 'lumpsum', 'Nos': 1.0, 'Height / depth (ft)': 1.0, 'Width (ft)': 1.0, 'Rate (INR)': 6000.0, 'Amount override (INR)': 8500.0, 'Deadline': '', 'Notes': 'Source row 37 — original fixed amount preserved'}, {'Section': 'Accessories', 'Description': 'False ceiling', 'Core / finish': 'Living', 'Carcass material': '', 'Shutter material': '', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 11.0, 'Width (ft)': 16.0, 'Rate (INR)': 180.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 38'}, {'Section': 'Accessories', 'Description': 'False ceiling', 'Core / finish': 'Dining', 'Carcass material': '', 'Shutter material': '', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 11.0, 'Width (ft)': 11.0, 'Rate (INR)': 180.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 39'}]}, {'name': 'Copy of Site revised', 'rows': [{'Section': 'Parents Bedroom', 'Description': 'Swing Wardrobe', 'Core / finish': 'Greenply/Laminate', 'Carcass material': 'MR PLY', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 7.0, 'Width (ft)': 5.0, 'Rate (INR)': 1600.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 7'}, {'Section': 'Parents Bedroom', 'Description': 'Frame type loft', 'Core / finish': 'Greenply/Laminate', 'Carcass material': '', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 2.0, 'Width (ft)': 5.0, 'Rate (INR)': 950.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 8'}, {'Section': 'Master Bedroom', 'Description': 'Swing Wardrobe', 'Core / finish': 'Greenply/Laminate', 'Carcass material': 'MR PLY', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 7.0, 'Width (ft)': 6.0, 'Rate (INR)': 1600.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 10'}, {'Section': 'Master Bedroom', 'Description': 'Frame loft-1', 'Core / finish': 'Greenply/Laminate', 'Carcass material': 'MR PLY', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 2.5, 'Width (ft)': 11.0, 'Rate (INR)': 1100.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 11'}, {'Section': 'Living room', 'Description': 'Tv unit drawers', 'Core / finish': 'Greenply/Laminate', 'Carcass material': 'MR PLY', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 1.5, 'Width (ft)': 5.0, 'Rate (INR)': 1750.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 13'}, {'Section': 'Living room', 'Description': 'Fluted panel', 'Core / finish': 'Greenply/Laminate', 'Carcass material': 'MR PLY', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 5.0, 'Width (ft)': 5.0, 'Rate (INR)': 425.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 14'}, {'Section': 'Kitchen', 'Description': 'Base unit', 'Core / finish': 'Greenply/Laminate', 'Carcass material': 'BWP', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 2.5, 'Width (ft)': 9.5, 'Rate (INR)': 1750.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 16'}, {'Section': 'Kitchen', 'Description': 'Base O/S', 'Core / finish': 'Greenply/Laminate', 'Carcass material': 'BWP', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 2.5, 'Width (ft)': 6.0, 'Rate (INR)': 1050.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 17'}, {'Section': 'Kitchen', 'Description': 'Wall unit', 'Core / finish': 'Greenply/Laminate', 'Carcass material': 'MR PLY', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 2.4, 'Width (ft)': 12.0, 'Rate (INR)': 1750.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 18'}, {'Section': 'Kitchen', 'Description': 'Spice rack', 'Core / finish': 'Greenply/Laminate', 'Carcass material': 'MR PLY', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 6.0, 'Width (ft)': 1.0, 'Rate (INR)': 800.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 19'}, {'Section': 'Kitchen', 'Description': 'Loft', 'Core / finish': 'Greenply/Laminate', 'Carcass material': 'MR PLY', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 2.9, 'Width (ft)': 25.0, 'Rate (INR)': 1050.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 20'}, {'Section': 'Kitchen', 'Description': 'Bottom Panel', 'Core / finish': 'Greenply/Laminate', 'Carcass material': 'MR PLY', 'Shutter material': 'HDHMR', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 1.5, 'Width (ft)': 25.0, 'Rate (INR)': 500.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 21'}, {'Section': 'Accessories', 'Description': 'Plate basket', 'Core / finish': '', 'Carcass material': '', 'Shutter material': '', 'Unit': 'nos', 'Nos': 1.0, 'Height / depth (ft)': 1.0, 'Width (ft)': 1.0, 'Rate (INR)': 3500.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 26'}, {'Section': 'Accessories', 'Description': 'Plain Basket', 'Core / finish': '', 'Carcass material': '', 'Shutter material': '', 'Unit': 'nos', 'Nos': 1.0, 'Height / depth (ft)': 1.0, 'Width (ft)': 1.0, 'Rate (INR)': 3200.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 27'}, {'Section': 'Accessories', 'Description': 'Cutlery tray', 'Core / finish': '', 'Carcass material': '', 'Shutter material': '', 'Unit': 'nos', 'Nos': 1.0, 'Height / depth (ft)': 1.0, 'Width (ft)': 1.0, 'Rate (INR)': 4900.0, 'Amount override (INR)': 4900.0, 'Deadline': '', 'Notes': 'Source row 28 — original fixed amount preserved'}, {'Section': 'Accessories', 'Description': 'Oilpullout', 'Core / finish': '', 'Carcass material': '', 'Shutter material': '', 'Unit': 'nos', 'Nos': 1.0, 'Height / depth (ft)': 1.0, 'Width (ft)': 1.0, 'Rate (INR)': 4800.0, 'Amount override (INR)': 4800.0, 'Deadline': '', 'Notes': 'Source row 29 — original fixed amount preserved'}, {'Section': 'Accessories', 'Description': 'Chimney', 'Core / finish': '', 'Carcass material': '', 'Shutter material': '', 'Unit': 'lumpsum', 'Nos': 1.0, 'Height / depth (ft)': 1.0, 'Width (ft)': 1.0, 'Rate (INR)': 15000.0, 'Amount override (INR)': 15000.0, 'Deadline': '', 'Notes': 'Source row 30 — original fixed amount preserved'}, {'Section': 'Accessories', 'Description': 'Electricals', 'Core / finish': '', 'Carcass material': '', 'Shutter material': '', 'Unit': 'lumpsum', 'Nos': 1.0, 'Height / depth (ft)': 1.0, 'Width (ft)': 1.0, 'Rate (INR)': 8500.0, 'Amount override (INR)': 8500.0, 'Deadline': '', 'Notes': 'Source row 31 — original fixed amount preserved'}, {'Section': 'Accessories', 'Description': 'Groove design', 'Core / finish': '', 'Carcass material': '', 'Shutter material': '', 'Unit': 'lumpsum', 'Nos': 1.0, 'Height / depth (ft)': 1.0, 'Width (ft)': 1.0, 'Rate (INR)': 2500.0, 'Amount override (INR)': 2500.0, 'Deadline': '', 'Notes': 'Source row 32 — original fixed amount preserved'}, {'Section': 'False ceiling', 'Description': 'Living False ceiling', 'Core / finish': '', 'Carcass material': '', 'Shutter material': '', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 11.0, 'Width (ft)': 16.0, 'Rate (INR)': 180.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 39'}, {'Section': 'False ceiling', 'Description': 'Dining False ceiling', 'Core / finish': '', 'Carcass material': '', 'Shutter material': '', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 11.0, 'Width (ft)': 11.0, 'Rate (INR)': 180.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 40'}, {'Section': 'False ceiling', 'Description': 'Bedroom 1', 'Core / finish': '', 'Carcass material': '', 'Shutter material': '', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 7.0, 'Width (ft)': 7.0, 'Rate (INR)': 180.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 41'}, {'Section': 'False ceiling', 'Description': 'Bedroom 2', 'Core / finish': '', 'Carcass material': '', 'Shutter material': '', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 7.0, 'Width (ft)': 7.0, 'Rate (INR)': 180.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 42'}, {'Section': 'False ceiling', 'Description': 'Bedroom 1', 'Core / finish': 'PVC PANEL', 'Carcass material': '', 'Shutter material': '', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 5.0, 'Width (ft)': 6.0, 'Rate (INR)': 200.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 43'}, {'Section': 'False ceiling', 'Description': 'Bedroom 2', 'Core / finish': 'PVC PANEL', 'Carcass material': '', 'Shutter material': '', 'Unit': 'sqft', 'Nos': 1.0, 'Height / depth (ft)': 5.0, 'Width (ft)': 6.0, 'Rate (INR)': 200.0, 'Amount override (INR)': None, 'Deadline': '', 'Notes': 'Source row 44'}]}]

if page == 'Clients':
    st.header('Clients & projects')
    if st.session_state.get('deleted_client_notice'):
        st.success(st.session_state.pop('deleted_client_notice'))
    st.write('Select a client in the sidebar to reopen their saved records.')
    with st.expander('Add a client', expanded=not bool(clients)):
        with st.form('new_client'):
            name = st.text_input('Client name *')
            site = st.text_input('Project / site address')
            contact = st.text_input('Contact details')
            deadline = st.date_input('Project deadline', value=None)
            create = st.form_submit_button('Create client', type='primary')
        if create:
            if not name.strip():
                st.error('Enter a client name.')
            else:
                project = new_project(name, variants[0]['rows'])
                project.update(site=site, contact=contact, deadline=deadline.isoformat() if deadline else '')
                try:
                    store.create(project)
                    st.session_state['pending_client'] = project['id']
                    st.rerun()
                except Exception:
                    st.error('Client was not created. Check the database connection.')
    if clients:
        project = current()
        st.subheader(project['name'])
        with st.form('client_details'):
            name = st.text_input('Client name', value=project['name'])
            contact = st.text_input('Contact', value=project.get('contact', ''))
            site = st.text_input('Site / project', value=project.get('site', ''))
            deadline = st.date_input('Project deadline', value=date.fromisoformat(project['deadline']) if project.get('deadline') else None)
            notes = st.text_area('Project notes', value=project.get('notes', ''))
            save = st.form_submit_button('Save client details', type='primary')
        if save:
            if not name.strip():
                st.error('Client name is required.')
            else:
                updated = deepcopy(project)
                updated.update(name=name.strip(), contact=contact, site=site, deadline=deadline.isoformat() if deadline else '', notes=notes)
                try:
                    save_project(updated)
                    st.success('Client details saved.')
                except Exception:
                    st.error('Client details were not saved. Reload if another window changed them.')
        with st.expander('Delete selected client'):
            selected_project = current()
            client_id = selected_project['id']
            st.warning(f"Permanently delete {selected_project['name']} and all of this client’s quotations, costs, materials and payment records. Other clients are unchanged.")
            st.download_button('Download this client’s backup before deleting',
                               json.dumps(selected_project, indent=2),
                               f'BYOT_client_{client_id}_backup.json', 'application/json',
                               key=f'delete_backup_{client_id}', on_click='ignore')
            st.caption('You can restore a downloaded backup from the sidebar. Unsaved form changes are not included.')
            confirmation = st.text_input('Type DELETE to confirm', key=f'delete_confirm_{client_id}')
            if st.button('Permanently delete this client', key=f'delete_client_{client_id}',
                         disabled=confirmation != 'DELETE'):
                try:
                    store.delete(client_id, st.session_state['revision'])
                except ConflictError as error:
                    st.error(str(error))
                except Exception:
                    st.error('Client was not deleted. Check the database connection.')
                else:
                    for state_key in list(st.session_state):
                        if state_key in ('project', 'revision', 'loaded_id', 'pending_client', 'unsaved', 'save_error', 'saved_at') or state_key.startswith(f'edit_{client_id}_') or state_key.startswith('delete_'):
                            st.session_state.pop(state_key, None)
                    clear_editors()
                    st.session_state['deleted_client_notice'] = 'Client deleted. Other client records are unchanged.'
                    st.rerun()
        st.divider()
        st.subheader('Start from the supplied quotation')
        st.caption('The workbook contains different revisions. Choose one; they will not be combined. Existing costs are not inferred from quote prices.')
        variant = st.selectbox('Quotation revision', range(len(variants)), format_func=lambda i: variants[i]['name'])
        acknowledge = st.checkbox('Replace this client’s quotation only with the selected Harsha revision')
        if st.button('Load selected quotation', disabled=not acknowledge):
            updated = deepcopy(current())
            updated['quote'] = deepcopy(variants[variant]['rows'])
            updated['sections'] = list(dict.fromkeys(r['Section'] for r in updated['quote']))
            updated['source'] = f"Supplied Harsha workbook — {variants[variant]['name']}; fixed amounts preserved. Final discounts / tax basis must be confirmed separately."
            updated['agreed_value'] = None
            updated['costs_complete'] = False
            try:
                save_project(updated)
                clear_editors()
                st.success('Quotation loaded. Enter the final agreed value on Profit if discounted.')
            except Exception:
                st.error('Quotation was not saved. Reload before trying again.')
    st.stop()

if not clients:
    st.info('Create your first client on the Clients page.')
    st.stop()

project = current()
st.subheader(project['name'])
st.caption(f"Project deadline: {project.get('deadline') or 'Not set'}")

sections_config = st.column_config.SelectboxColumn('Room / work heading', options=project['sections'])
deadline_config = st.column_config.TextColumn('Deadline (YYYY-MM-DD)', help='Example: 2026-12-01', validate=r'^$|^\d{4}-\d{2}-\d{2}$')
def numeric(label):
    return st.column_config.NumberColumn(label, min_value=0.0, step=0.01, format='%.2f')

if page == 'Costs':
    st.header('Quotation & project expenses')
    with st.expander('Add, rename or remove room / work headings'):
        with st.form('heading_add'):
            heading = st.text_input('New heading')
            add = st.form_submit_button('Add heading')
        if add and heading.strip():
            updated = deepcopy(current())
            if heading.strip() not in updated['sections']:
                updated['sections'].append(heading.strip())
                try:
                    save_project(updated); clear_editors(); st.rerun()
                except Exception:
                    st.error('Heading was not saved.')
        chosen = st.selectbox('Existing heading', project['sections']) if project['sections'] else None
        with st.form('heading_rename'):
            renamed = st.text_input('Replacement name')
            rename = st.form_submit_button('Rename heading')
        if rename and chosen and renamed.strip():
            updated = deepcopy(current())
            if renamed.strip() in updated['sections'] and renamed.strip() != chosen:
                st.error('That heading already exists.')
            else:
                updated['sections'] = [renamed.strip() if x == chosen else x for x in updated['sections']]
                for kind in ['quote', 'materials']:
                    for row in updated[kind]:
                        if row.get('Section') == chosen: row['Section'] = renamed.strip()
                try:
                    save_project(updated); clear_editors(); st.rerun()
                except Exception:
                    st.error('Heading was not renamed.')
        st.caption('A heading can be removed after its quote and material rows are reassigned or deleted.')
        if st.button('Remove selected heading', disabled=chosen is None):
            if any(r.get('Section') == chosen for k in ['quote', 'materials'] for r in current()[k]):
                st.warning('This heading has rows. Reassign or remove those rows first.')
            elif len(current()['sections']) <= 1:
                st.warning('Keep at least one heading.')
            else:
                updated = deepcopy(current()); updated['sections'].remove(chosen)
                try:
                    save_project(updated); clear_editors(); st.rerun()
                except Exception:
                    st.error('Heading was not removed.')
    st.markdown('#### Client quotation')
    st.caption('Prebuilt descriptions come from your workbook. sqft = Nos × height/depth × width. nos / lumpsum = Nos. Rate × quantity gives amount; an optional fixed-amount override takes precedence.')
    config = {c: numeric(c) for c in ['Nos', 'Height / depth (ft)', 'Width (ft)', 'Rate (INR)', 'Amount override (INR)']}
    config.update({'Section': sections_config, 'Unit': st.column_config.SelectboxColumn(options=['sqft', 'nos', 'lumpsum']), 'Deadline': deadline_config})
    editor('quote', QUOTE_COLUMNS, config)
    calculated = [{**r, **quote_line(r)} for r in current()['quote']]
    st.dataframe(pd.DataFrame(calculated)[['Section', 'Description', 'Quantity', 'Quoted amount (INR)']] if calculated else pd.DataFrame(), hide_index=True, width='stretch')
    st.metric('Quoted total', f"INR {totals(current())['quoted']:,.2f}")
    st.markdown('#### Other actual expenses')
    st.caption('Record labour, transport, installation and other spending here. Enter material purchases only on Materials so they are counted once.')
    config = {'Amount (INR)': numeric('Amount (INR)'), 'Deadline': deadline_config,
              'Category': st.column_config.SelectboxColumn(options=['Labour', 'Transport', 'Installation', 'Electrical labour', 'Painting', 'Overhead', 'Other']),
              'Status': st.column_config.SelectboxColumn(options=['Planned', 'Incurred', 'Paid'])}
    editor('expenses', EXPENSE_COLUMNS, config)
    st.caption('All entered expense rows, including planned commitments, are included in the project cost estimate.')

elif page == 'Materials':
    st.header('Materials & stores')
    st.caption('Add the material, purchasing store, quantity, purchase rate and deadline. Delivery charges are added once per row. All rows, including planned purchases, enter the cost estimate.')
    config = {c: numeric(c) for c in ['Quantity', 'Purchase rate (INR)', 'Delivery / other (INR)']}
    config.update({'Section': sections_config, 'Deadline': deadline_config,
                   'Purchase date': st.column_config.TextColumn('Purchase date (YYYY-MM-DD)'),
                   'Status': st.column_config.SelectboxColumn(options=['Planned', 'Ordered', 'Received', 'Paid'])})
    editor('materials', MATERIAL_COLUMNS, config)
    rows = [{**r, 'Purchase amount (INR)': material_amount(r)} for r in current()['materials']]
    st.metric('Recorded material purchases / commitments', f"INR {totals(current())['purchases']:,.2f}")
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')

elif page == 'Profit':
    st.header('Profit & collections')
    st.caption('Use the same tax basis for project value and expenses. The source workbook says taxes are included but provides no tax breakdown. This view does not calculate tax liabilities.')
    project = current()
    with st.form('profit_settings'):
        override = st.checkbox('Use a final agreed value instead of the quoted total', value=project.get('agreed_value') is not None)
        value = st.number_input('Final agreed project value (INR)', min_value=0.0, value=float(project.get('agreed_value') if project.get('agreed_value') is not None else totals(project)['quoted']), step=100.0)
        complete = st.checkbox('I have entered all project costs and checked the tax basis', value=project.get('costs_complete', False))
        submit = st.form_submit_button('Save project value & cost status', type='primary')
    if submit:
        updated = deepcopy(project)
        updated.update(agreed_value=value if override else None, costs_complete=complete)
        try:
            save_project(updated)
            st.success('Project value saved.')
        except Exception:
            st.error('Project value was not saved. Reload if another window changed it.')
    summary = totals(current())
    issues = completeness(current())
    cols = st.columns(3)
    cols[0].metric('Project value', f"INR {summary['revenue']:,.2f}")
    cols[1].metric('Recorded costs / commitments', f"INR {summary['cost']:,.2f}")
    label = 'Project surplus / (loss)' if current().get('costs_complete') and not issues else 'Provisional surplus / (loss)'
    cols[2].metric(label, f"INR {summary['profit']:,.2f}")
    st.write(f"**Margin:** {summary['margin']:.1f}%" if summary['margin'] is not None else '**Margin:** Not available for a zero project value')
    st.caption('Surplus = project value − material purchases − other recorded expenses. This is not cash received or statutory net profit; unrecorded overhead and tax adjustments are excluded.')
    if not current().get('costs_complete'):
        st.warning('Costs are not confirmed complete. The surplus is provisional, not earned profit.')
    if issues:
        with st.expander(f'{len(issues)} draft checks to review'):
            for issue in issues: st.write('• ' + issue)
    st.markdown('#### Payments received')
    editor('payments', PAYMENT_COLUMNS, {'Amount received (INR)': numeric('Amount received (INR)')})
    summary = totals(current())
    a,b = st.columns(2)
    a.metric('Payments received', f"INR {summary['receipts']:,.2f}")
    b.metric('Balance to collect / (overpaid)', f"INR {summary['outstanding']:,.2f}")
    with st.expander('Suggested payment milestones from the supplied workbook'):
        st.dataframe(pd.DataFrame([{'Milestone': n, 'Share': f'{v:.0%}', 'Amount (INR)': round(summary['revenue']*v, 2)} for n,v in [('Booking', .1), ('Design approval', .4), ('Before material dispatch', .3), ('Carcass installation', .15), ('Handover', .05)]]), hide_index=True)
    st.divider()
    st.subheader('Download project records')
    st.caption('The full workbook includes internal costs and profit. Use the quotation-only export when sharing with a client.')
    a,b = st.columns(2)
    with a:
        st.download_button('Full Excel workbook · internal', export_project(current(), LOGO), 'BYOT_project_internal.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', on_click='ignore')
    with b:
        st.download_button('Client quotation only', export_project(current(), LOGO, True), 'BYOT_client_quotation.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', on_click='ignore')
    st.download_button('Project backup (JSON)', json.dumps(current(), indent=2), 'BYOT_project_backup.json', 'application/json', on_click='ignore')

if page in ('Costs', 'Materials'):
    due = []
    for kind in ['quote', 'materials', 'expenses']:
        for r in current()[kind]:
            deadline = r.get('Deadline')
            if deadline:
                try:
                    day = date.fromisoformat(str(deadline))
                    if day < date.today() and r.get('Status') not in ('Paid', 'Received'):
                        due.append({'Item': r.get('Description') or r.get('Material') or r.get('Category'), 'Deadline': deadline})
                except ValueError:
                    st.warning(f'Check deadline {deadline}: use a valid YYYY-MM-DD date.')
    if due:
        with st.expander('Past-deadline entries to review'):
            st.dataframe(pd.DataFrame(due), hide_index=True)
