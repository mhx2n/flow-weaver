# ──────────────────────────────────────────────────────────────────────────────
# Section: 28_ultrafast_stability_03_28
# Original lines: 14515..14971
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===== ULTRAFAST STABILITY PATCH (2026-03-28) =====
# Best-effort final override placed just before __main__ so it wins over older duplicates.
# Goals:
# - Keep existing features intact
# - Prefer faster/stabler backends first
# - Reduce raw JSON leakage into user-visible output
# - Reduce long-message / long-poll explanation issues
# - Keep group/tutorial UX unchanged

GEMINI_TIMEOUT_SECONDS = 12
GEMINI_TEXT_TIMEOUT_SECONDS = 7
GEMINI_VISION_TIMEOUT_SECONDS = 14
_G3_CACHE_TTL_SECONDS = 1200


def _requests_with_retries(method, url: str, *, json_payload=None, params=None, timeout=12, max_tries=2):
    import requests as _rq
    last_err = None
    tries = max(1, min(int(max_tries or 1), 2))
    for i in range(tries):
        try:
            r = method(url, json=json_payload, params=params, timeout=timeout)
            if getattr(r, 'status_code', 0) == 200:
                return r
            if _is_gemini_quota_error(getattr(r, 'status_code', 0), getattr(r, 'text', '')):
                raise RateLimitError(f"Gemini rate-limited/quota exhausted (HTTP {getattr(r, 'status_code', 0)}).")
            if getattr(r, 'status_code', 0) in (500, 502, 503, 504):
                last_err = RuntimeError(f"HTTP {r.status_code}: {str(getattr(r, 'text', ''))[:200]}")
            else:
                r.raise_for_status()
                return r
        except RateLimitError:
            raise
        except Exception as e:
            last_err = e
        if i + 1 < tries:
            time.sleep(0.25 * (i + 1))
    if last_err:
        raise last_err
    raise RuntimeError('Request failed.')


def _looks_like_json_blob(s: str) -> bool:
    t = str(s or '').strip()
    if not t:
        return False
    if t.startswith('{') and '"answer"' in t:
        return True
    if t.startswith('```json'):
        return True
    return False


def _sanitize_quiz_explanation_text(text: str) -> str:
    t = str(text or '').strip()
    if not t:
        return ''
    if _looks_like_json_blob(t):
        try:
            data = _extract_json_strict(t)
            if isinstance(data, dict):
                t = str(data.get('explanation') or data.get('answer_text') or '').strip() or t
        except Exception:
            pass
    t = clean_latex(t)
    t = re.sub(r'```(?:json)?', '', t, flags=re.I)
    t = re.sub(r'(?i)^json\s*[:\-]\s*', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _sanitize_answer_text(text: str) -> str:
    raw = str(text or '').strip()
    if not raw:
        return ''
    if _looks_like_json_blob(raw):
        try:
            data = _extract_json_strict(raw)
            if isinstance(data, dict):
                for key in ('explanation', 'answer_text', 'answer', 'response', 'text'):
                    val = data.get(key)
                    if isinstance(val, str) and val.strip():
                        raw = val.strip()
                        break
        except Exception:
            pass
    raw = clean_latex(raw)
    raw = re.sub(r'```(?:[A-Za-z0-9_+\-]+)?', '', raw)
    raw = re.sub(r'\\\((.*?)\\\)', r'\1', raw)
    raw = re.sub(r'\\\[(.*?)\\\]', r'\1', raw)
    raw = re.sub(r'(?m)^\s*>\s?', '', raw)
    raw = re.sub(r'\n{3,}', '\n\n', raw).strip()
    return raw


def _trim_expl_for_poll(expl: str, link: str = '') -> str:
    t = _sanitize_quiz_explanation_text(expl)
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if lines:
        t = '\n'.join(lines[:2])
    if link:
        link = str(link or '').strip()
        if link:
            t = (t + '\n' if t else '') + link
    t = t.strip()
    if len(t) > 160:
        t = t[:157].rstrip() + '...'
    return t


def _answer_to_tg_html(answer: str, *, model_name: str = '', preserve_code: bool = False) -> str:
    raw = _sanitize_answer_text(_trim_for_telegram(str(answer or ''), 3200))
    if preserve_code:
        title = f"<b>{h(model_name)}</b>\n\n" if model_name else ''
        return title + f"<pre>{h(raw)}</pre>"

    out_lines = []
    if model_name:
        out_lines.append(f"<b>{h(model_name)}</b>")
        out_lines.append('')

    for raw_line in raw.split('\n'):
        html_line = _line_to_tg_html(raw_line)
        if html_line == '':
            if out_lines and out_lines[-1] != '':
                out_lines.append('')
            continue
        out_lines.append(html_line)

    html = '\n'.join(out_lines).strip()
    html = re.sub(r'\n{3,}', '\n\n', html)
    return html or h(raw)


def scrape_fresh_session():
    session = requests.Session()
    url = 'https://gemini.google.com/app'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'cache-control': 'no-cache',
        'pragma': 'no-cache'
    }
    try:
        response = session.get(url, headers=headers, timeout=8)
        html = response.text
        cookies = {c.name: c.value for c in session.cookies}
        snlm0e = extract_snlm0e_token(html) or extract_from_script_tags(html)
        if not snlm0e:
            return None
        params = extract_build_and_session_params(html)
        return {
            'session': session,
            'cookies': cookies,
            'snlm0e': snlm0e,
            'bl': params['bl'],
            'fsid': params['fsid'],
            'reqid': params['reqid'],
            'html': html,
        }
    except Exception:
        return None


def chat_with_gemini(prompt):
    start_time = time.time()
    scraped = None
    now_ts = time.time()
    try:
        cached = _G3_CACHE.get('data')
        if cached and (now_ts - float(_G3_CACHE.get('ts') or 0.0) < _G3_CACHE_TTL_SECONDS):
            scraped = cached
    except Exception:
        scraped = None

    if not scraped:
        scraped = scrape_fresh_session()
        if not scraped:
            return {'success': False, 'error': 'Failed to establish session with Gemini'}
        _G3_CACHE['data'] = scraped
        _G3_CACHE['ts'] = now_ts

    session = scraped['session']
    cookies = scraped['cookies']
    snlm0e = scraped['snlm0e']
    bl = scraped['bl']
    fsid = scraped['fsid']
    reqid = int(time.time() * 1000) % 1000000
    url = f"https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate?bl={bl}&f.sid={fsid}&hl=en-US&_reqid={reqid}&rt=c"
    payload = build_payload(prompt, snlm0e)
    cookie_str = '; '.join([f"{k}={v}" for k, v in cookies.items()])
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
        'x-same-domain': '1',
        'origin': 'https://gemini.google.com',
        'referer': 'https://gemini.google.com/',
        'Cookie': cookie_str,
    }
    try:
        response = session.post(url, data=payload, headers=headers, timeout=10)
        if response.status_code != 200:
            return {'success': False, 'error': f'HTTP {response.status_code}'}
        result = parse_streaming_response(response.text)
        response_time = round(time.time() - start_time, 2)
        if result:
            return {
                'success': True,
                'response': _sanitize_answer_text(result),
                'metadata': {
                    'response_time': f'{response_time}s',
                    'timestamp': datetime.utcnow().isoformat() + 'Z',
                    'model': 'gemini',
                },
            }
        return {'success': False, 'error': 'No response received from Gemini'}
    except requests.exceptions.RequestException as e:
        return {'success': False, 'error': str(e)}


def _try_gemini_text_backends(prompt: str, *, timeout_seconds: int = 7) -> Tuple[str, str]:
    last_error: Optional[Exception] = None

    if USE_OFFICIAL_GEMINI_REST_FALLBACK and GEMINI_API_KEYS:
        try:
            out = call_gemini_text_rest(prompt, timeout_seconds=max(6, int(timeout_seconds or 7)))
            if out and str(out).strip():
                return _sanitize_answer_text(str(out).strip()), 'Gemini'
        except Exception as e:
            last_error = e

    if USE_PERPLEXITY_FALLBACK:
        try:
            alt = query_ai(prompt)
            if alt and str(alt).strip():
                return _sanitize_answer_text(str(alt).strip()), 'Perplexity'
        except Exception as e:
            last_error = e

    try:
        out = gemini3_solve(prompt)
        if out and str(out).strip():
            return _sanitize_answer_text(str(out).strip()), 'Gemini'
    except Exception as e:
        last_error = e

    raise RuntimeError(str(last_error or 'AI backend is temporarily unavailable. Please try again.'))


def _coerce_mcq_result(raw_text: str, option_count: int) -> Optional[Dict[str, Any]]:
    raw = str(raw_text or '').strip()
    if not raw:
        return None
    data = None
    try:
        data = _extract_json_strict(raw)
    except Exception:
        data = _repair_to_json(
            raw,
            schema_hint='{"answer":1,"confidence":0,"explanation":".","why_not":{"A":".","B":".","C":".","D":".","E":"."}}',
            timeout_seconds=8,
        )
    if isinstance(data, dict):
        ans = int(data.get('answer', 0) or 0)
        if not (1 <= ans <= option_count):
            ans = _infer_option_from_text(raw, option_count)
        explanation = _sanitize_quiz_explanation_text(str(data.get('explanation', '') or '').strip() or raw[:500])
        why_not_raw = data.get('why_not', {}) if isinstance(data.get('why_not', {}), dict) else {}
        why_not = {str(k): _sanitize_quiz_explanation_text(v) for k, v in why_not_raw.items()}
        result = {
            'answer': ans,
            'confidence': int(data.get('confidence', 0) or 0),
            'explanation': explanation,
            'why_not': why_not,
        }
        if result['answer'] > 0:
            return result
    inferred = _infer_option_from_text(raw, option_count)
    if inferred > 0:
        return {
            'answer': inferred,
            'confidence': 0,
            'explanation': _sanitize_quiz_explanation_text(raw[:500]),
            'why_not': {},
        }
    return None


def _solve_text_via_prompt(prompt: str, preferred: str = 'G') -> Tuple[str, str]:
    code = (preferred or 'G').upper()
    if code == 'P':
        try:
            out = query_ai(prompt)
            if out and str(out).strip():
                return _sanitize_answer_text(str(out).strip()), 'Perplexity'
        except Exception:
            pass
        return _try_gemini_text_backends(prompt, timeout_seconds=7)
    if code == 'D':
        try:
            out = deepseek_solve_text(prompt)
            if out and str(out).strip():
                return _sanitize_answer_text(str(out).strip()), 'DeepSeek'
        except Exception:
            pass
        return _try_gemini_text_backends(prompt, timeout_seconds=7)
    return _try_gemini_text_backends(prompt, timeout_seconds=7)


def _try_gemini_mcq_backends(question: str, options: List[str]) -> Tuple[Dict[str, Any], str]:
    prompt, opts = _build_mcq_json_prompt(question, options)
    last_error: Optional[Exception] = None

    if USE_OFFICIAL_GEMINI_REST_FALLBACK and GEMINI_API_KEYS:
        try:
            raw = call_gemini_text_rest(prompt, timeout_seconds=7, force_json=True)
            data = _coerce_mcq_result(raw, len(opts))
            if isinstance(data, dict) and int(data.get('answer', 0) or 0) > 0:
                return data, 'Gemini'
        except Exception as e:
            last_error = e

    if USE_PERPLEXITY_FALLBACK:
        try:
            alt = query_ai(prompt)
            data = _coerce_mcq_result(alt or '', len(opts))
            if isinstance(data, dict) and int(data.get('answer', 0) or 0) > 0:
                return data, 'Perplexity'
        except Exception as e:
            last_error = e

    try:
        raw = gemini3_solve(prompt)
        data = _coerce_mcq_result(raw, len(opts))
        if isinstance(data, dict) and int(data.get('answer', 0) or 0) > 0:
            return data, 'Gemini'
    except Exception as e:
        last_error = e

    raise RuntimeError(str(last_error or 'AI backend is temporarily unavailable. Please try again.'))


def generate_quiz_items_gemini_then_verify(seed_question: str, seed_options: List[str]) -> List[Dict[str, Any]]:
    sq = (seed_question or '').strip()
    so = _normalize_options(seed_options or [], max_n=4)
    is_bn = _is_bangla_text(sq + ' ' + ' '.join(so))
    lang_rule = _quiz_language_rule_block(is_bn)
    schema_expl = _quiz_schema_example_explanation(is_bn)

    prompt = (
        'Return STRICT JSON only (no markdown, no extra text).\n'
        'Task: You are given a SEED quiz question (MCQ) with options.\n'
        '1) Infer the MICRO-TOPIC strictly from the seed.\n'
        '2) Generate exactly 3 NEW MCQs from that same micro-topic only.\n'
        '3) Each MCQ must have 4 options and exactly one correct answer.\n'
        '4) Keep difficulty similar to admission-style questions.\n'
        f'5) {lang_rule}\n'
        '6) Keep explanation SHORT (1-2 lines max).\n\n'
        'JSON format:\n'
        '{\n'
        '  "topic": "<major topic>",\n'
        '  "microtopic": "<micro-topic>",\n'
        '  "items": [\n'
        '    {"question":"...","options":["...","...","...","..."],"answer":1,"explanation":"' + schema_expl + '"}\n'
        '  ]\n'
        '}\n\n'
        f'Seed Question:\n{sq}\n\n'
        'Seed Options:\n' + '\n'.join([f"{_safe_letter(i+1)}. {so[i]}" for i in range(len(so))])
    )

    raw = None
    last_err = None
    if USE_GEMINI_REST_FOR_GENQUIZ and GEMINI_API_KEYS:
        try:
            raw = call_gemini_text_rest(prompt, timeout_seconds=8, force_json=True)
        except Exception as e:
            last_err = e
            raw = None
    if not raw and USE_PERPLEXITY_FALLBACK:
        try:
            raw = query_ai(prompt)
        except Exception as e:
            last_err = e
            raw = None
    if not raw:
        try:
            raw = gemini3_solve(prompt)
        except Exception as e:
            last_err = e
            raw = None
    if not raw:
        raise RuntimeError(f'Quiz generation failed: {last_err or "all backends unavailable"}')

    schema_hint = '{"microtopic":"<micro>","items":[{"question":"...","options":["...","...","...","..."],"answer":1,"explanation":"..."}]}'
    try:
        data = _extract_json_strict(raw)
    except Exception:
        repaired = _repair_to_json(raw, schema_hint=schema_hint, timeout_seconds=8)
        if not repaired:
            raise RuntimeError('Quiz generation failed: invalid JSON response.')
        data = repaired
    if not isinstance(data, dict):
        raise RuntimeError('Quiz generation failed.')

    items = data.get('items', []) or []
    out: List[Dict[str, Any]] = []
    for it in items[:3]:
        q = str(it.get('question', '')).strip()
        opts = _normalize_options([str(x) for x in (it.get('options', []) or [])], max_n=4)
        ans = int(it.get('answer', 0) or 0)
        expl = _sanitize_quiz_explanation_text(str(it.get('explanation', '')).strip())
        try:
            ver = perplexity_solve_mcq_json(q, opts)
            vans = int((ver or {}).get('answer', 0) or 0)
            vexpl = _sanitize_quiz_explanation_text(str((ver or {}).get('explanation', '') or '').strip())
            if 1 <= vans <= 4:
                ans = vans
            if vexpl:
                expl = vexpl
        except Exception:
            pass
        if q and opts and 1 <= ans <= 4:
            out.append({'question': q, 'options': opts, 'answer': ans, 'explanation': expl})
    return out[:3]


def _extract_message_text_for_ai(update: Update) -> str:
    msg = getattr(update, 'message', None)
    if not msg:
        return ''
    text = str(getattr(msg, 'text', '') or getattr(msg, 'caption', '') or '').strip()
    if text.startswith('/sh ') or text.startswith('.sh '):
        return text.split(' ', 1)[1].strip()
    return text


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err_text = str(context.error or '')
    err_l = err_text.lower()
    if 'message_too_long' in err_l or 'message is too long' in err_l:
        logger.warning('Suppressed long-message error: %s', err_text[:200])
        db_log('WARN', 'message_too_long', {'error': err_text[:120]})
        return
    if 'query is too old' in err_l or 'query_id_invalid' in err_l:
        logger.warning('Suppressed stale-callback error: %s', err_text[:200])
        db_log('WARN', 'stale_callback', {'error': err_text[:120]})
        return
    logger.exception('Unhandled error: %s', context.error)
    db_log('ERROR', 'unhandled_exception', {'error': err_text[:180]})

# ===== END ULTRAFAST STABILITY PATCH =====



