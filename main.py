"""
Monitor de Saldos - Mercado Esportivo
Roda na nuvem (Railway). Dispara às 06:59 / 14:29 / 21:55 (horário de Brasília).
"""

import re, requests, schedule, time
from datetime import datetime, timedelta, timezone

# ============================================================
SUPABASE_URL     = "https://yfdrifvhsiumdxgypkjm.supabase.co"
SUPABASE_KEY     = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlmZHJpZnZoc2l1bWR4Z3lwa2ptIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTkzMjg0OCwiZXhwIjoyMDkxNTA4ODQ4fQ.s1R7Akclh0LxGkljtHaBHCSJgbU9SFL8pvQArIiXsXQ"
TELEGRAM_TOKEN   = "8011340494:AAF9QJc8Dx1DBzpIPyKJSkKoiSTNwqYJXq0"
TELEGRAM_CHAT_ID = "-4659428992"
# ============================================================

# Horários de Brasília (UTC-3)
HORARIOS = ["06:59", "14:29", "21:55"]

EXCLUDED_TEXT  = {'LIMITADA', 'INATIVA', 'DESATIVADA', 'SACADA'}
SALDO_BAIXO    = 500.0
IMPORTACAO     = {'importação planilha', 'importacao planilha', 'importação'}

CASAS_ALVO = {
    'BET365', 'BETANO', 'BETFAIR',
    'BATEUBET', 'ESPORTIVA', 'BETVIP', 'MC GAMES', 'CASSINOBET',
    'GOLDEBET', 'JOGO DE OURO', 'PAGOLBET',
    'APOSTAGANHA', 'BLAZE',
    '7KBET', 'PINNACLE', 'BETBOO', 'KTO', 'BETFAST', 'BETNACIONAL',
}

GRUPOS = {
    'Principais' : ['BET365', 'BETANO', 'BETFAIR'],
    'Estrela'    : ['BATEUBET', 'ESPORTIVA', 'BETVIP', 'MC GAMES',
                    'CASSINOBET', 'GOLDEBET', 'JOGO DE OURO', 'PAGOLBET'],
    'Outras'     : ['APOSTAGANHA', 'BLAZE', '7KBET', 'PINNACLE',
                    'BETBOO', 'KTO', 'BETFAST', 'BETNACIONAL'],
}

LABELS = {
    'BET365'      : '🟢 Bet365',    'BETANO'      : '🟠 Betano',
    'BETFAIR'     : '🟡 Betfair',   'APOSTAGANHA' : 'Aposta Ganha',
    'BLAZE'       : 'Blaze',        'BATEUBET'    : 'Bateubet',
    'ESPORTIVA'   : 'Esportiva',    'BETVIP'      : 'Betvip',
    'MC GAMES'    : 'MC Games',     'CASSINOBET'  : 'Cassinobet',
    'GOLDEBET'    : 'Goldebet',     'JOGO DE OURO': 'Jogo de Ouro',
    'PAGOLBET'    : 'Pagolbet',     '7KBET'       : '7kBet',
    'PINNACLE'    : 'Pinnacle',     'BETBOO'      : 'Betboo',
    'KTO'         : 'KTO',          'BETFAST'     : 'Betfast',
    'BETNACIONAL' : 'Betnacional',
}

CONTAR_CONTAS   = {'BET365', 'BETANO', 'BETFAIR', 'KTO'}
SEMPRE_MOSTRAR  = {'BETBOO', 'KTO'}
GRUPO_SEM_LOGIN = {'Estrela'}


def brl(v):
    return f"R$ {v:_.2f}".replace('.', ',').replace('_', '.')

def fmt_data(iso):
    if not iso: return '—'
    try:
        dt = datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(timezone(timedelta(hours=-3)))
        return dt.strftime('%d/%m %H:%M')
    except:
        return '—'

def fmt_user(user):
    if not user or user.lower().strip() in IMPORTACAO:
        return None
    return user

def is_recente(iso, horas=24):
    if not iso: return False
    try:
        dt = datetime.fromisoformat(iso.replace('Z', '+00:00'))
        return (datetime.now(timezone.utc) - dt) <= timedelta(hours=horas)
    except:
        return False

def simplify_login(login):
    login = str(login or '').strip()
    digits = re.sub(r'\D', '', login)
    if len(digits) >= 8:
        return digits[:4] + '...'
    if '@' in login:
        parts = re.split(r'[._\-]', login.split('@')[0])
        parts = [re.sub(r'[^a-zA-Z]', '', p) for p in parts if len(re.sub(r'[^a-zA-Z]', '', p)) >= 2]
        name  = parts[0] if parts else re.sub(r'[^a-zA-Z]', '', login.split('@')[0])
    else:
        name = re.sub(r'[^a-zA-Z]', '', login)
    return name[:8].capitalize() if name else '?'

def is_inativa(s):
    if not s: return False
    return any(x in s.strip().upper() for x in EXCLUDED_TEXT)

def is_alerta(s):
    if not s: return False
    return not s.strip().upper() == 'ATIVA' and not is_inativa(s)

def fetch_contas():
    headers = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/contas?select=casa,saldo,situacao,login,atualizado_em,atualizado_por&order=casa.asc",
        headers=headers, timeout=15
    )
    r.raise_for_status()
    return r.json()

def parse_data(contas):
    data = {k: {
        'available': 0.0, 'contas': 0, 'saldos': [],
        'yellow': [], 'atualizadas': [], 'sem_att': []
    } for k in CASAS_ALVO}

    for c in contas:
        casa     = (c.get('casa') or '').strip().upper()
        if casa not in CASAS_ALVO: continue
        saldo    = float(c.get('saldo') or 0)
        situacao = c.get('situacao') or ''
        login    = c.get('login') or ''
        att_em   = c.get('atualizado_em') or ''
        att_por  = c.get('atualizado_por') or ''

        if is_inativa(situacao):
            pass
        elif is_alerta(situacao):
            data[casa]['yellow'].append({
                'login': login, 'situacao': situacao,
                'atualizado_em': att_em, 'atualizado_por': att_por,
            })
        else:
            data[casa]['available'] += saldo
            data[casa]['contas']    += 1
            data[casa]['saldos'].append(saldo)
            info = {'login': login, 'atualizado_em': att_em, 'atualizado_por': att_por}
            if is_recente(att_em):
                data[casa]['atualizadas'].append(info)
            else:
                data[casa]['sem_att'].append(info)

    return data

def build_message(data):
    brt = datetime.now(timezone(timedelta(hours=-3)))
    now = brt.strftime('%d/%m/%Y %H:%M')
    lines = ["📊 *Bookie Balances*", f"🕐 {now}", ""]
    all_yellow = []

    for grupo, casas in GRUPOS.items():
        sem_login = grupo in GRUPO_SEM_LOGIN
        lines.append(f"*{grupo}*")
        lines.append("")

        for casa in casas:
            d = data.get(casa)
            if not d: continue
            av, ct, saldos = d['available'], d['contas'], d['saldos']
            yw = d['yellow']
            label = LABELS.get(casa, casa)
            all_yellow.extend([(label, y) for y in yw])

            if av <= 0 and not yw and casa not in SEMPRE_MOSTRAR:
                continue

            linha = f"*{label}: {brl(av)}*"
            if casa in CONTAR_CONTAS:
                linha += f" _({ct} contas)_"
            baixas = [s for s in saldos if s < SALDO_BAIXO]
            if baixas:
                linha += f" ⚠️ _{len(baixas)} abaixo de {brl(SALDO_BAIXO)}_"
            lines.append(linha)

            if not sem_login:
                for cc in d['atualizadas']:
                    nome = simplify_login(cc['login'])
                    user = fmt_user(cc['atualizado_por'])
                    user_str = f" · {user}" if user else ""
                    lines.append(f"  ✔️ {nome} — att {fmt_data(cc['atualizado_em'])}{user_str}")
                if d['sem_att']:
                    nomes = ' / '.join(simplify_login(cc['login']) for cc in d['sem_att'])
                    lines.append(f"  ⏳ {nomes} — sem att nas últimas 24h")
            else:
                if d['atualizadas']:
                    att  = d['atualizadas'][0]
                    user = fmt_user(att['atualizado_por'])
                    user_str = f" · {user}" if user else ""
                    lines.append(f"  ✔️ att {fmt_data(att['atualizado_em'])}{user_str}")
                elif d['sem_att']:
                    lines.append(f"  ⏳ sem att nas últimas 24h")
            lines.append("")
        lines.append("")

    return '\n'.join(lines)

def send_telegram(message):
    url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    requests.post(url, json=payload, timeout=15).raise_for_status()

def job():
    try:
        brt = datetime.now(timezone(timedelta(hours=-3)))
        print(f"[{brt:%H:%M:%S}] Executando...")
        contas  = fetch_contas()
        print(f"  {len(contas)} contas carregadas")
        data    = parse_data(contas)
        message = build_message(data)
        send_telegram(message)
        print("  ✅ Mensagem enviada")
    except Exception as e:
        print(f"  ❌ Erro: {e}")

def job_penduradas():
    """Aviso diário: apostas PENDING cujo evento já passou (resolver no dash)."""
    try:
        headers = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}
        hoje = (datetime.utcnow() - timedelta(hours=3)).strftime('%Y-%m-%d')
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/apostas"
            f"?select=data_evento,evento,entrada,stake_unidades,tipster:tipster_id(nome)"
            f"&status=eq.PENDING&data_evento=lt.{hoje}&order=data_evento.asc&limit=15",
            headers=headers, timeout=15
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            print("  ✅ Nenhuma aposta pendurada")
            return
        lines = [f"⏰ *{len(rows)} aposta(s) pendente(s) com evento já encerrado:*", ""]
        for a in rows[:10]:
            d = a.get('data_evento') or ''
            d_fmt = f"{d[8:10]}/{d[5:7]}" if len(d) >= 10 else d
            tip = (a.get('tipster') or {}).get('nome') or '—'
            ev  = (a.get('evento') or a.get('entrada') or '?')[:40]
            su  = a.get('stake_unidades')
            su_str = f" ({su}u)" if su is not None else ""
            lines.append(f"• {d_fmt} — {tip} — {ev}{su_str}")
        if len(rows) > 10:
            lines.append(f"_… e mais {len(rows) - 10}_")
        lines.append("")
        lines.append("_Resolver no dash de registros._")
        send_telegram('\n'.join(lines))
        print(f"  ⏰ Aviso de {len(rows)} pendurada(s) enviado")
    except Exception as e:
        print(f"  ❌ Erro no job_penduradas: {e}")

# ── Aviso de silêncio no Planilhar ─────────────────────────────────
# Turnos (BRT): 07:00–14:30 e 14:30–22:00. O relógio de silêncio ZERA na
# virada de turno (o turno que entra não herda o buraco do anterior) e fora
# da janela não conta. Avisa aos 90min e re-avisa a cada 90min enquanto o
# silêncio durar (90/180/270...). Mensagens rotativas de rotina.
TURNO_MANHA  = (7, 0)
TURNO_TARDE  = (14, 30)
FIM_JANELA   = (22, 0)
SILENCIO_MIN = 90

_ultimo_aviso_silencio = None
_msg_idx = 0
MSGS_SILENCIO = [
    "⏸️ *{m} min sem registros no Planilhar.*\nBom momento pra resolver as apostas pendentes do dia no dash.",
    "⏸️ *{m} min sem registros no Planilhar.*\nAproveita pra atualizar no dash o saldo das contas que vocês usaram hoje (apostas, saques ou depósitos).",
    "⏸️ *{m} min sem registros no Planilhar.*\nVale revisar as apostas marcadas com 🤨 e corrigir o que ficou pendente.",
]

def brt_now():
    return datetime.utcnow() - timedelta(hours=3)

def job_silencio():
    global _ultimo_aviso_silencio, _msg_idx
    try:
        agora = brt_now()
        hm = (agora.hour, agora.minute)
        if hm < TURNO_MANHA or hm >= FIM_JANELA:
            _ultimo_aviso_silencio = None
            return
        turno = TURNO_TARDE if hm >= TURNO_TARDE else TURNO_MANHA
        t_ini = agora.replace(hour=turno[0], minute=turno[1], second=0, microsecond=0)

        headers = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/apostas?select=criado_em&order=criado_em.desc&limit=1",
            headers=headers, timeout=15
        )
        r.raise_for_status()
        rows = r.json()
        last_bet = None
        if rows and rows[0].get('criado_em'):
            dt = datetime.fromisoformat(rows[0]['criado_em'].replace('Z', '+00:00'))
            last_bet = dt.replace(tzinfo=None) - timedelta(hours=3)

        ref = max(x for x in (last_bet, t_ini) if x is not None)
        pode_reavisar = (_ultimo_aviso_silencio is None
                         or _ultimo_aviso_silencio < ref
                         or (agora - _ultimo_aviso_silencio) >= timedelta(minutes=SILENCIO_MIN))
        if (agora - ref) >= timedelta(minutes=SILENCIO_MIN) and pode_reavisar:
            send_telegram(MSGS_SILENCIO[_msg_idx % len(MSGS_SILENCIO)].format(m=SILENCIO_MIN))
            _ultimo_aviso_silencio = agora
            _msg_idx += 1
            print(f"  ⏸️ Aviso de silêncio enviado ({SILENCIO_MIN}min, turno {turno[0]:02d}:{turno[1]:02d})")
    except Exception as e:
        print(f"  ❌ Erro no job_silencio: {e}")

MSG_MISSOES = ("🎁 *Checklist de início de turno:*\n"
               "Ativem as missões da Betano nas contas — missão ativada é aposta grátis garantida. "
               "Não deixem freebet na mesa.")

def job_missoes():
    try:
        send_telegram(MSG_MISSOES)
        print("  🎁 Lembrete de missões enviado")
    except Exception as e:
        print(f"  ❌ Erro no job_missoes: {e}")

def main():
    print("🚀 Monitor Mercado Esportivo iniciado")
    print(f"   Horários programados (BRT): {', '.join(HORARIOS)}")

    for h in HORARIOS:
        schedule.every().day.at(h).do(job)

    # Força horário BRT no scheduler (Railway roda em UTC)
    # Ajuste: BRT = UTC-3, então convertemos os horários
    schedule.clear()
    for h in HORARIOS:
        hh, mm = map(int, h.split(':'))
        utc_hh = (hh + 3) % 24
        utc_time = f"{utc_hh:02d}:{mm:02d}"
        schedule.every().day.at(utc_time).do(job)
        print(f"   {h} BRT → {utc_time} UTC agendado")

    # Aviso diário de apostas penduradas — 11:00 BRT (14:00 UTC)
    schedule.every().day.at("14:00").do(job_penduradas)
    print("   11:00 BRT → 14:00 UTC agendado (penduradas)")

    # Vigia de silêncio no Planilhar — checa a cada 5 min
    schedule.every(5).minutes.do(job_silencio)
    print("   Vigia de silêncio ativo (90min, turnos 07:00-14:30 / 14:30-22:00 BRT)")

    # Lembrete de missões Betano — início de cada turno (07:30 / 15:00 BRT)
    schedule.every().day.at("10:30").do(job_missoes)
    schedule.every().day.at("18:00").do(job_missoes)
    print("   07:30 e 15:00 BRT agendados (missões Betano)")

    print("\n   Aguardando próximo horário...\n")
    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == '__main__':
    main()
