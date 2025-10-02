import os
import sys
import random
import time
import json
import requests
import re
from threading import Thread, Event
from bs4 import BeautifulSoup
import telebot
from telebot import types

# ---------------- إعدادات البوت ----------------
TELEGRAM_BOT_TOKEN = "8326165115:AAHqyCRzBhUyxYeOHIBIFSG-po70Tyko_g4"
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
USER_SESSIONS = {}
RUNNING_CYCLES = {}

# ---------------- إعدادات الـ API ----------------
AUTH_URL = 'https://mobile.vodafone.com.eg/auth/realms/vf-realm/protocol/openid-connect/token'
FAMILY_API_URL = "https://web.vodafone.com.eg/services/dxl/cg/customerGroupAPI/customerGroup"
CLIENT_ID = 'ana-vodafone-app'
CLIENT_SECRET = '95fd95fb-7489-4958-8ae6-d31a525cd20a'

SUBDOMAINS = [
    "mobile.vodafone.com.eg", "web.vodafone.com.eg", "010hotline.vodafone.com.eg", "dev.vodafone.com.eg",
    "digital.vodafone.com.eg", "ecommerce.vodafone.com.eg", "einvoice.vodafone.com.eg", "sb.vodafone.com.eg",
    "sm.vodafone.com.eg", "tenantapp.vodafone.com.eg", "workplace.vodafone.com.eg",
]

USER_AGENTS = [
    "Mozilla/5.0 (iPhone14,3; U; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/602.1.50 (KHTML, like Gecko) Version/15.0 Mobile/19A346 Safari/602.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]

DEFAULT_CONFIG = {
    'total_attempts': 10,  # تغيّرت لـ 10 زي الرسالة
    'delays': {"1": 300.0, "2": 10.0, "3": 10.0, "4": 300.0, "5": 10.0},
    'task_order': [1, 2, 5, 3, 4],
    'sync_tasks': [5, 3],
    'retries_accept': 3,
    'retries_add_remove': 3,
    'use_proxies': False
}

# ---------------- الدوال المساعدة ----------------
def get_fresh_token(phone_number, password):
    url = AUTH_URL
    headers = {"Content-Type": "application/x-www-form-urlencoded", "User-Agent": random.choice(USER_AGENTS)}
    data = {"username": phone_number, "password": password, "grant_type": "password",
            "client_secret": CLIENT_SECRET, "client_id": CLIENT_ID}
    try:
        response = requests.post(url, headers=headers, data=data, timeout=20)
        response.raise_for_status()
        return response.json().get("access_token")
    except Exception:
        return None

def is_token_valid(access_token, owner_number, user_agent):
    url = FAMILY_API_URL
    headers = create_headers(access_token, random.choice(SUBDOMAINS), user_agent, owner_number)
    try:
        response = requests.get(url, headers=headers, timeout=10)
        return response.status_code in [200, 201]
    except requests.exceptions.RequestException:
        return False

def create_headers(access_token_val, subdomain, user_agent, owner_number):
    return {
        "Authorization": f"Bearer {access_token_val}",
        "msisdn": owner_number,
        "Accept": "application/json",
        "Content-Type": "application/json; charset=UTF-8",
        "User-Agent": user_agent,
        "Origin": f"https://{subdomain}",
        "Referer": f"https://{subdomain}/spa/familySharing",
        "clientId": "WebsiteConsumer"
    }

def change_quota(access_token, owner_number, member_number, quota, user_agent, subdomain, proxy=None):
    url = FAMILY_API_URL
    headers = create_headers(access_token, subdomain, user_agent, owner_number)
    payload = {"category": [{"listHierarchyId": "TemplateID", "value": "47"}],
               "parts": {"characteristicsValue": {"characteristicsValue": [{"characteristicName": "quotaDist1", "type": "percentage", "value": quota}]},
                         "member": [{"id": [{"schemeName": "MSISDN", "value": owner_number}], "type": "Owner"},
                                    {"id": [{"schemeName": "MSISDN", "value": member_number}], "type": "Member"}]},
               "type": "QuotaRedistribution"}
    proxy_to_use = {"http": proxy, "https": proxy} if proxy else None
    try:
        response = requests.patch(url, headers=headers, json=payload, proxies=proxy_to_use, timeout=30)
        return response.status_code in [200, 201], f"تم {'بنجاح' if response.status_code in [200, 201] else 'بفشل'}"
    except Exception:
        return False, "خطأ في الاتصال"

def add_family_member(access_token, owner_number, member_number, quota_value, user_agent, subdomain, max_retries, proxy=None):
    url = FAMILY_API_URL
    headers = create_headers(access_token, subdomain, user_agent, owner_number)
    payload = {"name": "FlexFamily", "type": "SendInvitation", "category": [
        {"value": "523", "listHierarchyId": "PackageID"}, {"value": "47", "listHierarchyId": "TemplateID"},
        {"value": "523", "listHierarchyId": "TierID"}, {"value": "percentage", "listHierarchyId": "familybehavior"}],
        "parts": {"member": [{"id": [{"value": owner_number, "schemeName": "MSISDN"}], "type": "Owner"},
                             {"id": [{"value": member_number, "schemeName": "MSISDN"}], "type": "Member"}],
                  "characteristicsValue": {"characteristicsValue": [{"characteristicName": "quotaDist1", "value": str(40), "type": "percentage"}]}}}
    proxy_to_use = {"http": proxy, "https": proxy} if proxy else None
    for _ in range(max_retries):
        try:
            response = requests.post(url, data=json.dumps(payload), headers=headers, proxies=proxy_to_use, timeout=45)
            if response.status_code in [200, 201, 204]:
                return True, "تم إرسال الدعوة بنجاح"
        except Exception:
            pass
        time.sleep(2)
    return False, "فشل إرسال الدعوة"

def accept_invitation(member_token, owner_number, member_number, user_agent, subdomain, proxy=None):
    url = FAMILY_API_URL
    headers = {"Authorization": f"Bearer {member_token}", "msisdn": member_number,
               "Accept": "application/json", "Content-Type": "application/json; charset=UTF-8",
               "User-Agent": user_agent, "Origin": f"https://{subdomain}",
               "Referer": f"https://{subdomain}/spa/familySharing", "clientId": "WebsiteConsumer"}
    payload = {"category": [{"listHierarchyId": "TemplateID", "value": "47"}],
               "name": "FlexFamily", "parts": {"member": [{"id": [{"schemeName": "MSISDN", "value": owner_number}], "type": "Owner"},
                                                    {"id": [{"schemeName": "MSISDN", "value": member_number}], "type": "Member"}]},
               "type": "AcceptInvitation"}
    proxy_to_use = {"http": proxy, "https": proxy} if proxy else None
    try:
        response = requests.patch(url, headers=headers, json=payload, proxies=proxy_to_use, timeout=30)
        return response.status_code in [200, 201], f"تم {'قبول الدعوة' if response.status_code in [200, 201] else 'بفشل'}"
    except Exception:
        return False, "خطأ في الاتصال"

def remove_flex_family_member(access_token, owner_number, member_number, user_agent, subdomain, max_retries, proxy=None):
    url = FAMILY_API_URL
    headers = create_headers(access_token, subdomain, user_agent, owner_number)
    payload = {"name": "FlexFamily", "type": "FamilyRemoveMember", "category": [{"value": "47", "listHierarchyId": "TemplateID"}],
               "parts": {"member": [{"id": [{"value": owner_number, "schemeName": "MSISDN"}], "type": "Owner"},
                                    {"id": [{"value": member_number, "schemeName": "MSISDN"}], "type": "Member"}],
                         "characteristicsValue": {"characteristicsValue": [{"characteristicName": "Disconnect", "value": "0"},
                                                                          {"characteristicName": "LastMemberDeletion", "value": "1"}]}}}
    proxy_to_use = {"http": proxy, "https": proxy} if proxy else None
    for _ in range(max_retries):
        try:
            response = requests.patch(url, data=json.dumps(payload), headers=headers, proxies=proxy_to_use, timeout=30)
            if response.status_code in [200, 201]:
                return True, "تم حذف العضو بنجاح"
        except Exception:
            pass
        time.sleep(2)
    return False, "فشل حذف العضو"

def get_flex_amount(owner_number, owner_password):
    try:
        import string
        nonce = ''.join(random.choice(string.ascii_lowercase) for _ in range(10))
        with requests.Session() as session:
            base_url = 'https://web.vodafone.com.eg/auth/realms/vf-realm/protocol/openid-connect/auth'
            redirect_uri = 'https://web.vodafone.com.eg/ar/KClogin'
            url_action = f"{base_url}?client_id=website&redirect_uri={redirect_uri}&state=random_state&response_mode=query&response_type=code&scope=openid&nonce={nonce}&kc_locale=en"
            response_url_action = session.get(url_action)
            soup = BeautifulSoup(response_url_action.content, 'html.parser')
            form_action = soup.find('form').get('action')
            headers = {'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                       'Content-Type': 'application/x-www-form-urlencoded', 'Origin': 'https://web.vodafone.com.eg',
                       'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36'}
            data = {'username': owner_number, 'password': owner_password}
            response_login = session.post(form_action, headers=headers, data=data, allow_redirects=False)
            if 'Location' in response_login.headers and 'code=' in response_login.headers['Location']:
                code = response_login.headers['Location'].split('code=')[1]
                headers_token = {'Accept': '*/*', 'Content-Type': 'application/x-www-form-urlencoded',
                                 'Origin': 'https://web.vodafone.com.eg',
                                 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36'}
                data_token = {'code': code, 'grant_type': 'authorization_code', 'client_id': 'website', 'redirect_uri': redirect_uri}
                token_response = session.post('https://web.vodafone.com.eg/auth/realms/vf-realm/protocol/openid-connect/token', headers=headers_token, data=data_token)
                token = token_response.json().get('access_token')
                if token:
                    url = f'https://web.vodafone.com.eg/services/dxl/usage/usageConsumptionReport?bucket.product.publicIdentifier={owner_number}&@type=aggregated'
                    headers = {'channel': 'MOBILE', 'useCase': 'Promo', 'Authorization': f'Bearer {token}',
                               'api-version': 'v2', 'x-agent-operatingsystem': '11', 'clientId': 'AnaVodafoneAndroid',
                               'x-agent-device': 'OPPO CPH2059', 'x-agent-version': '2024.3.3', 'x-agent-build': '593',
                               'msisdn': owner_number, 'Content-Type': 'application/json', 'Accept': 'application/json',
                               'Accept-Language': 'ar', 'Host': 'web.vodafone.com.eg', 'Connection': 'Keep-Alive',
                               'Accept-Encoding': 'gzip', 'User-Agent': 'okhttp/4.11.0'}
                    response = requests.get(url, headers=headers)
                    pattern = r'"usageType":"limit","bucketBalance":\[\{"remainingValue":\{"amount":(.*?),"units":"FLEX"'
                    match = re.search(pattern, response.text)
                    return int(float(match.group(1))) if match else None
        return None
    except Exception:
        return None

# ---------------- إدارة الجلسات ----------------
def reset_user_session(user_id):
    USER_SESSIONS[user_id] = {
        'step': 0,
        'config': DEFAULT_CONFIG.copy(),
        'results': [],
        'proxies_list': [],
        'flex_amount': None,
        'running': False,
        'current_token': None,
        'failed_attempts': 0
    }
    RUNNING_CYCLES[user_id] = False

def get_user_session(message):
    user_id = message.from_user.id
    if user_id not in USER_SESSIONS:
        reset_user_session(user_id)
    return USER_SESSIONS[user_id]

def save_user_config(user_id):
    config = USER_SESSIONS[user_id]['config']
    with open(f'basic_config_{user_id}.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

def load_user_config(user_id):
    filename = f'basic_config_{user_id}.json'
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

# ---------------- الكود الأساسي ----------------
def run_flex_cycle(message):
    user_id = message.from_user.id
    session = get_user_session(message)
    config = session['config']
    proxies_list = session['proxies_list']
    total_attempts = config['total_attempts']
    cycle_count = 0

    for i in range(total_attempts):
        if not RUNNING_CYCLES[user_id]:
            bot.send_message(message.chat.id, "⏹️ تم إيقاف الدورة.")
            break

        summary_msgs = []
        bot.send_message(message.chat.id, f"🔁 بدأت حلقة رقم {i+1}/{total_attempts} ...")
        
        current_token = session['current_token']
        current_ua = random.choice(USER_AGENTS)
        if not current_token or not is_token_valid(current_token, config['owner_number'], current_ua):
            bot.send_message(message.chat.id, "🔑 جاري تجديد التوكن...")
            current_token = get_fresh_token(config['owner_number'], config['owner_password'])
            if not current_token:
                bot.send_message(message.chat.id, "❌ فشل تجديد التوكن، تخطي الحلقة.")
                session['failed_attempts'] += 1
                if session['failed_attempts'] >= 3:
                    time.sleep(300)  # انتظر 5 دقايق لو فشل 3 مرات
                    session['failed_attempts'] = 0
                continue
            session['current_token'] = current_token
            bot.send_message(message.chat.id, "✅ تم تجديد التوكن بنجاح!")
        summary_msgs.append("🔑 التوكن: ✅")

        current_proxy = random.choice(proxies_list) if config['use_proxies'] and proxies_list else None
        
        bot.send_message(message.chat.id, "⏳ جاري تغيير حصة العضو الأول إلى 10%...")
        ok, msg = change_quota(current_token, config['owner_number'], config['member1_number'], "10", current_ua, random.choice(SUBDOMAINS), current_proxy)
        summary_msgs.append(f"1️⃣ تغيير الحصة إلى 10%: {'✅' if ok else '❌'} {msg}")
        bot.send_message(message.chat.id, f"1️⃣ تغيير الحصة إلى 10%: {'✅' if ok else '❌'} {msg}")
        time.sleep(config['delays']["1"])
        
        bot.send_message(message.chat.id, "📩 جاري إرسال دعوة للعضو الثاني...")
        ok, msg = add_family_member(current_token, config['owner_number'], config['member2_number'], "40", current_ua, random.choice(SUBDOMAINS), config['retries_add_remove'], current_proxy)
        summary_msgs.append(f"2️⃣ دعوة العضو الثاني: {'✅' if ok else '❌'} {msg}")
        bot.send_message(message.chat.id, f"2️⃣ دعوة العضو الثاني: {'✅' if ok else '❌'} {msg}")
        time.sleep(config['delays']["2"])
        
        bot.send_message(message.chat.id, "⏳ انتظار 60 ثانية...")
        time.sleep(60.0)
        
        bot.send_message(message.chat.id, "🔄 جاري تنفيذ المهمتين المتزامنتين...")
        member2_token = get_fresh_token(config['member2_number'], config['member2_password'])
        if member2_token:
            sync_event = Event()
            accept_success = [False]
            quota_success = [False]
            start_time = time.time()

            def run_accept():
                ok, msg = accept_invitation(member2_token, config['owner_number'], config['member2_number'], current_ua, random.choice(SUBDOMAINS), current_proxy)
                accept_success[0] = ok
                bot.send_message(message.chat.id, f"👥 قبول الدعوة: {'✅' if ok else '❌'} {msg}")
                sync_event.set()

            def run_quota():
                ok, msg = change_quota(current_token, config['owner_number'], config['member1_number'], "40", current_ua, random.choice(SUBDOMAINS), current_proxy)
                quota_success[0] = ok
                bot.send_message(message.chat.id, f"💼 تغيير الحصة إلى 40%: {'✅' if ok else '❌'} {msg}")
                sync_event.set()

            thread1 = Thread(target=run_accept)
            thread2 = Thread(target=run_quota)
            thread1.start()
            thread2.start()

            thread1.join(timeout=15)
            thread2.join(timeout=15)
            sync_event.wait(timeout=1)

            if not thread1.is_alive() and not thread2.is_alive() and accept_success[0] and quota_success[0]:
                bot.send_message(message.chat.id, "✅ المهمتان اكتملتا!")
                summary_msgs.append("3️⃣ قبول الدعوة وتغيير الحصة: ✅")
            else:
                bot.send_message(message.chat.id, "❌ فشل التزامن.")
                summary_msgs.append("3️⃣ قبول الدعوة وتغيير الحصة: ❌")
        else:
            bot.send_message(message.chat.id, "❌ فشل الحصول على توكن العضو الثاني.")
            summary_msgs.append("3️⃣ فشل توكن العضو الثاني.")
        time.sleep(config['delays']["3"])
        
        bot.send_message(message.chat.id, "🗑️ جاري حذف العضو الثاني...")
        ok, msg = remove_flex_family_member(current_token, config['owner_number'], config['member2_number'], current_ua, random.choice(SUBDOMAINS), config['retries_add_remove'], current_proxy)
        summary_msgs.append(f"4️⃣ حذف العضو الثاني: {'✅' if ok else '❌'} {msg}")
        bot.send_message(message.chat.id, f"4️⃣ حذف العضو الثاني: {'✅' if ok else '❌'} {msg}")
        time.sleep(config['delays']["4"])
        
        bot.send_message(message.chat.id, "📊 جاري استرجاع كمية الفليكس...")
        flex_amount = get_flex_amount(config['owner_number'], config['owner_password'])
        flex_msg = f"💡 كمية فليكس: {flex_amount or 'غير متوفرة'}"
        summary_msgs.append(flex_msg)
        bot.send_message(message.chat.id, flex_msg)
        time.sleep(config['delays']["5"])

        bot.send_message(message.chat.id, "📋 الملخص:\n" + "\n".join(summary_msgs))

        cycle_count += 1
        if cycle_count % 5 == 0 and i + 1 < total_attempts:
            rest_time = random.uniform(10 * 60, 15 * 60)
            bot.send_message(message.chat.id, f"⏸️ راحة {rest_time/60:.1f} دقايق...")
            time.sleep(rest_time)
            bot.send_message(message.chat.id, "▶️ استئناف الدورة.")

    if RUNNING_CYCLES[user_id]:
        bot.send_message(message.chat.id, "🎉 اكتمال جميع الحلقات!")
        RUNNING_CYCLES[user_id] = False
        session['running'] = False

# ---------------- أوامر البوت ----------------
@bot.message_handler(commands=['start', 'help'])
def handle_start(message):
    reset_user_session(message.from_user.id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("بدء دورة إدارة مجموعة فليكس"), types.KeyboardButton("عرض الإعدادات الحالية"))
    markup.add(types.KeyboardButton("stop"))
    bot.send_message(message.chat.id, "👋 أهلاً بك! اختر من اللوحة:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "عرض الإعدادات الحالية")
def show_settings(message):
    session = get_user_session(message)
    conf = session['config']
    bot.reply_to(message, f"🔢 تكرارات: {conf['total_attempts']}\n⏱️ تأخيرات: {conf['delays']}\n🔀 مهام: {conf['task_order']}\n🔄 متزامنة: {conf['sync_tasks']}\n🧑‍💼 مالك: {conf.get('owner_number', '---')}\n👥 عضو1: {conf.get('member1_number', '---')}\n👥 عضو2: {conf.get('member2_number', '---')}\n🌐 بروكسي: {'نعم' if conf['use_proxies'] else 'لا'}", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: m.text == "بدء دورة إدارة مجموعة فليكس")
def ask_owner_number(message):
    session = get_user_session(message)
    if session['running']:
        bot.send_message(message.chat.id, "⚠️ دورة جارية! استخدم /stop.")
        return
    session['step'] = 1
    bot.send_message(message.chat.id, "👤 أدخل رقم المالك:")

@bot.message_handler(func=lambda m: get_user_session(m)['step'] == 1)
def ask_owner_pass(message):
    session = get_user_session(message)
    session['config']['owner_number'] = message.text.strip()
    session['step'] = 2
    bot.send_message(message.chat.id, "🔒 أدخل كلمة مرور المالك:")

@bot.message_handler(func=lambda m: get_user_session(m)['step'] == 2)
def ask_member1(message):
    session = get_user_session(message)
    session['config']['owner_password'] = message.text.strip()
    session['step'] = 3
    bot.send_message(message.chat.id, "👥 أدخل رقم العضو الأول:")

@bot.message_handler(func=lambda m: get_user_session(m)['step'] == 3)
def ask_member2(message):
    session = get_user_session(message)
    session['config']['member1_number'] = message.text.strip()
    session['step'] = 4
    bot.send_message(message.chat.id, "👥 أدخل رقم العضو الثاني:")

@bot.message_handler(func=lambda m: get_user_session(m)['step'] == 4)
def ask_member2_pass(message):
    session = get_user_session(message)
    session['config']['member2_number'] = message.text.strip()
    session['step'] = 5
    bot.send_message(message.chat.id, "🔑 أدخل كلمة مرور العضو الثاني:")

@bot.message_handler(func=lambda m: get_user_session(m)['step'] == 5)
def ask_proxy(message):
    session = get_user_session(message)
    session['config']['member2_password'] = message.text.strip()
    session['step'] = 6
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("نعم", "لا")
    bot.send_message(message.chat.id, "هل تريد بروكسيات؟", reply_markup=markup)

@bot.message_handler(func=lambda m: get_user_session(m)['step'] == 6)
def finish_config(message):
    session = get_user_session(message)
    use_proxy = message.text.strip() == "نعم"
    session['config']['use_proxies'] = use_proxy
    session['step'] = 7
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("نعم", "لا")
    bot.send_message(message.chat.id, "هل تريد حفظ الإعدادات؟", reply_markup=markup)

@bot.message_handler(func=lambda m: get_user_session(m)['step'] == 7)
def ask_total_attempts(message):
    session = get_user_session(message)
    saveit = message.text.strip() == "نعم"
    if saveit:
        save_user_config(message.from_user.id)
        bot.send_message(message.chat.id, "✅ تم الحفظ!", reply_markup=types.ReplyKeyboardRemove())
    else:
        bot.send_message(message.chat.id, "تم تجاهل الحفظ.", reply_markup=types.ReplyKeyboardRemove())
    session['step'] = 8
    bot.send_message(message.chat.id, "🔢 أدخل عدد التكرارات:")

@bot.message_handler(func=lambda m: get_user_session(m)['step'] == 8)
def final_save_and_start(message):
    session = get_user_session(message)
    try:
        total_attempts = int(message.text.strip())
        if total_attempts <= 0:
            bot.send_message(message.chat.id, "⚠️ العدد أكبر من صفر!")
            return
        session['config']['total_attempts'] = total_attempts
        session['step'] = 0
        session['running'] = True
        RUNNING_CYCLES[message.from_user.id] = True
        bot.send_message(message.chat.id, f"🚦 بدء الدورة بعد {total_attempts} تكرار...")
        run_flex_cycle(message)
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ ادخل رقم صحيح!")
        session['step'] = 8

@bot.message_handler(commands=['stop'])
def stop_cycle(message):
    user_id = message.from_user.id
    if user_id in RUNNING_CYCLES and RUNNING_CYCLES[user_id]:
        RUNNING_CYCLES[user_id] = False
        session = get_user_session(message)
        session['running'] = False
        bot.send_message(message.chat.id, "⏹️ تم إيقاف الدورة!")
    else:
        bot.send_message(message.chat.id, "⚠️ لا توجد دورة جارية.")

# ---------------- تشغيل البوت ----------------
if __name__ == "__main__":
    try:
        print("🤖 الكود جاهز للعبث! 😈")
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("تم إيقاف البوت.")
        sys.exit(0)
    except Exception as e:
        print(f"خطأ: {e}")
        sys.exit(1)
