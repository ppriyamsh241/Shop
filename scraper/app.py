from __future__ import annotations

import csv
import io
import json
import os
import re
import socket
import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.robotparser import RobotFileParser
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, render_template, send_file, request

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 4 * 1024 * 1024
USER_AGENT = 'AdvancedPythonScraper/2.0'
TIMEOUT = 15
MAX_PAGE_BYTES = 3 * 1024 * 1024
MAX_CRAWL_PAGES = 100
MAX_SITEMAP_URLS = 500
MAX_ITEMS = 500
DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), 'downloads')
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
JOBS = {}
LOCK = threading.Lock()
STOPWORDS = set('a an and are as at be by for from has have he her hers him his i if in is it its me my of on or our ours she so than that the their theirs them then there these they this to was we were what when where which who will with you your yours about after again all also am any because been before being but can could did do does doing down during each few had how into more most no nor not now only other over own same should some such too very'.split())


def now():
    return datetime.now(timezone.utc).isoformat()


def normalize_url(url):
    url = (url or '').strip()
    if not re.match(r'^https?://', url, re.I):
        url = 'https://' + url
    return urldefrag(url)[0]


def validate_public_url(url):
    url = normalize_url(url)
    p = urlparse(url)
    if p.scheme not in {'http', 'https'} or not p.hostname:
        raise ValueError('Enter a valid public http(s) URL.')
    if p.hostname.lower() in {'localhost', 'localhost.localdomain'}:
        raise ValueError('Localhost URLs are not allowed.')
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f'Could not resolve hostname: {exc}') from exc
    for info in infos:
        ip = info[4][0]
        octets = [int(x) for x in ip.split('.') if x.isdigit()]
        private = (ip.startswith('127.') or ip.startswith('10.') or ip.startswith('192.168.') or ip.startswith('169.254.') or (len(octets) == 4 and octets[0] == 172 and 16 <= octets[1] <= 31) or ip == '0.0.0.0')
        if private:
            raise ValueError('Private or local network targets are not allowed.')
    return url


def allowed_by_robots(url):
    p = urlparse(url)
    rp = RobotFileParser(f'{p.scheme}://{p.netloc}/robots.txt')
    try:
        rp.read()
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        return True


def fetch_html(url):
    url = validate_public_url(url)
    if not allowed_by_robots(url):
        raise PermissionError('This URL is disallowed by robots.txt.')
    r = requests.get(url, headers={'User-Agent': USER_AGENT, 'Accept': 'text/html,application/xhtml+xml'}, timeout=TIMEOUT, allow_redirects=True, stream=True)
    r.raise_for_status()
    ct = r.headers.get('content-type', '').lower()
    if 'text/html' not in ct and 'application/xhtml+xml' not in ct:
        raise ValueError('The URL did not return an HTML page.')
    data = r.raw.read(MAX_PAGE_BYTES + 1, decode_content=True)
    r.close()
    if len(data) > MAX_PAGE_BYTES:
        raise ValueError('Page is larger than the configured 3 MB limit.')
    r._content = data
    return r


def soup_for(html):
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style', 'noscript', 'template', 'svg']):
        tag.decompose()
    return soup


def keywords(text, limit=100):
    words = re.findall(r"[A-Za-z][A-Za-z'-]{2,}", text.lower())
    c = Counter(w.strip("'-") for w in words if w not in STOPWORDS)
    return [{'keyword': w, 'count': n} for w, n in c.most_common(limit)]


def tables(soup):
    out = []
    for i, table in enumerate(soup.find_all('table')[:MAX_ITEMS], 1):
        rows = []
        for tr in table.find_all('tr')[:200]:
            cells = tr.find_all(['th', 'td'])
            if cells:
                rows.append([c.get_text(' ', strip=True) for c in cells])
        if rows:
            caption = table.find('caption')
            out.append({'index': i, 'caption': caption.get_text(' ', strip=True) if caption else '', 'rows': rows})
    return out


def pagination(soup, base):
    out = []
    for a in soup.find_all('a', href=True):
        text = a.get_text(' ', strip=True).lower()
        rel = ' '.join(a.get('rel', [])).lower()
        label = (a.get('aria-label') or '').lower()
        title = (a.get('title') or '').lower()
        if any(x in text for x in ('next', 'older', 'more')) or 'next' in rel or 'next' in label or 'next' in title:
            out.append(urljoin(base, a['href']))
    return list(dict.fromkeys(out))[:20]


def scrape_page(url, selector=''):
    requested = validate_public_url(url)
    r = fetch_html(requested)
    final = validate_public_url(r.url)
    soup = soup_for(r.text)
    text = re.sub(r'\s+', ' ', soup.get_text(' ', strip=True)).strip()
    links = []
    for a in soup.find_all('a', href=True)[:MAX_ITEMS]:
        href = urljoin(final, a['href'])
        try: href = validate_public_url(href)
        except ValueError: continue
        links.append({'text': a.get_text(' ', strip=True), 'url': href})
    images = [{'alt': (x.get('alt') or '').strip(), 'url': urljoin(final, x['src'])} for x in soup.find_all('img', src=True)[:MAX_ITEMS]]
    selected = []
    if selector:
        try: selected = [x.get_text(' ', strip=True) for x in soup.select(selector)[:MAX_ITEMS]]
        except Exception as exc: raise ValueError(f'Invalid CSS selector: {exc}') from exc
    return {'url': final, 'status_code': r.status_code, 'title': soup.title.get_text(' ', strip=True) if soup.title else '', 'headings': [x.get_text(' ', strip=True) for x in soup.find_all(['h1','h2','h3'])[:MAX_ITEMS]], 'links': links, 'images': images, 'selected': selected, 'tables': tables(soup), 'pagination': pagination(soup, final), 'keywords': keywords(text), 'text': text[:200000]}


def same_domain(a, b):
    return (urlparse(a).hostname or '').lower() == (urlparse(b).hostname or '').lower()


def crawl(start, max_pages, selector, follow_pagination=True):
    start = validate_public_url(start)
    max_pages = max(1, min(int(max_pages), MAX_CRAWL_PAGES))
    queue, seen, pages, combined = [start], set(), [], Counter()
    while queue and len(pages) < max_pages:
        url = urldefrag(queue.pop(0))[0]
        if url in seen: continue
        seen.add(url)
        try:
            page = scrape_page(url, selector)
            pages.append(page)
            for item in page['keywords']: combined[item['keyword']] += item['count']
            for link in page['links']:
                if same_domain(start, link['url']) and link['url'] not in seen and link['url'] not in queue: queue.append(link['url'])
            if follow_pagination:
                for nxt in page['pagination']:
                    if same_domain(start, nxt) and nxt not in seen and nxt not in queue: queue.append(nxt)
        except Exception as exc:
            pages.append({'url': url, 'error': str(exc)})
        time.sleep(0.25)
    return {'start_url': start, 'page_count': len(pages), 'pages': pages, 'keywords': [{'keyword': k, 'count': v} for k, v in combined.most_common(100)]}


def parse_sitemap(url):
    url = validate_public_url(url)
    if not allowed_by_robots(url): raise PermissionError('This sitemap is disallowed by robots.txt.')
    r = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=TIMEOUT)
    r.raise_for_status()
    root = ET.fromstring(r.content[:5 * 1024 * 1024])
    kind = root.tag.rsplit('}', 1)[-1]
    if kind == 'sitemapindex': vals = [n.text.strip() for n in root.findall('.//{*}sitemap/{*}loc') if n.text]
    elif kind == 'urlset': vals = [n.text.strip() for n in root.findall('.//{*}url/{*}loc') if n.text]
    else: raise ValueError('Unsupported sitemap XML format.')
    return list(dict.fromkeys(vals))[:MAX_SITEMAP_URLS]


def write_files(job_id, result):
    jp, cp = os.path.join(DOWNLOAD_DIR, job_id + '.json'), os.path.join(DOWNLOAD_DIR, job_id + '.csv')
    with open(jp, 'w', encoding='utf-8') as f: json.dump(result, f, ensure_ascii=False, indent=2)
    with open(cp, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f); w.writerow(['page','status','title','error','keywords'])
        for p in result.get('pages', []): w.writerow([p.get('url',''),p.get('status_code',''),p.get('title',''),p.get('error',''),', '.join(x['keyword'] for x in p.get('keywords',[]))])
    return jp, cp


def run_job(job_id, data):
    try:
        result = crawl(data['url'], data.get('max_pages', 20), data.get('selector',''), data.get('follow_pagination', True))
        jp, cp = write_files(job_id, result)
        with LOCK: JOBS[job_id].update(status='completed', result=result, json_path=jp, csv_path=cp, finished_at=now())
    except Exception as exc:
        with LOCK: JOBS[job_id].update(status='failed', error=str(exc), finished_at=now())


@app.get('/')
def index(): return render_template('index.html')

@app.post('/api/scrape')
def api_scrape():
    d = request.get_json(silent=True) or {}
    try: return jsonify(scrape_page(d.get('url',''), d.get('selector','').strip()))
    except PermissionError as e: return jsonify(error=str(e)), 403
    except requests.RequestException as e: return jsonify(error=f'Request failed: {e}'), 502
    except Exception as e: return jsonify(error=str(e)), 400

@app.post('/api/crawl')
def api_crawl():
    d = request.get_json(silent=True) or {}
    try: validate_public_url(d.get('url',''))
    except Exception as e: return jsonify(error=str(e)), 400
    job_id = uuid.uuid4().hex
    with LOCK: JOBS[job_id] = {'id': job_id, 'status': 'queued', 'created_at': now()}
    threading.Thread(target=run_job, args=(job_id,d), daemon=True).start()
    return jsonify(job_id=job_id, status='queued'), 202

@app.get('/api/jobs')
def api_jobs():
    with LOCK: jobs = list(JOBS.values())
    return jsonify(sorted([{k:v for k,v in j.items() if k not in {'result','json_path','csv_path'}} for j in jobs], key=lambda x:x['created_at'], reverse=True)[:50])

@app.get('/api/jobs/<job_id>')
def api_job(job_id):
    with LOCK: j = JOBS.get(job_id)
    if not j: return jsonify(error='Job not found.'), 404
    out = {k:v for k,v in j.items() if k not in {'json_path','csv_path'}}
    if j.get('status') == 'completed': out['downloads'] = {'json': f'/api/jobs/{job_id}/download/json', 'csv': f'/api/jobs/{job_id}/download/csv'}
    return jsonify(out)

@app.get('/api/jobs/<job_id>/download/<fmt>')
def api_download(job_id, fmt):
    if fmt not in {'json','csv'}: return jsonify(error='Format must be json or csv.'), 400
    with LOCK: j = JOBS.get(job_id)
    if not j or j.get('status') != 'completed': return jsonify(error='Completed job not found.'), 404
    return send_file(j[fmt + '_path'], as_attachment=True, download_name=f'crawl-{job_id}.{fmt}')

@app.post('/api/sitemap')
def api_sitemap():
    d = request.get_json(silent=True) or {}
    try:
        urls = parse_sitemap(d.get('url','')); return jsonify(url=normalize_url(d.get('url','')), count=len(urls), urls=urls)
    except requests.RequestException as e: return jsonify(error=f'Request failed: {e}'), 502
    except Exception as e: return jsonify(error=str(e)), 400

@app.post('/api/sitemap-crawl')
def api_sitemap_crawl():
    d = request.get_json(silent=True) or {}
    try: urls = parse_sitemap(d.get('url',''))[:max(1,min(int(d.get('max_pages',50)),MAX_CRAWL_PAGES))]
    except Exception as e: return jsonify(error=str(e)), 400
    result, combined = {'start_url': d.get('url',''), 'page_count':0, 'pages':[], 'keywords':[]}, Counter()
    for url in urls:
        try:
            p = scrape_page(url, d.get('selector','')); result['pages'].append(p)
            for item in p.get('keywords',[]): combined[item['keyword']] += item['count']
        except Exception as e: result['pages'].append({'url':url,'error':str(e)})
        time.sleep(0.25)
    result['page_count'] = len(result['pages']); result['keywords'] = [{'keyword':k,'count':v} for k,v in combined.most_common(100)]
    job_id = uuid.uuid4().hex; jp, cp = write_files(job_id,result)
    with LOCK: JOBS[job_id] = {'id':job_id,'status':'completed','created_at':now(),'finished_at':now(),'result':result,'json_path':jp,'csv_path':cp}
    return jsonify(job_id=job_id,status='completed',result=result,downloads={'json':f'/api/jobs/{job_id}/download/json','csv':f'/api/jobs/{job_id}/download/csv'})

@app.post('/api/export')
def export_data():
    d = request.get_json(silent=True) or {}; fmt = d.get('format','json').lower(); data = d.get('data',{})
    if fmt == 'csv':
        out = io.StringIO(); w = csv.writer(out); w.writerow(['type','text','url','value','page'])
        for p in data.get('pages',[data]):
            for x in p.get('links',[]): w.writerow(['link',x.get('text',''),x.get('url',''),' ',p.get('url','')])
            for x in p.get('images',[]): w.writerow(['image',x.get('alt',''),x.get('url',''),' ',p.get('url','')])
            for x in p.get('keywords',[]): w.writerow(['keyword',x.get('keyword',''),' ',x.get('count',''),p.get('url','')])
        return send_file(io.BytesIO(out.getvalue().encode('utf-8-sig')),mimetype='text/csv',as_attachment=True,download_name='scrape.csv')
    return send_file(io.BytesIO(json.dumps(data,ensure_ascii=False,indent=2).encode()),mimetype='application/json',as_attachment=True,download_name='scrape.json')

if __name__ == '__main__': app.run(host='127.0.0.1', port=5000, debug=True)
