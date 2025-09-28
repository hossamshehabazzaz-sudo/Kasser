import os
import sys
import random
import time
import json
import requests
import re
import traceback
from threading import Thread, Event
from bs4 import BeautifulSoup
from colorama import init, Fore, Style
import telebot
from telebot import types
from datetime import datetime

# --- تهيئة الألوان ---
init(autoreset=True)

# --- إعدادات البوت ---
TELEGRAM_BOT_TOKEN = "7894565052:AAGua5sTPiNw8Y1SehVH-6KDMPaxEyChPgI"

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
USER_SESSIONS = {}  # لكل مستخدم بياناته
RUNNING_CYCLES = {}  # لتتبع الدورات الجارية

# --- تعريفات الألوان ---
BRIGHT_YELLOW = Style.BRIGHT + Fore.YELLOW
WHITE = Fore.WHITE
CYAN = Fore.CYAN
ERROR_COLOR = Style.BRIGHT + Fore.RED
SUCCESS_COLOR = Style.BRIGHT + Fore.GREEN
MAGENTA = Style.BRIGHT + Fore.MAGENTA
GOLD = Style.BRIGHT + Fore.LIGHTYELLOW_EX
RESET = Style.RESET_ALL
BOLD = Style.BRIGHT

# --- البيانات الأساسية ---
NAME = f"{BOLD}{MAGENTA}مـاتصلوا ع النبي ツ❥{RESET}"

# --- إعدادات الـ API ---
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
    'total_attempts': 20,  # قيمة افتراضية، هتتغير حسب إدخال المستخدم
    'delays': {
        "1": 300.0,
        "2": 10.0,
        "3": 10.0,
        "4": 300.0,
        "5": 10.0
    },
    'task_order': [1, 2, 5, 3, 4],
    'sync_tasks': [5, 3],
    'retries_accept': 3,
    'retries_add_remove': 3,
    'subdomains_config': {
        "quota_10": 1,
        "add_member": 1,
        "quota_40": 1,
        "remove_member": 1
    },
    'use_proxies': False
}

def print_success(message):
    print(f"{SUCCESS_COLOR}✅ {message}{RESET}")

def print_error(message):
    print(f"{ERROR_COLOR}❌ {message}{RESET}")

def print_info(message):
    print(f"{CYAN}ℹ️  {message}{RESET}")

def print_warning(message):
    print(f"{BRIGHT_YELLOW}⚠️  {message}{RESET}")

def print_step(message):
    print(f"{MAGENTA}🚀 {message}{RESET}")

# --- Telegram interactions helpers ---

def reset_user_session(user_id):
    USER_SESSIONS[user_id] = {
        'step': 0,
        'config': DEFAULT_CONFIG.copy(),
        'results': [],
        'proxies_list': [],
        'flex_amount': None,
        'running': False,
        'current_token': None,  # لتخزين التوكن الحالي
        'last_quota': None  # لتخزين النسخة السابقة عشان نتجنى التكرار
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

# --- API helpers ---

def get_fresh_token(phone_number, password):
    url = AUTH_URL
    headers = {"Content-Type": "application/x-www-form-urlencoded", "User-Agent": random.choice(USER_AGENTS)}
    data = {"username": phone_number, "password": password, "grant_type": "password",
            "client_secret": CLIENT_SECRET, "client_id": CLIENT_ID}
    try:
        response = requests.post(url, headers=headers, data=data, timeout=20)
        response.raise_for_status()
        access_token = response.json().get("access_token")
        return access_token
    except Exception as e:
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
    subdomain_to_use = subdomain if subdomain else random.choice(SUBDOMAINS)
    base_headers = {
        "Authorization": f"Bearer {access_token_val}",
        "msisdn": owner_number,
        "Accept": "application/json",
        "Content-Type": "application/json; charset=UTF-8",
        "User-Agent": user_agent,
        "Origin": f"https://{subdomain_to_use}",
        "Referer": f"https://{subdomain_to_use}/spa/familySharing",
        "clientId": "WebsiteConsumer"
    }
    return base_headers

def change_quota(access_token, owner_number, member_number, quota, user_agent, subdomain, proxy=None):
    url = FAMILY_API_URL
    headers = create_headers(access_token, subdomain, user_agent, owner_number)
    payload = {
        "category": [{"listHierarchyId": "TemplateID", "value": "47"}],
        "parts": {
            "characteristicsValue": {"characteristicsValue": [{"characteristicName": "quotaDist1", "type": "percentage", "value": quota}]},
            "member": [{"id": [{"schemeName": "MSISDN", "value": owner_number}], "type": "Owner"},
                       {"id": [{"schemeName": "MSISDN", "value": member_number}], "type": "Member"}]
        }, "type": "QuotaRedistribution"
    }
    proxy_to_use = {"http": proxy, "https": proxy} if proxy else None
    try:
        response = requests.patch(url, headers=headers, json=payload, proxies=proxy_to_use, timeout=30)
        if response.status_code in [200, 201]:
            return True, "تم تغيير الحصة بنجاح"
        return False, f"فشل تغيير الحصة: {response.status_code}"
    except Exception as e:
        return False, f"خطأ: {e}"

def add_family_member(access_token, owner_number, member_number, quota_value, user_agent, subdomain, max_retries, proxy=None):
    url = FAMILY_API_URL
    headers = create_headers(access_token, subdomain, user_agent, owner_number)
    payload = {
      "name": "FlexFamily", "type": "SendInvitation", "category": [
        {"value": "523", "listHierarchyId": "PackageID"}, {"value": "47", "listHierarchyId": "TemplateID"},
        {"value": "523", "listHierarchyId": "TierID"}, {"value": "percentage", "listHierarchyId": "familybehavior"}
      ], "parts": { "member": [
          {"id": [{"value": owner_number, "schemeName": "MSISDN"}], "type": "Owner"},
          {"id": [{"value": member_number, "schemeName": "MSISDN"}], "type": "Member"}
        ], "characteristicsValue": {
          "characteristicsValue": [{"characteristicName": "quotaDist1", "value": "10", "type": "percentage"}]  # تم تعديل القيمة إلى 10
        }
      }
    }
    proxy_to_use = {"http": proxy, "https": proxy} if proxy else None
    for attempt in range(max_retries):
        try:
            response = requests.post(url, data=json.dumps(payload), headers=headers, proxies=proxy_to_use, timeout=45)
            if response.status_code in [200, 201, 204]:
                return True, "تم إرسال الدعوة بنجاح"
        except Exception as e:
            pass
        time.sleep(2)
    return False, "فشل إرسال الدعوة بعد عدة محاولات"

def accept_invitation(member_token, owner_number, member_number, user_agent, subdomain, proxy=None):
    url = FAMILY_API_URL
    headers = {
        "Authorization": f"Bearer {member_token}",
        "msisdn": member_number,
        "Accept": "application/json",
        "Content-Type": "application/json; charset=UTF-8",
        "User-Agent": user_agent,
        "Origin": f"https://{subdomain}",
        "Referer": f"https://{subdomain}/spa/familySharing",
        "clientId": "WebsiteConsumer"
    }
    payload = {
        "category": [{"listHierarchyId": "TemplateID", "value": "47"}],
        "name": "FlexFamily",
        "parts": {
            "member": [
                {"id": [{"schemeName": "MSISDN", "value": owner_number}], "type": "Owner"},
                {"id": [{"schemeName": "MSISDN", "value": member_number}], "type": "Member"}
            ]
        },
        "type": "AcceptInvitation"
    }
    proxy_to_use = {"http": proxy, "https": proxy} if proxy else None
    try:
        response = requests.patch(url, headers=headers, json=payload, proxies=proxy_to_use, timeout=30)
        if response.status_code in [200, 201]:
            return True, "تم قبول الدعوة"
        return False, f"فشل قبول الدعوة: {response.status_code}"
    except Exception as e:
        return False, f"خطأ: {e}"

def remove_flex_family_member(access_token, owner_number, member_number, user_agent, subdomain, max_retries, proxy=None):
    url = FAMILY_API_URL
    headers = create_headers(access_token, subdomain, user_agent, owner_number)
    payload = {
        "name": "FlexFamily", "type": "FamilyRemoveMember",
        "category": [{"value": "47", "listHierarchyId": "TemplateID"}],
        "parts": {
            "member": [
                {"id": [{"value": owner_number, "schemeName": "MSISDN"}], "type": "Owner"},
                {"id": [{"value": member_number, "schemeName": "MSISDN"}], "type": "Member"}
            ],
            "characteristicsValue": {
                "characteristicsValue": [
                    {"characteristicName": "Disconnect", "value": "0"},
                    {"characteristicName": "LastMemberDeletion", "value": "1"}
                ]
            }
        }
    }
    proxy_to_use = {"http": proxy, "https": proxy} if proxy else None
    for attempt in range(max_retries):
        try:
            response = requests.patch(url, data=json.dumps(payload), headers=headers, proxies=proxy_to_use, timeout=30)
            if response.status_code in [200, 201]:
                return True, "تم حذف العضو بنجاح"
        except Exception as e:
            pass
        time.sleep(2)
    return False, "فشل حذف العضو بعد عدة محاولات"

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
            headers = {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://web.vodafone.com.eg',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36'
            }
            data = {
                'username': owner_number,
                'password': owner_password,
            }
            response_login = session.post(form_action, headers=headers, data=data, allow_redirects=False)
            if 'Location' in response_login.headers and 'code=' in response_login.headers['Location']:
                code = response_login.headers['Location'].split('code=')[1]
                headers_token = {
                    'Accept': '*/*',
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Origin': 'https://web.vodafone.com.eg',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36'
                }
                data_token = {
                    'code': code,
                    'grant_type': 'authorization_code',
                    'client_id': 'website',
                    'redirect_uri': redirect_uri
                }
                token_response = session.post('https://web.vodafone.com.eg/auth/realms/vf-realm/protocol/openid-connect/token', headers=headers_token, data=data_token)
                token = token_response.json().get('access_token')

                if token:
                    url = f'https://web.vodafone.com.eg/services/dxl/usage/usageConsumptionReport?bucket.product.publicIdentifier={owner_number}&@type=aggregated'
                    headers = {
                        'channel': 'MOBILE',
                        'useCase': 'Promo',
                        'Authorization': f'Bearer {token}',
                        'api-version': 'v2',
                        'x-agent-operatingsystem': '11',
                        'clientId': 'AnaVodafoneAndroid',
                        'x-agent-device': 'OPPO CPH2059',
                        'x-agent-version': '2024.3.3',
                        'x-agent-build': '593',
                        'msisdn': owner_number,
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        'Accept-Language': 'ar',
                        'Host': 'web.vodafone.com.eg',
                        'Connection': 'Keep-Alive',
                        'Accept-Encoding': 'gzip',
                        'User-Agent': 'okhttp/4.11.0'
                    }
                    response = requests.get(url, headers=headers)
                    pattern = r'"usageType":"limit","bucketBalance":\[\{"remainingValue":\{"amount":(.*?),"units":"FLEX"'
                    match = re.search(pattern, response.text)
                    if match:
                        flex = int(float(match.group(1)))
                        return flex
        return None
    except Exception as e:
        return None

# --- Telegram Bot Logic ---

@bot.message_handler(commands=['start', 'help'])
def handle_start(message):
    reset_user_session(message.from_user.id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("بدء دورة إدارة مجموعة فليكس"), types.KeyboardButton("عرض الإعدادات الحالية"))
    markup.add(types.KeyboardButton("stop"), types.KeyboardButton("استئناف"))
    bot.send_message(message.chat.id, f"👋 أهلا بك في بوت إدارة مجموعة فودافون فليكس الذكي!\n\nاختر من اللوحة التالية:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "عرض الإعدادات الحالية")
def show_settings(message):
    session = get_user_session(message)
    conf = session['config']
    bot.reply_to(
        message,
        f"🔢 عدد التكرارات: {conf['total_attempts']}\n"
        f"⏱️ التأخيرات: {conf['delays']}\n"
        f"🔀 ترتيب المهام: {conf['task_order']}\n"
        f"🔄 المهام المتزامنة: {conf['sync_tasks']}\n"
        f"🧑‍💼 رقم المالك: {conf.get('owner_number', '---')}\n"
        f"👥 العضو1: {conf.get('member1_number', '---')}\n"
        f"👥 العضو2: {conf.get('member2_number', '---')}\n"
        f"🌐 بروكسي: {'نعم' if conf['use_proxies'] else 'لا'}",
        reply_markup=types.ReplyKeyboardRemove()
    )

@bot.message_handler(func=lambda m: m.text == "بدء دورة إدارة مجموعة فليكس")
def ask_owner_number(message):
    session = get_user_session(message)
    if session['running']:
        bot.send_message(message.chat.id, "⚠️ دورة جارية بالفعل! استخدم /stop لإيقافها أولاً.")
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
    bot.send_message(message.chat.id, "هل تريد استخدام بروكسيات؟", reply_markup=markup)

@bot.message_handler(func=lambda m: get_user_session(m)['step'] == 6)
def finish_config(message):
    session = get_user_session(message)
    use_proxy = message.text.strip() == "نعم"
    session['config']['use_proxies'] = use_proxy
    session['step'] = 7
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("نعم", "لا")
    bot.send_message(message.chat.id, "هل تريد حفظ الإعدادات لاستخدامها لاحقًا?", reply_markup=markup)

@bot.message_handler(func=lambda m: get_user_session(m)['step'] == 7)
def ask_total_attempts(message):
    session = get_user_session(message)
    saveit = message.text.strip() == "نعم"
    if saveit:
        save_user_config(message.from_user.id)
        bot.send_message(message.chat.id, "✅ تم حفظ الإعدادات بنجاح!", reply_markup=types.ReplyKeyboardRemove())
    else:
        bot.send_message(message.chat.id, "تم تجاهل الحفظ.", reply_markup=types.ReplyKeyboardRemove())
    session['step'] = 8
    bot.send_message(message.chat.id, "🔢 أدخل عدد التكرارات اللي عايز تعمله (مثلاً: 20):")

@bot.message_handler(func=lambda m: get_user_session(m)['step'] == 8)
def final_save_and_start(message):
    session = get_user_session(message)
    try:
        total_attempts = int(message.text.strip())
        if total_attempts <= 0:
            bot.send_message(message.chat.id, "⚠️ العدد لازم يكون أكبر من صفر! جرب تاني.")
            return
        session['config']['total_attempts'] = total_attempts
        session['step'] = 0
        session['running'] = True
        RUNNING_CYCLES[message.from_user.id] = True
        bot.send_message(message.chat.id, f"🚦 جاري بدء الدورة بعد {total_attempts} تكرار...")
        run_flex_cycle(message)
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ من فضلك ادخل رقم صحيح! جرب تاني.")
        session['step'] = 8

@bot.message_handler(func=lambda m: m.text == "stop")
def stop_cycle(message):
    user_id = message.from_user.id
    if user_id in RUNNING_CYCLES and RUNNING_CYCLES[user_id]:
        RUNNING_CYCLES[user_id] = False
        session = get_user_session(message)
        session['running'] = False
        bot.send_message(message.chat.id, "⏹️ تم إيقاف الدورة بنجاح!")
    else:
        bot.send_message(message.chat.id, "⚠️ لا توجد دورة جارية لإيقافها.")

@bot.message_handler(func=lambda m: m.text == "استئناف")
def resume_cycle(message):
    user_id = message.from_user.id
    session = get_user_session(message)
    if not session['running'] and user_id in RUNNING_CYCLES and not RUNNING_CYCLES[user_id]:
        session['running'] = True
        RUNNING_CYCLES[user_id] = True
        bot.send_message(message.chat.id, "▶️ تم استئناف الدورة بنجاح!")
        run_flex_cycle(message)
    else:
        bot.send_message(message.chat.id, "⚠️ الدورة جارية بالفعل أو لم تتوقف من قبل!")

def run_flex_cycle(message):
    user_id = message.from_user.id
    session = get_user_session(message)
    config = session['config']
    proxies_list = session['proxies_list']
    total_attempts = config['total_attempts']
    cycle_count = 0

    for i in range(total_attempts):
        if not RUNNING_CYCLES[user_id]:
            bot.send_message(message.chat.id, "⏹️ تم إيقاف الدورة من قبل المستخدم.")
            break

        summary_msgs = []  # يتم تهيئة الملخص لكل دورة جديدة
        bot.send_message(message.chat.id, f"🔁 بدأت حلقة رقم {i+1}/{total_attempts} ...")

        # تحديث التوكن قبل كل حلقة
        start_time = datetime.now()
        bot.send_message(message.chat.id, f"🔑 جاري التحقق من التوكن أو تجديده... (بدأ الساعة: {start_time.strftime('%H:%M:%S')})")
        current_token = session['current_token']
        if not current_token or not is_token_valid(current_token, config['owner_number'], random.choice(USER_AGENTS)):
            current_token = get_fresh_token(config['owner_number'], config['owner_password'])
            if not current_token:
                end_time = datetime.now()
                bot.send_message(message.chat.id, f"❌ فشل الحصول على توكن جديد. سيتم تخطي الحلقة. (انتهى الساعة: {end_time.strftime('%H:%M:%S')}, المدة: {(end_time - start_time).total_seconds():.2f} ثانية)")
                continue
            session['current_token'] = current_token
        end_time = datetime.now()
        bot.send_message(message.chat.id, f"✅ التوكن جاهز أو تم تجديده بنجاح! (انتهى الساعة: {end_time.strftime('%H:%M:%S')}, المدة: {(end_time - start_time).total_seconds():.2f} ثانية)")
        summary_msgs.append(f"🔑 التوكن: ✅ (المدة: {(end_time - start_time).total_seconds():.2f} ثانية)")

        current_ua = random.choice(USER_AGENTS)
        current_proxy = random.choice(proxies_list) if config['use_proxies'] and proxies_list else None

        # 1- تغيير الحصة إلى 10%
        start_time = datetime.now()
        bot.send_message(message.chat.id, f"⏳ جاري تغيير حصة العضو الأول إلى 10%... (بدأ الساعة: {start_time.strftime('%H:%M:%S')})")
        ok, msg = change_quota(current_token, config['owner_number'], config['member1_number'], "10", current_ua, random.choice(SUBDOMAINS), current_proxy)
        end_time = datetime.now()
        summary_msgs.append(f"1️⃣ تغيير الحصة إلى 10%: {'✅' if ok else '❌'} {msg} (المدة: {(end_time - start_time).total_seconds():.2f} ثانية)")
        bot.send_message(message.chat.id, f"1️⃣ تغيير الحصة إلى 10%: {'✅' if ok else '❌'} {msg} (انتهى الساعة: {end_time.strftime('%H:%M:%S')}, المدة: {(end_time - start_time).total_seconds():.2f} ثانية)")
        time.sleep(config['delays']["1"])

        # 2- إرسال دعوة للعضو الثاني
        start_time = datetime.now()
        bot.send_message(message.chat.id, f"📩 جاري إرسال دعوة للعضو الثاني... (بدأ الساعة: {start_time.strftime('%H:%M:%S')})")
        ok, msg = add_family_member(current_token, config['owner_number'], config['member2_number'], "10", current_ua, random.choice(SUBDOMAINS), config['retries_add_remove'], current_proxy)
        end_time = datetime.now()
        summary_msgs.append(f"2️⃣ دعوة العضو الثاني: {'✅' if ok else '❌'} {msg} (المدة: {(end_time - start_time).total_seconds():.2f} ثانية)")
        bot.send_message(message.chat.id, f"2️⃣ دعوة العضو الثاني: {'✅' if ok else '❌'} {msg} (انتهى الساعة: {end_time.strftime('%H:%M:%S')}, المدة: {(end_time - start_time).total_seconds():.2f} ثانية)")

        # فاصل 60 ثانية
        start_time = datetime.now()
        bot.send_message(message.chat.id, f"⏳ انتظار 60 ثانية قبل الخطوة التالية... (بدأ الساعة: {start_time.strftime('%H:%M:%S')})")
        time.sleep(60.0)
        end_time = datetime.now()
        bot.send_message(message.chat.id, f"✅ اكتمل الانتظار (انتهى الساعة: {end_time.strftime('%H:%M:%S')}, المدة: {(end_time - start_time).total_seconds():.2f} ثانية)")

        # 3- قبول الدعوة + تغيير الحصة بتناوب عشوائي (10%, 20%, 40%) متزامن
        start_time = datetime.now()
        # اختيار نسبة عشوائية مختلفة عن السابقة
        available_quotas = ["10", "20", "40"]
        last_quota = session['last_quota']
        if last_quota:
            available_quotas.remove(last_quota)  # إزالة النسخة السابقة
        quota_percentage = random.choice(available_quotas)
        session['last_quota'] = quota_percentage  # تحديث النسخة اللي استخدمت
        bot.send_message(message.chat.id, f"🔄 جاري تنفيذ المهمتين المتزامنتين (قبول الدعوة وتغيير الحصة إلى {quota_percentage}%)... (بدأ الساعة: {start_time.strftime('%H:%M:%S')})")
        member2_token = get_fresh_token(config['member2_number'], config['member2_password'])
        if member2_token:
            # إنشاء الخيوط
            threads = []
            
            # Thread لقبول الدعوة
            def run_accept():
                ok, msg = accept_invitation(member2_token, config['owner_number'], config['member2_number'], current_ua, random.choice(SUBDOMAINS), current_proxy)
                bot.send_message(message.chat.id, f"👥 قبول الدعوة: {'✅' if ok else '❌'} {msg} (انتهى الساعة: {datetime.now().strftime('%H:%M:%S')})")
                return ok, msg

            # Thread لتغيير الحصة
            def run_quota():
                ok, msg = change_quota(current_token, config['owner_number'], config['member1_number'], quota_percentage, current_ua, random.choice(SUBDOMAINS), current_proxy)
                bot.send_message(message.chat.id, f"💼 تغيير الحصة إلى {quota_percentage}%: {'✅' if ok else '❌'} {msg} (انتهى الساعة: {datetime.now().strftime('%H:%M:%S')})")
                return ok, msg

            t1 = Thread(target=run_accept)
            t2 = Thread(target=run_quota)
            threads.append(t1)
            threads.append(t2)

            # بدء الخيوط
            for t in threads:
                t.start()

            # انتظار انتهاء خيط قبول الدعوة
            t1.join()
            # إضافة تأخير ثابت 2 ثانية
            time.sleep(2)
            bot.send_message(message.chat.id, "⏳ انتظار 2 ثانية بين قبول الدعوة وتغيير الحصة...")
            # بدء وانتظار خيط تغيير الحصة
            t2.start()
            t2.join()

            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()
            bot.send_message(message.chat.id, f"✅ المهمتان المتزامنتان اكتملتا! (انتهى الساعة: {end_time.strftime('%H:%M:%S')}, المدة: {execution_time:.2f} ثانية)")
            summary_msgs.append(f"3️⃣ قبول الدعوة وتغيير الحصة إلى {quota_percentage}%: ✅ (المدة: {execution_time:.2f} ثانية)")
        else:
            end_time = datetime.now()
            bot.send_message(message.chat.id, f"❌ فشل الحصول على توكن العضو الثاني - تخطى المهمة. (انتهى الساعة: {end_time.strftime('%H:%M:%S')})")
            summary_msgs.append("3️⃣ فشل الحصول على توكن العضو الثاني - تخطى المهمة.")
        time.sleep(config['delays']["3"])

        # 4- حذف العضو الثاني
        start_time = datetime.now()
        bot.send_message(message.chat.id, f"🗑️ جاري حذف العضو الثاني... (بدأ الساعة: {start_time.strftime('%H:%M:%S')})")
        ok, msg = remove_flex_family_member(current_token, config['owner_number'], config['member2_number'], current_ua, random.choice(SUBDOMAINS), config['retries_add_remove'], current_proxy)
        end_time = datetime.now()
        summary_msgs.append(f"4️⃣ حذف العضو الثاني: {'✅' if ok else '❌'} {msg} (المدة: {(end_time - start_time).total_seconds():.2f} ثانية)")
        bot.send_message(message.chat.id, f"4️⃣ حذف العضو الثاني: {'✅' if ok else '❌'} {msg} (انتهى الساعة: {end_time.strftime('%H:%M:%S')}, المدة: {(end_time - start_time).total_seconds():.2f} ثانية)")

        # الحصول على كمية الفليكس
        start_time = datetime.now()
        bot.send_message(message.chat.id, f"📊 جاري استرجاع كمية الفليكس المتبقية... (بدأ الساعة: {start_time.strftime('%H:%M:%S')})")
        flex_amount = get_flex_amount(config['owner_number'], config['owner_password'])
        end_time = datetime.now()
        flex_msg = f"💡 كمية فليكس المتبقية: {flex_amount or 'غير متوفرة'} (المدة: {(end_time - start_time).total_seconds():.2f} ثانية)"
        summary_msgs.append(flex_msg)
        bot.send_message(message.chat.id, flex_msg)

        time.sleep(config['delays']["4"])

        # عرض الملخص بعد كل دورة
        bot.send_message(message.chat.id, "📋 الملخص للحلقة الحالية:\n" + "\n".join(summary_msgs))

        # زيادة عداد الدورات وإضافة راحة عشوائية بعد كل 5 دورات
        cycle_count += 1
        if cycle_count % 5 == 0 and i + 1 < total_attempts:
            start_time = datetime.now()
            rest_time = random.uniform(10 * 60, 15 * 60)  # من 10 إلى 15 دقيقة
            bot.send_message(message.chat.id, f"⏸️ جاري الراحة لمدة {rest_time/60:.1f} دقائق لتجنب الحظر... (بدأ الساعة: {start_time.strftime('%H:%M:%S')})")
            time.sleep(rest_time)
            end_time = datetime.now()
            bot.send_message(message.chat.id, f"▶️ تم استئناف الدورة بعد الراحة. (انتهى الساعة: {end_time.strftime('%H:%M:%S')}, المدة: {(end_time - start_time).total_seconds()/60:.1f} دقائق)")

    if RUNNING_CYCLES[user_id]:
        bot.send_message(message.chat.id, "🎉 اكتملت جميع حلقات الإدارة بنجاح!")
        RUNNING_CYCLES[user_id] = False
        session = get_user_session(message)
        session['running'] = False

# --- تشغيل البوت ---
if __name__ == "__main__":
    try:
        print("🤖 الكود ليس للبيع لتواصل مع المالك @EL1NINJA ...")
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("تم إيقاف البوت.")
        sys.exit(0)
    except Exception as e:
        print(f"حدث خطأ غير متوقع: {e}")
        traceback.print_exc()
        sys.exit(1)
