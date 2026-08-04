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

DOW_NOMES = ['Domingo','Segunda','Terça','Quarta','Quinta','Sexta','Sábado']

def _fu(v):
    """+12,3u / -4,8u"""
    v = float(v)
    s = f"{abs(v):,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("+" if v >= 0 else "-") + s + "u"

def _fi(v):
    return f"{int(v):,}".replace(",", ".")

def _t_hoje_1a(d):
    x = d.get('hoje_1a') or {}
    if not x.get('n'): return None
    return f"📅 Neste dia, há exatamente 1 ano: {x['n']} entradas registradas e {_fu(x['pl'])} no fechamento."

def _t_mes(d):
    m = d.get('mes') or {}
    if m.get('atual') is None or m.get('ano_passado') is None: return None
    return f"🗓️ O mês atual está em {_fu(m['atual'])}. O mesmo mês do ano passado fechou em {_fu(m['ano_passado'])}."

def _t_top30(d):
    x = d.get('top30') or {}
    if not x.get('nome'): return None
    return f"🏆 Tipster mais lucrativo dos últimos 30 dias: {x['nome']} — {_fu(x['pl'])} a {x['roi']}% de ROI."

def _t_oddg(d):
    x = d.get('oddg30') or {}
    if not x.get('odd'): return None
    return f"🎯 Maior odd que virou green nos últimos 30 dias: {x['odd']} — {x['evento']} ({x.get('tipster') or '—'})."

def _t_hist(d):
    x = d.get('hist') or {}
    if not x.get('n'): return None
    return f"📚 A operação já registrou {_fi(x['n'])} apostas e {_fi(x['inv'])}u investidas — P/L histórico de {_fu(x['pl'])}."

def _t_streak(d):
    dias = d.get('d15') or []
    if len(dias) < 2: return None
    seq = 0; sinal = None
    for row in reversed(dias):
        pl = float(row.get('pl') or 0)
        s = 1 if pl > 0 else (-1 if pl < 0 else 0)
        if s == 0: break
        if sinal is None: sinal = s
        if s != sinal: break
        seq += 1
    if seq < 2: return None
    if sinal > 0:
        return f"🔥 A operação vem de {seq} dias seguidos no verde."
    return f"🧊 São {seq} dias seguidos no vermelho — hora de virar o jogo."

def _t_dow(d):
    x = d.get('dow') or {}
    if x.get('idx') is None: return None
    return f"📊 Historicamente, {DOW_NOMES[int(x['idx'])]} é o melhor dia da semana da operação: {_fu(x['pl'])} acumuladas."

def _t_pico(d):
    x = d.get('pico') or {}
    if x.get('falta') is None: return None
    falta = float(x['falta'])
    if falta <= 0:
        return "🏔️ A operação está NO PICO histórico de lucro — cada green a partir daqui é recorde novo."
    return f"🏔️ Faltam {_fu(falta)[1:]} para bater o pico histórico de lucro da operação."

def _t_g7(d):
    x = d.get('g7') or {}
    if not x.get('u'): return None
    return f"💎 Maior green da semana: {_fu(x['u'])} — {x['evento']} ({x.get('tipster') or '—'})."

def _t_media15(d):
    dias = d.get('d15') or []
    if len(dias) < 10: return None
    tot = sum(float(r.get('pl') or 0) for r in dias)
    med = tot / len(dias)
    if med >= 0:
        return f"📈 Média dos últimos {len(dias)} dias: {_fu(med)} por dia — ritmo de {_fu(med*30)} ao mês."
    return f"📉 Média dos últimos {len(dias)} dias: {_fu(med)} por dia. Fase de reconstrução."

def _t_verdes15(d):
    dias = d.get('d15') or []
    if len(dias) < 10: return None
    verdes = sum(1 for r in dias if float(r.get('pl') or 0) > 0)
    return f"🟢 Dos últimos {len(dias)} dias, {verdes} fecharam no verde ({round(verdes/len(dias)*100)}%)."

DOW_FRASE = {0:'os domingos', 1:'as segundas', 2:'as terças', 3:'as quartas',
             4:'as quintas', 5:'as sextas', 6:'os sábados'}

def _t_100k(d):
    x = d.get('hist') or {}
    n = int(x.get('n') or 0)
    if not n: return None
    if n >= 100000:
        return f"🎯 Marco cruzado: a operação já passou das 100.000 apostas registradas ({_fi(n)})."
    return f"🎯 Faltam {_fi(100000 - n)} apostas para a operação cruzar as 100.000 registradas."

def _t_pior_dia_dist(d):
    x = d.get('pior_dia') or {}
    if not x.get('d'): return None
    dias = (brt_now().date() - datetime.strptime(x['d'], '%Y-%m-%d').date()).days
    return (f"🩹 O pior dia da história ({_fu(x['pl'])}) foi há {dias} dias. "
            f"Desde então: {_fu(x['desde'])} acumuladas.")

def _t_melhor_mes(d):
    x = d.get('melhor_mes') or {}
    m = d.get('mes') or {}
    if not x.get('m') or m.get('atual') is None: return None
    mm = f"{x['m'][5:7]}/{x['m'][2:4]}"
    atual = float(m['atual']); recorde = float(x['pl'])
    mes_atual_str = brt_now().strftime('%Y-%m')
    if x['m'] == mes_atual_str or atual >= recorde:
        return f"👑 O mês atual já é o melhor da história da operação: {_fu(atual)}."
    return (f"👑 O melhor mês da história segue sendo {mm}: {_fu(recorde)}. "
            f"O atual está a {_fu(recorde - atual)[1:]} de alcançá-lo.")

def _t_bookie30(d):
    x = d.get('bookie30') or {}
    if not x.get('nome'): return None
    return f"🏦 Casa mais acionada nos últimos 30 dias: {x['nome']}, {_fi(x['n'])} entradas."

def _t_acerto(d):
    x = d.get('acerto') or {}
    if x.get('mes') is None or x.get('hist') is None: return None
    return f"✅ Taxa de acerto do mês: {x['mes']}% — histórico da operação: {x['hist']}%."

def _t_odd_tipica(d):
    x = d.get('odd_media') or {}
    if x.get('semana') is None or x.get('hist') is None: return None
    s, h = float(x['semana']), float(x['hist'])
    if abs(s - h) < 0.10:
        tom = "em linha com o padrão histórico"
    elif s > h:
        tom = "semana mais agressiva que o padrão"
    else:
        tom = "semana mais conservadora que o padrão"
    return f"⚖️ Odd típica (mediana) da semana: {s:.2f} vs {h:.2f} do histórico — {tom}."

def _t_dow_hoje(d):
    arr = d.get('dow_todos') or []
    if not arr: return None
    idx = (brt_now().weekday() + 1) % 7  # Python Mon=0 → Postgres Sun=0
    reg = next((r for r in arr if int(r.get('idx', -1)) == idx), None)
    if not reg: return None
    return f"📆 Hoje é {DOW_NOMES[idx]} — historicamente, {DOW_FRASE[idx]} somam {_fu(reg['pl'])} pra operação."

def _t_dia_volume(d):
    x = d.get('dia_volume') or {}
    if not x.get('d'): return None
    dt = x['d']
    return f"🌊 O dia mais movimentado da história: {dt[8:10]}/{dt[5:7]}/{dt[2:4]}, {_fi(x['n'])} entradas registradas."

TEMPLATES_CURIOSIDADE = [_t_100k, _t_pior_dia_dist, _t_melhor_mes, _t_bookie30, _t_acerto, _t_odd_tipica, _t_dow_hoje, _t_dia_volume, _t_media15, _t_verdes15, _t_pico, _t_top30, _t_hoje_1a, _t_g7, _t_dow, _t_streak, _t_oddg, _t_mes, _t_hist]

JANELA_ANTI_REPETICAO = 8  # últimos envios proibidos de repetir (2 dias com 4/dia)

def job_curiosidade(slot=0):
    """Uma curiosidade sobre a operação, 4x/dia, sem repetir template na janela."""
    try:
        headers = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}',
                   'Content-Type': 'application/json'}
        r = requests.post(f"{SUPABASE_URL}/rest/v1/rpc/curiosidades_operacao",
                          headers=headers, json={}, timeout=20)
        r.raise_for_status()
        dados = r.json()

        # memória: índices enviados recentemente ficam proibidos
        proibidos = set()
        try:
            rl = requests.get(
                f"{SUPABASE_URL}/rest/v1/bot_curiosidades_log"
                f"?select=template_idx&order=id.desc&limit={JANELA_ANTI_REPETICAO}",
                headers=headers, timeout=15
            )
            rl.raise_for_status()
            proibidos = {row['template_idx'] for row in rl.json()}
        except Exception as e:
            print(f"  ⚠️ Log de curiosidades indisponível ({e}); sigo sem memória")

        n = len(TEMPLATES_CURIOSIDADE)
        base = (brt_now().timetuple().tm_yday * 4 + slot) % n
        frase, escolhido = None, None
        # 1ª volta: fora da janela e com dado; 2ª volta: qualquer um com dado
        for exigir_inedito in (True, False):
            for i in range(n):
                idx = (base + i) % n
                if exigir_inedito and idx in proibidos: continue
                frase = TEMPLATES_CURIOSIDADE[idx](dados)
                if frase:
                    escolhido = idx
                    break
            if frase: break
        if not frase: return

        send_telegram(f"💡 *Curiosidade da operação*\n{frase}")
        try:
            requests.post(f"{SUPABASE_URL}/rest/v1/bot_curiosidades_log",
                          headers=headers, json={'template_idx': escolhido}, timeout=15)
        except Exception:
            pass
        print(f"  💡 Curiosidade enviada (slot {slot}, template {escolhido})")
    except Exception as e:
        print(f"  ❌ Erro no job_curiosidade: {e}")

MSG_MISSOES = ("🎁 *Checklist de início de turno:*\n"
               "Ativem as missões da Betano nas contas — missão ativada é aposta grátis garantida. "
               "Não deixem freebet na mesa.")

MSG_SALDOS_TURNO = ("🧭 *Início de turno:*\n"
                    "Deem uma olhada nos saldos disponíveis nas principais casas — "
                    "saber onde tem munição é o que define a prioridade de uso no dia.")

def job_saldos_turno():
    try:
        send_telegram(MSG_SALDOS_TURNO)
        print("  🧭 Lembrete de saldos/prioridade enviado")
    except Exception as e:
        print(f"  ❌ Erro no job_saldos_turno: {e}")

def job_missoes():
    try:
        # dia sim, dia não (paridade do dia no calendário — não depende de restart)
        if brt_now().date().toordinal() % 2 != 0:
            return
        send_telegram(MSG_MISSOES)
        print("  🎁 Lembrete de missões enviado")
    except Exception as e:
        print(f"  ❌ Erro no job_missoes: {e}")

def main():
    print("🚀 Monitor Mercado Esportivo iniciado")
    # Relatório de saldos DESATIVADO em 30/07/26 a pedido do Samuel.
    # (funções job/build_message permanecem; reativar = reagendar HORARIOS aqui)
    print("   Relatório de saldos: desativado")
    schedule.clear()

    # Aviso diário de apostas penduradas — 11:00 BRT (14:00 UTC)
    schedule.every().day.at("14:00").do(job_penduradas)
    print("   11:00 BRT → 14:00 UTC agendado (penduradas)")

    # Vigia de silêncio no Planilhar — checa a cada 5 min
    schedule.every(5).minutes.do(job_silencio)
    print("   Vigia de silêncio ativo (90min, turnos 07:00-14:30 / 14:30-22:00 BRT)")

    # Saldos/prioridade do dia — início de cada turno (07:30 / 15:00 BRT)
    schedule.every().day.at("10:30").do(job_saldos_turno)
    schedule.every().day.at("18:00").do(job_saldos_turno)
    print("   07:30 e 15:00 BRT agendados (saldos/prioridade do turno)")

    # Lembrete de missões Betano — 08:30 BRT, dia sim dia não
    schedule.every().day.at("11:30").do(job_missoes)
    print("   08:30 BRT agendado (missões Betano, dia sim dia não)")

    # Curiosidades da operação — 09:30 / 12:30 / 17:30 / 21:30 BRT
    schedule.every().day.at("12:30").do(job_curiosidade, slot=0)
    schedule.every().day.at("15:30").do(job_curiosidade, slot=1)
    schedule.every().day.at("20:30").do(job_curiosidade, slot=2)
    schedule.every().day.at("00:30").do(job_curiosidade, slot=3)
    print("   09:30, 12:30, 17:30 e 21:30 BRT agendados (curiosidades)")

    print("\n   Aguardando próximo horário...\n")
    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == '__main__':
    main()
